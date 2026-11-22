# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unknown ``AUTOBOT_*`` keys: the nearest-match suggestion and the warn-vs-refuse policy (#17419).

Detection lives in ``env_drift_detector``; this module is the policy over what it found, so
warn-versus-refuse is one switch. Every settings model reads the same ``.env`` with
``extra="ignore"``, so a mistyped key is dropped and the field keeps its default. ``extra="forbid"``
is not the fix (the process environment legitimately carries unrelated variables); the detector is
scoped to the ``AUTOBOT_`` namespace instead.

The refuse step is announced, not sudden: until ``UNKNOWN_KEY_REFUSE_AFTER`` an unknown key only
warns, and the message says when that ends. On and after it the policy resolves to ``refuse``.
"""

from __future__ import annotations

import difflib
import inspect
import re
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Iterable, Iterator

if TYPE_CHECKING:  # annotations only: the runtime import is lazy
    from pydantic_settings import BaseSettings

#: Unknown ``AUTOBOT_*`` keys warn before this date and are refused on and after it.
UNKNOWN_KEY_REFUSE_AFTER = date(2027, 3, 1)
POLICY_WARN = "warn"
POLICY_REFUSE = "refuse"
#: ``difflib`` ratio below which two names are not offered as "did you mean".
SUGGESTION_CUTOFF = 0.8
_NAMESPACE = "AUTOBOT_"
#: ``LLMConfig.get_provider_for_agent`` reads ``AUTOBOT_<AGENT_ID>_PROVIDER`` at runtime for any agent id, so the
#: agent segment is open-ended and cannot be listed. The ``_PROVIDER`` suffix is the contract: a key ending in it
#: is a supported override, and a misspelt suffix (``_PROVIDR``) or prefix (``AUTOBOT_`` mistyped) still fails.
_AGENT_PROVIDER_OVERRIDE = re.compile(r"AUTOBOT_[A-Z0-9]+(?:_[A-Z0-9]+)*_PROVIDER")


def is_agent_provider_override(key: str) -> bool:
    """True for a per-agent provider override: supported at runtime though no model field declares it."""
    return _AGENT_PROVIDER_OVERRIDE.fullmatch(key) is not None


def resolve_policy(today: date | None = None, *, deadline: date = UNKNOWN_KEY_REFUSE_AFTER) -> str:
    """``refuse`` on and after *deadline*, ``warn`` before it; *today* defaults to the current UTC date."""
    now = today or datetime.now(timezone.utc).date()
    return POLICY_REFUSE if now >= deadline else POLICY_WARN


def suggest_key(key: str, declared: Iterable[str]) -> str | None:
    """The declared name closest to *key*, or ``None`` when nothing is close enough to be a typo of it."""
    matches = difflib.get_close_matches(key, sorted(declared), n=1, cutoff=SUGGESTION_CUTOFF)
    return matches[0] if matches else None


def describe_unknown_key(
    key: str, suggestion: str | None, policy: str, *, deadline: date = UNKNOWN_KEY_REFUSE_AFTER
) -> str:
    """One finding, in words an operator can act on; the date is read from *deadline*, never retyped."""
    parts = [f"{_NAMESPACE} key '{key}' is declared by no settings model and no registry entry"]
    if suggestion:
        parts.append(f"did you mean '{suggestion}'?")
    if policy == POLICY_REFUSE:
        parts.append(f"unknown keys are refused since {deadline.isoformat()}")
    else:
        parts.append(f"unknown keys will be refused from {deadline.isoformat()}")
    return "; ".join(parts)


def _field_names(field) -> set[str]:
    from pydantic import AliasChoices  # lazy: policy and message helpers stay importable without pydantic

    validation = field.validation_alias
    choices = validation.choices if isinstance(validation, AliasChoices) else [validation]
    return {n for n in (field.alias, *choices) if isinstance(n, str) and n.startswith(_NAMESPACE)}


def _settings_classes(module) -> Iterator[type[BaseSettings]]:
    from pydantic_settings import BaseSettings

    for value in vars(module).values():
        if inspect.isclass(value) and issubclass(value, BaseSettings) and value is not BaseSettings:
            yield value


def declared_env_names() -> set[str]:
    """Every ``AUTOBOT_*`` name an SSOT settings model binds or the env registry registers."""
    from autobot_shared import ssot_config
    from autobot_shared.env_registry import REGISTRY

    names = {name for name in REGISTRY if name.startswith(_NAMESPACE)}
    for cls in _settings_classes(ssot_config):
        for field in cls.model_fields.values():
            names |= _field_names(field)
    return names
