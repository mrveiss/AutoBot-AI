# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Relative time ("5m ago") comes from the kit's ``formatRelativeTime``, not a hand-built string (#19606).

**The boundary.** The count is every template literal in a ``.vue`` or ``.ts`` file under
``autobot-frontend/src`` and ``autobot-slm-frontend/src`` that interpolates a number and ends in a
unit and the word ``ago`` (``${n}m ago``, ``${n} hours ago``), excluding tests, specs, stories, the
generated API types, the locale files and comment lines. The kit (``libs/autobot-ui``) is not
scanned: ``formatRelativeTime`` there is the one home. A translated key such as
``t('x.minutesAgo', { count })`` holds no ``${...}`` and is not counted.

**What the pin holds.** The remaining sites sit in files an open PR held when this landed
(``BrowserSessionManager``, ``SourceManager``, ``DeviceManagementPanel``). The pin goes down as each
moves to the kit; it never goes up (#19283). The reach floor guards the scan itself: a moved folder
would otherwise read as a clean 0.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table
from repo_tests._reach import declare

_ROOTS = ("autobot-frontend/src", "autobot-slm-frontend/src")
_EXCLUDED = re.compile(r"(\.test\.|\.spec\.|\.stories\.|/__tests__/|/types/generated/|/locales/|/i18n/locales/)")
_UNIT = r"(?:s|m|h|d|w|mo|y|sec|secs|min|mins|hr|hrs|seconds?|minutes?|hours?|days?|weeks?|months?|years?)"
_HAND_BUILT = re.compile(rf"`[^`\n]*\$\{{[^}}`\n]*\}}\s*{_UNIT}\s+ago\b[^`\n]*`")
_COMMENT_LINE = re.compile(r"^[ \t]*(?://|\*|/\*).*$", re.M)

# Measured on origin/main with this detector; lowered as the held files move to the kit.
PINS = {"hand_built_ago_strings": 10}


def _sources(src: Path) -> list[Path]:
    return [
        p
        for p in sorted(src.rglob("*"))
        if p.suffix in (".ts", ".vue")
        and "node_modules" not in p.parts
        and not _EXCLUDED.search("/" + p.relative_to(src).as_posix())
    ]


def _hand_built(path: Path) -> int:
    return len(_HAND_BUILT.findall(_COMMENT_LINE.sub("", path.read_text(encoding="utf-8"))))


def scan(src: Path) -> tuple[int, int]:
    """Return (hand-built strings, files scanned) for one app's ``src``."""
    sources = _sources(src)
    return sum(_hand_built(p) for p in sources), len(sources)


def _population(root: Path) -> list[str]:
    return [p.relative_to(root).as_posix() for rel in _ROOTS for p in _sources(root / rel)]


def verdict(now: int, pinned: int) -> str | None:
    """Why *now* hand-built strings do not match the pin, or None."""
    if now > pinned:
        return (
            f"{now} hand-built relative-time strings, pin allows {pinned} (#19606). "
            "Use formatRelativeTime from @autobot/ui and pass the app's current locale."
        )
    if now < pinned:
        return f"{now} hand-built relative-time strings, pin says {pinned}: lower PINS to {now} in this PR (#19606)."
    return None


# The scan must reach the population, or a moved folder reads as a clean 0.
REACH = declare(
    "frontend-hand-built-relative-time-scan",
    discover=_population,
    floor=1058,  # mid-window: population 1083, window (1033, 1083)
    growth=50,
    what=".ts/.vue sources in both frontends",
    roots=_ROOTS,
)


class TestTheDetectorWorksBeforeItsOutputIsRead:
    def _w(self, src: Path, rel: str, body: str) -> None:
        target = src / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def test_it_counts_each_hand_built_shape(self, tmp_path: Path) -> None:
        self._w(tmp_path, "components/A.vue", "return `${s}s ago`\nreturn `${Math.floor(s / 60)}m ago`\n")
        self._w(tmp_path, "utils/b.ts", "return `${n} hours ago`\n")
        self._w(tmp_path, "views/C.vue", "t('k', `${Math.floor(x / 86400)}d ago`)\n")
        self._w(tmp_path, "views/D.vue", "const s = `Updated ${n} minutes ago`\n")
        assert scan(tmp_path)[0] == 5

    def test_a_kit_call_a_translated_key_and_plain_text_are_not_hand_built(self, tmp_path: Path) -> None:
        body = (
            "formatRelativeTime(x, { locale })\n"
            "t('k.minutesAgo', { count })\n"
            "const s = 'just now'\n"
            "const u = `${n} items`\n"
            "const v = `ago ${n}`\n"
        )
        self._w(tmp_path, "components/A.vue", body)
        assert scan(tmp_path)[0] == 0

    def test_it_skips_tests_stories_generated_types_locales_and_comments(self, tmp_path: Path) -> None:
        self._w(tmp_path, "components/A.test.ts", "`${n}m ago`\n")
        self._w(tmp_path, "components/__tests__/B.ts", "`${n}m ago`\n")
        self._w(tmp_path, "components/C.stories.ts", "`${n}m ago`\n")
        self._w(tmp_path, "types/generated/api.ts", "`${n}m ago`\n")
        self._w(tmp_path, "components/D.vue", "// `${n}m ago`\n * `${n}h ago`\n")
        assert scan(tmp_path)[0] == 0

    def test_a_new_hand_built_string_fires_the_guard(self, tmp_path: Path) -> None:
        self._w(tmp_path, "components/New.vue", "return `${mins}m ago`\n")
        found = scan(tmp_path)[0]
        assert found == 1
        message = verdict(found, 0)
        assert message is not None and "formatRelativeTime" in message

    def test_a_pin_above_the_count_is_asked_to_come_down(self) -> None:
        message = verdict(2, 3)
        assert message is not None and "lower PINS to 2" in message
        assert verdict(3, 3) is None


def test_the_apps_do_not_hand_build_relative_time_beyond_the_pin() -> None:
    root = repo_root()
    for rel in _ROOTS:
        assert (root / rel).is_dir(), f"{rel} has moved; this guard reads it by path"
    now = sum(_hand_built(root / path) for path in REACH.examined(root))
    assert verdict(now, PINS["hand_built_ago_strings"]) is None, verdict(now, PINS["hand_built_ago_strings"])


def test_the_pin_was_not_raised_against_the_base() -> None:
    base = base_table(repo_root(), ("repo_tests/frontend_hand_built_relative_time_19606_test.py",), "PINS")
    if not base:
        return  # the guard is new at this base; nothing to compare against yet
    key = "hand_built_ago_strings"
    assert PINS[key] <= base[key], f"PINS rose from {base[key]} to {PINS[key]} (#19606); the pin only goes down."
