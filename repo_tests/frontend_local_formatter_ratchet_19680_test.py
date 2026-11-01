# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Components use the kit's byte, uptime and duration formatters, not their own copies (#19680).

**The boundary.** The count is every local declaration named ``formatDuration``,
``formatUptime``, ``formatFileSize``, ``formatBytes`` or ``formatSize`` (a ``function`` or a
``const`` bound to an arrow/function expression) in a ``.vue`` or ``.ts`` file under the
``components``, ``views`` and ``composables`` folders of ``autobot-frontend/src`` and
``autobot-slm-frontend/src``, excluding tests, specs, stories and comment lines. An alias such
as ``const formatSize = formatFileSize`` is a re-binding of the kit's function, not a copy.
16 were measured on main at ee1bfa15dc. The kit's own formatters (``libs/autobot-ui``) are
outside the scanned folders by construction.

**Out of scope: ``stores/`` and ``utils/``.** ``utils/`` holds the canonical helpers
(``formatHelpers`` re-exports the kit's), so a declaration there is the one allowed home, not a
copy. ``stores/`` holds state, not display text; a formatter there is not the component-level
duplication this class measures. Both folders are simply not scanned.

**Shapes matched:** ``function``; ``const x = (...) =>`` / ``function`` / generic ``<T>(``
(including ``(`` on the next line); object or class methods ``formatDuration(x) {``; and
properties ``formatDuration: (x) =>``.

**Nothing is deferred any more.** ``MessageAttachments`` (``formatSize``) and
``WorkflowHistory`` (``formatDuration(workflow)``) were the last two, held by open PRs when
this landed; both now call the kit formatters, so the pin is 0 and the exact check below keeps
it there.

**One number, not a per-file table**, for the reason given in
``slm_raw_setinterval_ratchet_19482_test.py``. The pin is down-only against the base (#19283).
The reach floor guards the scan itself: a moved folder would otherwise read as a clean 0.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table
from repo_tests._reach import declare

_ROOTS = ("autobot-frontend/src", "autobot-slm-frontend/src")
_FOLDERS = ("components", "views", "composables")
_EXCLUDED = re.compile(r"(\.test\.|\.spec\.|\.stories\.|/__tests__/)")
_NAMES = r"(?:formatDuration|formatUptime|formatFileSize|formatBytes|formatSize)"
_ARROW_TAIL = r"=\s*(?:async\s*)?(?:<[^>]*>\s*)?(?:\(|function\b|[A-Za-z_]\w*\s*=>)"
# Every declaration form, matched over the whole text so a binding split across lines is seen.
_DECLARATION = re.compile(
    rf"^[ \t]*(?:export[ \t]+)?(?:"
    rf"(?:async[ \t]+)?function[ \t]+{_NAMES}\s*[(<]"  # function declaration
    rf"|const[ \t]+{_NAMES}\s*(?::[^\n]*?)?{_ARROW_TAIL}"  # const arrow / function expression
    rf"|(?:async[ \t]+)?{_NAMES}\s*(?:<[^>]*>)?\([^)]*\)\s*(?::[^{{;=]+)?\{{"  # object / class method
    rf"|{_NAMES}[ \t]*:\s*(?:async\s*)?(?:<[^>]*>\s*)?(?:\(|function\b|[A-Za-z_]\w*\s*=>)"  # property
    rf")",
    re.M,
)
_COMMENT_LINE = re.compile(r"^[ \t]*(?://|\*|/\*).*$", re.M)

# 16 measured on ee1bfa15dc; 0 after the last two migrated.
PINS = {"local_formatter_declarations": 0}


def _sources(src: Path) -> list[Path]:
    """The component, view and composable sources of one app's ``src``."""
    found = []
    for folder in _FOLDERS:
        for path in sorted((src / folder).rglob("*")):
            rel = "/" + path.relative_to(src).as_posix()
            if path.suffix in (".ts", ".vue") and not _EXCLUDED.search(rel):
                found.append(path)
    return found


def _declarations(path: Path) -> int:
    return len(_DECLARATION.findall(_COMMENT_LINE.sub("", path.read_text(encoding="utf-8"))))


def scan(src: Path) -> tuple[int, int]:
    """Return (declarations, files scanned) for one app's ``src``."""
    sources = _sources(src)
    return sum(_declarations(p) for p in sources), len(sources)


def _population(root: Path) -> list[str]:
    return [p.relative_to(root).as_posix() for rel in _ROOTS for p in _sources(root / rel)]


# The scan must reach the population, or a moved folder reads as a clean 0.
REACH = declare(
    "frontend-local-formatter-scan",
    discover=_population,
    floor=903,  # mid-window: population 928, window (878, 928)
    growth=50,
    what="component, view and composable sources in both frontends",
    roots=_ROOTS,
)


class TestTheDetectorWorksBeforeItsOutputIsRead:
    def _w(self, src: Path, rel: str, body: str) -> None:
        target = src / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def test_it_counts_each_declaration_shape(self, tmp_path: Path) -> None:
        self._w(tmp_path, "components/A.vue", "function formatDuration(ms: number): string {\n")
        self._w(tmp_path, "components/B.vue", "const formatSize = (bytes: number): string => {\n")
        self._w(tmp_path, "composables/c.ts", "  function formatUptime(seconds: number) {\n")
        self._w(tmp_path, "views/D.vue", "const formatBytes = function (b) {\n")
        self._w(tmp_path, "views/E.vue", "const formatFileSize = async (b) => b\n")
        assert scan(tmp_path)[0] == 5

    def test_it_counts_method_property_multiline_and_generic_forms(self, tmp_path: Path) -> None:
        self._w(tmp_path, "components/A.vue", "const api = {\n  formatDuration(ms: number) {\n    return 1\n  },\n}\n")
        self._w(tmp_path, "components/B.vue", "const o = {\n  formatBytes: (b: number) => b,\n}\n")
        self._w(tmp_path, "components/C.vue", "const formatSize =\n  (bytes: number): string => {\n")
        self._w(tmp_path, "components/D.vue", "const formatUptime = <T,>(s: T) => s\n")
        self._w(tmp_path, "components/E.vue", "const formatFileSize: (b: number) => string = (b) => `${b}`\n")
        assert scan(tmp_path)[0] == 5

    def test_a_use_an_alias_a_wrapper_and_an_import_are_not_declarations(self, tmp_path: Path) -> None:
        body = (
            "import { formatDuration } from '@/utils/formatHelpers'\n"
            "const formatSize = formatFileSize\n"
            "const label = formatDuration(ms, opts)\n"
            "function runningFor(s) { return formatDuration(s, null) }\n"
            "const formatDurationLabel = (ms) => ms\n"
            "const o = { formatUptime: uptimeText, formatSize }\n"
            "if (formatDuration(a, b)) {\n"
        )
        self._w(tmp_path, "components/A.vue", body)
        assert scan(tmp_path)[0] == 0

    def test_it_skips_tests_stories_comments_and_other_folders(self, tmp_path: Path) -> None:
        self._w(tmp_path, "components/A.test.ts", "function formatDuration(ms) {\n")
        self._w(tmp_path, "components/__tests__/B.ts", "function formatSize(b) {\n")
        self._w(tmp_path, "components/C.vue", "// function formatBytes(b) {\n * function formatSize(b) {\n")
        self._w(tmp_path, "utils/formatHelpers.ts", "function formatDuration(ms) {\n")
        assert scan(tmp_path) == (0, 1)


def test_the_apps_do_not_hand_roll_more_formatters_than_pinned() -> None:
    root = repo_root()
    for rel in _ROOTS:
        assert (root / rel).is_dir(), f"{rel} has moved; this guard reads it by path"
    now = sum(_declarations(root / rel) for rel in REACH.examined(root))
    pinned = PINS["local_formatter_declarations"]
    assert now <= pinned, (
        f"{now} local formatter declarations, pin allows {pinned} (#19680). "
        "Use formatDuration / formatUptime / formatFileSize from utils/formatHelpers (@autobot/ui)."
    )
    assert (
        now == pinned
    ), f"{now} local formatter declarations, pin says {pinned}: lower PINS to {now} in this PR (#19680)."


def test_the_pin_was_not_raised_against_the_base() -> None:
    base = base_table(repo_root(), ("repo_tests/frontend_local_formatter_ratchet_19680_test.py",), "PINS")
    if not base:
        return  # the guard is new at this base; nothing to compare against yet
    key = "local_formatter_declarations"
    assert PINS[key] <= base[key], f"PINS rose from {base[key]} to {PINS[key]} (#19680); the pin only goes down."
