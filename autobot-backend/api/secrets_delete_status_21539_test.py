# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21539: a failed secret delete is answered with the status its audit record implies, on every route.

``secrets_delete_outcome.error_for`` reads the same classification as ``outcome_for``: not found is 404 and
permission denied is 403. The table drives each failure kind of the #21506 test through the main route and both
envelope routes and asserts the HTTP status AND the audit record. Bodies built from the exception text by the
envelope routes' ``_mapped`` (a ``SecretAccessError`` / ``SecretNotFoundError``) and the detail of an
``HTTPException`` are the routes' existing behaviour and are not asserted leak-free here.
"""

# flake8: noqa: F811 -- pytest fixtures imported by name are re-requested as parameters

import pytest

from api import secrets as secrets_module
from api.envelope_secrets_delete_20640_test import _SECRET, _Coordinator, _run, _trail
from api.secrets_defects_20557_test import _outcome
from api.secrets_defects_20557_test import _trail as _main_trail
from api.secrets_delete_outcome import error_for
from api.secrets_delete_outcome_21506_test import _EXPECTED, _KEYS, _LEAK, _failure, store  # noqa: F401 -- fixture
from api.secrets_system_vault_17731_test import _SECRET_ID, client_and_vault  # noqa: F401 -- fixture

_STATUS = {
    "http-404": 404,
    "http-409": 409,
    "http-503": 503,
    "permission-error": 403,
    "access-error": 403,
    "not-found-error": 404,
    "runtime-error": 500,
}
#: Keys whose response body is built from the exception text by the route today (not part of this fix).
_ECHOED_MAIN = {"http-404", "http-409", "http-503"}
_ECHOED_ENVELOPE = _ECHOED_MAIN | {"access-error", "not-found-error"}


def test_the_status_table_covers_every_failure_kind() -> None:
    assert list(_STATUS) == _KEYS


@pytest.mark.parametrize("key", _KEYS, ids=_KEYS)
def test_error_for_gives_the_status_the_record_implies(key) -> None:
    error = error_for(_failure(key))

    if key.startswith("http-") or key == "runtime-error":
        assert error is None
        return
    assert error.status_code == _STATUS[key]
    assert _LEAK not in str(error.detail)


@pytest.mark.parametrize("key", _KEYS, ids=_KEYS)
def test_the_main_route_answers_the_status_and_records_the_outcome(
    key, client_and_vault, monkeypatch
) -> None:  # noqa: F811
    client, _vault = client_and_vault()
    secrets_module.secrets_manager.delete_secret.side_effect = _failure(key)
    ops = _main_trail(monkeypatch)

    response = client.delete(f"/api/secrets/{_SECRET_ID}")

    assert response.status_code == _STATUS[key]
    result, details = _outcome(ops)
    assert (result, details["reason"]) == _EXPECTED[key]
    assert _LEAK not in repr(ops.await_args_list)
    if key not in _ECHOED_MAIN:
        assert _LEAK not in response.text


@pytest.mark.parametrize("kind", ["user", "service"], ids=["user", "service"])
@pytest.mark.parametrize("key", _KEYS, ids=_KEYS)
def test_the_envelope_routes_answer_the_status_and_record_the_outcome(key, kind, store) -> None:
    url = ("/api/v2/secrets/" if kind == "user" else "/api/v2/secrets/system/") + _SECRET

    response, _client = _run(_Coordinator(error=_failure(key)), url, store)

    assert response.status_code == _STATUS[key]
    assert _trail(store) == [("attempted", "before_write"), (_EXPECTED[key][0], _EXPECTED[key][1])]
    assert _LEAK not in repr([e.metadata for e in store.events])
    if key not in _ECHOED_ENVELOPE:
        assert _LEAK not in response.text
