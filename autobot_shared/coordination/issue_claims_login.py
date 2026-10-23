# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``issue_claims login`` / ``logout``: the claims credential's client half (#18811).

Owner decision 2026-10-18: the CLI's credential comes from the canonical secrets manager and
lives in the kernel user keyring, never on disk.

``login`` prompts for the AutoBot username and password with ``getpass`` (never argv or the
environment), signs in through ``/api/auth/login`` for a login JWT, and with it asks the backend
to mint a claims-client credential in the user's own vault. The credential (``<secret_id>.<verifier>``)
goes straight into ``@u``; the password and the JWT are dropped and never stored.

``logout`` revokes the credential in the secrets manager, then removes the key. A credential the
backend no longer recognises (401: already revoked or expired) is removed too; any other failure
keeps the key, so the revocation can be retried rather than the handle lost.

The kernel keyring is cleared on reboot: run ``login`` again afterwards.
"""

from __future__ import annotations

import getpass
from typing import Callable

import httpx

from autobot_shared.coordination import issue_claims_api as api
from autobot_shared.coordination.issue_claims import EXIT_OK, EXIT_UNREADABLE, EXIT_USAGE
from autobot_shared.coordination.kernel_keyring import KeyNotFound
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

LOGIN_PATH = "/api/auth/login"

#: ``prompt(text) -> str`` without echo; tests replace it.
Prompt = Callable[[str], str]


def _no_url() -> tuple[int, dict]:
    return EXIT_USAGE, {"error": "bad-request", "message": f"{api.API_URL_ENV} is not set", "granted": False}


async def _login_jwt(http: httpx.AsyncClient, prompt: Prompt) -> str | None:
    """A login JWT for the prompted user, or ``None`` when the backend refused the sign-in."""
    username = prompt("AutoBot username: ").strip()
    password = prompt("AutoBot password: ")
    response = await http.post(await api.checked_url(LOGIN_PATH), json={"username": username, "password": password})
    if response.status_code != 200:
        return None
    body = response.json()
    return body.get("token") or body.get("access_token")


async def _mint(http: httpx.AsyncClient, jwt: str) -> dict | None:
    """The minted ``{credential, secret_id, username}``, or ``None`` when minting was refused."""
    url = await api.checked_url(api.CREDENTIALS_PATH)
    response = await http.post(url, headers={"Authorization": f"Bearer {jwt}"})
    return response.json() if response.status_code == 201 else None


async def run_login(prompt: Prompt = getpass.getpass) -> tuple[int, dict]:
    """Sign in, mint a claims credential, and keep it in ``@u`` only."""
    base = api.api_base_url()
    if not base:
        return _no_url()
    try:
        async with api.client({}) as http:
            jwt = await _login_jwt(http, prompt)
            minted = await _mint(http, jwt) if jwt else None
        if minted is None:
            return EXIT_UNREADABLE, api.claims_refusal("login-refused", "AuthRefused")
        api.keyring().add(api.keyring_description(base), minted["credential"].encode("utf-8"))
    except Exception as exc:  # noqa: BLE001 -- any failure leaves nothing stored and is a refusal
        logger.error("issue-claims login failed (%s); nothing stored", type(exc).__name__)
        return EXIT_UNREADABLE, api.claims_refusal("login-failed", type(exc).__name__)
    body = {"logged_in": True, "username": minted["username"], "secret_id": minted["secret_id"], "keyring": "@u"}
    return EXIT_OK, body


async def _revoke(credential: str) -> int:
    """The backend's status for revoking *credential*."""
    async with api.client({api.CREDENTIAL_HEADER: credential}) as http:
        response = await http.delete(await api.checked_url(api.CREDENTIALS_PATH))
    return response.status_code


async def run_logout() -> tuple[int, dict]:
    """Revoke the credential in the secrets manager, then remove it from ``@u``."""
    base = api.api_base_url()
    if not base:
        return _no_url()
    try:
        credential = api.stored_credential(base)
        status = await _revoke(credential)
        if status not in (200, 401):
            return EXIT_UNREADABLE, api.claims_refusal(
                "revoke-failed", f"HTTP{status}", "the key was kept; retry logout"
            )
        api.keyring().unlink(api.keyring_description(base))
    except KeyNotFound:
        return EXIT_OK, {"logged_out": True, "revoked": False, "message": "no credential in the keyring"}
    except Exception as exc:  # noqa: BLE001 -- the key is kept so the revocation can be retried
        logger.error("issue-claims logout failed (%s); the key was kept", type(exc).__name__)
        return EXIT_UNREADABLE, api.claims_refusal(
            "revoke-failed", type(exc).__name__, "the key was kept; retry logout"
        )
    return EXIT_OK, {"logged_out": True, "revoked": status == 200}
