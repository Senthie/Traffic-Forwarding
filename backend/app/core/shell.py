"""统一的系统命令执行层。

设计约束：
* 只接受参数列表，永远不拼接 shell 字符串（防注入）。
* 统一处理超时、编码（netsh 在中文系统输出 GBK）、无窗口启动。
* 返回值携带完整命令原文，供审计日志与前端回显。
"""

from __future__ import annotations

import asyncio
import shlex
import time
from dataclasses import dataclass, field

CREATE_NO_WINDOW = 0x08000000
POWERSHELL = "powershell.exe"

# 强制 PowerShell 以 UTF-8 输出，避免 GBK 乱码
_PS_PREFIX = (
    "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
    "$ProgressPreference='SilentlyContinue'; "
    "$ErrorActionPreference='Stop'; "
)


@dataclass
class CmdResult:
    args: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @property
    def output(self) -> str:
        text = (self.stdout or "").strip()
        if not text:
            text = (self.stderr or "").strip()
        return text

    def command_line(self) -> str:
        return " ".join(shlex.quote(a) for a in self.args)

    def summary(self, limit: int = 800) -> str:
        out = self.output.replace("\r\n", "\n").strip()
        if len(out) > limit:
            out = out[:limit] + "…"
        return out


def _decode(raw: bytes, encoding: str) -> str:
    if not raw:
        return ""
    try:
        text = raw.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        text = raw.decode("utf-8", errors="replace")
    return text.replace("\ufeff", "").strip()


async def run_exec(
    args: list[str],
    *,
    timeout: float = 25.0,
    encoding: str = "gbk",
) -> CmdResult:
    """执行外部命令（无 shell）。"""
    argv = [str(a) for a in args]
    started = time.perf_counter()

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW,
        )
    except (FileNotFoundError, OSError) as exc:
        return CmdResult(
            args=argv,
            returncode=-1,
            stderr=f"无法启动命令 {argv[0]}: {exc}",
            duration_ms=(time.perf_counter() - started) * 1000,
        )

    timed_out = False
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        timed_out = True
        with_suppress = getattr(proc, "kill", None)
        if with_suppress is not None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        out, err = await proc.communicate()

    return CmdResult(
        args=argv,
        returncode=proc.returncode if proc.returncode is not None else -1,
        stdout=_decode(out, encoding),
        stderr=_decode(err, encoding),
        duration_ms=(time.perf_counter() - started) * 1000,
        timed_out=timed_out,
    )


async def run_powershell(script: str, *, timeout: float = 25.0) -> CmdResult:
    """执行一段 PowerShell 脚本，输出强制 UTF-8。"""
    return await run_exec(
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            _PS_PREFIX + script,
        ],
        timeout=timeout,
        encoding="utf-8",
    )


async def run_netsh(args: list[str], *, timeout: float = 20.0) -> CmdResult:
    return await run_exec(
        ["netsh", "interface", "portproxy", *[str(a) for a in args]],
        timeout=timeout,
        encoding="gbk",
    )
