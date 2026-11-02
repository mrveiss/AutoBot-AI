# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Components use the kit's date and time formatters, not their own copies (#19905).

**The boundary.** The count is every local declaration named ``formatDate``, ``formatTime``,
``formatDateTime``, ``formatTimestamp``, ``formatRelativeTime`` or ``formatTimeAgo`` (a ``function``
or a ``const`` bound to an arrow/function expression, or an object/class method or property) in a
``.vue`` or ``.ts`` file under the ``components``, ``views`` and ``composables`` folders of
``autobot-frontend/src`` and ``autobot-slm-frontend/src``, excluding tests, specs, stories and
comment lines. Since #20004 the count also holds every named local function that *formats a date
through its body* -- ``toLocaleDateString``/``toLocaleTimeString``/``Intl.DateTimeFormat``, or
``toLocaleString`` beside a ``Date`` -- whatever it is called (``fmtDate``, ``formatExpiry``,
``renderStamp``, a ``private`` method); the detector is ``_local_date_formatter_detect.py``. A
function is counted once, by name or by behaviour. ``Intl.DateTimeFormat().resolvedOptions()``
(asking for the browser timezone) and ``toLocaleString`` on a number are not date formatting. ``const formatTime = createDateFormatter({...})`` and an alias such as
``const formatDate = formatDateTime`` are bindings of the kit's function, not copies, and are not
counted. The kit (``libs/autobot-ui``) and ``utils/`` hold the canonical helpers and are not scanned.
Baseline re-measured for #20004 on main at 5b0014f63a plus that PR's migrations.

**What the pin holds.** Three groups remain, each on purpose: (1) relative-time formatters that
take their wording from i18n keys with their own thresholds (``formatRelativeTime``,
``formatTimeAgo``, a few ``formatTime``/``formatDate``) -- the kit's ``formatTimeAgo`` is English
only and has fixed tiers, so they stay until the kit gains an i18n-aware relative formatter
(#19606); (2) duration formatters that happen to be called ``formatTime`` (#19680, #19929);
(3) declarations in files an open PR held when this landed.
The pin goes down as each is moved.

**One number, not a per-file table**, for the reason given in
``slm_raw_setinterval_ratchet_19482_test.py``. The pin is down-only against the base (#19283). The
reach floor guards the scan itself: a moved folder would otherwise read as a clean 0.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._local_date_formatter_detect import date_formatter_names
from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table
from repo_tests._reach import declare

_ROOTS = ("autobot-frontend/src", "autobot-slm-frontend/src")
_FOLDERS = ("components", "views", "composables")
_EXCLUDED = re.compile(r"(\.test\.|\.spec\.|\.stories\.|/__tests__/)")
_NAMES = r"(?:formatDate|formatTime|formatDateTime|formatTimestamp|formatRelativeTime|formatTimeAgo)"
_MODIFIERS = r"(?:(?:public|private|protected|static|readonly)[ \t]+)*"
_ARROW_TAIL = r"=\s*(?:async\s*)?(?:<[^>]*>\s*)?(?:\(|function\b|[A-Za-z_]\w*\s*=>)"
# Every declaration form, matched over the whole text so a binding split across lines is seen.
_DECLARATION = re.compile(
    rf"^[ \t]*(?:export[ \t]+)?(?:"
    rf"(?:async[ \t]+)?function[ \t]+{_NAMES}\s*[(<]"  # function declaration
    rf"|const[ \t]+{_NAMES}\s*(?::[^\n]*?)?{_ARROW_TAIL}"  # const arrow / function expression
    rf"|{_MODIFIERS}(?:async[ \t]+)?{_NAMES}\s*(?:<[^>]*>)?\([^)]*\)\s*(?::[^{{;=]+)?\{{"  # object / class method
    rf"|{_MODIFIERS}{_NAMES}[ \t]*:\s*(?:async\s*)?(?:<[^>]*>\s*)?(?:\(|function\b|[A-Za-z_]\w*\s*=>)"  # property
    rf")",
    re.M,
)
_COMMENT_LINE = re.compile(r"^[ \t]*(?://|\*|/\*).*$", re.M)

# Two measures, so the down-only comparison against the base stays meaningful (#20004): the first is
# the name-only count this guard has always pinned (32 at the base, 24 now); the second is the
# functions only the behavioural detector finds, a measure that did not exist at the base.
# Measured on 5b0014f63a plus #20004's migrations.
NAMED = "local_date_formatter_declarations"
BEHAVIOUR = "local_date_formatter_functions_by_behaviour"
PINS = {NAMED: 24, BEHAVIOUR: 20}


def _sources(src: Path) -> list[Path]:
    """The component, view and composable sources of one app's ``src``."""
    found = []
    for folder in _FOLDERS:
        for path in sorted((src / folder).rglob("*")):
            rel = "/" + path.relative_to(src).as_posix()
            if path.suffix in (".ts", ".vue") and not _EXCLUDED.search(rel):
                found.append(path)
    return found


_NAMED = re.compile(rf"^{_NAMES}$")


def _counts(text: str) -> dict[str, int]:
    """Declarations by name, and the behavioural formatters whose name the list does not hold."""
    text = _COMMENT_LINE.sub("", text)
    by_behaviour = [n for n in date_formatter_names(text) if not _NAMED.match(n)]
    return {NAMED: len(_DECLARATION.findall(text)), BEHAVIOUR: len(by_behaviour)}


def _measure(paths: list[Path]) -> dict[str, int]:
    """Both measures summed over *paths*."""
    totals = dict.fromkeys(PINS, 0)
    for path in paths:
        for key, n in _counts(path.read_text(encoding="utf-8")).items():
            totals[key] += n
    return totals


def scan(src: Path) -> tuple[int, int]:
    """Return (declarations, files scanned) for one app's ``src``."""
    sources = _sources(src)
    return sum(_measure(sources).values()), len(sources)


def _population(root: Path) -> list[str]:
    return [p.relative_to(root).as_posix() for rel in _ROOTS for p in _sources(root / rel)]


# The scan must reach the population, or a moved folder reads as a clean 0.
REACH = declare(
    "frontend-local-date-formatter-scan",
    discover=_population,
    floor=903,  # re-pinned mid-window by scripts/repin_reach_floors.py (#19905)
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
        self._w(tmp_path, "components/A.vue", "function formatDate(d: string): string {\n")
        self._w(tmp_path, "components/B.vue", "const formatTime = (ts: number): string => {\n")
        self._w(tmp_path, "composables/c.ts", "  function formatTimestamp(ts: string) {\n")
        self._w(tmp_path, "views/D.vue", "const formatRelativeTime = function (b) {\n")
        self._w(tmp_path, "views/E.vue", "const formatTimeAgo = async (b) => b\n")
        self._w(tmp_path, "views/F.vue", "function formatDateTime(iso: string | null) {\n")
        assert scan(tmp_path)[0] == 6

    def test_it_counts_method_property_multiline_and_generic_forms(self, tmp_path: Path) -> None:
        self._w(tmp_path, "components/A.vue", "const api = {\n  formatDate(d: string) {\n    return 1\n  },\n}\n")
        self._w(tmp_path, "components/B.vue", "const o = {\n  formatTime: (b: number) => b,\n}\n")
        self._w(tmp_path, "components/C.vue", "const formatTimestamp =\n  (ts: string): string => {\n")
        self._w(tmp_path, "components/D.vue", "const formatDateTime = <T,>(s: T) => s\n")
        self._w(tmp_path, "components/E.vue", "const formatTimeAgo: (b: number) => string = (b) => `${b}`\n")
        self._w(tmp_path, "components/F.vue", "class K {\n  private formatDate(d: string) {\n    return d\n  }\n}\n")
        self._w(tmp_path, "components/G.vue", "class L {\n  static formatTime: (b: number) => number = (b) => b\n}\n")
        assert scan(tmp_path)[0] == 7

    def test_a_kit_formatter_an_alias_a_use_and_an_import_are_not_declarations(self, tmp_path: Path) -> None:
        body = (
            "import { formatDate } from '@/utils/formatHelpers'\n"
            "const formatTime = createDateFormatter({ kind: 'time' })\n"
            "const formatTimestamp = formatDateTime\n"
            "const label = formatDate(d, opts)\n"
            "function shown(d) { return formatDate(d, null) }\n"
            "const formatDateRange = (a, b) => a\n"
            "const o = { formatTimeAgo: ago, formatDate }\n"
            "if (formatDate(a, b)) {\n"
        )
        self._w(tmp_path, "components/A.vue", body)
        assert scan(tmp_path)[0] == 0

    def test_it_skips_tests_stories_comments_and_other_folders(self, tmp_path: Path) -> None:
        self._w(tmp_path, "components/A.test.ts", "function formatDate(d) {\n")
        self._w(tmp_path, "components/__tests__/B.ts", "function formatTime(b) {\n")
        self._w(tmp_path, "components/C.vue", "// function formatDate(b) {\n * function formatTime(b) {\n")
        self._w(tmp_path, "utils/formatHelpers.ts", "function formatDate(d) {\n")
        assert scan(tmp_path) == (0, 1)


def test_a_hand_rolled_formatter_is_found_whatever_it_is_called(tmp_path: Path) -> None:
    """Controls for #20004: the name never decides, the body does."""
    w = TestTheDetectorWorksBeforeItsOutputIsRead()._w
    w(tmp_path, "components/A.vue", "const zzStampify = (v: string) => new Date(v).toLocaleString()\n")
    w(
        tmp_path,
        "components/B.vue",
        "function qq(d: Date) {\n  return d.toLocaleTimeString('en', { hour: '2-digit' })\n}\n",
    )
    w(
        tmp_path,
        "components/C.vue",
        "class K {\n  private static renderStamp(d: Date): string {\n    return d.toLocaleDateString()\n  }\n}\n",
    )
    w(
        tmp_path,
        "components/D.vue",
        "const o = {\n  wibble: (iso: string) => new Intl.DateTimeFormat('en').format(new Date(iso)),\n}\n",
    )
    w(tmp_path, "components/E.vue", "const f = (v: string) =>\n  new Date(v)\n    .toLocaleString()\n")
    assert scan(tmp_path)[0] == 5


def test_a_number_a_timezone_probe_a_nested_use_and_a_kit_call_are_not_date_formatters(tmp_path: Path) -> None:
    w = TestTheDetectorWorksBeforeItsOutputIsRead()._w
    w(tmp_path, "components/A.vue", "const group = (n: number) => n.toLocaleString()\n")
    w(tmp_path, "components/B.vue", "function zone() {\n  return Intl.DateTimeFormat().resolvedOptions().timeZone\n}\n")
    w(
        tmp_path,
        "components/C.vue",
        "const shown = createDateFormatter({ kind: 'time' })\nconst x = (a).toLocaleString()\n",
    )
    w(tmp_path, "components/D.vue", "function outer() {\n  return items.map((n) => n.toLocaleString())\n}\n")
    assert scan(tmp_path)[0] == 0


def test_a_formatter_counts_once_when_it_is_named_and_formats(tmp_path: Path) -> None:
    w = TestTheDetectorWorksBeforeItsOutputIsRead()._w
    w(tmp_path, "components/A.vue", "function formatDate(d: string) {\n  return new Date(d).toLocaleDateString()\n}\n")
    assert scan(tmp_path)[0] == 1


def test_the_apps_do_not_hand_roll_more_date_formatters_than_pinned() -> None:
    root = repo_root()
    for rel in _ROOTS:
        assert (root / rel).is_dir(), f"{rel} has moved; this guard reads it by path"
    now = _measure([root / rel for rel in REACH.examined(root)])
    assert now.keys() == PINS.keys()
    for key, pinned in PINS.items():
        assert now[key] <= pinned, (
            f"{now[key]} {key}, pin allows {pinned} (#19905, #20004). "
            "Use formatDate / formatDateTime / formatISOString / formatTimeAgo or createDateFormatter "
            "from utils/formatHelpers (@autobot/ui)."
        )
        assert now[key] == pinned, f"{now[key]} {key}, pin says {pinned}: lower PINS[{key!r}] to {now[key]} (#20004)."


def test_the_pin_was_not_raised_against_the_base() -> None:
    base = base_table(repo_root(), ("repo_tests/frontend_local_date_formatter_ratchet_19905_test.py",), "PINS")
    if not base:
        return  # the guard is new at this base; nothing to compare against yet
    for key, pinned in PINS.items():
        if key in base:  # a measure the base did not have starts at its first measurement (#20004)
            assert pinned <= base[key], f"PINS[{key!r}] rose from {base[key]} to {pinned}; the pin only goes down."
