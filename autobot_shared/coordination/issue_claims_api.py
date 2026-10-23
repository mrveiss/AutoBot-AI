# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The issue-claims CLI's API transport (#18811, parent #17098).

A developer checkout has no registry credential (its ``.env`` is the placeholder copy), so
``python -m autobot_shared.coordination.issue_claims`` can reach the registry through AutoBot's
``/api/coordination/issue-claims`` instead. It is used when ``AUTOBOT_ISSUE_CLAIMS_API_URL`` is set.

* The base URL is exactly that value -- never derived from the SSOT ``backend_url`` (#18810) --
  and must be ``https``, or ``http`` to a loopback host only: the credential never crosses a
  network in the clear.
* The credential is a secrets-manager reference plus verifier (``issue_claims_login``), read from
  the kernel user keyring on each run and sent in ``CREDENTIAL_HEADER``; never argv, never an
  environment value, never a file, never printed or logged.
* The URL is operator-configured, so it is registered as an internal origin and still goes through
  the egress policy (a malformed or metadata-address URL is refused); redirects are not followed.
* Exit codes are the Redis transport's: 200 -> 0, 409 -> 1 (held, body names the holder), 400/422 -> 4,
  everything else -- 401/403 (``error_class`` ``AuthRefused``), 5xx, transport failure, no credential
  in the keyring (``not-logged-in``) -- -> 3. Nothing is granted on a failure (fail closed).
"""

from __future__ import annotations

import argparse
import ipaddress
from typing import Any
from urllib.parse import urlsplit

import httpx

from autobot_shared.coordination.issue_claims import EXIT_HELD, EXIT_OK, EXIT_UNREADABLE, EXIT_USAGE
from autobot_shared.coordination.kernel_keyring import KernelKeyring, KeyNotFound
from autobot_shared.egress_allowlist import register_internal_origin_provider
from autobot_shared.env_utils import env_int_clamped, env_str
from autobot_shared.http_egress_guard import assert_egress_policy
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

API_URL_ENV = "AUTOBOT_ISSUE_CLAIMS_API_URL"
API_PATH = "/api/coordination/issue-claims"
CREDENTIALS_PATH = f"{API_PATH}/credentials"
#: The one header the claims credential travels in; the generic auth middleware never reads it.
CREDENTIAL_HEADER = "X-AutoBot-Claims-Credential"
LOGIN_HINT = "run `python -m autobot_shared.coordination.issue_claims login` (the kernel keyring is cleared on reboot)"


class InsecureApiUrl(ValueError):
    """The configured URL would send the credential over plain HTTP to a non-loopback host."""


def api_base_url() -> str:
    """The configured API base URL, or ``""`` when the Redis transport applies."""
    return env_str(API_URL_ENV, "").strip().rstrip("/")


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def normalised_base_url(url: str) -> str:
    """``scheme://host:port/path`` with the default port explicit; raises :class:`InsecureApiUrl`."""
    parts = urlsplit(url.strip())
    scheme, host = parts.scheme.lower(), (parts.hostname or "").lower()
    if not host or scheme not in ("https", "http"):
        raise InsecureApiUrl("the issue-claims API URL must be an http(s) URL with a host")
    if scheme == "http" and not _is_loopback(host):
        raise InsecureApiUrl("the issue-claims API URL must be https unless the host is loopback")
    port = parts.port or (443 if scheme == "https" else 80)
    shown = f"[{host}]" if ":" in host else host
    return f"{scheme}://{shown}:{port}{parts.path.rstrip('/')}"


def keyring_description(base_url: str) -> str:
    """The ``@u`` key description: one credential per backend, keyed by its normalised URL."""
    return f"autobot:issue-claims:{normalised_base_url(base_url)}"


def keyring() -> KernelKeyring:
    """The kernel keyring; tests replace this with one over a fake syscall."""
    return KernelKeyring()


async def _configured_origin() -> list[str]:
    return [api_base_url()]


def timeout_s() -> int:
    return env_int_clamped("AUTOBOT_ISSUE_CLAIMS_API_TIMEOUT_S", 10, min_v=1, max_v=120)


def client(headers: dict[str, str]) -> httpx.AsyncClient:
    """The HTTP client; tests replace this to supply a mock transport."""
    return httpx.AsyncClient(headers=headers, timeout=timeout_s(), follow_redirects=False)


async def checked_url(path: str) -> str:
    """The full URL for *path*, once transport security and the egress policy allow it."""
    base = api_base_url()
    normalised_base_url(base)
    register_internal_origin_provider(_configured_origin)
    url = f"{base}{path}"
    await assert_egress_policy(url)
    return url


def stored_credential(base_url: str) -> str:
    """The credential in the keyring for *base_url*; raises :class:`KeyNotFound` when there is none."""
    return keyring().read(keyring_description(base_url)).decode("utf-8")


def claims_refusal(error: str, error_class: str, message: str = "") -> dict:
    body = {"error": error, "error_class": error_class, "granted": False}
    return {**body, "message": message} if message else body


def _request_for(args: argparse.Namespace) -> tuple[str, str, dict[str, Any]]:
    """``(method, path, httpx kwargs)`` for the parsed subcommand."""
    if args.cmd == "list":
        return "GET", API_PATH, {}
    path = f"{API_PATH}/{args.number}"
    if args.cmd == "who":
        return "GET", path, {}
    if args.cmd == "release":
        return "DELETE", path, {"params": {"owner": args.owner}}
    body = {"owner": args.owner, "note": args.note}
    if args.ttl_s is not None:
        body["ttl_s"] = args.ttl_s
    return "POST", path, {"json": body}


def _detail(response: httpx.Response) -> Any:
    try:
        return response.json().get("detail")
    except (ValueError, AttributeError):
        return None


def map_response(response: httpx.Response) -> tuple[int, dict]:
    """Map an API answer onto the CLI's exit code and JSON body."""
    status = response.status_code
    if status == 200:
        return EXIT_OK, response.json()
    if status == 409 and isinstance(_detail(response), dict):
        return EXIT_HELD, _detail(response)
    if status in (400, 422):
        return EXIT_USAGE, {"error": "bad-request", "message": str(_detail(response)), "granted": False}
    error_class = "AuthRefused" if status in (401, 403) else f"HTTP{status}"
    return EXIT_UNREADABLE, claims_refusal("registry-unreadable", error_class)


async def run_api_command(args: argparse.Namespace) -> tuple[int, dict]:
    """Send *args*' subcommand to the API; a failure to get any answer is ``EXIT_UNREADABLE``."""
    method, path, kwargs = _request_for(args)
    try:
        url = await checked_url(path)
        credential = stored_credential(api_base_url())
        async with client({CREDENTIAL_HEADER: credential}) as http:
            response = await http.request(method, url, **kwargs)
        return map_response(response)
    except KeyNotFound:
        return EXIT_UNREADABLE, claims_refusal(
            "not-logged-in", "KeyNotFound", f"no issue-claims credential; {LOGIN_HINT}"
        )
    except Exception as exc:  # noqa: BLE001 -- every failure to get an answer fails closed
        logger.error("issue claims API unreachable (%s); refusing, nothing granted", type(exc).__name__)
        return EXIT_UNREADABLE, claims_refusal("registry-unreadable", type(exc).__name__)
