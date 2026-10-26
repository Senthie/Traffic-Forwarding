"""ARP 网段扫描：列出每张网卡所在网段中已被占用的 IPv4 地址。

两种引擎：

1. ``npcap``：通过 ``wpcap.dll`` 发送原始 ARP 请求并抓取应答。
   能发现禁 Ping 的设备，结果最准确，需要安装 Npcap。
2. ``fallback``：向网段内每个地址发一个 UDP 包，迫使系统发起 ARP 解析，
   随后读取 ``Get-NetNeighbor`` 邻居表。无需额外依赖，但只能看到
   本轮真正解析成功的条目，可能漏掉静默设备。

上层（路由）始终能拿到结果，只是 ``summary.engine`` 与 ``warning`` 会标明
当前用的是哪种引擎。
"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import ipaddress
import json
import logging
import os
import re
import socket
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime

from ..core.elevation import is_admin
from ..core.shell import run_powershell
from ..schemas.scan import ScanHost, ScanResult, ScanSummary

log = logging.getLogger(__name__)

MAX_HOSTS = 1024
DEFAULT_TIMEOUT = 2.5
_ADAPTER_TTL = 30.0
_WPCAP_TTL = 10.0

_WPCAP_CANDIDATES = (
    r"C:\Windows\System32\Npcap\wpcap.dll",
    r"C:\Windows\System32\wpcap.dll",
    r"C:\Windows\SysWOW64\Npcap\wpcap.dll",
    r"C:\Windows\SysWOW64\wpcap.dll",
)

_ETH_P_ARP = 0x0806
_ARPHRD_ETHER = 1
_ETHERTYPE_IP = 0x0800
_BCAST_MAC = b"\xff" * 6


class ScanError(RuntimeError):
    """扫描无法进行（参数错误、网卡不存在、抓包失败……）。"""


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #


@dataclass
class AdapterInfo:
    alias: str
    address: str
    prefix_length: int
    mac: str | None = None
    guid: str | None = None
    description: str | None = None


@dataclass
class NpcapLib:
    dll: ctypes.WinDLL  # type: ignore[name-defined]
    path: str
    version: str | None = None
    _dll_dir: object | None = field(default=None, repr=False)


# --------------------------------------------------------------------------- #
# 通用小工具
# --------------------------------------------------------------------------- #


def _parse_json(text: str) -> list[dict]:
    text = (text or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("JSON 解析失败：%s", text[:200])
        return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _normalize_mac(value: str | None) -> str | None:
    """统一成 ``aa:bb:cc:dd:ee:ff``，过滤全 0 / 广播 / 组播。"""
    if not value:
        return None
    text = value.strip().replace("-", ":").lower()
    parts = text.split(":")
    if len(parts) != 6 or any(len(p) != 2 for p in parts):
        return None
    try:
        octets = [int(p, 16) for p in parts]
    except ValueError:
        return None
    if all(o == 0x00 for o in octets) or all(o == 0xFF for o in octets):
        return None
    if octets[0] & 0x01:  # 组播 / 广播位
        return None
    return ":".join(f"{o:02x}" for o in octets)


def _mac_to_bytes(mac: str | None) -> bytes | None:
    normalized = _normalize_mac(mac)
    if normalized is None:
        return None
    return bytes(int(part, 16) for part in normalized.split(":"))


def build_targets(
    address: str,
    prefix_length: int,
    scope: str,
    *,
    max_hosts: int = MAX_HOSTS,
) -> tuple[ipaddress.IPv4Network, list[str], bool]:
    """返回 (实际扫描网段, 目标地址列表, 是否被截断)。"""
    interface = ipaddress.ip_interface(f"{address}/{prefix_length}")
    network = interface.network

    # 快速模式：前缀比 /24 更大时，只扫该地址所在的 /24，避免一下子几千个地址
    if scope == "auto" and network.prefixlen < 24:
        network = ipaddress.ip_interface(f"{address}/24").network

    assert isinstance(network, ipaddress.IPv4Network)
    hosts = [str(ip) for ip in network.hosts()]
    truncated = len(hosts) > max_hosts
    if truncated:
        hosts = hosts[:max_hosts]
    return network, hosts, truncated


# --------------------------------------------------------------------------- #
# 网卡信息（别名 / MAC / GUID）
# --------------------------------------------------------------------------- #

_adapter_cache: tuple[float, list[AdapterInfo]] | None = None

_ADAPTER_SCRIPT = (
    "Get-NetIPAddress -AddressFamily IPv4 | ForEach-Object {"
    "$a = Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue;"
    "[pscustomobject]@{"
    "Alias=$_.InterfaceAlias;Address=$_.IPAddress;Prefix=[int]$_.PrefixLength;"
    "Mac=$a.MacAddress;Guid=$a.InterfaceGuid;Description=$a.InterfaceDescription"
    "}} | ConvertTo-Json -Compress"
)


async def list_adapters(*, force: bool = False) -> list[AdapterInfo]:
    global _adapter_cache

    now = time.monotonic()
    if not force and _adapter_cache and now - _adapter_cache[0] < _ADAPTER_TTL:
        return _adapter_cache[1]

    result = await run_powershell(_ADAPTER_SCRIPT, timeout=20.0)
    adapters: list[AdapterInfo] = []
    if result.ok:
        for row in _parse_json(result.stdout):
            address = str(row.get("Address") or "").strip()
            if not address:
                continue
            try:
                ip = ipaddress.ip_address(address)
            except ValueError:
                continue
            if ip.version != 4:
                continue
            try:
                prefix = int(row.get("Prefix"))
            except (TypeError, ValueError):
                prefix = 24
            adapters.append(
                AdapterInfo(
                    alias=str(row.get("Alias") or "未知网卡"),
                    address=address,
                    prefix_length=max(0, min(prefix, 32)),
                    mac=_normalize_mac(str(row.get("Mac") or "").strip() or None),
                    guid=str(row.get("Guid") or "").strip() or None,
                    description=str(row.get("Description") or "").strip() or None,
                )
            )
    else:
        log.warning("读取网卡信息失败：%s", result.output[:200])

    adapters.sort(key=lambda a: tuple(int(part) for part in a.address.split(".")))
    _adapter_cache = (now, adapters)
    return adapters


async def find_adapter(address: str) -> AdapterInfo:
    adapters = await list_adapters()
    for adapter in adapters:
        if adapter.address == address:
            return adapter
    # 缓存可能是旧的（刚插的网卡 / DHCP 换了地址），强制刷新一次
    for adapter in await list_adapters(force=True):
        if adapter.address == address:
            return adapter
    raise ScanError(f"本机找不到地址为 {address} 的网卡")


# --------------------------------------------------------------------------- #
# Npcap 加载
# --------------------------------------------------------------------------- #

_lib_cache: tuple[float, NpcapLib | None] | None = None


def _bind_wpcap(path: str) -> NpcapLib:
    dll_dir = None
    directory = os.path.dirname(path)
    if directory and os.path.isdir(directory):
        with contextlib.suppress(OSError):
            dll_dir = os.add_dll_directory(directory)

    dll = ctypes.WinDLL(path)  # type: ignore[attr-defined]

    dll.pcap_findalldevs.argtypes = [
        ctypes.POINTER(ctypes.POINTER(_pcap_if)),
        ctypes.c_char_p,
    ]
    dll.pcap_findalldevs.restype = ctypes.c_int
    dll.pcap_freealldevs.argtypes = [ctypes.POINTER(_pcap_if)]
    dll.pcap_freealldevs.restype = None
    dll.pcap_open_live.argtypes = [
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
    ]
    dll.pcap_open_live.restype = ctypes.c_void_p
    dll.pcap_close.argtypes = [ctypes.c_void_p]
    dll.pcap_close.restype = None
    dll.pcap_next_ex.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.POINTER(_pcap_pkthdr)),
        ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
    ]
    dll.pcap_next_ex.restype = ctypes.c_int
    dll.pcap_sendpacket.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.c_int,
    ]
    dll.pcap_sendpacket.restype = ctypes.c_int
    dll.pcap_geterr.argtypes = [ctypes.c_void_p]
    dll.pcap_geterr.restype = ctypes.c_char_p
    dll.pcap_lib_version.argtypes = []
    dll.pcap_lib_version.restype = ctypes.c_char_p

    version = None
    with contextlib.suppress(Exception):
        raw = dll.pcap_lib_version()
        if raw:
            text = raw.decode("utf-8", "replace")
            match = re.search(r"Npcap version ([\d.]+)", text, re.IGNORECASE)
            version = match.group(1) if match else text

    return NpcapLib(dll=dll, path=path, version=version, _dll_dir=dll_dir)


class _timeval(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]


class _pcap_pkthdr(ctypes.Structure):
    _fields_ = [
        ("ts", _timeval),
        ("caplen", ctypes.c_uint),
        ("len", ctypes.c_uint),
    ]


class _pcap_if(ctypes.Structure):
    pass


_pcap_if._fields_ = [
    ("next", ctypes.POINTER(_pcap_if)),
    ("name", ctypes.c_char_p),
    ("description", ctypes.c_char_p),
    ("addresses", ctypes.c_void_p),
    ("flags", ctypes.c_uint),
]


def load_wpcap(*, force: bool = False) -> NpcapLib | None:
    """加载 wpcap.dll；未安装 Npcap 时返回 None（10 秒内复用结果）。"""
    global _lib_cache

    if os.name != "nt":
        return None

    now = time.monotonic()
    if not force and _lib_cache and now - _lib_cache[0] < _WPCAP_TTL:
        return _lib_cache[1]

    lib: NpcapLib | None = None
    last_error: Exception | None = None

    for candidate in _WPCAP_CANDIDATES:
        if not os.path.exists(candidate):
            continue
        try:
            lib = _bind_wpcap(candidate)
            break
        except OSError as exc:  # pragma: no cover - 依赖系统环境
            last_error = exc
            log.warning("加载 %s 失败：%s", candidate, exc)

    if lib is None:
        with contextlib.suppress(OSError):
            lib = _bind_wpcap("wpcap.dll")

    if lib is None and last_error is not None:
        log.info("Npcap 不可用：%s", last_error)

    _lib_cache = (now, lib)
    return lib


def engine_info(*, force: bool = False) -> dict:
    lib = load_wpcap(force=force)
    available = lib is not None
    return {
        "engine": "npcap" if available else "fallback",
        "npcap_available": available,
        "npcap_version": lib.version if lib else None,
        "npcap_path": lib.path if lib else None,
        "admin": is_admin(),
        "reason": None
        if available
        else "未检测到 wpcap.dll（Npcap 未安装，或安装时未选中 Npcap API）",
        "note": None
        if available
        else "当前使用邻居表回退引擎：先向网段发 UDP 包触发 ARP 解析，再读取系统邻居表，"
        "可能漏掉不响应 ARP 的设备。安装 Npcap 后刷新即可自动切换为真 ARP 扫描。",
    }


# --------------------------------------------------------------------------- #
# 原始 ARP 报文
# --------------------------------------------------------------------------- #


def _build_arp_request(src_mac: bytes, src_ip: bytes, dst_ip: bytes) -> bytes:
    ethernet = _BCAST_MAC + src_mac + struct.pack("!H", _ETH_P_ARP)
    arp = (
        struct.pack("!HHBBH", _ARPHRD_ETHER, _ETHERTYPE_IP, 6, 4, 1)
        + src_mac
        + src_ip
        + b"\x00" * 6
        + dst_ip
    )
    frame = ethernet + arp
    if len(frame) < 60:  # 以太网最小帧，太短的帧部分网卡会丢弃
        frame += b"\x00" * (60 - len(frame))
    return frame


def _parse_arp(frame: bytes) -> tuple[str | None, str | None]:
    if len(frame) < 42:
        return None, None
    ethertype = struct.unpack("!H", frame[12:14])[0]
    if ethertype != _ETH_P_ARP:
        return None, None
    htype, ptype, hlen, plen, oper = struct.unpack("!HHBBH", frame[14:22])
    if htype != _ARPHRD_ETHER or ptype != _ETHERTYPE_IP or hlen != 6 or plen != 4:
        return None, None
    if oper not in (1, 2):
        return None, None
    sender_mac = ":".join(f"{b:02x}" for b in frame[22:28])
    sender_ip = socket.inet_ntoa(frame[28:32])
    return sender_ip, sender_mac


def _cstr(value: bytes | None) -> str:
    if not value:
        return ""
    return value.decode("utf-8", "replace").strip()


def _find_device(lib: NpcapLib, adapter: AdapterInfo) -> bytes:
    devices = ctypes.POINTER(_pcap_if)()
    errbuf = ctypes.create_string_buffer(1024)
    if lib.dll.pcap_findalldevs(ctypes.byref(devices), errbuf) != 0:
        raise ScanError(f"枚举 Npcap 设备失败：{_cstr(errbuf.value)}")

    guid = (adapter.guid or "").strip().lower()
    description = (adapter.description or "").strip().lower()
    exact: bytes | None = None
    fuzzy: bytes | None = None

    try:
        node = devices
        while node:
            device = node.contents
            name = device.name or b""
            desc = _cstr(device.description).lower()
            lowered = name.decode("utf-8", "replace").lower()
            if guid and guid in lowered:
                exact = name
                break
            if description and desc and description in desc and fuzzy is None:
                fuzzy = name
            node = device.next
    finally:
        lib.dll.pcap_freealldevs(devices)

    chosen = exact or fuzzy
    if chosen is None:
        raise ScanError(f"Npcap 设备列表里找不到网卡「{adapter.alias}」，请确认该网卡处于启用状态")
    return chosen


def _npcap_scan(
    lib: NpcapLib,
    adapter: AdapterInfo,
    targets: list[str],
    timeout: float,
) -> dict[str, str]:
    """阻塞式 ARP 扫描，返回 {ip: mac}。由调用方放进线程里跑。"""
    device = _find_device(lib, adapter)
    dd = lib.dll

    errbuf = ctypes.create_string_buffer(1024)
    handle = dd.pcap_open_live(device, 65536, 0, 20, errbuf)
    if not handle:
        raise ScanError(f"打开网卡失败：{_cstr(errbuf.value)}")

    try:
        src_mac = _mac_to_bytes(adapter.mac)
        if src_mac is None:
            raise ScanError("网卡 MAC 无效，无法构造 ARP 报文")
        src_ip = socket.inet_aton(adapter.address)

        pending: dict[str, float] = {ip: -1e9 for ip in targets}
        found: dict[str, str] = {}
        interval = max(timeout / 3.0, 0.2)
        started = time.monotonic()
        sent = 0
        header = ctypes.POINTER(_pcap_pkthdr)()
        data = ctypes.POINTER(ctypes.c_ubyte)()

        while pending and time.monotonic() - started < timeout:
            now = time.monotonic()
            for ip_text, last_sent in list(pending.items()):
                if now - last_sent < interval:
                    continue
                frame = _build_arp_request(src_mac, src_ip, socket.inet_aton(ip_text))
                buffer = (ctypes.c_ubyte * len(frame)).from_buffer_copy(frame)
                if dd.pcap_sendpacket(handle, buffer, len(frame)) != 0:
                    raise ScanError(f"发送 ARP 请求失败：{_cstr(dd.pcap_geterr(handle))}")
                pending[ip_text] = now
                sent += 1
                if sent % 32 == 0:
                    time.sleep(0.002)  # 给驱动一点喘息时间，避免发送队列溢出

            rc = dd.pcap_next_ex(handle, ctypes.byref(header), ctypes.byref(data))
            if rc == 1:
                frame = ctypes.string_at(data, header.contents.caplen)
                sender_ip, sender_mac = _parse_arp(frame)
                if sender_ip and sender_ip in pending:
                    found[sender_ip] = sender_mac or ""
                    pending.pop(sender_ip, None)
            elif rc == -1:
                raise ScanError(f"抓包失败：{_cstr(dd.pcap_geterr(handle))}")
            elif rc == -2:  # pragma: no cover - 实时设备不会返回 EOF
                break

        return found
    finally:
        dd.pcap_close(handle)


# --------------------------------------------------------------------------- #
# 回退引擎：UDP 触发 ARP + 邻居表
# --------------------------------------------------------------------------- #


def _send_udp_probes(source_ip: str, targets: list[str]) -> None:
    """向每个目标发一个 UDP 包；系统会为它们发起 ARP 解析。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setblocking(False)
        with contextlib.suppress(OSError):
            sock.bind((source_ip, 0))
        for target in targets:
            with contextlib.suppress(OSError):
                # 端口随意，目的只是触发一次 ARP 查询
                sock.sendto(b"\x00", (target, 33434))
    finally:
        sock.close()


_NEIGHBOR_SCRIPT = (
    "Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
    "Where-Object { $_.LinkLayerAddress -and $_.LinkLayerAddress -ne '' } | "
    "Select-Object IPAddress,LinkLayerAddress,State,InterfaceAlias | "
    "ConvertTo-Json -Compress"
)


async def _neighbors() -> list[dict]:
    result = await run_powershell(_NEIGHBOR_SCRIPT, timeout=20.0)
    if not result.ok:
        log.warning("读取邻居表失败：%s", result.output[:200])
        return []
    return _parse_json(result.stdout)


async def _fallback_scan(
    adapter: AdapterInfo,
    targets: list[str],
    timeout: float,
) -> dict[str, str]:
    await asyncio.to_thread(_send_udp_probes, adapter.address, targets)
    await asyncio.sleep(min(max(timeout * 0.6, 0.6), 1.8))

    wanted = set(targets)
    found: dict[str, str] = {}
    for row in await _neighbors():
        ip_text = str(row.get("IPAddress") or "").strip()
        if ip_text not in wanted:
            continue
        state = str(row.get("State") or "").strip().lower()
        if state in {"incomplete", "unreachable"}:
            continue
        mac = _normalize_mac(str(row.get("LinkLayerAddress") or ""))
        if mac is None:
            continue
        found[ip_text] = mac
    return found


# --------------------------------------------------------------------------- #
# 对外入口
# --------------------------------------------------------------------------- #


async def scan(
    address: str,
    prefix_length: int = 24,
    scope: str = "auto",
    timeout: float = DEFAULT_TIMEOUT,
) -> ScanResult:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError as exc:
        raise ScanError(f"不是合法的 IP 地址：{address}") from exc
    if ip.version != 4:
        raise ScanError("目前只支持 IPv4 扫描")
    if not 0 <= prefix_length <= 32:
        raise ScanError("前缀长度必须在 0 ~ 32 之间")
    if scope not in {"auto", "full"}:
        raise ScanError("scope 只能是 auto 或 full")

    timeout = max(0.5, min(float(timeout), 10.0))
    network, targets, truncated = build_targets(str(ip), prefix_length, scope)
    adapter = await find_adapter(str(ip))

    started = time.perf_counter()
    engine = "fallback"
    warning: str | None = None

    lib = load_wpcap()
    if lib is not None and adapter.mac:
        try:
            found = await asyncio.to_thread(_npcap_scan, lib, adapter, targets, timeout)
            engine = "npcap"
        except (ScanError, OSError, ValueError) as exc:
            log.warning("Npcap 扫描 %s 失败，回退：%s", adapter.alias, exc)
            warning = f"Npcap 扫描失败（{exc}），已改用邻居表回退。"
            found = await _fallback_scan(adapter, targets, timeout)
    else:
        reasons: list[str] = []
        if lib is None:
            reasons.append("未检测到 Npcap（wpcap.dll）")
        if not adapter.mac:
            reasons.append("读取不到网卡 MAC")
        warning = "；".join(reasons) + "，已改用邻居表回退。"
        found = await _fallback_scan(adapter, targets, timeout)

    target_set = set(targets)
    hosts: list[ScanHost] = []
    for ip_text, mac in found.items():
        if ip_text not in target_set:
            continue
        is_local = ip_text == adapter.address
        hosts.append(
            ScanHost(
                ip=ip_text,
                mac=mac or (adapter.mac if is_local else None),
                is_local=is_local,
            )
        )
    if adapter.address in target_set and adapter.address not in found:
        hosts.append(ScanHost(ip=adapter.address, mac=adapter.mac, is_local=True))

    hosts.sort(key=lambda item: ipaddress.ip_address(item.ip))
    elapsed_ms = (time.perf_counter() - started) * 1000

    if truncated:
        extra = f"网段过大，仅扫描了前 {MAX_HOSTS} 个地址"
        warning = f"{warning}；{extra}" if warning else extra

    alive = len(hosts)
    summary = ScanSummary(
        network=str(network),
        prefix_length=network.prefixlen,
        interface_alias=adapter.alias,
        interface_address=adapter.address,
        engine=engine,  # type: ignore[arg-type]
        total=len(targets),
        alive=alive,
        idle=max(0, len(targets) - alive),
        elapsed_ms=round(elapsed_ms, 1),
        truncated=truncated,
        warning=warning,
        checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )
    log.info(
        "ARP 扫描 %s (%s, %s) 在线 %d/%d，耗时 %.0f ms",
        adapter.alias,
        network,
        engine,
        alive,
        len(targets),
        elapsed_ms,
    )
    return ScanResult(summary=summary, hosts=hosts)
