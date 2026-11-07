# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The rollback's fleet verification, against the real ``Node`` table in sqlite (#20214).

The suite stubs sqlalchemy and ``models.database``; a query is only worth testing against the real
ones, so this file loads them for the length of each test (the harness of
``tests/api/test_replication_session_lifetime_15549.py``, which carries the full explanation).
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

from services import code_rollback as cr
from services.rollback_commits import CommitInfo

_SLM_ROOT = Path(__file__).resolve().parents[1]
TARGET = CommitInfo(commit="b" * 40, date="2026-10-01T10:00:00+00:00", subject="an earlier change")


def _is_sqlalchemy_key(name: str) -> bool:
    return name == "sqlalchemy" or name.startswith("sqlalchemy.")


def _build_real_modules() -> dict:
    saved = {n: m for n, m in sys.modules.items() if _is_sqlalchemy_key(n)}
    saved.update({n: sys.modules.get(n) for n in ("models.database", "models.schemas")})
    for name in list(saved):
        sys.modules.pop(name, None)
    try:
        for name in ("sqlalchemy", "sqlalchemy.ext", "sqlalchemy.ext.asyncio", "sqlalchemy.orm"):
            importlib.import_module(name)
        importlib.import_module("sqlalchemy.dialects.sqlite")
        spec = importlib.util.spec_from_file_location("models.database", _SLM_ROOT / "models" / "database.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["models.database"] = module
        spec.loader.exec_module(module)
        return {n: m for n, m in sys.modules.items() if _is_sqlalchemy_key(n)} | {"models.database": module}
    finally:
        for name in [n for n in sys.modules if _is_sqlalchemy_key(n)]:
            del sys.modules[name]
        sys.modules.pop("models.database", None)
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod


_REAL = _build_real_modules()


@contextlib.contextmanager
def _real_modules_swapped():
    saved = {name: sys.modules.get(name) for name in _REAL}
    sys.modules.update(_REAL)
    try:
        yield
    finally:
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)


class _DbService:
    def __init__(self, maker):
        self._maker = maker

    @contextlib.asynccontextmanager
    async def session(self):
        async with self._maker() as session:
            yield session


async def _verify(tmp_path, versions: dict) -> SimpleNamespace:
    job = SimpleNamespace(status="completed", failure_reason=None)
    with _real_modules_swapped():
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from models.database import Base, Node

        url = f"sqlite+aiosqlite:///{tmp_path / 'nodes.db'}"
        engine = create_async_engine(url)  # canonical: ignore py-adhoc-db-engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine
        async with maker() as session:
            session.add_all(
                Node(node_id=n, hostname=n, ip_address=f"10.0.0.{i}", code_version=v)
                for i, (n, v) in enumerate(versions.items(), 1)
            )
            await session.commit()
        try:
            await cr._verify_fleet_at_target(job, _DbService(maker), TARGET)
        finally:
            await engine.dispose()
    return job


async def test_a_node_off_the_target_fails_the_job(tmp_path):
    job = await _verify(tmp_path, {"n1": "x" * 40, "n2": TARGET.commit})
    assert job.status == "failed" and "1 node(s) are not confirmed on" in job.failure_reason


async def test_a_node_whose_version_was_never_written_is_not_confirmed(tmp_path):
    job = await _verify(tmp_path, {"n1": None, "n2": TARGET.commit})
    assert job.status == "failed" and "1 node(s) are not confirmed on" in job.failure_reason


async def test_every_node_on_the_target_keeps_the_job_completed(tmp_path):
    job = await _verify(tmp_path, {"n1": TARGET.commit, "n2": TARGET.commit})
    assert job.status == "completed"
