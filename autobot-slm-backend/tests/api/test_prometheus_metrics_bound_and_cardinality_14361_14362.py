# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Prometheus scrape handler: bounded cardinality and bounded queries (#14361, #14362).

#14361: ``_generate_prometheus_metrics`` used to emit ``trace_id`` as a label on
``autobot_trace_duration_ms`` — a new series per request, retained by Prometheus
forever. Replaced with a real histogram bucketed by duration and labeled only by
``status`` (a small, bounded set). Per-request correlation moved to a structured
log line; it also remains queryable through the existing authenticated
``/performance/traces`` routes.

#14362: ``get_prometheus_metrics`` ran two queries with no ``LIMIT`` — every
``PerformanceTrace`` row from the last hour, and every ``SLODefinition`` row with
the ``enabled`` filter applied in Python after the fetch. Query cost scaled with
table size on every scrape, and the route is intentionally unauthenticated
(#14339 — Prometheus cannot authenticate), so nothing gates how often it is hit.
Fixed with a server-side ``LIMIT``, the ``enabled`` filter pushed into SQL, and a
short TTL cache so duplicate/overlapping scrapes reuse one query.

Strategy for the DB-backed tests (mirrors ``tests/api/test_slm_endpoints_12515.py``):
the root conftest stubs ``sqlalchemy``/``models.database``/``config`` as
MagicMocks for import-time safety, so the real ``sqlalchemy``/``models.database``
modules are loaded once here and swapped in to import ``api.performance`` with
genuine ORM machinery, then driven against a real in-memory SQLite
``AsyncSession`` (aiosqlite). ``config.settings`` stays a MagicMock — its two
new attributes are set directly per test, which exercises exactly what the
handler reads without needing to real-load ``config`` (which touches env files
and network probes at import time).
"""

from __future__ import annotations

import contextlib
import importlib
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("aiosqlite")

_SLM_ROOT = Path(__file__).resolve().parents[2]
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))

_SQLALCHEMY_MODULES = ("sqlalchemy", "sqlalchemy.ext", "sqlalchemy.ext.asyncio", "sqlalchemy.orm")


def _is_sqlalchemy_key(name: str) -> bool:
    return name == "sqlalchemy" or name.startswith("sqlalchemy.")


def _load_real_module(name: str, path: Path):
    """Exec *path* under canonical *name* (registered so relative imports work)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _build_real_modules() -> dict:
    """One-time real sqlalchemy + models.database snapshot.

    Copied from ``test_slm_endpoints_12515.py``: the root conftest stubs these
    as MagicMocks for import-time safety, so the real packages are loaded once
    here and swapped in on demand.
    """
    saved = {name: mod for name, mod in sys.modules.items() if _is_sqlalchemy_key(name)}
    saved["models.database"] = sys.modules.get("models.database")
    for name in list(saved):
        sys.modules.pop(name, None)
    try:
        for name in _SQLALCHEMY_MODULES:
            importlib.import_module(name)
        importlib.import_module("sqlalchemy.dialects.sqlite")
        _load_real_module("models.database", _SLM_ROOT / "models" / "database.py")
        return {name: mod for name, mod in sys.modules.items() if _is_sqlalchemy_key(name)} | {
            "models.database": sys.modules["models.database"],
        }
    finally:
        for name in [n for n in sys.modules if _is_sqlalchemy_key(n)]:
            del sys.modules[name]
        sys.modules.pop("models.database", None)
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)


_REAL_MODULES = _build_real_modules()


@contextlib.contextmanager
def _real_modules_swapped():
    """Temporarily put the real sqlalchemy/models.database modules into sys.modules."""
    saved = {name: sys.modules.get(name) for name in _REAL_MODULES}
    sys.modules.update(_REAL_MODULES)
    try:
        yield
    finally:
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)


def _load_api_module(dotted: str):
    """Import a real ``api.*`` router module under the real-module swap."""
    with _real_modules_swapped():
        sys.modules.pop(dotted, None)
        return importlib.import_module(dotted)


with _real_modules_swapped():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Import under the swap once; the bound references (real PerformanceTrace,
# SLODefinition, select, ...) survive after stubs are restored.
performance = _load_api_module("api.performance")
_db_models = _REAL_MODULES["models.database"]
Base = _db_models.Base
PerformanceTrace = _db_models.PerformanceTrace
SLODefinition = _db_models.SLODefinition


async def _close_session_and_engine(session, engine) -> None:
    """Close *session*, then dispose *engine* — see #13329 for why not __aexit__."""
    try:
        await session.close()
    finally:
        await engine.dispose()


@pytest.fixture
async def db():
    """A fresh real in-memory SQLite AsyncSession per test."""
    with _real_modules_swapped():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        await _close_session_and_engine(session, engine)


@pytest.fixture(autouse=True)
def _metrics_settings(monkeypatch):
    """Reset the two settings this handler reads before every test.

    ``config.settings`` is the root conftest's MagicMock stub; setting
    attributes on it directly is equivalent to the real ``Settings`` fields
    the handler reads (``config.py``: ``metrics_max_traces`` /
    ``metrics_cache_ttl_seconds``), without real-loading ``config`` (which
    touches env files and network probes at import time).
    """
    monkeypatch.setattr(performance.settings, "metrics_max_traces", 100, raising=False)
    monkeypatch.setattr(performance.settings, "metrics_cache_ttl_seconds", 0, raising=False)


def _trace(trace_id: str, status: str, duration_ms: float, age_seconds: int = 0) -> PerformanceTrace:
    return PerformanceTrace(
        trace_id=trace_id,
        name="op",
        status=status,
        duration_ms=duration_ms,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
    )


def _slo(slo_id: str, name: str, enabled: bool) -> SLODefinition:
    return SLODefinition(
        slo_id=slo_id,
        name=name,
        target_percent=99.9,
        metric_type="latency",
        threshold_value=100.0,
        threshold_unit="ms",
        enabled=enabled,
    )


def _series_label_keys(text: str) -> set[str]:
    """Every distinct label key used across the trace-duration series."""
    keys: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("autobot_trace_duration_ms"):
            continue
        match = re.search(r"\{([^}]*)\}", line)
        if not match:
            continue
        for pair in match.group(1).split(","):
            keys.add(pair.split("=", 1)[0])
    return keys


def _series_lines(text: str) -> list[str]:
    """Every trace-duration series line, with the sample value stripped.

    Stripping the value isolates the *shape* (metric name + labels) so two
    renders with different durations but the same status set compare equal.
    """
    lines = []
    for line in text.splitlines():
        if line.startswith("autobot_trace_duration_ms") and not line.startswith("#"):
            name_and_labels = line.rsplit(" ", 1)[0]
            lines.append(name_and_labels)
    return lines


# ---------------------------------------------------------------------------
# #14361 — cardinality
# ---------------------------------------------------------------------------


def test_series_shape_does_not_scale_with_trace_count():
    """Ten traces or five hundred: the emitted series set must be identical.

    Before the fix, one line was emitted per trace (labeled by trace_id), so
    this would fail outright — series count scaled 1:1 with trace count.
    """
    statuses = ("ok", "error")

    def build(n: int) -> list[PerformanceTrace]:
        return [_trace(f"trace-{i}", statuses[i % 2], float(i + 1)) for i in range(n)]

    small_series = set(_series_lines(performance._generate_prometheus_metrics(build(5), [])))
    large_series = set(_series_lines(performance._generate_prometheus_metrics(build(500), [])))

    assert small_series, "no series were emitted at all — the histogram generator regressed"
    assert small_series == large_series, (
        "the emitted series shape changed with trace count — cardinality must be a "
        "function of (buckets x statuses) only (#14361)"
    )


def test_no_per_request_identifier_in_the_label_set():
    """A realistic mix of distinct requests must not leak a per-request label.

    Asserts on the label *keys* — not merely that one particular string is
    absent — because the invariant is "no per-request identifier ever
    becomes a label", not "this specific trace_id string never appears".
    """
    statuses = ("ok", "error", "timeout")
    traces = [_trace(f"req-{i:04d}", statuses[i % 3], float(1 + (i * 37) % 20000)) for i in range(250)]

    text = performance._generate_prometheus_metrics(traces, [])

    label_keys = _series_label_keys(text)
    assert label_keys, "no labels were emitted at all — the histogram generator regressed"
    assert label_keys <= {"status", "le"}, f"a per-request identifier leaked into the label set: {label_keys}"

    for trace in traces:
        assert trace.trace_id not in text, f"{trace.trace_id} appears verbatim in the scrape output"


def test_histogram_is_a_real_histogram_not_one_line_per_trace():
    """bucket/sum/count must all be present — the old shape had none of them."""
    traces = [_trace("t1", "ok", 5.0), _trace("t2", "ok", 15000.0)]
    text = performance._generate_prometheus_metrics(traces, [])

    assert 'autobot_trace_duration_ms_bucket{status="ok",le="+Inf"} 2' in text
    assert 'autobot_trace_duration_ms_count{status="ok"} 2' in text
    assert 'autobot_trace_duration_ms_sum{status="ok"} 15005.0' in text


# ---------------------------------------------------------------------------
# #14362 — bounded queries
# ---------------------------------------------------------------------------


async def test_traces_query_is_bounded_regardless_of_table_size(db, monkeypatch):
    """The DB actually enforces the bound — a real sqlite table, not a stub
    that echoes back whatever list it was handed."""
    monkeypatch.setattr(performance.settings, "metrics_max_traces", 3, raising=False)

    for i in range(10):
        db.add(_trace(f"trace-{i}", "ok", float(i)))
    await db.commit()

    text = await performance._get_prometheus_metrics_text(db, cache=performance._MetricsCache())

    assert 'autobot_trace_duration_ms_count{status="ok"} 3' in text, (
        "expected the query to be capped at metrics_max_traces=3 even though 10 rows "
        f"exist. Full text:\n{text}"
    )


async def test_disabled_slo_never_reaches_the_output(db):
    """The ``enabled`` filter must be enforced by the query, not a Python loop.

    ``_generate_prometheus_metrics`` no longer filters by ``enabled`` at all
    (#14362 pushes that into SQL) — so if the query regresses back to
    ``select(SLODefinition)`` with no WHERE clause, the disabled SLO leaks
    into the output and this goes red.
    """
    db.add(_slo("slo-enabled", "Enabled SLO", enabled=True))
    db.add(_slo("slo-disabled", "Disabled SLO", enabled=False))
    await db.commit()

    text = await performance._get_prometheus_metrics_text(db, cache=performance._MetricsCache())

    assert "slo-enabled" in text
    assert "slo-disabled" not in text


async def test_repeated_calls_within_the_ttl_do_not_requery(db, monkeypatch):
    """A second call inside the TTL must not touch the database at all."""
    monkeypatch.setattr(performance.settings, "metrics_cache_ttl_seconds", 60.0, raising=False)

    db.add(_trace("trace-1", "ok", 5.0))
    await db.commit()

    calls = {"n": 0}
    real_execute = db.execute

    async def counting_execute(stmt):
        calls["n"] += 1
        return await real_execute(stmt)

    monkeypatch.setattr(db, "execute", counting_execute)

    cache = performance._MetricsCache()
    first = await performance._get_prometheus_metrics_text(db, cache=cache)
    assert calls["n"] == 2, f"expected exactly 2 queries (traces + SLOs) on the first call, got {calls['n']}"

    second = await performance._get_prometheus_metrics_text(db, cache=cache)
    assert first == second
    assert calls["n"] == 2, f"a call inside the TTL re-queried the database: {calls['n']} total calls"


async def test_the_cache_expires_and_requeries_after_the_ttl(db, monkeypatch):
    """The TTL is not infinite — a genuine scrape after it elapses sees fresh data."""
    monkeypatch.setattr(performance.settings, "metrics_cache_ttl_seconds", 1.0, raising=False)

    db.add(_trace("trace-1", "ok", 5.0))
    await db.commit()

    fake_clock = [1_000.0]
    monkeypatch.setattr(performance.time, "monotonic", lambda: fake_clock[0])

    calls = {"n": 0}
    real_execute = db.execute

    async def counting_execute(stmt):
        calls["n"] += 1
        return await real_execute(stmt)

    monkeypatch.setattr(db, "execute", counting_execute)

    cache = performance._MetricsCache()
    await performance._get_prometheus_metrics_text(db, cache=cache)
    assert calls["n"] == 2

    fake_clock[0] += 2.0  # past the 1s TTL
    await performance._get_prometheus_metrics_text(db, cache=cache)
    assert calls["n"] == 4, f"expected a fresh pair of queries once the TTL elapsed, got {calls['n']} total calls"
