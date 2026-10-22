"""管理员权限检测与自提权重启。"""

from __future__ import annotations

import ctypes
import os
import sys


def is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - 极端情况下退化为 False
        return False


def relaunch_as_admin() -> bool:
    """以管理员身份重新启动当前进程。返回是否成功发起。

    打包后重新启动 exe；开发时重新启动 python + uvicorn 命令行。
    """
    if os.name != "nt":
        return False

    if getattr(sys, "frozen", False):
        exe = sys.executable
        params = " ".join(sys.argv[1:])
    else:
        exe = sys.executable
        params = " ".join(f'"{a}"' for a in sys.argv)

    try:
        rc = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None, "runas", exe, params, os.getcwd(), 1
        )
        return rc > 32
    except Exception:
        return False
