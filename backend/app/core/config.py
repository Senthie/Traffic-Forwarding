"""应用级配置。

所有路径与端口均可通过环境变量覆盖，便于打包后复用同一份代码。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "TrafficForwarding"
APP_VERSION = "0.2.0"

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _resolve_static_dir() -> Path:
    """开发 / PyInstaller 打包两种布局都能找到前端产物。"""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidates.append(base / "app" / "static")
        candidates.append(base / "backend" / "app" / "static")
    candidates.append(BACKEND_DIR / "app" / "static")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


STATIC_DIR = _resolve_static_dir()


def _default_data_dir() -> Path:
    """打包后写 LOCALAPPDATA，开发时写到 backend/data。"""
    if env := os.environ.get("TFM_DATA_DIR"):
        return Path(env)
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME
    return BACKEND_DIR / "data"


@dataclass(frozen=True)
class Settings:
    host: str = field(default_factory=lambda: os.environ.get("TFM_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.environ.get("TFM_PORT", "8000")))
    data_dir: Path = field(default_factory=_default_data_dir)
    probe_timeout: float = field(
        default_factory=lambda: float(os.environ.get("TFM_PROBE_TIMEOUT", "1.5"))
    )
    probe_concurrency: int = field(
        default_factory=lambda: int(os.environ.get("TFM_PROBE_CONCURRENCY", "32"))
    )
    command_timeout: float = field(
        default_factory=lambda: float(os.environ.get("TFM_COMMAND_TIMEOUT", "25"))
    )
    dev_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
    )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"


settings = Settings()
