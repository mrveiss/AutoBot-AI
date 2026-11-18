# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A role's active credentials reach the agent run as env vars (#20533).

Covers the name policy, resolution through the secrets manager (active only),
the audited refusal, redaction in ``LLC_INVOKE_CONTEXT``, the child env, and the
scheduler hook that attaches them.
"""

from __future__ import annotations

import json
import logging
import uuid
from types import SimpleNamespace
from typing import AsyncIterator
from unittest.mock import patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.adapters.process_adapter import LLCProcessAdapter, _build_minimal_env
from llc.adapters.subprocess_support import (
    inject_agent_credentials,
    serialize_invoke_context,
)
from llc.credential_env import (
    REFUSED_BAD_FORMAT,
    REFUSED_PROTECTED,
    ROLE_CREDENTIALS_KEY,
    env_name_refusal,
)
from llc.models.activity import LLCActivityLog
from llc.models.enums import MembershipRole, RoleHolderType
from llc.models.membership import LLCCompanyMembership
from llc.models.role_assignment import LLCRoleAssignment
from llc.models.role_credential import LLCRoleCredential
from llc.models.secret import LLCSecret
from llc.scheduler.role_credentials import attach_role_credentials
from llc.services.role import RoleService
from llc.services.role_assignment import RoleAssignmentService
from llc.services.role_credential import RoleCredentialService
from llc.services.role_credential_env import REFUSED_EVENT, RoleCredentialEnvResolver
from llc.services.secret import SecretService
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base
from user_management.models.role import Role

_ADMIN = uuid.uuid4()
_VALUE = "s3cr3t-value-20533-XYZ"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _master_key(monkeypatch):  # noqa: ANN001
    monkeypatch.setenv("LLC_SECRET_MASTER_KEY", "test-master-key-20533")


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    tables = [
        LLCActivityLog.__table__,
        Role.__table__,
        LLCCompanyMembership.__table__,
        LLCRoleAssignment.__table__,
        LLCRoleCredential.__table__,
        LLCSecret.__table__,
    ]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


async def _world(factory, secrets: dict[str, str], *, revoke: tuple[str, ...] = ()):  # noqa: ANN001
    """A company, an agent holding one role, and *secrets* attached to that role."""
    company, agent = uuid.uuid4(), uuid.uuid4()
    async with factory() as s:
        s.add(
            LLCCompanyMembership(
                id=uuid.uuid4(),
                company_id=company,
                user_id=_ADMIN,
                role=MembershipRole.ADMIN.value,
            )
        )
        await s.commit()
        role = await RoleService().create(s, company_id=company, name="SRE", actor_user_id=_ADMIN)
        await RoleAssignmentService().assign(
            s,
            company_id=company,
            role_id=role.id,
            holder_type=RoleHolderType.AGENT,
            holder_id=agent,
            actor_user_id=_ADMIN,
        )
        for name, value in secrets.items():
            row = await SecretService().set(s, str(company), name, value, actor=str(_ADMIN))
            await RoleCredentialService().attach(
                s,
                company_id=company,
                role_id=role.id,
                secret_id=row.id,
                actor_user_id=_ADMIN,
            )
        for name in revoke:
            await SecretService().revoke(s, str(company), name, actor=str(_ADMIN))
        await s.commit()
    return company, agent


async def _resolve(factory, company, agent):  # noqa: ANN001
    async with factory() as s:
        out = await RoleCredentialEnvResolver().resolve_for_agent(s, company, agent)
        await s.commit()
    return out


@pytest.mark.parametrize(
    "name",
    [
        "PATH",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "AUTOBOT_LLC_API_KEY",
        "LLC_INVOKE_CONTEXT",
        "HOME",
        "SHELL",
        "NODE_OPTIONS",
        "BASH_ENV",
        "GIT_SSH_COMMAND",
        "ANTHROPIC_API_KEY",
        "DYLD_INSERT_LIBRARIES",
    ],
)
def test_protected_names_are_refused(name):  # noqa: ANN001
    assert env_name_refusal(name) == REFUSED_PROTECTED


@pytest.mark.parametrize(
    "name",
    ["stripe-key", "lower", "1ABC", "A B", "", "A=B", "X" * 129, "KEY\n", None, 5],
)
def test_malformed_names_are_refused(name):  # noqa: ANN001
    assert env_name_refusal(name) == REFUSED_BAD_FORMAT


@pytest.mark.parametrize("name", ["STRIPE_API_KEY", "GITHUB_TOKEN", "A", "DB_PASSWORD_2"])
def test_ordinary_names_are_accepted(name):  # noqa: ANN001
    assert env_name_refusal(name) is None


@pytest.mark.asyncio
async def test_active_role_credential_value_is_resolved(factory):  # noqa: ANN001
    company, agent = await _world(factory, {"STRIPE_API_KEY": _VALUE})
    assert await _resolve(factory, company, agent) == {"STRIPE_API_KEY": _VALUE}


@pytest.mark.asyncio
async def test_revoked_credential_is_not_resolved(factory):  # noqa: ANN001
    company, agent = await _world(factory, {"KEEP_KEY": "a", "GONE_KEY": "b"}, revoke=("GONE_KEY",))
    assert await _resolve(factory, company, agent) == {"KEEP_KEY": "a"}


@pytest.mark.asyncio
async def test_agent_without_the_role_gets_nothing(factory):  # noqa: ANN001
    company, _ = await _world(factory, {"STRIPE_API_KEY": _VALUE})
    assert await _resolve(factory, company, uuid.uuid4()) == {}


@pytest.mark.asyncio
async def test_refused_name_is_audited_not_renamed_and_never_logged(factory, caplog):  # noqa: ANN001
    company, agent = await _world(factory, {"PATH": _VALUE, "bad-name": _VALUE, "OK_KEY": "ok"})
    with caplog.at_level(logging.DEBUG):
        resolved = await _resolve(factory, company, agent)
    assert resolved == {"OK_KEY": "ok"}
    async with factory() as s:
        rows = (
            (await s.execute(sa.select(LLCActivityLog).where(LLCActivityLog.action == REFUSED_EVENT))).scalars().all()
        )
    reasons = sorted(r.after_state["reason"] for r in rows)
    assert reasons == [REFUSED_BAD_FORMAT, REFUSED_PROTECTED]
    blob = caplog.text + json.dumps([r.after_state for r in rows])
    assert _VALUE not in blob and "bad-name" not in blob


def test_serialized_context_masks_values_but_keeps_names():
    ctx = {"task_id": "t1", ROLE_CREDENTIALS_KEY: {"STRIPE_API_KEY": _VALUE}}
    out = serialize_invoke_context(ctx)
    assert _VALUE not in out and "STRIPE_API_KEY" in out
    assert ctx[ROLE_CREDENTIALS_KEY]["STRIPE_API_KEY"] == _VALUE, "the caller's context must not be mutated"


def test_child_env_receives_values_and_context_blob_does_not():
    ctx = {"agent_api_key": "run-key", ROLE_CREDENTIALS_KEY: {"STRIPE_API_KEY": _VALUE}}  # pragma: allowlist secret
    env = _build_minimal_env({}, ctx)
    assert env["STRIPE_API_KEY"] == _VALUE
    assert env["AUTOBOT_LLC_API_KEY"] == "run-key"  # pragma: allowlist secret
    assert _VALUE not in env["LLC_INVOKE_CONTEXT"] and "run-key" not in env["LLC_INVOKE_CONTEXT"]


def test_injection_rechecks_names_and_cannot_override_protected_vars():
    env = {"PATH": "/usr/bin", "AUTOBOT_LLC_API_KEY": "real"}  # pragma: allowlist secret
    ctx = {
        "agent_api_key": "real",  # pragma: allowlist secret
        ROLE_CREDENTIALS_KEY: {  # pragma: allowlist secret
            "PATH": "/evil",
            "AUTOBOT_LLC_API_KEY": "x",
            "LD_PRELOAD": "y",
            "OK": "1",
        },
    }
    inject_agent_credentials(env, ctx)
    assert env["PATH"] == "/usr/bin" and env["AUTOBOT_LLC_API_KEY"] == "real"  # pragma: allowlist secret
    assert "LD_PRELOAD" not in env and env["OK"] == "1"


@pytest.mark.asyncio
async def test_scheduler_hook_attaches_for_subprocess_adapters_only(factory):  # noqa: ANN001
    company, agent = await _world(factory, {"STRIPE_API_KEY": _VALUE})
    agent_row = {"agent_id": str(agent), "company_id": str(company)}
    with patch("llc.scheduler.role_credentials.get_async_session_factory", return_value=factory):
        ctx = {"company_id": str(company)}
        await attach_role_credentials(LLCProcessAdapter(), agent_row, ctx)
        assert ctx[ROLE_CREDENTIALS_KEY] == {"STRIPE_API_KEY": _VALUE}
        http_ctx = {"company_id": str(company)}
        await attach_role_credentials(SimpleNamespace(), agent_row, http_ctx)  # e.g. an HTTP adapter
        assert ROLE_CREDENTIALS_KEY not in http_ctx
