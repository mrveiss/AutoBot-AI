# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Frozen exemptions for the response-model secret guard (#17865).

Kept in its own module for two reasons. The guard file crossed the 600-line
ceiling, and the ceiling is split rather than raised. More importantly, a
change to an exemption is then a diff to THIS file and nothing else, so
granting one cannot ride along inside an unrelated change to the detector.

Two structures, deliberately not one:

    _WAIVED              audited, intentional, here is the reason
    _UNAUDITED_BASELINE  present before the guard, NOT YET AUDITED

Conflating them is how a baseline becomes a permanent exemption, so they have
different key shapes, different tests, and
``test_every_exemption_carries_a_real_reason`` rejects a baseline entry that
claims to be audited -- that would be a waiver wearing a baseline's key.
"""

from __future__ import annotations

#: (model, field, METHOD, path) -> why this one is intentional.
#:
#: Keyed by the ROUTE, not by the model. `_WAIVED` keyed on (model, field)
#: alone would exempt every future route that reuses the model, including one
#: with a different authorisation posture (CodeRabbit, #17865). A waiver is a
#: written reason for ONE endpoint, not a property of a schema.
_WAIVED: dict[tuple[str, str, str, str], str] = {
    ("MFASetupResponse", "secret", "POST", "/setup"): (
        "TOTP enrolment. The shared secret IS the deliverable -- the user cannot "
        "enrol an authenticator without it -- returned once, at setup, for the "
        "CALLER'S OWN account: the handler binds `current_user` and resolves the "
        "row by that username. That is the precise contrast with #17865, which "
        "bound the identity to `_` and discarded it."
    ),
}


#: PRE-EXISTING sites, frozen so the guard can be introduced without pretending
#: they are fine. This is NOT a waiver list: a waiver says "audited, intentional,
#: here is why"; this says "present before the guard existed and NOT YET AUDITED".
#: Conflating the two is how a baseline becomes a permanent exemption.
#:
#: The widened detector found these only once it followed generic subscripts and
#: nesting -- they were invisible to the first version, which is the whole reason
#: CodeRabbit's finding mattered. Draining this set is tracked separately; the
#: ratchet below means it can only shrink.
_UNAUDITED_BASELINE: dict[tuple[str, str, str, str], str] = {
    ("autobot-backend/api/secrets.py", "POST /", "SecretCreatedData", "secret"): (
        "`secret: Dict[str, Any]` -- an UNTYPED dict, so this guard cannot tell "
        "whether the value travels in it. That unauditability is itself the finding. Tracked at #17899."
    ),
    ("autobot-backend/api/secrets.py", "GET /{secret_id}", "SecretCreatedData", "secret"): (
        "Same untyped `Dict[str, Any]` as above. Tracked at #17899."
    ),
    ("autobot-backend/api/secrets.py", "PUT /{secret_id}", "SecretCreatedData", "secret"): (
        "Same untyped `Dict[str, Any]` as above. Tracked at #17899."
    ),
    ("autobot-backend/api/secrets.py", "DELETE /{secret_id}", "SecretCreatedData", "secret"): (
        "Same untyped `Dict[str, Any]` as above. Tracked at #17899."
    ),
    ("autobot-backend/api/secrets.py", "GET /", "SecretsListData", "secrets"): (
        "`secrets: List[Dict[str, Any]]` -- untyped elements; same limit as above. Tracked at #17899."
    ),
    ("autobot-backend/api/terminal.py", "POST /sessions", "TerminalSessionCreateResponse", "ssh_keys"): (
        "`ssh_keys: Dict[str, Any]` (schemas_terminal.py:27) -- untyped, so this guard "
        "cannot see whether private key material travels in it. Same unauditable shape "
        "as the secrets.py routes. Tracked at #17899."
    ),
}


#: Frozen count. Raising it is permitted ONLY to record pre-existing sites that a
#: WIDENED detector newly sees -- never to admit a new violation. It went 8 -> 18
#: when the scan was extended to `autobot_shared` and stopped exempting ciphertext
#: and hashes (review of #17865); every one of those sites predates this guard.
#: 18 -> 14 (#17899): the four `autobot-backend/api/llm.py` entries were audited and
#: moved to `_WAIVED`. The ratchet turning DOWN is the only direction this number
#: may move, and draining the baseline is what it is for.
#:
#: 14 -> 12 (#17865): `response_model_exclude` for `api_key` on the two
#: `llm_config.py` routes stopped them firing, so those entries were deleted rather
#: than left standing. A fixed site leaves the baseline; the number only goes down.
#:
#: 12 -> 6 (#18638): the six `autobot-slm-backend/api/llm_config.py` entries, and the four
#: `LLMConfigResponse` GET /config waivers above, were artifacts of the index keying classes
#: by BARE NAME (#17935). The SLM's `LLMConfigResponse` nested an `LLMConfig` that the index
#: merged with `autobot_shared/ssot_config.py`'s (which declares the three provider keys), and
#: the main backend's `LLMConfigResponse` was merged with the SLM's. Renaming the SLM models
#: (`SlmLLMConfig`, `SlmLLMConfigResponse`) ended both merges: `SlmLLMConfig` declares none of
#: those fields, and the main model resolves to itself. Nothing was fixed or widened -- the
#: findings were never about these routes, so the entries go.
_BASELINE_FROZEN_AT = 6
