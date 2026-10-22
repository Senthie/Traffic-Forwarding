from __future__ import annotations

from fastapi import APIRouter

from ..core.config import APP_VERSION, settings
from ..core.elevation import is_admin, relaunch_as_admin
from ..schemas.rule import InterfaceInfo, SystemStatus
from ..services import firewall, netinfo

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatus)
async def status() -> SystemStatus:
    interfaces = await netinfo.list_interfaces()
    profiles = await firewall.firewall_profiles()
    return SystemStatus(
        version=APP_VERSION,
        admin=is_admin(),
        host=settings.host,
        port=settings.port,
        data_dir=str(settings.data_dir),
        probe_timeout=settings.probe_timeout,
        firewall_available=is_admin(),
        firewall_profiles=profiles,
        interfaces_count=len(interfaces),
    )


@router.get("/interfaces", response_model=list[InterfaceInfo])
async def interfaces(refresh: bool = False) -> list[InterfaceInfo]:
    return await netinfo.list_interfaces(force=refresh)


@router.post("/elevate")
async def elevate() -> dict:
    """以管理员身份重新启动应用（会弹 UAC）。"""
    if is_admin():
        return {"started": False, "reason": "当前已是管理员"}
    started = relaunch_as_admin()
    return {"started": started, "reason": None if started else "提权请求被拒绝或失败"}
