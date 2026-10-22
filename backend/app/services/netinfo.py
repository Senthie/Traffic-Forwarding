"""本机网卡与端口占用信息。"""

from __future__ import annotations

import asyncio
import errno
import ipaddress
import json
import logging
import socket

from ..core.shell import run_powershell
from ..schemas.rule import InterfaceInfo

log = logging.getLogger(__name__)

_cache: tuple[float, list[InterfaceInfo]] | None = None
_CACHE_TTL = 10.0


def _parse_json(text: str) -> list[dict]:
    text = (text or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("网卡信息 JSON 解析失败：%s", text[:200])
        return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    return [d for d in data if isinstance(d, dict)]


def _fallback_interfaces() -> list[InterfaceInfo]:
    found: dict[str, InterfaceInfo] = {}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addr = info[4][0]
            found.setdefault(
                addr,
                InterfaceInfo(alias="(本机)", address=addr, prefix_length=None),
            )
    except OSError:
        pass
    found.setdefault(
        "127.0.0.1",
        InterfaceInfo(alias="Loopback", address="127.0.0.1", prefix_length=8, is_loopback=True),
    )
    return list(found.values())


async def list_interfaces(*, force: bool = False) -> list[InterfaceInfo]:
    global _cache

    now = asyncio.get_running_loop().time()
    if not force and _cache and now - _cache[0] < _CACHE_TTL:
        return _cache[1]

    script = (
        "Get-NetIPAddress -AddressFamily IPv4 "
        "| Select-Object InterfaceAlias,IPAddress,PrefixLength "
        "| ConvertTo-Json -Compress"
    )
    result = await run_powershell(script, timeout=20.0)

    items: list[InterfaceInfo] = []
    if result.ok:
        for row in _parse_json(result.stdout):
            address = str(row.get("IPAddress") or "").strip()
            if not address:
                continue
            try:
                ip = ipaddress.ip_address(address)
            except ValueError:
                continue
            items.append(
                InterfaceInfo(
                    alias=str(row.get("InterfaceAlias") or "未知网卡"),
                    address=address,
                    prefix_length=row.get("PrefixLength"),
                    is_loopback=ip.is_loopback,
                )
            )
    else:
        log.warning("Get-NetIPAddress 失败，使用回退方案：%s", result.output[:200])
        items = _fallback_interfaces()

    if not items:
        items = _fallback_interfaces()

    items.sort(key=lambda i: (i.is_loopback, i.address))
    _cache = (now, items)
    return items


async def local_addresses() -> set[str]:
    return {i.address for i in await list_interfaces()}


def port_in_use(address: str, port: int) -> bool:
    """尝试 bind 判断端口是否被占用（不需要管理员权限）。

    注意：只有 EADDRINUSE 才算"被占用"。地址不属于本机时会抛
    WSAEADDRNOTAVAIL（10049），那是另一个问题，不能误报成端口冲突。
    """
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.bind((address, port))
        return False
    except OSError as exc:
        winerror = getattr(exc, "winerror", None)
        return winerror == 10048 or exc.errno == errno.EADDRINUSE
