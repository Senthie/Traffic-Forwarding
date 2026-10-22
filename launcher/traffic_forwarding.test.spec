# -*- mode: python ; coding: utf-8 -*-
"""仅用于冒烟测试：与正式 spec 相同，但不嵌 requireAdministrator 清单。

构建：uv run pyinstaller --noconfirm --clean launcher/traffic_forwarding.test.spec
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
BACKEND = ROOT / "backend"

a = Analysis(
    [str(ROOT / "launcher" / "main.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=[
        (str(BACKEND / "app" / "static"), "backend/app/static"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "app.main",
        "app.core.config",
        "app.core.shell",
        "app.core.elevation",
        "app.schemas.rule",
        "app.services.portproxy",
        "app.services.netinfo",
        "app.services.probe",
        "app.services.firewall",
        "app.services.metadata",
        "app.services.rules",
        "app.api.routes_rules",
        "app.api.routes_system",
        "app.api.routes_probe",
        "app.api.routes_firewall",
        "app.api.routes_logs",
        "webview",
        "webview.platforms.winforms",
        "clr",
        "clr_loader",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="traffic-forwarding-test",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
    manifest=None,
)
