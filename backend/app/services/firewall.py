"""Windows 防火墙规则（仅 TCP 入站 Allow）。

注意：在部分机器上 `Get-NetFirewallRule` 非管理员会被拒绝访问，
因此所有读取都带权限判断，不可用时抛 FirewallUnavailable 由上层降级展示。
"""

from __future__ import annotations

import json
import logging

from ..core.elevation import is_admin
from ..core.shell import CmdResult, run_powershell

log = logging.getLogger(__name__)


class FirewallUnavailable(RuntimeError):
    """当前上下文（通常是缺少管理员权限）无法访问防火墙。"""


def _require_admin() -> None:
    if not is_admin():
        raise FirewallUnavailable("需要管理员权限才能读取或修改防火墙规则")


def ps_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


_LIST_SCRIPT = """
$filters = @{}
foreach ($f in (Get-NetFirewallPortFilter -All)) { $filters[$f.InstanceID] = $f }
$out = @()
foreach ($r in (Get-NetFirewallRule -Direction Inbound -Action Allow)) {
    $f = $filters[$r.InstanceID]
    if (-not $f) { continue }
    if ([string]$f.Protocol -ne 'TCP') { continue }
    $out += [pscustomobject]@{
        Name    = [string]$r.DisplayName
        Port    = [string]$f.LocalPort
        Profile = [string]$r.Profile
        Enabled = [string]$r.Enabled
        Action  = [string]$r.Action
    }
}
$out | ConvertTo-Json -Compress -Depth 3
"""


def port_matches(local_ports: str, port: int) -> bool:
    text = (local_ports or "").strip()
    if not text:
        return False
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if part in {"Any", "*"}:
            return True
        if "-" in part:
            start, _, end = part.partition("-")
            if start.strip().isdigit() and end.strip().isdigit():
                if int(start) <= port <= int(end):
                    return True
        elif part.isdigit() and int(part) == port:
            return True
    return False


async def list_inbound_tcp_allow() -> list[dict]:
    _require_admin()
    result = await run_powershell(_LIST_SCRIPT, timeout=60.0)
    if not result.ok:
        raise FirewallUnavailable(result.summary() or "读取防火墙规则失败")

    text = (result.stdout or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FirewallUnavailable(f"防火墙规则解析失败：{exc}") from exc
    if isinstance(data, dict):
        data = [data]
    return [d for d in data if isinstance(d, dict)]


async def get_rule_by_name(name: str) -> dict | None:
    """查询指定 DisplayName 的入站 Allow 规则。"""
    _require_admin()
    script = (
        f"$r = Get-NetFirewallRule -DisplayName {ps_quote(name)} "
        "-Direction Inbound -ErrorAction SilentlyContinue; "
        "if ($r) { $r | Select-Object DisplayName,Enabled,Action,Profile | ConvertTo-Json -Compress }"
    )
    result = await run_powershell(script, timeout=30.0)
    text = (result.stdout or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    return data if isinstance(data, dict) else None


async def create_rule(display_name: str, port: int, profiles: str = "Any") -> CmdResult:
    _require_admin()
    script = (
        f"New-NetFirewallRule -DisplayName {ps_quote(display_name)} "
        f"-Direction Inbound -Protocol TCP -LocalPort {int(port)} "
        f"-Action Allow -Profile {profiles} | Out-Null; "
        "Write-Output 'CREATED'"
    )
    return await run_powershell(script, timeout=45.0)


async def remove_rule(display_name: str) -> CmdResult:
    _require_admin()
    script = (
        f"Remove-NetFirewallRule -DisplayName {ps_quote(display_name)} -ErrorAction Stop; "
        "Write-Output 'REMOVED'"
    )
    return await run_powershell(script, timeout=45.0)


async def firewall_profiles() -> list[dict]:
    """各 profile 的启用状态。非管理员时返回空列表。"""
    if not is_admin():
        return []
    result = await run_powershell(
        "Get-NetFirewallProfile | Select-Object Name,Enabled | ConvertTo-Json -Compress",
        timeout=30.0,
    )
    text = (result.stdout or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    return [d for d in data if isinstance(d, dict)]
