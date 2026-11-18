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

The SLM is an admin-only server panel (#20628): its ``get_current_user`` refuses every non-admin
session with 403 before the shared gate runs, and that refusal is not a gate denial. So the two
services share the gate only for admin-session roles (``is_admin_role``); parity is compared on those
rows, the SLM's non-admin rows are asserted to be 403 on their own, and the "every denial audited"
rule applies to the gate's denials (every backend row, the SLM's admin-session rows).

API-key narrowing is not in this table: the backend accepts no user API keys
(``api_key_scopes_are_enforced_16040_test``), so there is no backend row to compare.
"""

import json
import os
import subprocess  # nosec B404  # runs this repo's own probe under the test interpreter
import sys

import pytest
from repo_tests._paths import repo_root

from autobot_shared.auth.permissions import is_admin_role

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
import auth_revocation
from auth_middleware import get_auth_middleware
middleware = get_auth_middleware()
# Same stub as the SLM probe: the probe measures permission verdicts, not the password-change epoch,
# which the backend gate enforces on every path since #18688 slice 3 (and fails closed without Redis).
patch.object(auth_revocation, "is_token_revoked_by_password_change", AsyncMock(return_value=False)).start()

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


def _admin_session(row: str) -> bool:
    """Whether the SLM lets this row's role past its admin-only refusal (#20628) to the shared gate."""
    return is_admin_role(row.split("|", 1)[0])


def _shared(table: dict) -> dict:
    return {k: v for k, v in _rows(table).items() if _admin_session(k)}


def _differing(backend: dict, slm: dict) -> list:
    return sorted(k for k in backend if backend[k] != slm.get(k))


def test_both_services_give_identical_verdicts(verdicts):
    backend, slm = _shared(verdicts["backend"]), _shared(verdicts["slm"])
    assert len(backend) > 100, "FIX THE SWEEP: too few admin-session rows to compare"
    assert backend.keys() == slm.keys()
    differing = _differing(backend, slm)
    assert differing == [], f"{len(differing)} rows differ, e.g. {[(k, backend[k], slm[k]) for k in differing[:5]]}"


def test_a_differing_admin_row_fails_the_comparison(verdicts):
    """Control: the comparison is not vacuous -- flipping one shared row is caught."""
    backend, slm = _shared(verdicts["backend"]), _shared(verdicts["slm"])
    row = next(iter(slm))
    slm[row] = "403" if slm[row] == "allow" else "allow"
    assert _differing(backend, slm) == [row]


def test_the_slm_refuses_every_non_admin_role_on_every_permission(verdicts):
    """#20628: an admin-only panel. The floor keeps an empty or admin-only table from passing."""
    refused = {k: v for k, v in _rows(verdicts["slm"]).items() if not _admin_session(k)}
    assert len(refused) > 500, f"FIX THE SWEEP: only {len(refused)} non-admin rows"
    assert {v for v in refused.values()} == {"403"}, sorted(k for k, v in refused.items() if v != "403")[:5]


def test_every_denial_is_audited_in_both_services(verdicts):
    """The gate audits its denials: all backend rows, and the SLM rows that reach the gate (not its admin-only refusal)."""
    for service, table in verdicts.items():
        rows = _rows(table) if service == "backend" else _shared(table)
        denials = sum(1 for v in rows.values() if v == "403")
        assert table["__audited__"] == denials, f"{service}: {denials} denials, {table['__audited__']} audited"


def test_the_table_is_a_real_mix_not_a_uniform_answer(verdicts):
    """Contrast: parity of a probe that refused (or 401'd) everything would be meaningless."""
    for service, table in verdicts.items():
        values = list(_rows(table).values())
        assert values.count("allow") > 100 and values.count("403") > 100 and "401" not in values, service


@pytest.mark.parametrize(
    ("row", "backend_expected", "slm_expected"),
    [
        ("user|no-db|no-org|chat.use", "allow", "403"),  # the SLM refuses a non-admin session (#20628)
        ("user|no-db|no-org|admin.system", "403", "403"),
        (
            "readonly|db|no-org|knowledge.write",
            "allow",
            "403",
        ),  # system-role DB grant, platform-wide (#18259); SLM: #20628
        ("user|db|no-org|admin.system", "403", "403"),  # a company-role grant does not leave its company (#18338)
        ("user|db|org|admin.system", "allow", "403"),  # ... and applies inside it; SLM: #20628
        ("user|no-db|org|admin.system", "403", "403"),  # no user_id, no DB lookup
        ("Admin|no-db|no-org|chat.use", "403", "403"),  # strict role reading
        ("superadmin|no-db|no-org|admin.system", "allow", "allow"),  # #19125: superadmin holds admin's set
    ],
)
def test_pinned_rows(verdicts, row, backend_expected, slm_expected):
    expected = {"backend": backend_expected, "slm": slm_expected}
    for service, table in verdicts.items():
        assert table[row] == expected[service], f"{service}: {row} -> {table[row]}, expected {expected[service]}"
