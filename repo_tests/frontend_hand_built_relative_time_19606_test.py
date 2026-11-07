# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Relative time ("5m ago") comes from the kit's ``createRecencyFormatter``, never a hand-built ladder (#19606).

This is the ONE guard for the class. Each shape of "build the words yourself" is a key of ``PINS``,
all counted over the same scanned files: every ``.vue`` or ``.ts`` file under ``autobot-frontend/src``
and ``autobot-slm-frontend/src``, excluding tests, specs, stories, the generated API types, the locale
files and comment lines. The kit (``libs/autobot-ui``) is not scanned: it is the one home.

**The shapes.**

- ``hand_built_ago_strings`` (shape B): a template literal that interpolates a number and ends in a unit
  and the word ``ago`` (``${n}m ago``, ``${n} hours ago``).
- ``translated_ago_ladders`` (shape A): a call that passes an interpolation object to a translated
  "<n> <unit> ago" key, ``t('secrets.auditLog.hoursAgo', { hours })`` -- the threshold ladder over keys
  that ``createRecencyFormatter`` replaces. The detector is the code shape, not the key list: a key with
  no ``Ago`` in its name (``t('k.justNow')``, ``t('x.expiresIn', { time })``) is not counted. It looks at
  the call, so ``t('k.minutesAgo', { count })`` is invisible to the first key and counted by this one.
- ``translated_ago_values`` (shape D, the locale files holding the orphaned "... ago" keys) is NOT here
  yet: the locale files are held by open PRs, so that key is added in the follow-up that removes the
  keys, with the same table and the same down-only comparison.

**What the pins hold.** Nothing: both are 0 and any new site fails (#19283). The reach floor guards the
scan itself: a moved folder would otherwise read as a clean 0.
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

# Measured on origin/main with these detectors; each key only goes down.
PINS = {"hand_built_ago_strings": 0, "translated_ago_ladders": 0}
_TRANSLATED = re.compile(
    r"""(?:(?<![\w.])|(?<=\bglobal\.))\$?t\(\s*['"][\w.]*(?:seconds?|minutes?|hours?|days?)Ago['"]\s*,\s*\{"""
)


def _sources(src: Path) -> list[Path]:
    return [
        p
        for p in sorted(src.rglob("*"))
        if p.suffix in (".ts", ".vue")
        and "node_modules" not in p.parts
        and not _EXCLUDED.search("/" + p.relative_to(src).as_posix())
    ]


def _code(path: Path) -> str:
    return _COMMENT_LINE.sub("", path.read_text(encoding="utf-8"))


def _hand_built(path: Path) -> int:
    return len(_HAND_BUILT.findall(_code(path)))


def _translated(path: Path) -> int:
    return len(_TRANSLATED.findall(_code(path)))


_DETECTORS = {
    "hand_built_ago_strings": _hand_built,
    "translated_ago_ladders": _translated,
}


def scan(src: Path) -> tuple[int, int]:
    """Return (hand-built strings, files scanned) for one app's ``src``."""
    sources = _sources(src)
    return sum(_hand_built(p) for p in sources), len(sources)


def _population(root: Path) -> list[str]:
    return [p.relative_to(root).as_posix() for rel in _ROOTS for p in _sources(root / rel)]


def verdict(now: int, pinned: int, key: str = "hand_built_ago_strings") -> str | None:
    """Why *now* sites of shape *key* do not match the pin, or None."""
    if now > pinned:
        return (
            f"{now} {key}, pin allows {pinned} (#19606). "
            "Use createRecencyFormatter (or formatRelativeTime) from @autobot/ui and pass the app's current locale."
        )
    if now < pinned:
        return f"{now} {key}, pin says {pinned}: lower PINS[{key!r}] to {now} in this PR (#19606)."
    return None


# The scan must reach the population, or a moved folder reads as a clean 0.
REACH = declare(
    "frontend-hand-built-relative-time-scan",
    discover=_population,
    growth=50,
    what=".ts/.vue sources in both frontends",
    roots=_ROOTS,
)


def _ladders(text: str) -> int:
    return len(_TRANSLATED.findall(text))


class TestTheDetectorWorksBeforeItsOutputIsRead:
    def _w(self, src: Path, rel: str, body: str) -> None:
        target = src / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def test_it_counts_each_hand_built_shape(self, tmp_path: Path) -> None:
        self._w(
            tmp_path,
            "components/A.vue",
            "return `${s}s ago`\nreturn `${Math.floor(s / 60)}m ago`\n",
        )
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

    def test_a_translated_ago_key_with_values_is_counted_by_the_second_key_not_the_first(self, tmp_path: Path) -> None:
        self._w(tmp_path, "components/A.vue", "return t('k.minutesAgo', { count })\n")
        assert scan(tmp_path)[0] == 0
        assert _translated(tmp_path / "components/A.vue") == 1

    def test_the_translated_ladder_detector_has_controls(self) -> None:
        assert _ladders("t('k.hoursAgo', { hours })") == 1  # positive control
        assert _ladders("{{ $t('k.daysAgo', { days }) }}") == 1
        assert _ladders("i18n.global.t('k.minutesAgo', { n })") == 1
        assert _ladders("$t('k.minutesAgo', { n })") == 1
        assert _ladders("obj.t('k.minutesAgo', { n })") == 0
        assert _ladders("t(\n  'k.secondsAgo',\n  { n }\n)") == 1
        assert _ladders("t('k.justNow')") == 0  # negative controls
        assert _ladders("t('security.secretsManager.expiresIn', { time: x })") == 0
        assert _ladders("format('k.hoursAgo', { hours })") == 0

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
        assert message is not None and "lower PINS['hand_built_ago_strings'] to 2" in message
        assert verdict(3, 3) is None


def test_the_apps_do_not_hand_build_relative_time_beyond_the_pins() -> None:
    root = repo_root()
    for rel in _ROOTS:
        assert (root / rel).is_dir(), f"{rel} has moved; this guard reads it by path"
    paths = REACH.examined(root)
    assert PINS.keys() == _DETECTORS.keys()
    for key, detect in _DETECTORS.items():
        now = sum(detect(root / path) for path in paths)
        assert verdict(now, PINS[key], key) is None, verdict(now, PINS[key], key)


def test_the_pin_was_not_raised_against_the_base() -> None:
    base = base_table(
        repo_root(),
        ("repo_tests/frontend_hand_built_relative_time_19606_test.py",),
        "PINS",
    )
    if not base:
        return  # the guard is new at this base; nothing to compare against yet
    for key, pinned in PINS.items():
        if key in base:  # a measure the base did not have starts at its first measurement
            assert (
                pinned <= base[key]
            ), f"PINS[{key!r}] rose from {base[key]} to {pinned} (#19606); the pin only goes down."
