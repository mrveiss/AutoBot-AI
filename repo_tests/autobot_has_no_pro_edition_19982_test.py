# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AutoBot has no Pro or Premium edition, and nothing a user reads may say it does (#19982).

The browser tab title said "AutoBot Pro" on every page. There is no such edition (maintainer
decision, 2026-10-30), so two checks keep it from coming back:

1. **The product name is never followed by "Pro"** in any tracked text file outside changelogs
   (history is allowed to say what it said).
2. **User-facing text never offers AutoBot as a Pro or Premium tier**: the values of the main-app and
   SLM locale files, and the text of the ``.vue`` components of both frontends.

Scope, stated so an empty result is read correctly: check 1 reads every git-tracked file, minus
changelogs and this file (whose control strings spell the phrase on purpose). Check 2 reads only the
two frontends' ``src`` trees; it does not read backend strings, docs or mockups. Check 2's patterns
are tier phrases (``premium`` as a word, ``pro`` followed by edition/plan/tier/..., "upgrade to
pro"), not the bare word ``pro``, so another vendor's plan named in a hint is not a hit unless it uses
those phrases. Both checks fail below their reach floor, and the detectors are proven to fire on
control strings.

NOT in scope, by decision on #19982: other vendors' plans (``docs/backend/llm-fallback.md``, the
HuggingFace token hint), the sample attack phrase in ``query_sanitizer.py``, the mockup's sample plugin
"PDF Ingest Pro", and the logging-destination doc. None names an AutoBot edition. ``_ALLOWED`` is the
narrow place to record a future exception, as ``(path, exact text)``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_THIS_FILE = "repo_tests/autobot_has_no_pro_edition_19982_test.py"
_CHANGELOG_GLOBS = ("*CHANGELOG*", "*Changelog*", "*changelog*")
_FRONTEND_SRC = ("autobot-frontend/src", "autobot-slm-frontend/src")
_LOCALE_DIRS = ("autobot-frontend/src/i18n/locales/", "autobot-slm-frontend/src/locales/")

#: The product name followed by Pro, with any of the separators it is written with.
PRO_NAME = re.compile(r"\bauto[\s_-]?bot[\s_-]?pro\b", re.IGNORECASE)

#: A tier offered to a user: "premium" as a word, "Pro" naming an edition, or an upgrade prompt.
TIER_OFFER = re.compile(
    r"\bpremium\b"
    r"|\bpro[\s-]+(?:edition|plan|tier|version|license|licence|subscription|features?|users?|only)\b"
    r"|\b(?:upgrade|go|switch)\s+to\s+pro\b"
    r"|\b(?:requires?|needs?)\s+(?:a\s+)?pro\b",
    re.IGNORECASE,
)

#: (repo-relative path, exact text) pairs allowed to match TIER_OFFER. Empty: every match is a defect.
_ALLOWED: frozenset[tuple[str, str]] = frozenset()


def _tracked(root: Path, *patterns: str, exclude: tuple[str, ...] = ()) -> list[str]:
    try:
        return tracked_paths(root, *patterns, exclude=exclude)
    except EmptyEnumeration:
        return []


def _name_population(root: Path) -> list[str]:
    return [p for p in _tracked(root, ".", exclude=_CHANGELOG_GLOBS) if p != _THIS_FILE]


def _user_text_population(root: Path) -> list[str]:
    found = _tracked(root, *_FRONTEND_SRC)
    return [p for p in found if p.endswith(".vue") or (p.endswith(".json") and p.startswith(_LOCALE_DIRS))]


#: Measured 2026-10-30: ~12.7k tracked files; the floor is re-pinned mid-window by scripts/repin_reach_floors.py.
NAME_REACH = declare(
    "autobot-has-no-pro-name",
    discover=_name_population,
    what="tracked non-changelog files",
    floor=12746,  # mid-window: population 12946, window (12546, 12946)
    growth=400,
)

USER_TEXT_REACH = declare(
    "autobot-has-no-pro-tier-in-user-text",
    discover=_user_text_population,
    what="frontend .vue components and locale files",
    floor=407,  # mid-window: population 607, window (207, 607)
    growth=400,
    roots=_FRONTEND_SRC,
)


def name_hits(text: str) -> list[str]:
    """Every spelling of the product name followed by Pro in *text*."""
    return [m.group(0) for m in PRO_NAME.finditer(text)]


def tier_hits(text: str) -> list[str]:
    """Every tier offer in *text*."""
    return [m.group(0) for m in TIER_OFFER.finditer(text)]


def _strings(node: object):
    """Every string VALUE of a parsed locale file; keys are identifiers, not user text."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def _user_texts(root: Path, rel: str) -> list[str]:
    raw = (root / rel).read_text(encoding="utf-8", errors="replace")
    return list(_strings(json.loads(raw))) if rel.endswith(".json") else raw.splitlines()


def test_the_product_name_is_never_followed_by_pro() -> None:
    root = repo_root()
    offenders = []
    for rel in NAME_REACH.examined(root):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        offenders.extend(f"{rel}: {hit!r}" for hit in name_hits(text))
    assert not offenders, "There is no AutoBot Pro edition (#19982); the product is AutoBot:\n" + "\n".join(offenders)


def test_user_facing_text_never_offers_autobot_as_pro_or_premium() -> None:
    root = repo_root()
    offenders = []
    for rel in USER_TEXT_REACH.examined(root):
        for text in _user_texts(root, rel):
            offenders.extend(f"{rel}: {hit!r}" for hit in tier_hits(text) if (rel, text.strip()) not in _ALLOWED)
    assert (
        not offenders
    ), "There is no Pro or Premium AutoBot (#19982); reword, or record a narrow allowance in _ALLOWED:\n" + "\n".join(
        offenders
    )


def test_the_name_detector_fires_on_every_spelling() -> None:
    """Control strings: if this passes while the tree is clean, a clean result means something."""
    for control in ("AutoBot Pro", "autobot pro", "AUTOBOT-PRO", "Auto_Bot_Pro", "- AutoBot Pro"):
        assert name_hits(f"title: {control}"), control
    for fine in ("AutoBot Process", "AutoBot Project", "AutoBot", "autobot-pro" + "ject"):
        assert not name_hits(fine), fine


def test_the_tier_detector_fires_on_offers_and_not_on_other_text() -> None:
    for control in (
        "Creative & Premium",
        "Unlock Premium",
        "Pro edition",
        "the Pro plan",
        "Pro-only feature",
        "Upgrade to Pro",
        "Go to pro",
        "requires a Pro licence",
    ):
        assert tier_hits(control), control
    for fine in (
        "Creative & Elegant",
        "Uses your HuggingFace account token (PRO or Inference API access required).",
        "Production architecture",
        "improve the process",
        "PDF Ingest Pro",
    ):
        assert not tier_hits(fine), fine


def test_the_user_text_scan_reads_locale_values_and_ignores_keys() -> None:
    parsed = json.loads('{"premium": {"label": "Fine", "list": ["Go to pro", "Plain"]}}')
    texts = list(_strings(parsed))
    assert texts == ["Fine", "Go to pro", "Plain"]
    assert [t for t in texts if tier_hits(t)] == ["Go to pro"]


def test_both_scans_read_the_locale_files_of_both_frontends() -> None:
    root = repo_root()
    read = set(USER_TEXT_REACH.examined(root))
    for prefix in _LOCALE_DIRS:
        assert any(p.startswith(prefix) and p.endswith(".json") for p in read), prefix
    assert any(p.endswith(".vue") for p in read)
    assert _THIS_FILE not in set(NAME_REACH.examined(root))
