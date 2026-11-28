# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21506: a failed secret delete maps to ONE audit outcome, whichever route it fails on.

``secrets_delete_outcome.outcome_for`` is the only failure-to-outcome mapping. A missing secret records
``failed`` / ``not_found`` whether it is an HTTP 404 or ``SecretNotFoundError``, as the ACCESS and UPDATE
records do. The route tests drive the same failures through the main route and both envelope routes and
compare the records; the main route's seam (``secrets_manager.delete_secret``) and the envelope seam
(the coordinator's delete) can raise any exception, so every key below runs on all three routes.
"""

# flake8: noqa: F811 -- pytest fixtures imported by name are re-requested as parameters

import pytest
from fastapi import HTTPException

from api import secrets as secrets_module
from api import secrets_audit_store_18648_test as audit_base
from api.envelope_secrets_delete_20640_test import _SECRET, _Coordinator, _run, _trail
from api.secrets_defects_20557_test import _outcome
from api.secrets_defects_20557_test import _trail as _main_trail
from api.secrets_delete_outcome import outcome_for
from api.secrets_system_vault_17731_test import _SECRET_ID, client_and_vault  # noqa: F401 -- fixture
from services.envelope_secrets_service import SecretAccessError, SecretNotFoundError

store = audit_base.store

_EXPECTED = {
    "http-404": ("failed", "not_found"),
    "http-409": ("denied", "has_dependents"),
    "http-503": ("denied", "http_503"),
    "permission-error": ("denied", "permission_denied"),
    "access-error": ("denied", "permission_denied"),
    "not-found-error": ("failed", "not_found"),
    "runtime-error": ("failed", "RuntimeError"),
}
_KEYS = list(_EXPECTED)
_LEAK = "LEAK-secret-name-and-value"


def _failure(key: str) -> BaseException:
    """The exception a key names, built fresh so no test shares one instance."""
    if key.startswith("http-"):
        return HTTPException(status_code=int(key[5:]), detail=_LEAK)
    return {
        "permission-error": PermissionError(_LEAK),
        "access-error": SecretAccessError(_LEAK),
        "not-found-error": SecretNotFoundError(_LEAK),
        "runtime-error": RuntimeError(_LEAK),
    }[key]


@pytest.mark.parametrize("key", _KEYS, ids=_KEYS)
def test_the_shared_mapping_gives_each_failure_its_outcome(key) -> None:
    assert outcome_for(_failure(key)) == _EXPECTED[key]


def test_a_missing_secret_records_the_same_outcome_in_both_forms() -> None:
    assert outcome_for(HTTPException(status_code=404)) == outcome_for(SecretNotFoundError()) == ("failed", "not_found")


@pytest.mark.parametrize("key", _KEYS, ids=_KEYS)
def test_the_main_route_records_the_shared_outcome(key, client_and_vault, monkeypatch) -> None:  # noqa: F811
    client, _vault = client_and_vault()
    secrets_module.secrets_manager.delete_secret.side_effect = _failure(key)
    ops = _main_trail(monkeypatch)

    client.delete(f"/api/secrets/{_SECRET_ID}")

    result, details = _outcome(ops)
    assert (result, details["reason"]) == _EXPECTED[key]
    assert _LEAK not in repr(ops.await_args_list)


@pytest.mark.parametrize("kind", ["user", "service"], ids=["user", "service"])
@pytest.mark.parametrize("key", _KEYS, ids=_KEYS)
def test_the_envelope_routes_record_the_shared_outcome(key, kind, store) -> None:
    url = ("/api/v2/secrets/" if kind == "user" else "/api/v2/secrets/system/") + _SECRET

    _run(_Coordinator(error=_failure(key)), url, store)

    assert _trail(store) == [("attempted", "before_write"), (_EXPECTED[key][0], _EXPECTED[key][1])]
    assert _LEAK not in repr([e.metadata for e in store.events])
