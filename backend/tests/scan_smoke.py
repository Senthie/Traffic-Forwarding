"""手工冒烟：不经过 HTTP，直接调用 ARP 扫描服务。

用法（在 backend 目录下）：
    .venv\\Scripts\\python.exe tests\\scan_smoke.py 192.168.1.226 24 auto
    .venv\\Scripts\\python.exe tests\\scan_smoke.py 192.168.1.226 24 auto --fallback
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services import arpscan  # noqa: E402


async def main() -> int:
    args = [item for item in sys.argv[1:] if item != "--fallback"]
    if "--fallback" in sys.argv:
        # 强制走回退引擎，用于在没有 Npcap 的机器上验证邻居表逻辑
        arpscan.load_wpcap = lambda **_: None  # type: ignore[assignment]

    print("engine:", json.dumps(arpscan.engine_info(), ensure_ascii=False))

    if len(args) >= 1:
        cases = [(args[0], int(args[1]) if len(args) > 1 else 24, args[2] if len(args) > 2 else "auto")]
    else:
        adapters = await arpscan.list_adapters()
        cases = [(a.address, a.prefix_length, "auto") for a in adapters if not a.address.startswith("127.")]

    for address, prefix, scope in cases:
        try:
            result = await arpscan.scan(address, prefix, scope, 2.0)
        except arpscan.ScanError as exc:
            print(f"[{address}/{prefix} {scope}] 失败：{exc}")
            continue
        summary = result.summary
        print(
            f"[{summary.interface_alias}] {summary.network} {summary.engine} "
            f"total={summary.total} alive={summary.alive} idle={summary.idle} "
            f"{summary.elapsed_ms}ms truncated={summary.truncated}"
        )
        if summary.warning:
            print("  warning:", summary.warning)
        for host in result.hosts:
            tag = " (本机)" if host.is_local else ""
            print(f"  {host.ip:<15} {host.mac or '-':<17}{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
