"""排查 portproxy 注册表位置。"""

from __future__ import annotations

import winreg


def walk(path: str, depth: int = 0) -> None:
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ)
    except OSError as exc:
        print(f"{'  ' * depth}[ERR] {path} -> {exc}")
        return
    with key:
        sub_count, value_count, _ = winreg.QueryInfoKey(key)
        print(f"{'  ' * depth}[OK ] {path}  subkeys={sub_count} values={value_count}")
        for i in range(value_count):
            name, value, _ = winreg.EnumValue(key, i)
            print(f"{'  ' * depth}      value {name!r} = {value!r}")
        for i in range(sub_count):
            walk(f"{path}\\{winreg.EnumKey(key, i)}", depth + 1)


for root in (
    r"SYSTEM\CurrentControlSet\Services\PortProxy",
    r"SYSTEM\CurrentControlSet\Services\PortProxy\v4tov4",
    r"SYSTEM\CurrentControlSet\Services\PortProxy\v4tov4\tcp",
):
    walk(root)
    print("-" * 40)
