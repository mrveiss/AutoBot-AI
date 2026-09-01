# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One concept, one implementation — fragmentation may shrink, never grow (#12730, #12731).

The design system is advisory rather than enforced, so the same concept is
implemented several incompatible ways and appearance varies by which view you
happen to be in. #12731 records four dimensions of this. Measuring them found
the picture is directionally right and, in one case, far worse than filed:

* **Button classes.** #12731 describes "2 per-view button-class systems"
  (`btn-primary` and `btn-action-primary`). The real shape is that there is no
  canonical definition at all: 102 files declare a `.btn-*` rule, 380 rule
  declarations in total, across 115 distinct class names — and shared
  stylesheets (`assets/tailwind.css`, `assets/vue-notus.css`) already define
  `btn-primary`, so every one of those views is redefining something that
  exists. The counts have grown since filing, not shrunk (`btn-primary` usages
  85 -> 210).
* **Notification.** Four entry points — `useToast`, `useNotificationConfig`,
  `NotificationBridge`, `showNotification`. Smaller than #12731's figures,
  which counted word occurrences rather than modules; `useNotification` and
  `$toast` are already gone.
* **Date formatting.** Four approaches: `toLocaleString`, `formatDate`,
  `toLocaleDateString`, `Intl.DateTimeFormat`.
* **z-index.** 52 hardcoded declarations, with no scale, so
  stacking order is decided per file.

This guard does not consolidate any of it — that is many PRs' work across
#12730. It exists so the job is finite: the numbers may only move one way while
that work proceeds.

**Fails in BOTH directions**, matching `python_file_size_ratchet_baseline.py`
and the contract ratchet. Growth is a regression; an unrecorded *shrink* is
also a failure, because a baseline that drifts below the real number stops
being evidence — lower the constant in the commit that does the work.

Counting is textual. These are `.vue` single-file components mixing template,
script and style, and a Python guard cannot parse them without a TypeScript and
CSS toolchain that CI would then have to keep working. A stable regex that is
slightly over-inclusive is worth more than an exact count that breaks: what is
asserted is the direction of the number, not its absolute truth.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_FRONTEND_SRC = _REPO_ROOT / "autobot-frontend" / "src"

_SOURCE_SUFFIXES = (".ts", ".vue", ".css", ".scss")

# Floor, not a census: a walk that stops matching must fail loudly rather than
# pass by reaching nothing.
_MIN_SOURCE_FILES = 500

# --- The ratchet ---------------------------------------------------------
#
# Lower these as consolidation lands. Never raise one to make a new view pass:
# use the shared definition instead of declaring another local one.

BASELINE = {
    # Files declaring at least one `.btn-*` CSS rule. Target is 1 — a single
    # shared stylesheet.
    "button_definition_files": 102,
    # Distinct `.btn-*` class names declared anywhere.
    "button_class_names": 115,
    # Distinct notification entry points. Target is 1 canonical API, the rest
    # thin shims or removed.
    "notification_entry_points": 4,
    # Distinct date-formatting approaches in use.
    "date_format_approaches": 4,
    # Hardcoded `z-index: <number>` declarations, i.e. stacking order decided
    # per file rather than by a scale.
    "hardcoded_zindex_declarations": 52,
}

_BTN_RULE_RE = re.compile(r"^\s*\.(btn-[a-z0-9-]+)\s*[,{]", re.MULTILINE)
_ZINDEX_RE = re.compile(r"^\s*z-index:\s*-?\d+", re.MULTILINE)

_NOTIFICATION_ENTRY_POINTS = (
    "useToast",
    "useNotificationConfig",
    "NotificationBridge",
    "showNotification",
)

_DATE_FORMAT_APPROACHES = {
    "toLocaleDateString": re.compile(r"\btoLocaleDateString\s*\("),
    "toLocaleString": re.compile(r"\btoLocaleString\s*\("),
    "Intl.DateTimeFormat": re.compile(r"\bIntl\.DateTimeFormat\s*\("),
    "formatDate": re.compile(r"\bformatDate\s*\("),
}


def _is_test(path: Path) -> bool:
    """Test scaffolding is not product surface.

    A spec asserting on a button class or a formatted date is not another
    implementation of the concept; counting it would make the ratchet grow
    whenever someone adds coverage.
    """
    return "__tests__" in path.parts or ".test." in path.name or ".spec." in path.name


def _source_files() -> list[Path]:
    return [
        path
        for path in sorted(_FRONTEND_SRC.rglob("*"))
        if path.suffix in _SOURCE_SUFFIXES
        and path.is_file()
        and "node_modules" not in path.parts
        and not _is_test(path)
    ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _measure() -> dict[str, int]:
    button_files = 0
    button_names: set[str] = set()
    zindex = 0
    notification: set[str] = set()
    dates: set[str] = set()

    for path in _source_files():
        text = _read(path)

        names = _BTN_RULE_RE.findall(text)
        if names:
            button_files += 1
            button_names.update(names)

        zindex += len(_ZINDEX_RE.findall(text))

        for entry in _NOTIFICATION_ENTRY_POINTS:
            if re.search(rf"\b{re.escape(entry)}\b", text):
                notification.add(entry)

        for label, pattern in _DATE_FORMAT_APPROACHES.items():
            if pattern.search(text):
                dates.add(label)

    return {
        "button_definition_files": button_files,
        "button_class_names": len(button_names),
        "notification_entry_points": len(notification),
        "date_format_approaches": len(dates),
        "hardcoded_zindex_declarations": zindex,
    }


_ADVICE = {
    "button_definition_files": "Use the shared button styles rather than redeclaring `.btn-*` in another view.",
    "button_class_names": "Reuse an existing button class rather than inventing another name for the same role.",
    "notification_entry_points": "Route through the canonical notification API; additional entry points should be thin shims or removed.",
    "date_format_approaches": "Use the shared date formatter rather than another `toLocale*`/`Intl` call.",
    "hardcoded_zindex_declarations": "Take the value from the z-index scale rather than hardcoding a number.",
}


def test_the_tree_this_guard_reads_is_present() -> None:
    """A moved frontend would make every count zero, and zero passes."""
    assert _FRONTEND_SRC.is_dir(), f"{_FRONTEND_SRC} is missing — this guard is pinned to the wrong path"

    found = len(_source_files())
    assert found >= _MIN_SOURCE_FILES, (
        f"only {found} source file(s) found, expected at least {_MIN_SOURCE_FILES} — the walk has "
        "stopped reaching the frontend, which would make every ratchet below pass by counting nothing"
    )


@pytest.mark.parametrize("dimension", sorted(BASELINE))
def test_fragmentation_only_shrinks(dimension: str) -> None:
    """Growth is a regression; an unrecorded shrink is a stale baseline."""
    actual = _measure()[dimension]
    baseline = BASELINE[dimension]

    assert actual <= baseline, (
        f"{dimension} is {actual}, ratchet allows {baseline} (#12730, #12731).\n{_ADVICE[dimension]}"
    )
    assert actual == baseline, (
        f"{dimension} is down to {actual} but the baseline still says {baseline} — "
        "lower it in the commit that did the work, so the number stays a deliberate claim"
    )
