"""TCP 健康探测：监听段 + 目标段。

相比 Test-NetConnection（3~5 秒/条），这里使用 asyncio 并发 + 1.5 秒超时，
5 条规则可在 2 秒内完成。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from ..core.config import settings
from ..schemas.rule import HealthInfo

log = logging.getLogger(__name__)

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(max(1, settings.probe_concurrency))
    return _semaphore


async def tcp_probe(host: str, port: int, timeout: float) -> tuple[bool, float | None, str | None]:
    """返回 (是否连通, 延迟毫秒, 错误信息)。"""
    started = time.perf_counter()
    writer = None
    try:
        async with _get_semaphore():
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=timeout
            )
        latency = (time.perf_counter() - started) * 1000
        return True, latency, None
    except asyncio.TimeoutError:
        return False, None, f"连接超时（>{timeout:g}s）"
    except ConnectionRefusedError:
        return False, None, "连接被拒绝（端口未监听）"
    except OSError as exc:
        return False, None, f"连接失败：{exc.strerror or exc}"
    finally:
        if writer is not None:
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()


async def probe_rule(rule: dict, *, timeout: float | None = None) -> HealthInfo:
    """对一个 portproxy 规则做双段探测。"""
    timeout = timeout or settings.probe_timeout
    listen_ok, listen_ms, listen_err = await tcp_probe(
        rule["listen_address"], rule["listen_port"], timeout
    )
    target_ok, target_ms, target_err = await tcp_probe(
        rule["connect_address"], rule["connect_port"], timeout
    )

    if not listen_ok:
        state = "down"
    elif target_ok:
        state = "healthy"
    else:
        state = "half-open"

    error = None
    if listen_err:
        error = f"监听端：{listen_err}"
    if target_err:
        error = f"{error}；目标端：{target_err}" if error else f"目标端：{target_err}"

    return HealthInfo(
        state=state,  # type: ignore[arg-type]
        listen_ok=listen_ok,
        target_ok=target_ok,
        listen_latency_ms=round(listen_ms, 1) if listen_ms is not None else None,
        target_latency_ms=round(target_ms, 1) if target_ms is not None else None,
        checked_at=None,
        error=error,
    )


async def probe_many(rules: list[dict], *, timeout: float | None = None) -> dict[str, HealthInfo]:
    started = time.perf_counter()
    results = await asyncio.gather(
        *(probe_rule(rule, timeout=timeout) for rule in rules),
        return_exceptions=True,
    )

    from datetime import datetime

    now = datetime.now().astimezone()
    out: dict[str, HealthInfo] = {}
    for rule, result in zip(rules, results, strict=False):
        if isinstance(result, BaseException):
            log.exception("探测异常 %s", rule.get("id"), exc_info=result)
            out[rule["id"]] = HealthInfo(state="unknown", checked_at=now, error=str(result))
        else:
            result.checked_at = now
            out[rule["id"]] = result

    elapsed = (time.perf_counter() - started) * 1000
    log.info("探测 %d 条规则耗时 %.0f ms", len(rules), elapsed)
    return out
