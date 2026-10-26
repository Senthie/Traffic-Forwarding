"""ARP 网段扫描相关的请求 / 响应模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

ScanEngine = Literal["npcap", "fallback"]
ScanScope = Literal["auto", "full"]


class ScanEngineInfo(BaseModel):
    engine: ScanEngine
    npcap_available: bool
    npcap_version: str | None = None
    npcap_path: str | None = None
    admin: bool = False
    reason: str | None = None
    note: str | None = None


class ScanRequest(BaseModel):
    address: str = Field(description="网卡自身的 IPv4 地址，用来自动定位网卡与网段")
    prefix_length: int = Field(default=24, ge=0, le=32)
    scope: ScanScope = Field(
        default="auto",
        description="auto=快速模式（前缀小于 /24 时只扫所在 /24）；full=按完整前缀扫描（最多 1024 个地址）",
    )
    timeout: float = Field(default=2.5, ge=0.5, le=10.0, description="抓包等待秒数")

    @field_validator("address")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class ScanHost(BaseModel):
    ip: str
    mac: str | None = None
    is_local: bool = False


class ScanSummary(BaseModel):
    network: str
    prefix_length: int
    interface_alias: str | None = None
    interface_address: str
    engine: ScanEngine
    total: int
    alive: int
    idle: int
    elapsed_ms: float
    truncated: bool = False
    warning: str | None = None
    checked_at: str


class ScanResult(BaseModel):
    summary: ScanSummary
    hosts: list[ScanHost] = Field(default_factory=list)
