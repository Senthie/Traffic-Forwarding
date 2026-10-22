from __future__ import annotations

import asyncio

from fastapi import APIRouter

from ..schemas.rule import HealthInfo, ProbeRequest
from ..services import portproxy, probe
from ..services.rules import RuleError

router = APIRouter(prefix="/probe", tags=["probe"])


@router.post("/batch", response_model=dict[str, HealthInfo])
async def probe_batch(payload: ProbeRequest | None = None) -> dict[str, HealthInfo]:
    """并发探测（默认全部规则）。"""
    rules = await asyncio.to_thread(portproxy.read_rules)
    if payload and payload.ids:
        wanted = set(payload.ids)
        rules = [r for r in rules if r["id"] in wanted]
    return await probe.probe_many(rules)


@router.post("/{rule_id}", response_model=HealthInfo)
async def probe_one(rule_id: str) -> HealthInfo:
    rules = await asyncio.to_thread(portproxy.read_rules)
    target = next((r for r in rules if r["id"] == rule_id), None)
    if target is None:
        raise RuleError(f"规则 {rule_id} 不存在", status=404)
    result = await probe.probe_many([target])
    return result[rule_id]
