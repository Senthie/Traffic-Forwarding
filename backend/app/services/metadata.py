"""SQLite 元数据：规则名称/备注/审计日志/设置。

portproxy 本身没有名称概念，这部分信息只能由应用自己维护。
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from ..core.config import settings

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS rule_meta (
    rule_id            TEXT PRIMARY KEY,
    name               TEXT,
    note               TEXT,
    firewall_rule_name TEXT,
    profiles           TEXT DEFAULT 'Any',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    action     TEXT NOT NULL,
    rule_id    TEXT,
    detail     TEXT,
    command    TEXT,
    returncode INTEGER,
    output     TEXT,
    ok         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC);
"""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Store:
    _instance: "Store | None" = None
    _instance_lock = threading.Lock()

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(SCHEMA)
        log.info("元数据数据库：%s", path)

    @classmethod
    def instance(cls) -> "Store":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = Store(settings.db_path)
            return cls._instance

    # ---------- 规则元数据 ----------

    def all_meta(self) -> dict[str, dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM rule_meta").fetchall()
        return {row["rule_id"]: dict(row) for row in rows}

    def get_meta(self, rule_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM rule_meta WHERE rule_id = ?", (rule_id,)
            ).fetchone()
        return dict(row) if row else None

    def upsert_meta(
        self,
        rule_id: str,
        *,
        name: str | None,
        note: str | None,
        firewall_rule_name: str | None,
        profiles: str = "Any",
    ) -> None:
        now = _now()
        with self._lock, self._conn:
            exists = self._conn.execute(
                "SELECT 1 FROM rule_meta WHERE rule_id = ?", (rule_id,)
            ).fetchone()
            if exists:
                self._conn.execute(
                    "UPDATE rule_meta SET name=?, note=?, firewall_rule_name=?, "
                    "profiles=?, updated_at=? WHERE rule_id=?",
                    (name, note, firewall_rule_name, profiles, now, rule_id),
                )
            else:
                self._conn.execute(
                    "INSERT INTO rule_meta "
                    "(rule_id, name, note, firewall_rule_name, profiles, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (rule_id, name, note, firewall_rule_name, profiles, now, now),
                )

    def delete_meta(self, rule_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM rule_meta WHERE rule_id = ?", (rule_id,))

    # ---------- 审计日志 ----------

    def log(
        self,
        action: str,
        *,
        rule_id: str | None = None,
        detail: str | None = None,
        command: str | None = None,
        returncode: int | None = None,
        output: str | None = None,
        ok: bool = True,
    ) -> None:
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "INSERT INTO audit_log (ts, action, rule_id, detail, command, returncode, output, ok) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (_now(), action, rule_id, detail, command, returncode, output, 1 if ok else 0),
                )
        except sqlite3.Error:  # 审计失败不应影响主流程
            log.exception("写入审计日志失败")

    def list_logs(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["ok"] = bool(item.get("ok"))
            result.append(item)
        return result

    # ---------- 设置 ----------

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
