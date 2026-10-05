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
    ("LLMConfigResponse", "api_key", "GET", "/config"): (
        "AUDITED (#17899). The field is NOT declared on this model at all: `LLMConfigResponse` "
        "in autobot-backend/api/schemas_agent.py:793 declares nothing and sets `extra: "
        '"allow"`. It is attributed here because the index keys classes by BARE NAME across '
        "all three trees and merges autobot-slm-backend/api/llm_config.py:76's same-named "
        "class, which does nest `LLMConfig` -- a real defect in the index, tracked at #17935 "
        "and not fixed here because it needs import resolution and would change the violation "
        "path too. What the route serialises was traced rather than assumed: api/llm.py:64 -> "
        'ConfigService.get_llm_config() -> config/model_config.py:147, returning `{"ollama": '
        '..., "unified": get_nested("backend.llm")}`. Nothing writes a credential into that '
        "nested subtree -- the only candidate, `_apply_embedding_config` at api/llm.py:333-337, "
        "calls `ConfigSyncOps.set` (config/sync_ops.py:60), which stores a FLAT top-level key, "
        "so `get_nested` never reaches it; the checked-in `backend.llm` section is "
        '`{"ollama": {"endpoint": ...}}`. The model still PERMITS any field, so the route '
        "is recorded in no_secret_passthrough_routes_17899.py as unverifiable rather than read "
        "as clean."
    ),
    ("LLMConfigResponse", "anthropic_api_key", "GET", "/config"): (
        "AUDITED (#17899). The field is NOT declared on this model at all: `LLMConfigResponse` "
        "in autobot-backend/api/schemas_agent.py:793 declares nothing and sets `extra: "
        '"allow"`. It is attributed here because the index keys classes by BARE NAME across '
        "all three trees and merges autobot-slm-backend/api/llm_config.py:76's same-named "
        "class, which does nest `LLMConfig` -- a real defect in the index, tracked at #17935 "
        "and not fixed here because it needs import resolution and would change the violation "
        "path too. Same route and same traced payload as the `api_key` entry above. The model "
        "still PERMITS any field, so the route is recorded in "
        "no_secret_passthrough_routes_17899.py as unverifiable rather than read as clean."
    ),
    ("LLMConfigResponse", "brave_search_api_key", "GET", "/config"): (
        "AUDITED (#17899). The field is NOT declared on this model at all: `LLMConfigResponse` "
        "in autobot-backend/api/schemas_agent.py:793 declares nothing and sets `extra: "
        '"allow"`. It is attributed here because the index keys classes by BARE NAME across '
        "all three trees and merges autobot-slm-backend/api/llm_config.py:76's same-named "
        "class, which does nest `LLMConfig` -- a real defect in the index, tracked at #17935 "
        "and not fixed here because it needs import resolution and would change the violation "
        "path too. Same route and same traced payload as the `api_key` entry above. The model "
        "still PERMITS any field, so the route is recorded in "
        "no_secret_passthrough_routes_17899.py as unverifiable rather than read as clean."
    ),
    ("LLMConfigResponse", "openai_api_key", "GET", "/config"): (
        "AUDITED (#17899). The field is NOT declared on this model at all: `LLMConfigResponse` "
        "in autobot-backend/api/schemas_agent.py:793 declares nothing and sets `extra: "
        '"allow"`. It is attributed here because the index keys classes by BARE NAME across '
        "all three trees and merges autobot-slm-backend/api/llm_config.py:76's same-named "
        "class, which does nest `LLMConfig` -- a real defect in the index, tracked at #17935 "
        "and not fixed here because it needs import resolution and would change the violation "
        "path too. Same route and same traced payload as the `api_key` entry above. The model "
        "still PERMITS any field, so the route is recorded in "
        "no_secret_passthrough_routes_17899.py as unverifiable rather than read as clean."
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
    ("autobot-slm-backend/api/llm_config.py", "GET", "LLMConfigResponse", "api_key"): (
        "Masked at llm_config.py:196 (`provider.api_key = _mask_api_key(...)`), and "
        "being changed from masking to omission by PR #17846, which OWNS this file. "
        "Not touched here: same file, one PR, one agent."
    ),
    ("autobot-slm-backend/api/llm_config.py", "PUT", "LLMConfigResponse", "api_key"): (
        "Same model and same file as the GET above; #17846 territory."
    ),
    ("autobot-backend/api/secrets.py", "POST /", "SecretCreatedData", "secret"): (
        "`secret: Dict[str, Any]` -- an UNTYPED dict, so this guard cannot tell "
        "whether the value travels in it. That unauditability is itself the finding."
    ),
    ("autobot-backend/api/secrets.py", "GET /{secret_id}", "SecretCreatedData", "secret"): (
        "Same untyped `Dict[str, Any]` as above."
    ),
    ("autobot-backend/api/secrets.py", "PUT /{secret_id}", "SecretCreatedData", "secret"): (
        "Same untyped `Dict[str, Any]` as above."
    ),
    ("autobot-backend/api/secrets.py", "DELETE /{secret_id}", "SecretCreatedData", "secret"): (
        "Same untyped `Dict[str, Any]` as above."
    ),
    ("autobot-backend/api/secrets.py", "GET /", "SecretsListData", "secrets"): (
        "`secrets: List[Dict[str, Any]]` -- untyped elements; same limit as above."
    ),
    ("autobot-backend/api/terminal.py", "POST /sessions", "TerminalSessionCreateResponse", "ssh_keys"): (
        "`ssh_keys: Dict[str, Any]` (schemas_terminal.py:27) -- untyped, so this guard "
        "cannot see whether private key material travels in it. Same unauditable shape "
        "as the secrets.py routes."
    ),
    ("autobot-slm-backend/api/llm_config.py", "GET", "LLMConfigResponse", "anthropic_api_key"): (
        "Nests `LLMConfig`. `provider.api_key` is masked at llm_config.py:196, but these "
        "are DIFFERENT fields and were not checked. PR #17846 owns this file."
    ),
    ("autobot-slm-backend/api/llm_config.py", "GET", "LLMConfigResponse", "brave_search_api_key"): (
        "Nests `LLMConfig`; see the anthropic entry above. #17846 territory."
    ),
    ("autobot-slm-backend/api/llm_config.py", "GET", "LLMConfigResponse", "openai_api_key"): (
        "Nests `LLMConfig`; see the anthropic entry above. #17846 territory."
    ),
    ("autobot-slm-backend/api/llm_config.py", "PUT", "LLMConfigResponse", "anthropic_api_key"): (
        "Same model and file as the GET above; #17846 territory."
    ),
    ("autobot-slm-backend/api/llm_config.py", "PUT", "LLMConfigResponse", "brave_search_api_key"): (
        "Same model and file as the GET above; #17846 territory."
    ),
    ("autobot-slm-backend/api/llm_config.py", "PUT", "LLMConfigResponse", "openai_api_key"): (
        "Same model and file as the GET above; #17846 territory."
    ),
}


#: Frozen count. Raising it is permitted ONLY to record pre-existing sites that a
#: WIDENED detector newly sees -- never to admit a new violation. It went 8 -> 18
#: when the scan was extended to `autobot_shared` and stopped exempting ciphertext
#: and hashes (review of #17865); every one of those sites predates this guard.
#: 18 -> 14 (#17899): the four `autobot-backend/api/llm.py` entries were audited and
#: moved to `_WAIVED`. The ratchet turning DOWN is the only direction this number
#: may move, and draining the baseline is what it is for.
_BASELINE_FROZEN_AT = 14
