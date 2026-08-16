# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""``company_id`` must not diverge further in type (#14312).

The LLC module declares ``company_id`` two ways: ``UUID(as_uuid=True)`` in most
models, and ``String(255)`` in four. Both describe the same thing — the primary
key of a row in ``organizations`` — and the same column is already compared both
ways in live code (``goal.py`` passes the raw value, ``portability.py`` wraps it
in ``str()``).

Converting the four is a real change with a real blast radius: 225
``company_id: str`` declarations and 88 ``str(company_id)`` coercions, against a
live shared schema. It is tracked in #14312 and is not attempted here.

What this file does is stop the split **growing**. It asserts the divergent set
is exactly the four known models — so a fifth fails, and fixing one also fails
until this list is updated. A ratchet, not an allowlist: an allowlist quietly
tolerates whatever is in it, and a stale exemption naming a moved file exempts
nothing while still reading as coverage.

Deliberately parsed from source rather than from the mapped columns, because
importing every LLC model to inspect it drags in the whole application graph and
would make this guard fail for reasons unrelated to what it guards.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict

_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

#: Models that still declare company_id as a string. Shrinking this is #14312;
#: growing it is the regression this file exists to catch.
_KNOWN_STRING_TYPED = {"secret.py", "goal.py", "budget.py", "api_key.py"}

# Matches the column type in `company_id: Mapped[...] = mapped_column(<TYPE>,`
# across both declaration styles used in this package.
_COMPANY_ID = re.compile(
    r"company_id:\s*Mapped\[[^\]]+\]\s*=\s*mapped_column\(\s*\n?\s*([A-Za-z_.]+(?:\([^)]*\))?)",
    re.M,
)


def _declared_types() -> Dict[str, str]:
    """Map model filename -> the type company_id is declared with."""
    found: Dict[str, str] = {}
    for path in sorted(_MODELS_DIR.glob("*.py")):
        match = _COMPANY_ID.search(path.read_text(encoding="utf-8"))
        if match:
            found[path.name] = match.group(1)
    return found


def test_the_parser_actually_finds_the_models() -> None:
    """Presence check first.

    A regex that matches nothing makes every assertion below pass while
    verifying nothing — an empty result reading as a clean result. The exact
    count is deliberately not pinned, only that the parser sees a realistic
    number of models and all four known string-typed ones.
    """
    declared = _declared_types()
    assert len(declared) >= 15, f"parser found only {len(declared)} models: {sorted(declared)}"
    missing = _KNOWN_STRING_TYPED - set(declared)
    assert not missing, f"parser failed to see known models: {sorted(missing)}"


def test_no_new_model_declares_company_id_as_a_string() -> None:
    """The ratchet: the string-typed set must be exactly the four known ones."""
    declared = _declared_types()
    string_typed = {name for name, type_ in declared.items() if "String" in type_ or "Text" in type_}

    unexpected = string_typed - _KNOWN_STRING_TYPED
    assert not unexpected, (
        f"new model(s) declare company_id as a string: {sorted(unexpected)}. "
        "company_id is the primary key of an organizations row — declare it "
        "UUID(as_uuid=True). See #14312."
    )

    fixed = _KNOWN_STRING_TYPED - string_typed
    assert not fixed, (
        f"{sorted(fixed)} no longer declare company_id as a string — good. "
        "Remove them from _KNOWN_STRING_TYPED so the ratchet keeps its grip."
    )


def test_every_other_model_uses_the_uuid_type() -> None:
    """The positive half: everything outside the known set must be UUID.

    Asserting only "no new strings" would miss a model declaring company_id as,
    say, an Integer — a different divergence with the same root cause.
    """
    offenders = {
        name: type_
        for name, type_ in _declared_types().items()
        if name not in _KNOWN_STRING_TYPED and "UUID" not in type_.upper()
    }
    assert not offenders, f"company_id declared with a non-UUID type: {offenders}"
