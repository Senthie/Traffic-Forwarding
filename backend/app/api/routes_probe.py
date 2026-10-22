from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, HTTPException

from ..schemas.rule import AuditEntry, ImportResult, RuleCreate
from ..services import rules as rules_service
from ..services.metadata import Store

router = APIRouter(tags=["logs"])


@router.get("/logs", response_model=list[AuditEntry])
async def list_logs(limit: int = 100) -> list[AuditEntry]:
    limit = max(1, min(limit, 1000))
    rows = await asyncio.to_thread(Store.instance().list_logs, limit)
    return [AuditEntry(**row) for row in rows]


@router.get("/export")
async def export_rules() -> dict:
    return await rules_service.export_rules()


@router.post("/import", response_model=ImportResult)
async def import_rules(payload: dict = Body(...)) -> ImportResult:
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list):
        raise HTTPException(status_code=400, detail="请求体需要包含 rules 数组")

    items: list[RuleCreate] = []
    messages: list[str] = []
    for index, raw in enumerate(raw_rules):
        try:
            items.append(RuleCreate.model_validate(raw))
        except Exception as exc:  # noqa: BLE001 - 汇总所有格式错误
            messages.append(f"第 {index + 1} 条格式错误：{exc}")

    result = await rules_service.import_rules(items)
    result.messages = messages + result.messages
    return result
