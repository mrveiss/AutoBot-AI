# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Both services' REAL route dependencies answer one (role, DB grants, org, permission) table alike (#18263, #18264).

Each service is imported in its own subprocess (they reuse top-level package names).
The probe builds a FastAPI app whose routes depend on that service's own
``require_permission`` -- the SLM's ``services.auth``, the backend's ``auth_rbac`` --
and calls them over HTTP with a bearer token that SAME service mints
(``auth_service.create_access_token`` / ``AuthenticationMiddleware.create_jwt_token``).
So the caller is resolved by each service's own authentication (``get_current_user``
/ ``get_user_from_request``), not injected; a service that dropped ``user_id`` or
``org_id`` from its caller, read the role differently, or stopped wiring the shared
gate would answer differently here. Only the deny-audit writer and the DB grant
loader are stood in for; the loader's answer depends on the org it is asked for.
So this proves token decoding and gate wiring agree, NOT each service's DB grant path
(middleware -> UserService -> scoped query); that is #18363. The shared query itself
is exercised on real SQLite in ``role_permission_query_test``.

API-key narrowing is not in this table: the backend accepts no user API keys
(``api_key_scopes_are_enforced_16040_test``), so there is no backend row to compare.
"""

import json
import os
import subprocess  # nosec B404  # runs this repo's own probe under the test interpreter
import sys

import pytest
from repo_tests._paths import repo_root

_ROOT = repo_root()

_COMMON = r"""
import json, sys
from unittest.mock import AsyncMock, patch
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from autobot_shared.auth import permission_gate
from autobot_shared.auth.permissions import Permission, Role

ORG = "00000000-0000-0000-0000-0000000000d4"
USER = "00000000-0000-0000-0000-0000000000c3"
audited = []

async def _audit(request, caller, permissions):
    audited.append(permissions)

async def _db(user_id, org_id):
    # A system-role grant everywhere; a company-role grant only inside ORG (#18338).
    return {"knowledge.write"} | ({"admin.system"} if str(org_id) == ORG else set())

def run(binding, mint):
    gate = binding._permission_gate
    gate._wire_rbac, gate._load_db_names = (lambda: None), _db
    permission_gate.audit_permission_denied = _audit
    app = FastAPI()
    for p in Permission:
        app.add_api_route(f"/p/{p.value}", lambda: {}, dependencies=[Depends(binding.require_permission(p))])
    client, out = TestClient(app), {}
    for role in [r.value for r in Role] + ["Admin", "bogus"]:
        for uname, uid in (("no-db", None), ("db", USER)):
            for oname, org in (("no-org", None), ("org", ORG)):
                headers = {"Authorization": "Bearer " + mint(role, uid, org)}
                for p in Permission:
                    status = client.get(f"/p/{p.value}", headers=headers).status_code
                    out[f"{role}|{uname}|{oname}|{p.value}"] = "allow" if status == 200 else str(status)
    out["__audited__"] = len(audited)
    print("PARITY:" + json.dumps(out, sort_keys=True))
"""

_SLM = r"""
import services.auth as binding
patch.object(binding, "is_jti_revoked", AsyncMock(return_value=False)).start()
patch.object(binding, "is_token_revoked_by_password_change", AsyncMock(return_value=False)).start()

import time

def mint(role, user_id, org_id):
    # iat backdated: jwt_core verifies with zero leeway, and a backward clock step refuses
    # a fresh token as not-yet-valid (#18347). The probe measures the gate, not the clock.
    claims = {"sub": "parity", "role": role, "admin": False, "iat": int(time.time()) - 30}
    claims.update({k: v for k, v in (("user_id", user_id), ("org_id", org_id)) if v})
    return binding.auth_service.create_access_token(data=claims)

run(binding, mint)
"""

_BACKEND = r"""
import datetime as _datetime
import types
import auth_middleware
import auth_rbac as binding
from auth_middleware import get_auth_middleware
middleware = get_auth_middleware()

class _Backdated(_datetime.datetime):
    # create_jwt_token stamps iat from datetime.now(); backdated for the same reason as the SLM (#18347).
    @classmethod
    def now(cls, tz=None):
        return _datetime.datetime.now(tz) - _datetime.timedelta(seconds=30)

auth_middleware.datetime = types.SimpleNamespace(datetime=_Backdated, timezone=_datetime.timezone, timedelta=_datetime.timedelta)
middleware.enable_auth = True  # the probe measures the gate, not the auth-disabled shortcut

def mint(role, user_id, org_id):
    data = {"username": "parity", "role": role}
    data.update({k: v for k, v in (("user_id", user_id), ("org_id", org_id)) if v})
    return middleware.create_jwt_token(data)

run(binding, mint)
"""

_SERVICES = {"backend": ("autobot-backend", _BACKEND), "slm": ("autobot-slm-backend", _SLM)}


def _probe(service: str) -> dict:
    directory, body = _SERVICES[service]
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join((str(_ROOT), str(_ROOT / directory))),
        # The SLM config writes generated keys to disk when these are unset.
        SLM_SECRET_KEY="parity-probe-secret-key-0123456789abcdef",  # pragma: allowlist secret
        SLM_ENCRYPTION_KEY="parity-probe-encryption-key-0123456789ab",  # pragma: allowlist secret
    )
    result = subprocess.run(  # nosec B603  # fixed argv: this interpreter and the probe above
        [sys.executable, "-c", _COMMON + body],
        cwd=str(_ROOT / directory),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    lines = [line for line in result.stdout.splitlines() if line.startswith("PARITY:")]
    assert result.returncode == 0 and lines, f"{service} probe failed:\n{result.stderr[-3000:]}"
    return json.loads(lines[-1][len("PARITY:") :])


@pytest.fixture(scope="module")
def verdicts() -> dict:
    return {service: _probe(service) for service in _SERVICES}


def _rows(table: dict) -> dict:
    return {k: v for k, v in table.items() if k != "__audited__"}


def test_both_services_give_identical_verdicts(verdicts):
    backend, slm = _rows(verdicts["backend"]), _rows(verdicts["slm"])
    differing = sorted(k for k in backend if backend[k] != slm.get(k))
    assert backend.keys() == slm.keys()
    assert differing == [], f"{len(differing)} rows differ, e.g. {[(k, backend[k], slm[k]) for k in differing[:5]]}"


def test_every_denial_is_audited_in_both_services(verdicts):
    for service, table in verdicts.items():
        denials = sum(1 for v in _rows(table).values() if v == "403")
        assert table["__audited__"] == denials, f"{service}: {denials} denials, {table['__audited__']} audited"


def test_the_table_is_a_real_mix_not_a_uniform_answer(verdicts):
    """Contrast: parity of a probe that refused (or 401'd) everything would be meaningless."""
    for service, table in verdicts.items():
        values = list(_rows(table).values())
        assert values.count("allow") > 100 and values.count("403") > 100 and "401" not in values, service


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ("user|no-db|no-org|chat.use", "allow"),
        ("user|no-db|no-org|admin.system", "403"),
        ("readonly|db|no-org|knowledge.write", "allow"),  # system-role DB grant, platform-wide (#18259)
        ("user|db|no-org|admin.system", "403"),  # a company-role grant does not leave its company (#18338)
        ("user|db|org|admin.system", "allow"),  # ... and applies inside it
        ("user|no-db|org|admin.system", "403"),  # no user_id, no DB lookup
        ("Admin|no-db|no-org|chat.use", "403"),  # strict role reading
        ("superadmin|no-db|no-org|admin.system", "403"),  # #13854: no granular permissions
    ],
)
def test_pinned_rows(verdicts, row, expected):
    for service, table in verdicts.items():
        assert table[row] == expected, f"{service}: {row} -> {table[row]}, expected {expected}"
