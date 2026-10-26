"""ARP 网段扫描接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.scan import ScanEngineInfo, ScanRequest, ScanResult
from ..services import arpscan

router = APIRouter(prefix="/scan", tags=["scan"])


@router.get("/engine", response_model=ScanEngineInfo)
async def engine(refresh: bool = False) -> ScanEngineInfo:
    """当前扫描引擎：Npcap（原始 ARP）或邻居表回退。"""
    return ScanEngineInfo(**arpscan.engine_info(force=refresh))


@router.post("/arp", response_model=ScanResult)
async def arp_scan(payload: ScanRequest) -> ScanResult:
    try:
        return await arpscan.scan(
            address=payload.address,
            prefix_length=payload.prefix_length,
            scope=payload.scope,
            timeout=payload.timeout,
        )
    except arpscan.ScanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
