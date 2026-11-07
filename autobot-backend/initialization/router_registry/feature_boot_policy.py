# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which feature-router import failures abort startup (#6690, #19319).

``AUTOBOT_FEATURE_ROUTERS_STRICT`` decides whether ANY failed feature router aborts startup:
strict in dev/CI, lenient in production (``autobot_shared/ssot_role_mirrors.py``). Lenient mode is
for optional features. A security control is not optional, so the routers in
``REQUIRED_FEATURE_ROUTERS`` abort startup on an import failure whatever the strict value says:
production must not quietly lose the endpoints that authenticate, authorise, handle or revoke
credentials, or assess security, and carry on with only an ERROR line (security review of #19319).

Entries are the router *name* (the fourth element of a ``FEATURE_ROUTER_CONFIGS`` tuple); a test
pins every entry to a configured router so a rename cannot silently drop one.
"""

from typing import Any, Dict, List

from autobot_shared.env_utils import truthy

#: name -> why its absence is a security regression, not a missing feature.
REQUIRED_FEATURE_ROUTERS: Dict[str, str] = {
    "provider_auth": "provider credential connect/disconnect -- the only way to revoke a provider login",
    "secrets": "secrets store management, incl. credential rotation/deletion",  # pragma: allowlist secret
    "envelope_secrets": "envelope-encrypted secrets store surface",  # pragma: allowlist secret
    "workflow_secrets": "per-workflow credential management and revocation",  # pragma: allowlist secret
    "llm_keys": "admin issue/revoke of virtual LLM API keys (credential handling)",
    "run_jwt": "run JWT refresh (authentication of agent runs)",
    "security": "command approval gate, security audit and threat intelligence (authorisation)",
    "elevation": "privilege-escalation request/approval flow (authorisation)",
    "permissions": "permission-system rules and approval management (authorisation)",
    "workflow_permissions": "workflow RBAC and its permission audit log (authorisation)",
    "security_assessment": "security assessment endpoints",
}


def _describe(results: List[Dict[str, Any]]) -> str:
    return "; ".join(f"{r['name']} ({r['module']}): {r['error']}" for r in results)


def enforce_feature_boot_policy(results: List[Dict[str, Any]], strict_value: str) -> None:
    """Raise when startup must not continue with the routers that failed to load.

    Args:
        results: this pass's feature-group load results (``name``/``module``/``loaded``/``error``).
        strict_value: the configured ``AUTOBOT_FEATURE_ROUTERS_STRICT`` value.

    Raises:
        RuntimeError: a required router failed (any mode), or any router failed in strict mode.
    """
    failed = [r for r in results if not r["loaded"]]
    required = [r for r in failed if r["name"] in REQUIRED_FEATURE_ROUTERS]
    if required:
        raise RuntimeError(
            f"{len(required)} required security feature router(s) failed to import; startup refused "
            f"regardless of AUTOBOT_FEATURE_ROUTERS_STRICT -- {_describe(required)}"
        )
    if failed and truthy(strict_value):
        raise RuntimeError(
            f"AUTOBOT_FEATURE_ROUTERS_STRICT=1 — {len(failed)} feature router(s) failed to load: {_describe(failed)}"
        )
