"""规则编排：合并"系统状态 + 应用元数据 + 防火墙 + 健康"，并提供增删改校验。"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from datetime import datetime

from ..core.elevation import is_admin
from ..schemas.rule import (
    FirewallStatus,
    ImportResult,
    RuleBase,
    RuleCreate,
    RuleOut,
    ValidationIssue,
    ValidationOut,
)
from . import firewall, netinfo, portproxy, probe
from .metadata import Store

log = logging.getLogger(__name__)


class RuleError(RuntimeError):
    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def require_admin() -> None:
    if not is_admin():
        raise RuleError("该操作需要管理员权限，请以管理员身份重新启动应用。", status=403)


async def _firewall_snapshot() -> tuple[list[dict], bool, str | None]:
    """返回 (规则列表, 是否可用, 不可用原因)。"""
    try:
        return await firewall.list_inbound_tcp_allow(), True, None
    except firewall.FirewallUnavailable as exc:
        return [], False, str(exc)
    except Exception as exc:  # pragma: no cover - 防御性
        log.exception("读取防火墙失败")
        return [], False, f"{type(exc).__name__}: {exc}"


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _split_profiles(value: object) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in text.split(",") if p.strip()]
    return parts


async def collect_rules(*, with_health: bool = False) -> list[RuleOut]:
    system_rules = await asyncio.to_thread(portproxy.read_rules)
    meta = await asyncio.to_thread(Store.instance().all_meta)
    fw_entries, fw_available, fw_error = await _firewall_snapshot()
    by_name = {(e.get("Name") or "").strip().lower(): e for e in fw_entries}

    health_map = {}
    if with_health and system_rules:
        health_map = await probe.probe_many(system_rules)

    collected: list[RuleOut] = []
    for raw in system_rules:
        m = meta.get(raw["id"], {})
        status = FirewallStatus(available=fw_available, error=fw_error)
        fw_name = (m.get("firewall_rule_name") or "").strip() or None

        entry = None
        if fw_name:
            status.rule_name = fw_name
            entry = by_name.get(fw_name.lower())
        if entry is None and fw_available:
            for candidate in fw_entries:
                if firewall.port_matches(str(candidate.get("Port") or ""), raw["listen_port"]):
                    entry = candidate
                    status.reused_by = str(candidate.get("Name") or "")
                    break
        if entry is not None:
            status.exists = True
            status.enabled = _truthy(entry.get("Enabled"))
            status.action = str(entry.get("Action") or "Allow")
            status.profiles = _split_profiles(entry.get("Profile"))
            if not status.rule_name:
                status.rule_name = str(entry.get("Name") or "")

        collected.append(
            RuleOut(
                id=raw["id"],
                name=m.get("name"),
                note=m.get("note"),
                listen_address=raw["listen_address"],
                listen_port=raw["listen_port"],
                connect_address=raw["connect_address"],
                connect_port=raw["connect_port"],
                proto=raw.get("proto", "tcp"),
                firewall_rule_name=fw_name,
                firewall=status,
                health=health_map.get(raw["id"]),
                is_named=bool(m.get("name")),
                created_at=m.get("created_at"),
            )
        )
    return collected


async def validate_payload(payload: RuleBase, *, exclude_id: str | None = None) -> ValidationOut:
    issues: list[ValidationIssue] = []

    local = await netinfo.local_addresses()
    if payload.listen_address not in local:
        issues.append(
            ValidationIssue(
                level="error",
                field="listen_address",
                message=(
                    f"监听地址 {payload.listen_address} 不属于本机任何网卡，"
                    "netsh 会创建成功但规则永不生效"
                ),
            )
        )

    existing = await asyncio.to_thread(portproxy.read_rules)
    for rule in existing:
        if exclude_id and rule["id"] == exclude_id:
            continue
        if (
            rule["listen_address"] == payload.listen_address
            and rule["listen_port"] == payload.listen_port
        ):
            issues.append(
                ValidationIssue(
                    level="error",
                    field="listen_port",
                    message=(
                        f"已存在相同监听端的规则 "
                        f"{rule['listen_address']}:{rule['listen_port']} → "
                        f"{rule['connect_address']}:{rule['connect_port']}"
                    ),
                )
            )
            break

    if (
        payload.connect_address == payload.listen_address
        and payload.connect_port == payload.listen_port
    ):
        issues.append(
            ValidationIssue(
                level="error",
                field="connect_address",
                message="目标地址与本机监听完全相同，会形成环回",
            )
        )

    if payload.listen_port < 1024:
        issues.append(
            ValidationIssue(
                level="info",
                field="listen_port",
                message=f"端口 {payload.listen_port} 属于特权端口，注意与系统服务冲突",
            )
        )

    same_listen = exclude_id is not None and exclude_id == portproxy.make_id(
        payload.listen_address, payload.listen_port
    )
    if (
        not same_listen
        and payload.listen_address in local
        and netinfo.port_in_use(payload.listen_address, payload.listen_port)
    ):
        issues.append(
            ValidationIssue(
                level="warning",
                field="listen_port",
                message=f"端口 {payload.listen_port} 当前已被其它进程占用，转发可能不生效",
            )
        )

    target_ok, _latency, target_err = await probe.tcp_probe(
        payload.connect_address, payload.connect_port, timeout=1.2
    )
    if not target_ok:
        issues.append(
            ValidationIssue(
                level="warning",
                field="connect_address",
                message=f"目标当前不可达（{target_err}），规则仍可创建，稍后可重新探测",
            )
        )

    return ValidationOut(
        ok=not any(i.level == "error" for i in issues),
        issues=issues,
        normalized=RuleCreate.model_validate(payload.model_dump()),
        target_reachable=target_ok,
    )


def _audit_command(store: Store, action: str, rule_id: str, result) -> None:
    store.log(
        action,
        rule_id=rule_id,
        command=result.command_line(),
        returncode=result.returncode,
        output=result.summary(),
        ok=result.ok,
    )


async def create_rule(payload: RuleCreate) -> RuleOut:
    require_admin()
    store = Store.instance()

    validation = await validate_payload(payload)
    if not validation.ok:
        message = "；".join(i.message for i in validation.issues if i.level == "error")
        raise RuleError(message)

    rule_id = portproxy.make_id(payload.listen_address, payload.listen_port)

    add = await portproxy.add_rule(
        payload.listen_address,
        payload.listen_port,
        payload.connect_address,
        payload.connect_port,
    )
    _audit_command(store, "portproxy.add", rule_id, add)
    if not add.ok:
        raise RuleError(f"创建转发规则失败：{add.summary() or 'netsh 返回非零退出码'}", status=502)

    fw_name: str | None = None
    if payload.open_firewall:
        fw_name = (payload.firewall_rule_name or payload.name).strip()
        try:
            existing = await firewall.get_rule_by_name(fw_name)
            if existing is None:
                created = await firewall.create_rule(fw_name, payload.listen_port, payload.profiles)
                _audit_command(store, "firewall.create", rule_id, created)
                if not created.ok:
                    rollback = await portproxy.delete_rule(
                        payload.listen_address, payload.listen_port
                    )
                    _audit_command(store, "portproxy.delete(rollback)", rule_id, rollback)
                    raise RuleError(
                        f"开放防火墙端口失败，已回滚转发规则：{created.summary()}",
                        status=502,
                    )
            else:
                store.log(
                    "firewall.reuse",
                    rule_id=rule_id,
                    detail=f"复用已有防火墙规则 {fw_name}",
                )
        except firewall.FirewallUnavailable as exc:
            log.warning("防火墙不可用，跳过：%s", exc)

    store.upsert_meta(
        rule_id,
        name=payload.name,
        note=payload.note,
        firewall_rule_name=fw_name,
        profiles=payload.profiles,
    )
    store.log("rule.create", rule_id=rule_id, detail=f"新增 {rule_id}")
    return await _get_rule(rule_id)


async def update_rule(old_id: str, payload: RuleCreate) -> RuleOut:
    require_admin()
    store = Store.instance()

    old = next((r for r in await asyncio.to_thread(portproxy.read_rules) if r["id"] == old_id), None)
    if old is None:
        raise RuleError(f"规则 {old_id} 不存在", status=404)

    validation = await validate_payload(payload, exclude_id=old_id)
    if not validation.ok:
        message = "；".join(i.message for i in validation.issues if i.level == "error")
        raise RuleError(message)

    new_id = portproxy.make_id(payload.listen_address, payload.listen_port)
    endpoint_changed = (
        old["listen_address"] != payload.listen_address
        or old["listen_port"] != payload.listen_port
        or old["connect_address"] != payload.connect_address
        or old["connect_port"] != payload.connect_port
    )

    if endpoint_changed:
        removed = await portproxy.delete_rule(old["listen_address"], old["listen_port"])
        _audit_command(store, "portproxy.delete", old_id, removed)
        if not removed.ok:
            raise RuleError(f"删除旧规则失败：{removed.summary()}", status=502)

        added = await portproxy.add_rule(
            payload.listen_address,
            payload.listen_port,
            payload.connect_address,
            payload.connect_port,
        )
        _audit_command(store, "portproxy.add", new_id, added)
        if not added.ok:
            restore = await portproxy.add_rule(
                old["listen_address"],
                old["listen_port"],
                old["connect_address"],
                old["connect_port"],
            )
            _audit_command(store, "portproxy.add(rollback)", old_id, restore)
            raise RuleError(f"创建新规则失败，已尝试回滚：{added.summary()}", status=502)

    old_meta = store.get_meta(old_id) or {}
    old_fw_name = (old_meta.get("firewall_rule_name") or "").strip() or None
    desired_fw_name = (payload.firewall_rule_name or payload.name).strip() if payload.open_firewall else None

    try:
        if old_fw_name and old_fw_name != desired_fw_name:
            removed_fw = await firewall.remove_rule(old_fw_name)
            _audit_command(store, "firewall.delete", old_id, removed_fw)
        if desired_fw_name:
            existing = await firewall.get_rule_by_name(desired_fw_name)
            if existing is None:
                created = await firewall.create_rule(
                    desired_fw_name, payload.listen_port, payload.profiles
                )
                _audit_command(store, "firewall.create", new_id, created)
    except firewall.FirewallUnavailable as exc:
        log.warning("防火墙不可用，跳过：%s", exc)

    if old_id != new_id:
        store.delete_meta(old_id)

    store.upsert_meta(
        new_id,
        name=payload.name,
        note=payload.note,
        firewall_rule_name=desired_fw_name,
        profiles=payload.profiles,
    )
    store.log("rule.update", rule_id=new_id, detail=f"{old_id} → {new_id}")
    return await _get_rule(new_id)


async def delete_rule(rule_id: str, *, delete_firewall: bool = False) -> None:
    require_admin()
    store = Store.instance()

    old = next((r for r in await asyncio.to_thread(portproxy.read_rules) if r["id"] == rule_id), None)
    if old is None:
        raise RuleError(f"规则 {rule_id} 不存在", status=404)

    removed = await portproxy.delete_rule(old["listen_address"], old["listen_port"])
    _audit_command(store, "portproxy.delete", rule_id, removed)
    if not removed.ok:
        raise RuleError(f"删除转发规则失败：{removed.summary()}", status=502)

    if delete_firewall:
        meta = store.get_meta(rule_id) or {}
        fw_name = (meta.get("firewall_rule_name") or "").strip()
        if fw_name:
            try:
                result = await firewall.remove_rule(fw_name)
                _audit_command(store, "firewall.delete", rule_id, result)
            except firewall.FirewallUnavailable as exc:
                log.warning("防火墙不可用，跳过删除：%s", exc)

    store.delete_meta(rule_id)
    store.log("rule.delete", rule_id=rule_id, detail=f"删除 {rule_id}")


async def _get_rule(rule_id: str) -> RuleOut:
    rules = await collect_rules(with_health=False)
    for rule in rules:
        if rule.id == rule_id:
            return rule
    raise RuleError(f"规则 {rule_id} 在系统中不存在", status=404)


async def orphans() -> list[dict]:
    """防火墙里存在、但对应转发规则已消失的条目。"""
    meta = await asyncio.to_thread(Store.instance().all_meta)
    rules = await asyncio.to_thread(portproxy.read_rules)
    live = {r["id"] for r in rules}
    entries, available, _ = await _firewall_snapshot()
    if not available:
        return []
    by_name = {(e.get("Name") or "").strip().lower(): e for e in entries}

    result = []
    for rule_id, m in meta.items():
        if rule_id in live:
            continue
        fw_name = (m.get("firewall_rule_name") or "").strip()
        if not fw_name:
            continue
        entry = by_name.get(fw_name.lower())
        if entry is None:
            continue
        result.append(
            {
                "name": fw_name,
                "port": entry.get("Port"),
                "rule_id": rule_id,
                "detail": f"转发规则 {rule_id} 已不存在，但防火墙仍开放端口 {entry.get('Port')}",
            }
        )
    return result


async def export_rules() -> dict:
    rules = await collect_rules(with_health=False)
    return {
        "version": 1,
        "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "rules": [
            {
                "name": r.name or r.id,
                "note": r.note,
                "listen_address": r.listen_address,
                "listen_port": r.listen_port,
                "connect_address": r.connect_address,
                "connect_port": r.connect_port,
                "open_firewall": bool(r.firewall_rule_name),
                "firewall_rule_name": r.firewall_rule_name,
            }
            for r in rules
        ],
    }


async def import_rules(items: list[RuleCreate]) -> ImportResult:
    result = ImportResult()
    for item in items:
        try:
            await create_rule(item)
            result.created += 1
        except (RuleError, ValueError) as exc:
            result.failed += 1
            result.messages.append(f"{item.listen_address}:{item.listen_port} - {exc}")
    return result


def is_local_ip(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False
