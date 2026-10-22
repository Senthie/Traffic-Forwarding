# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

构建：uv run pyinstaller --noconfirm --clean launcher/traffic_forwarding.spec
产物：dist/traffic-forwarding.exe（onefile + requireAdministrator manifest）
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
        (str(BACKEND / "pyproject.toml"), "backend"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        # 入口脚本改名为 main.py 后仍需显式声明后端包，
        # 避免 PyInstaller 静态分析漏掉（历史上曾因入口名 app.py 与 app 包冲突而漏包）
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
        # pywebview 在运行时才 import，静态分析看不到
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
    name="traffic-forwarding",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "launcher" / "app.ico"),
    manifest=str(ROOT / "launcher" / "app.manifest"),
    # PyInstaller 6 必须显式指定 uac_admin=True，
    # 否则即使传了自定义 manifest，也会被合并成 asInvoker（启动时不会弹 UAC）
    uac_admin=True,
)
