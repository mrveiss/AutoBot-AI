# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Baseline reasons for SLM i18n display labels moved out of hard-coded strings (#18863).

Kept apart from ``secrets_baseline_reason_entries.py``, which sits near the 600-line
ratchet (it was split for size once already, #17134); that module merges this table into
``SPECIFIC_REASONS``. Depends on nothing, so there is no import cycle.

Each value is a display message the SLM shows; its key contains ``password`` or ``ApiKey``,
which trips the Secret Keyword denylist. Every hash was confirmed by re-hashing the literal
(plain SHA1 of the label reproduces the stored hashed_secret), not asserted from the key.
"""

from __future__ import annotations

_FILE = "autobot-slm-frontend/src/locales/en.json"
_TYPE = "Secret Keyword"

# (hashed_secret, i18n key, the display label)
_LABELS = (
    (
        "d69c3b1ac54be7da3666d9937b9c78e7c309d6e8",  # pragma: allowlist secret
        "passwordsDoNotMatch",
        "Passwords do not match",
    ),
    (
        "819016c764d26903929956010f9a91bb4005eb0d",  # pragma: allowlist secret
        "aPIKeyRevoked",
        "API key revoked successfully",
    ),
    (
        "6c56a9249cba324d029f725f1f7c0e47184e2dcf",  # pragma: allowlist secret
        "passwordIsRequired",
        "Password is required",
    ),
    (
        "95157b8c7d13ffdda0fb3830a2c6a28f3eebb70f",  # pragma: allowlist secret
        "failedToLoadApiKeys",
        "Failed to load API keys",
    ),
    (
        "5e78089eaca9d6ab15f3c481cc1c35f58d79e764",  # pragma: allowlist secret
        "failedToCreateApiKey",
        "Failed to create API key",
    ),
    (
        "db3a5f4081b1f0c8dd70000ec496eb83d9e6593a",  # pragma: allowlist secret
        "failedToRevokeApiKey",
        "Failed to revoke API key",
    ),
    (
        "c037844c130ec1178fb0a262f2b6bd8afe83590e",  # pragma: allowlist secret
        "confirmRevokeApiKey",
        "Are you sure you want to revoke this API key? ...",
    ),
)

SLM_LABEL_REASONS: dict[tuple[str, str, str], str] = {
    (_FILE, _TYPE, digest): (
        f"the i18n display message `{label}` (settings.securitySettings / user-management key "
        f"`{key}`, moved out of a hard-coded string by #18863), not a credential; the key name "
        "trips the Secret Keyword denylist. Plain SHA1 of the literal message reproduces this hash."
    )
    for digest, key, label in _LABELS
}
