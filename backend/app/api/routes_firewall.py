from __future__ import annotations

from fastapi import APIRouter

from ..services import firewall
from ..services import rules as rules_service

router = APIRouter(prefix="/firewall", tags=["firewall"])


@router.get("/rules")
async def list_firewall_rules() -> dict:
    try:
        entries = await firewall.list_inbound_tcp_allow()
        return {"available": True, "error": None, "rules": entries}
    except firewall.FirewallUnavailable as exc:
        return {"available": False, "error": str(exc), "rules": []}


@router.get("/orphans")
async def list_orphans() -> list[dict]:
    return await rules_service.orphans()
