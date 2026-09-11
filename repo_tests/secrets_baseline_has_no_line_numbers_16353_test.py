# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``.secrets.baseline`` must carry no ``line_number`` field (#16353).

The detect-secrets pre-commit hook rewrites the baseline whenever a staged file
with findings gains or loses lines, even when no finding is added or removed:
``trim()`` (``secrets_collection.py:180-182``, v1.5.0) copies the fresh scan's
line number onto every stored entry whose own ``line_number`` is non-zero. Two
PRs that only shift lines in the same file then conflict in the baseline, and
whichever lands second regenerates -- and rewrites -- it again.

Stripping the field breaks that cycle without touching the upstream hook. A
loaded entry with no ``line_number`` defaults to 0 (``potential_secret.py:30``,
``:83-90``), ``trim()``'s guard is false for a zero, so it is never overwritten,
and ``json()`` omits a zero field on write (``potential_secret.py:107-108``).
detect-secrets' own identity for a finding is ``(filename, secret_hash, type)``
(``secrets_collection.py:51-54``) -- line-independent already -- so a stripped
baseline stays stripped through the hook, and a line-only move produces no diff.

A *regenerate* reintroduces the field: ``detect-secrets scan --baseline``
re-adds ``line_number`` when it merges a fresh scan into the baseline
(``main.py:85-87``), and ``--slim`` is ignored together with ``--baseline``. So
the strip below is a step to repeat after any regenerate, not a one-time edit --
this guard is what catches a regenerate that skipped it, before the next PR's
line-only diff does instead.
"""

from __future__ import annotations

import functools
import importlib.util
import json
import sys
from types import ModuleType

from repo_tests._paths import repo_root

_REPO_ROOT = repo_root()
_BASELINE = _REPO_ROOT / ".secrets.baseline"
_FLOOR_GATE = _REPO_ROOT / "pipeline-scripts" / "secrets_rescan_floor.py"

_STRIP_COMMAND = "jq --indent 2 'del(.results[][].line_number)' .secrets.baseline > tmp && mv tmp .secrets.baseline"
_WHY = (
    "detect-secrets scan --baseline re-adds line_number when it merges a fresh scan into the "
    "baseline, and --slim is ignored together with --baseline -- so a regenerated baseline "
    "needs this strip re-applied."
)


@functools.lru_cache(maxsize=None)
def _floor_gate() -> ModuleType:
    """The same rescan-floor script the CI gate and ``no_tracked_key_material_test.py`` use."""
    spec = importlib.util.spec_from_file_location("_secrets_rescan_floor_16353", _FLOOR_GATE)
    assert spec is not None and spec.loader is not None, f"cannot load {_FLOOR_GATE}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _offenders(results: dict) -> list[str]:
    """Every entry that still carries ``line_number``, rendered without its hash value."""
    return [
        f"{path}: {entry.get('type', '?')} hashed_secret={entry.get('hashed_secret', '?')}"
        for path, entries in results.items()
        for entry in entries
        if "line_number" in entry
    ]


def test_baseline_carries_no_line_numbers() -> None:
    """Line-only moves must not touch the committed baseline (#16353)."""
    baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
    results = baseline.get("results")
    assert isinstance(results, dict) and results, (
        f"{_BASELINE} holds no results -- an empty or unparsed baseline proves nothing; "
        "this guard needs a real population to check"
    )
    floor = _floor_gate().FLOOR
    total = sum(len(entries) for entries in results.values())
    assert total >= floor, (
        f"{_BASELINE} holds {total} entries, below the {floor}-entry floor "
        "pipeline-scripts/secrets_rescan_floor.py enforces -- too few to trust this guard's verdict"
    )
    offenders = _offenders(results)
    assert not offenders, (
        f"{len(offenders)} baseline entr{'y' if len(offenders) == 1 else 'ies'} still "
        "carr" + ("ies" if len(offenders) == 1 else "y") + " a line_number, so the next line "
        "move in that file will rewrite the baseline again:\n"
        + "\n".join(offenders[:10])
        + f"\n\nRe-strip it: {_STRIP_COMMAND}\nWhy: {_WHY}"
    )


def _fake_entry(with_line_number: bool) -> dict:
    """A baseline-shaped entry. Not a secret -- a placeholder hash, never scanned as one."""
    fake_hash = "not-a-real-hash"  # pragma: allowlist secret
    entry = {"type": "Secret Keyword", "hashed_secret": fake_hash}  # pragma: allowlist secret
    if with_line_number:
        entry["line_number"] = 7
    return entry


def test_a_planted_line_number_is_caught() -> None:
    """Self-test: the detector actually looks, on a baseline it knows is wrong."""
    planted = {"planted.py": [_fake_entry(with_line_number=True)]}
    hash_value = _fake_entry(with_line_number=False)["hashed_secret"]
    assert _offenders(planted) == [f"planted.py: Secret Keyword hashed_secret={hash_value}"]


def test_offenders_is_empty_on_a_stripped_entry() -> None:
    """Self-test's other half: an entry with the field already removed is not an offender."""
    clean = {"clean.py": [_fake_entry(with_line_number=False)]}
    assert _offenders(clean) == []
