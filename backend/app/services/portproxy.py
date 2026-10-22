"""portproxy 规则的读写。

读：直接访问注册表（结构化、无本地化解析、速度快）。
写：走 `netsh`（注册表直写不会立即生效，netsh 才会触发通知流程）。
"""

from __future__ import annotations

import ipaddress
import logging
import winreg

from ..core.shell import CmdResult, run_netsh

log = logging.getLogger(__name__)

LISTEN_ROOT = r"SYSTEM\CurrentControlSet\Services\PortProxy"
TABLE_KEYS = ("v4tov4", "v4tov6", "v6tov4", "v6tov6")


def make_id(address: str, port: int) -> str:
    return f"{address}:{port}"


def pick_table(listen_address: str, connect_address: str) -> str:
    listen_v6 = ipaddress.ip_address(listen_address).version == 6
    connect_v6 = ipaddress.ip_address(connect_address).version == 6
    if not listen_v6 and not connect_v6:
        return "v4tov4"
    if not listen_v6 and connect_v6:
        return "v4tov6"
    if listen_v6 and not connect_v6:
        return "v6tov4"
    return "v6tov6"


def _read_value(key: winreg.HKEYType, name: str) -> str | None:
    try:
        value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return str(value)


def _parse_pair(text: str) -> tuple[str, int] | None:
    """解析 "地址/端口"，IPv6 地址里不含 '/'，用 rpartition 安全切分。"""
    address, _, port_text = str(text).rpartition("/")
    address = address.strip()
    port_text = port_text.strip()
    if not address or not port_text.isdigit():
        return None
    port = int(port_text)
    if not 1 <= port <= 65535:
        return None
    return address, port


def _register(found: dict[str, dict], table: str, listen: tuple[str, int], connect: tuple[str, int]) -> None:
    address, port = listen
    rule_id = make_id(address, port)
    if rule_id in found:
        return
    found[rule_id] = {
        "id": rule_id,
        "listen_address": address,
        "listen_port": port,
        "connect_address": connect[0],
        "connect_port": connect[1],
        "proto": "tcp",
        "table": table,
    }


def read_rules() -> list[dict]:
    """读取全部 portproxy 规则（HKLM 读权限，普通用户即可）。

    注册表在实机上存在两种存储形式，必须都支持：
      1) 值形式（本机实测）：键 ...\\v4tov4\\tcp 下 值名="IP/端口"，值数据="目标IP/目标端口"
      2) 子键形式：子键名="IP/端口"，子键内 connectaddress / connectport 两个值
    """
    found: dict[str, dict] = {}

    for table in TABLE_KEYS:
        path = f"{LISTEN_ROOT}\\{table}\\tcp"
        try:
            base = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ)
        except OSError:
            continue  # 该方向没有任何规则
        with base:
            sub_count, value_count, _ = winreg.QueryInfoKey(base)

            # 形式 1：值
            for index in range(value_count):
                try:
                    name, data, _type = winreg.EnumValue(base, index)
                except OSError:
                    break
                listen = _parse_pair(name)
                connect = _parse_pair(data)
                if listen is None or connect is None:
                    log.debug("跳过无法解析的 portproxy 值：%r = %r", name, data)
                    continue
                _register(found, table, listen, connect)

            # 形式 2：子键
            for index in range(sub_count):
                try:
                    sub = winreg.EnumKey(base, index)
                except OSError:
                    break
                listen = _parse_pair(sub)
                if listen is None:
                    log.debug("跳过无法解析的 portproxy 子键：%r", sub)
                    continue
                connect_address = connect_port = None
                try:
                    with winreg.OpenKey(base, sub, 0, winreg.KEY_READ) as sub_key:
                        connect_address = _read_value(sub_key, "connectaddress")
                        connect_port = _read_value(sub_key, "connectport")
                except OSError:
                    continue
                if not connect_address or not connect_port or not connect_port.isdigit():
                    log.debug("portproxy 子键 %s 缺少 connect* 值", sub)
                    continue
                _register(found, table, listen, (connect_address, int(connect_port)))

    rules = list(found.values())
    rules.sort(key=lambda r: (r["listen_port"], r["listen_address"]))
    return rules


async def add_rule(
    listen_address: str,
    listen_port: int,
    connect_address: str,
    connect_port: int,
) -> CmdResult:
    table = pick_table(listen_address, connect_address)
    return await run_netsh(
        [
            "add",
            table,
            f"listenaddress={listen_address}",
            f"listenport={listen_port}",
            f"connectaddress={connect_address}",
            f"connectport={connect_port}",
        ]
    )


async def delete_rule(listen_address: str, listen_port: int) -> CmdResult:
    """删除时无需知道方向表，netsh 会按 v4tov4 匹配；IPv6 监听端需逐个尝试。"""
    errors: list[CmdResult] = []
    for table in ("v4tov4", "v4tov6", "v6tov4", "v6tov6"):
        result = await run_netsh(
            [
                "delete",
                table,
                f"listenaddress={listen_address}",
                f"listenport={listen_port}",
            ],
            timeout=15.0,
        )
        if result.ok:
            return result
        errors.append(result)

    # 全部失败：返回第一条有实际错误输出的结果
    for result in errors:
        if result.output:
            return result
    return errors[0]
