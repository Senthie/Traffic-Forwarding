"""FastAPI 入口。

开发：uvicorn app.main:app --reload --port 8000
生产：由 launcher/app.py 在后台线程启动，并托管前端静态资源。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .api import routes_firewall, routes_logs, routes_probe, routes_rules, routes_system
from .core.config import APP_NAME, APP_VERSION, STATIC_DIR, settings
from .core.elevation import is_admin
from .services.metadata import Store
from .services.rules import RuleError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s - %(message)s",
)
log = logging.getLogger("traffic_forwarding")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Store.instance()
    log.info(
        "%s %s 启动 | 管理员=%s | 数据目录=%s | 静态资源=%s",
        APP_NAME,
        APP_VERSION,
        is_admin(),
        settings.data_dir,
        STATIC_DIR if STATIC_DIR.exists() else "(未构建)",
    )
    yield


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Windows 端口转发 / 防火墙规则管理",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.dev_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RuleError)
async def handle_rule_error(request: Request, exc: RuleError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"detail": str(exc), "ok": False})


app.include_router(routes_rules.router, prefix="/api")
app.include_router(routes_system.router, prefix="/api")
app.include_router(routes_probe.router, prefix="/api")
app.include_router(routes_firewall.router, prefix="/api")
app.include_router(routes_logs.router, prefix="/api")


@app.get("/api/health", tags=["system"])
async def health() -> dict:
    return {
        "ok": True,
        "version": APP_VERSION,
        "admin": is_admin(),
        "has_static": STATIC_DIR.exists(),
    }


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str) -> FileResponse:
    """托管构建后的前端；非静态文件一律返回 index.html（SPA 路由）。"""
    index = STATIC_DIR / "index.html"
    if not STATIC_DIR.exists():
        return JSONResponse(
            status_code=404,
            content={
                "detail": "前端尚未构建。开发时请访问 http://127.0.0.1:5173，"
                "或先执行 npm run build 并复制到 backend/app/static。"
            },
        )

    root = STATIC_DIR.resolve()
    candidate = (STATIC_DIR / full_path).resolve()
    if full_path and candidate.is_file() and root in candidate.parents:
        return FileResponse(candidate)
    return FileResponse(index)
