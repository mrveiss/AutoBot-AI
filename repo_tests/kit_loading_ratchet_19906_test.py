# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Loading states use the kit's spinner and skeleton, not hand-rolled ones (#19906).

**The boundary.** Two counts over every ``.vue`` and ``.css`` file under ``autobot-frontend/src``,
``autobot-slm-frontend/src`` and ``autobot-plugins`` (no ``node_modules``/``dist``, no tests,
specs or stories, no comment lines):

* ``local_keyframes_spin`` -- a ``@keyframes spin`` declaration. The kit owns the one rotation
  (``aui-spin`` in ``BaseSpinner``); a local ``spin`` is a hand-rolled spinner.
* ``utility_spin_lines`` -- a line carrying the ``animate-spin`` or ``fa-spin`` class.

**What is deferred.** Both pins are down-only. The first batch moved 15 of the 30 ``@keyframes
spin`` onto the kit and 4 ``animate-spin`` lines with them. The 15 left are 12 files held by open
PRs, two shared design-system stylesheets whose ``.spinner`` class other views still consume, and
the VNC plugin, which does not depend on the kit. Each later batch lowers the pins.

**One number per pattern, not a per-file table**, for the reason given in
``slm_raw_setinterval_ratchet_19482_test.py``. The reach floor guards the scan itself: a moved
folder would otherwise read as a clean 0.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table
from repo_tests._reach import declare

_ROOTS = ("autobot-frontend/src", "autobot-slm-frontend/src", "autobot-plugins")
_SKIPPED = re.compile(r"(/node_modules/|/dist/|\.test\.|\.spec\.|\.stories\.|/__tests__/)")
_KEYFRAMES = re.compile(r"@keyframes\s+spin(?![\w-])")
_UTILITY = re.compile(r"\b(?:animate-spin|fa-spin)(?![\w-])")
_COMMENT_LINE = re.compile(r"^[ \t]*(?://|\*|/\*).*$", re.M)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/|<!--.*?-->", re.S)


def _code_only(text: str) -> str:
    """*text* with block comments blanked (newlines kept) and comment lines dropped."""
    blanked = _BLOCK_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return _COMMENT_LINE.sub("", blanked)


# 30 and 321 measured on bb5f0299e0; 15 and 317 after the first batch.
PINS = {"local_keyframes_spin": 15, "utility_spin_lines": 315}


def _sources(base: Path) -> list[Path]:
    """The ``.vue`` and ``.css`` sources under one root."""
    found = []
    for path in sorted(base.rglob("*")):
        if path.suffix in (".vue", ".css") and not _SKIPPED.search("/" + path.relative_to(base).as_posix()):
            found.append(path)
    return found


def counts(base: Path) -> tuple[int, int]:
    """Return (local ``@keyframes spin``, ``animate-spin``/``fa-spin`` lines) under ``base``."""
    keyframes = utility = 0
    for path in _sources(base):
        text = _code_only(path.read_text(encoding="utf-8"))
        keyframes += len(_KEYFRAMES.findall(text))
        utility += sum(1 for line in text.splitlines() if _UTILITY.search(line))
    return keyframes, utility


def _population(root: Path) -> list[str]:
    return [p.relative_to(root).as_posix() for rel in _ROOTS for p in _sources(root / rel)]


# The scan must reach the population, or a moved folder reads as a clean 0.
REACH = declare(
    "frontend-hand-rolled-spinner-scan",
    discover=_population,
    floor=593,  # mid-window: population 618, window [568, 618] (#19906)
    growth=50,
    what="vue and css sources of both frontends and the plugins",
    roots=_ROOTS,
)


class TestTheDetectorWorksBeforeItsOutputIsRead:
    def _w(self, base: Path, rel: str, body: str) -> None:
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def test_it_counts_a_local_keyframes_spin(self, tmp_path: Path) -> None:
        self._w(tmp_path, "A.vue", "<style>\n@keyframes spin {\n  to { transform: rotate(360deg); }\n}\n</style>\n")
        self._w(tmp_path, "b.css", "@keyframes spin { to { transform: rotate(360deg); } }\n")
        assert counts(tmp_path) == (2, 0)

    def test_it_counts_each_utility_spin_line(self, tmp_path: Path) -> None:
        self._w(tmp_path, "A.vue", '<i class="fas fa-spin"></i>\n<svg class="h-4 animate-spin"></svg>\n')
        assert counts(tmp_path) == (0, 2)

    def test_the_kit_keyframe_a_longer_name_a_comment_and_tests_are_not_counted(self, tmp_path: Path) -> None:
        self._w(tmp_path, "A.vue", "@keyframes aui-spin { }\n@keyframes spin-slow { }\n// animate-spin\n")
        self._w(tmp_path, "A.stories.vue", "@keyframes spin { }\n")
        self._w(tmp_path, "node_modules/x/B.vue", "@keyframes spin { }\n")
        assert counts(tmp_path) == (0, 0)

    def test_a_multiline_block_comment_and_a_trailing_comment_are_not_counted(self, tmp_path: Path) -> None:
        self._w(tmp_path, "A.vue", '/*\n@keyframes spin {\n}\n  animate-spin\n*/\n<!--\n<i class="fa-spin"></i>\n-->\n')
        self._w(tmp_path, "b.css", "/* @keyframes spin */\n")
        assert counts(tmp_path) == (0, 0)

    def test_the_pin_check_fails_on_a_planted_copy(self, tmp_path: Path) -> None:
        self._w(tmp_path, "A.vue", '<style>@keyframes spin { }</style>\n<i class="fa-spin"></i>\n')
        planted = counts(tmp_path)
        assert planted == (1, 1)
        assert violations(planted, {"local_keyframes_spin": 0, "utility_spin_lines": 1})  # over the pin
        assert violations(planted, {"local_keyframes_spin": 1, "utility_spin_lines": 2})  # under: lower it
        assert not violations(planted, {"local_keyframes_spin": 1, "utility_spin_lines": 1})


def violations(now: tuple[int, int], pins: dict[str, int]) -> list[str]:
    """What is wrong with the measured (keyframes, utility) counts against *pins*; empty when exact."""
    found = []
    for key, value in zip(("local_keyframes_spin", "utility_spin_lines"), now):
        pinned = pins[key]
        if value > pinned:
            found.append(
                f"{value} {key}, pin allows {pinned} (#19906). "
                "Use BaseSpinner / BaseSkeleton from @autobot/ui, or BaseButton :loading in an action."
            )
        elif value < pinned:
            found.append(f"{value} {key}, pin says {pinned}: lower PINS to {value} in this PR (#19906).")
    return found


def test_the_apps_do_not_hand_roll_more_spinners_than_pinned() -> None:
    root = repo_root()
    for rel in _ROOTS:
        assert (root / rel).is_dir(), f"{rel} has moved; this guard reads it by path"
    now = tuple(sum(c) for c in zip(*(counts(root / rel) for rel in _ROOTS)))
    assert not violations(now, PINS)


def test_the_pin_was_not_raised_against_the_base() -> None:
    base = base_table(repo_root(), ("repo_tests/kit_loading_ratchet_19906_test.py",), "PINS")
    if not base:
        return  # the guard is new at this base; nothing to compare against yet
    for key, value in PINS.items():
        assert value <= base[key], f"PINS[{key}] rose from {base[key]} to {value} (#19906); the pin only goes down."
