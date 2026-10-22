from __future__ import annotations

import ipaddress
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

HealthState = Literal["healthy", "half-open", "down", "unknown"]


class HealthInfo(BaseModel):
    state: HealthState = "unknown"
    listen_ok: bool = False
    target_ok: bool = False
    listen_latency_ms: float | None = None
    target_latency_ms: float | None = None
    checked_at: datetime | None = None
    error: str | None = None

    @property
    def label(self) -> str:  # pragma: no cover - 仅前端展示用
        return self.state


class FirewallStatus(BaseModel):
    rule_name: str | None = None
    exists: bool = False
    enabled: bool = False
    action: str | None = None
    profiles: list[str] = Field(default_factory=list)
    # 端口已被别的规则覆盖时，这里记录那条规则名
    reused_by: str | None = None
    available: bool = True
    error: str | None = None


class RuleOut(BaseModel):
    id: str
    name: str | None = None
    note: str | None = None
    listen_address: str
    listen_port: int
    connect_address: str
    connect_port: int
    proto: str = "tcp"
    firewall_rule_name: str | None = None
    firewall: FirewallStatus | None = None
    health: HealthInfo | None = None
    is_named: bool = False
    created_at: str | None = None


def _validate_ip(value: str) -> str:
    value = value.strip()
    try:
        ipaddress.ip_address(value)
    except ValueError as exc:  # noqa: TRY003
        raise ValueError(f"不是合法的 IP 地址：{value}") from exc
    return value


class RuleBase(BaseModel):
    name: str = Field(min_length=1, max_length=80, description="展示名，同时用于派生防火墙规则名")
    note: str | None = Field(default=None, max_length=500)
    listen_address: str
    listen_port: int = Field(ge=1, le=65535)
    connect_address: str
    connect_port: int = Field(ge=1, le=65535)
    open_firewall: bool = True
    firewall_rule_name: str | None = Field(default=None, max_length=120)
    profiles: str = Field(default="Any", description="Any / Domain,Private / Private …")

    @field_validator("listen_address", "connect_address")
    @classmethod
    def _check_ip(cls, v: str) -> str:
        return _validate_ip(v)

    @field_validator("profiles")
    @classmethod
    def _check_profiles(cls, v: str) -> str:
        allowed = {"any", "domain", "private", "public"}
        parts = [p.strip() for p in v.split(",") if p.strip()]
        if not parts:
            raise ValueError("profiles 不能为空")
        for p in parts:
            if p.lower() not in allowed:
                raise ValueError(f"不支持的 profile：{p}")
        return ",".join(p.capitalize() if p.lower() != "any" else "Any" for p in parts)


class RuleCreate(RuleBase):
    pass


class RuleUpdate(RuleBase):
    pass


class ValidationIssue(BaseModel):
    level: Literal["error", "warning", "info"] = "error"
    field: str | None = None
    message: str


class ValidationOut(BaseModel):
    ok: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    normalized: RuleCreate | None = None
    target_reachable: bool | None = None
    listen_latency_ms: float | None = None


class InterfaceInfo(BaseModel):
    alias: str
    address: str
    prefix_length: int | None = None
    is_loopback: bool = False


class SystemStatus(BaseModel):
    version: str
    admin: bool
    host: str
    port: int
    data_dir: str
    probe_timeout: float
    firewall_available: bool
    firewall_profiles: list[dict] = Field(default_factory=list)
    interfaces_count: int = 0


class AuditEntry(BaseModel):
    id: int
    ts: str
    action: str
    rule_id: str | None = None
    detail: str | None = None
    command: str | None = None
    returncode: int | None = None
    output: str | None = None
    ok: bool = True


class ProbeRequest(BaseModel):
    ids: list[str] | None = None


class ImportResult(BaseModel):
    created: int = 0
    failed: int = 0
    messages: list[str] = Field(default_factory=list)
