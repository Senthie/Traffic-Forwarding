from __future__ import annotations

from fastapi import APIRouter, Response

from ..schemas.rule import RuleCreate, RuleOut, ValidationOut
from ..services import rules as rules_service

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("", response_model=list[RuleOut])
async def list_rules(with_health: bool = False) -> list[RuleOut]:
    """列出全部 portproxy 规则（含元数据、防火墙状态，可选健康状态）。"""
    return await rules_service.collect_rules(with_health=with_health)


@router.post("/validate", response_model=ValidationOut)
async def validate_rule(
    payload: RuleCreate,
    exclude_id: str | None = None,
) -> ValidationOut:
    """干跑校验，不落盘。

    编辑既有规则时必须传 exclude_id（被编辑规则的 id），
    否则规则会与"自己"比较，误报「已存在相同监听端」。
    """
    return await rules_service.validate_payload(payload, exclude_id=exclude_id)


@router.get("/{rule_id}", response_model=RuleOut)
async def get_rule(rule_id: str) -> RuleOut:
    return await rules_service._get_rule(rule_id)


@router.post("", response_model=RuleOut, status_code=201)
async def create_rule(payload: RuleCreate) -> RuleOut:
    return await rules_service.create_rule(payload)


@router.put("/{rule_id}", response_model=RuleOut)
async def update_rule(rule_id: str, payload: RuleCreate) -> RuleOut:
    return await rules_service.update_rule(rule_id, payload)


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(rule_id: str, delete_firewall: bool = False) -> Response:
    await rules_service.delete_rule(rule_id, delete_firewall=delete_firewall)
    return Response(status_code=204)
