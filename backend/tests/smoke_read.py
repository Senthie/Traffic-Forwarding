"""手工冒烟脚本：验证注册表读取 / 网卡枚举 / 并发探测。

用法：cd backend && uv run python tests/smoke_read.py
结果写入 backend/data/smoke.json（避免中文在 GBK 终端乱码）。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services import netinfo, portproxy, probe  # noqa: E402


async def main() -> int:
    rules = portproxy.read_rules()
    interfaces = await netinfo.list_interfaces()
    health = await probe.probe_many(rules)

    payload = {
        "rules": rules,
        "interfaces": [i.model_dump() for i in interfaces],
        "health": {k: v.model_dump(mode="json") for k, v in health.items()},
    }

    out = BACKEND_DIR / "data" / "smoke.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"RULES={len(rules)} INTERFACES={len(interfaces)} PROBED={len(health)}")
    for rule in rules:
        h = health.get(rule["id"])
        print(
            f"  {rule['listen_address']}:{rule['listen_port']} -> "
            f"{rule['connect_address']}:{rule['connect_port']}  state={h.state if h else '?'}"
        )
    print(f"WROTE={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
