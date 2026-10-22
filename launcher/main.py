"""桌面启动器：后台线程运行 uvicorn，并用 pywebview 打开窗口。

开发：uv run --extra gui python launcher/app.py
打包：PyInstaller 以 launcher/traffic_forwarding.spec 为入口（见 scripts/build.ps1 -Exe）
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

IS_FROZEN = bool(getattr(sys, "frozen", False))


def _base_dir() -> Path:
    if IS_FROZEN:
        # PyInstaller 单目录模式下资源位于 _MEIPASS
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


BASE_DIR = _base_dir()
BACKEND_DIR = BASE_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _ensure_streams() -> Path | None:
    """PyInstaller 的 windowed 模式（console=False）会把 stdout/stderr 置为 None。

    uvicorn 的日志格式化器会调用 sys.stdout.isatty()，None 会直接抛
    AttributeError: 'NoneType' object has no attribute 'isatty'。
    这里把它们重定向到 %LOCALAPPDATA%\\TrafficForwarding\\launcher.log，
    既避免崩溃，也留下可排查的日志。
    """
    if sys.stdout is not None and sys.stderr is not None:
        return None

    log_dir = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "TrafficForwarding"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        stream = open(log_dir / "launcher.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    except OSError:
        stream = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115

    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")  # noqa: SIM115
    return log_dir / "launcher.log"


LOG_FILE = _ensure_streams()

# uvicorn 与后端在 main() 内延迟导入：
# 这样即使导入阶段就崩溃，也能被 __main__ 的兜底捕获并写入 launcher.log。

_MUTEX_HANDLE = None


def _acquire_instance_lock() -> bool:
    """单实例锁。

    没有它的时候，用户关掉窗口后若进程仍残留，再双击一次就会多出一个实例，
    表现就是"关掉一个又弹出一个新窗口"。这里用命名互斥体拦住第二个实例。
    """
    global _MUTEX_HANDLE
    if os.name != "nt":
        return True

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE

        handle = kernel32.CreateMutexW(None, True, "Local\\TrafficForwarding.SingleInstance")
        last_error = ctypes.get_last_error()
        if not handle:
            return True
        if last_error == 183:  # ERROR_ALREADY_EXISTS
            return False
        _MUTEX_HANDLE = handle
        return True
    except Exception:  # noqa: BLE001 - 加锁失败不应阻止启动
        return True


def _notify_already_running() -> None:
    message = "转发管理器已在运行，请查看任务栏中已打开的窗口。"
    print(message)
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "转发管理器", 0x40)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def _is_admin() -> bool:
    try:
        from app.core.elevation import is_admin

        return is_admin()
    except Exception:  # noqa: BLE001 - 判定失败按非管理员处理
        return False


def _prompt_admin_required() -> None:
    """未以管理员身份启动时：弹窗提醒并关闭程序。

    对话框给两个选择——「是」以管理员身份重启，「否」直接退出。
    """
    message = (
        "本程序需要管理员权限才能管理端口转发与防火墙规则。\n\n"
        "请点击『是』以管理员身份重新启动，或点击『否』退出程序。"
    )
    print("[launcher] 未以管理员身份运行，提示后退出")

    MB_YESNO = 0x00000004
    MB_ICONWARNING = 0x00000030
    MB_SETFOREGROUND = 0x00010000
    MB_TOPMOST = 0x00040000
    IDYES = 6

    try:
        import ctypes

        choice = ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            None,
            message,
            "转发管理器 · 需要管理员权限",
            MB_YESNO | MB_ICONWARNING | MB_SETFOREGROUND | MB_TOPMOST,
        )
    except Exception:  # noqa: BLE001 - 极端环境下退化为仅写日志
        print(message, file=sys.stderr)
        return

    if choice == IDYES:
        try:
            from app.core.elevation import relaunch_as_admin

            if not relaunch_as_admin():
                print("[launcher] 提权启动失败（用户取消 UAC 或无权限）")
        except Exception as exc:  # noqa: BLE001
            print(f"[launcher] 提权启动异常：{exc}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_ready(port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def main() -> int:
    # 自检：仅验证 pywebview / pythonnet 是否已正确打包
    if os.environ.get("TFM_SELFTEST") == "1":
        try:
            import clr  # noqa: F401  # pythonnet 运行时
            import webview

            print(f"SELFTEST OK create_window={hasattr(webview, 'create_window')}")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"SELFTEST FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2

    headless = os.environ.get("TFM_NO_GUI") == "1"
    allow_no_admin = os.environ.get("TFM_ALLOW_NO_ADMIN") == "1"

    # 权限检查必须在加锁之前：否则用户点「以管理员身份重新启动」时，
    # 新实例会被本进程还没释放的单实例锁挡住，表现为"点了没反应"。
    if not headless and not allow_no_admin and not _is_admin():
        _prompt_admin_required()
        return 0

    import uvicorn

    from app.main import app

    if not headless and not _acquire_instance_lock():
        _notify_already_running()
        return 0

    port = int(os.environ.get("TFM_PORT", "0")) or _free_port()
    os.environ["TFM_PORT"] = str(port)
    print(f"[launcher] 启动后端 port={port}")

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="uvicorn", daemon=True)
    thread.start()

    if not _wait_ready(port):
        print("后端未能在预期时间内启动", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{port}"
    print(f"界面地址：{url}")
    print("提示：修改转发规则需要以管理员身份运行本程序。")

    # 无窗口模式：仅启动后端（便于自动化测试 / 浏览器打开）
    if os.environ.get("TFM_NO_GUI") == "1":
        print("TFM_NO_GUI=1，未创建窗口。按 Ctrl+C 退出。")
        try:
            thread.join()
        except KeyboardInterrupt:
            server.should_exit = True
        return 0

    try:
        import webview  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        print("未安装 pywebview，改为在默认浏览器中打开。")
        import webbrowser

        webbrowser.open(url)
        thread.join()
        return 0

    print("[launcher] 创建窗口")
    window = webview.create_window(
        "转发管理器",
        url,
        width=1280,
        height=820,
        min_size=(1024, 640),
    )

    def _on_closed() -> None:
        print("[launcher] 窗口已关闭，准备退出")
        server.should_exit = True

    window.events.closed += _on_closed

    webview.start()
    print("[launcher] webview.start() 返回，强制退出进程")

    # 关窗后必须确定性地退出：否则 pythonnet/WinForms 或 onefile 的父进程残留，
    # 用户下次启动时会看到"又冒出一个窗口"。
    server.should_exit = True
    thread.join(timeout=5.0)
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:  # noqa: BLE001
        pass
    os._exit(0)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - 窗口模式下必须自己记录，否则静默退出
        import traceback

        traceback.print_exc()
        if LOG_FILE is not None:
            try:
                sys.stderr.write(f"\n[crash] 详见 {LOG_FILE}\n")
                sys.stderr.flush()
            except Exception:  # noqa: BLE001
                pass
        raise SystemExit(1) from None
    raise SystemExit(main())
