# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SLM login needs nothing from the main app at request time (#21153, #10200, ADR-012).

The SLM authenticates against its own ``users`` table (the copy the main app keeps current
through ``/internal/person-copy``). Here a real in-memory database holds an admin, the one
outbound client the SLM has for the main app is made to raise a connection error, and the
login lookup still succeeds. A source guard pins that the login modules never import that
client, so a later request-time call would fail this file rather than a user.
"""

import ast
import secrets
import sys
import uuid
from pathlib import Path

import pytest

from autobot_shared.user_management.base_service import TenantContext

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from _real_orm_import import import_modules_with_real_orm, real_modules_swapped  # noqa: E402

_SLM = Path(__file__).resolve().parents[2]

# This directory's conftest stands in for sqlalchemy and the SLM's ``user_management`` package; the real ones are the
# system under test. The shared helper imports them once, for real, and the references are held for the whole module
# (SQLAlchemy's class registry is weak, so a dropped ``Organization`` would stop ``Role`` resolving it).
_LOADED = import_modules_with_real_orm(
    import_names=(
        "user_management",
        "user_management.models",
        "user_management.models.api_key",
        "user_management.models.user",
        "autobot_shared.user_management.user_service",
        "services.main_backend_client",
    )
)
User = _LOADED[3].User
UserService = _LOADED[-2].UserService
main_backend_client = _LOADED[-1]

with real_modules_swapped():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.ext.compiler import compiles


# the JSONB class the models were declared with (a second import of the dialect would be a different class)
@compiles(type(User.metadata.tables["organizations"].c.settings.type), "sqlite")
def _jsonb_as_json(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


class _SlmUserService(UserService):
    user_model = User


@pytest.fixture()
async def session():
    # the conftest stubs sqlalchemy; the dialect plugin and lazy ORM imports need the real one for the whole test
    with real_modules_swapped():
        engine = create_async_engine("sqlite+aiosqlite://")  # canonical: ignore py-adhoc-db-engine
        async with engine.begin() as conn:
            await conn.run_sync(User.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine
        async with maker() as db:
            yield db
        await engine.dispose()


_PASSWORD = secrets.token_urlsafe(16)


async def _seed_admin(db):
    svc = _SlmUserService(db, TenantContext(is_platform_admin=True))
    db.add(
        User(
            id=uuid.uuid4(),
            username="admin",
            email="admin@example.test",
            password_hash=svc.hash_password(_PASSWORD),
            is_active=True,
            is_platform_admin=True,
        )
    )
    await db.commit()
    return svc


@pytest.fixture()
def main_app_down(monkeypatch):
    """The SLM's one client for the main app, made to fail; ``awaited`` records every call that reaches it."""
    awaited = []

    async def _down(*args, **kwargs):
        awaited.append((args, kwargs))
        raise ConnectionError("main app unreachable")

    monkeypatch.setattr(main_backend_client, "call_main_backend", _down)
    return awaited


@pytest.mark.asyncio
async def test_login_works_from_the_local_copy_with_the_main_app_unreachable(session, main_app_down):
    svc = await _seed_admin(session)
    user = await svc.authenticate("admin", _PASSWORD)
    by_email = await svc.authenticate("admin@example.test", _PASSWORD)
    assert user is not None and user.username == "admin" and user.is_platform_admin
    assert by_email is not None and by_email.id == user.id
    assert main_app_down == []


@pytest.mark.asyncio
async def test_a_wrong_password_is_refused_not_an_error_with_the_main_app_unreachable(session, main_app_down):
    svc = await _seed_admin(session)
    assert await svc.authenticate("admin", _PASSWORD + "x") is None
    assert main_app_down == []


_LOGIN_PATH = (
    "api/auth.py",
    "api/login_rate_limit.py",
    "services/auth.py",
    "services/token_denylist.py",
    "user_management/services/__init__.py",
)
_FORBIDDEN = ("main_backend_client", "httpx", "aiohttp", "requests", "urllib3")


@pytest.mark.parametrize("rel", _LOGIN_PATH)
def test_the_login_path_imports_no_client_for_the_main_app(rel):
    tree = ast.parse((_SLM / rel).read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
            imported += [a.name for a in node.names]
    bad = [m for m in imported if any(m == f or m.startswith(f + ".") or m.endswith("." + f) for f in _FORBIDDEN)]
    assert not bad, f"{rel} reaches the main app at request time: {bad}"
