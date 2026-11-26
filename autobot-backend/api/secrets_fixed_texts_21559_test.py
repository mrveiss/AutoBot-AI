# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#21559: the main secret update route answers a refusal or bad request with fixed texts, not "Internal server error"."""

# flake8: noqa: F811 -- pytest fixtures imported by name are re-requested as parameters

import pytest

from api import secrets as secrets_module
from api.secrets_system_vault_17731_test import _SECRET_ID, client_and_vault  # noqa: F401 -- fixture
from autobot_shared.http_refusal import REFUSAL_TEXT

_LEAK = "LEAK-21559-update-marker"


@pytest.mark.parametrize(
    "error, status, text",
    [(PermissionError(_LEAK), 403, REFUSAL_TEXT[403]), (ValueError(_LEAK), 400, REFUSAL_TEXT[400])],
    ids=["refused", "invalid"],
)
def test_update_answers_with_a_fixed_text(error, status, text, client_and_vault) -> None:
    client, _vault = client_and_vault()
    secrets_module.secrets_manager.update_secret.side_effect = error

    response = client.put(f"/api/secrets/{_SECRET_ID}", json={"description": "x"})

    assert response.status_code == status, response.text
    assert response.json()["detail"] == text
    assert _LEAK not in response.text


def test_update_of_a_missing_secret_answers_with_the_shared_not_found_text(client_and_vault) -> None:
    client, _vault = client_and_vault()

    response = client.put("/api/secrets/no-such-secret", json={"description": "x"})

    assert (response.status_code, response.json()["detail"]) == (404, REFUSAL_TEXT[404])
