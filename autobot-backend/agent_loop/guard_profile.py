# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unified guard profile for the agent loop (GH#11150).

Consolidates the loop's discretionary safety guards behind one switch,
``AUTOBOT_GUARD_PROFILE``, so a deployment can describe its posture in one place
instead of flipping several independently-named env vars.

Guard matrix (fields are ``AgentLoopConfig`` guard booleans / limits):

    field                          minimal   standard(*)  strict
    -----------------------------  --------  -----------  ------
    require_approval_for_sensitive   False       True      True
    pre_action_verifier_enabled      False       True      True
    halt_on_stagnation               False       True      True
    abstain_on_low_confidence        False       True      True
    max_identical_tool_calls           5           3        2

(*) ``standard`` is the default and reproduces today's ``AgentLoopConfig``
defaults exactly.

Per-guard env vars override the profile (and win over it):
    AUTOBOT_GUARD_REQUIRE_APPROVAL   -> require_approval_for_sensitive (bool)
    AUTOBOT_GUARD_VERIFIER           -> pre_action_verifier_enabled    (bool)
    AUTOBOT_GUARD_STAGNATION_HALT    -> halt_on_stagnation             (bool)
    AUTOBOT_GUARD_ABSTAIN            -> abstain_on_low_confidence       (bool)
    AUTOBOT_GUARD_MAX_IDENTICAL      -> max_identical_tool_calls        (int)

Always-on safety guards are NOT governed here: forbidden_work enforcement
(agent identity, GH#11145) and config-protection (``AUTOBOT_ALLOW_CONFIG_EDITS``,
GH#11148) are controlled separately by design.
"""

import os

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

DEFAULT_PROFILE = "standard"

# ``standard`` intentionally carries NO overrides so it reproduces the
# AgentLoopConfig dataclass defaults exactly (the AC's "no behaviour change").
GUARD_PROFILES: dict[str, dict[str, object]] = {
    "minimal": {
        "require_approval_for_sensitive": False,
        "pre_action_verifier_enabled": False,
        "halt_on_stagnation": False,
        "abstain_on_low_confidence": False,
        "max_identical_tool_calls": 5,
    },
    "standard": {},
    "strict": {
        "require_approval_for_sensitive": True,
        "pre_action_verifier_enabled": True,
        "halt_on_stagnation": True,
        "abstain_on_low_confidence": True,
        "max_identical_tool_calls": 2,
    },
}


def _as_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# env var -> (config field, parser)
_ENV_OVERRIDES: dict[str, tuple[str, object]] = {
    "AUTOBOT_GUARD_REQUIRE_APPROVAL": ("require_approval_for_sensitive", _as_bool),
    "AUTOBOT_GUARD_VERIFIER": ("pre_action_verifier_enabled", _as_bool),
    "AUTOBOT_GUARD_STAGNATION_HALT": ("halt_on_stagnation", _as_bool),
    "AUTOBOT_GUARD_ABSTAIN": ("abstain_on_low_confidence", _as_bool),
    "AUTOBOT_GUARD_MAX_IDENTICAL": ("max_identical_tool_calls", int),
}


def resolve_profile_name() -> str:
    """Return the active profile name, defaulting to ``standard`` for unset/unknown."""
    name = os.environ.get("AUTOBOT_GUARD_PROFILE", "").strip().lower() or DEFAULT_PROFILE
    if name not in GUARD_PROFILES:
        logger.warning(
            "AUTOBOT_GUARD_PROFILE='%s' is not a known profile (%s); using '%s'.",
            name,
            ", ".join(GUARD_PROFILES),
            DEFAULT_PROFILE,
        )
        return DEFAULT_PROFILE
    return name


def resolve_guard_config_overrides() -> dict[str, object]:
    """Resolve ``AgentLoopConfig`` guard overrides from profile + per-guard env vars.

    Per-guard env vars win over the profile. An empty dict means "no overrides"
    (i.e. the standard profile with no env overrides → today's defaults).
    """
    overrides = dict(GUARD_PROFILES[resolve_profile_name()])
    for env_var, (field_name, parser) in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None or raw.strip() == "":
            continue
        try:
            overrides[field_name] = parser(raw)  # type: ignore[operator]
        except (ValueError, TypeError) as exc:
            logger.warning("Ignoring invalid %s=%r: %s", env_var, raw, exc)
    return overrides
