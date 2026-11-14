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

**What the pin holds.** Nothing: every held file has moved (``SecretAuditLog.vue``, the SLM's
``AlertsMonitor.vue`` and ``LLMFallbacksView.vue`` to the kit's ``createRecencyFormatter`` and
``createDateFormatter`` for #19606; ``TerminalWindow.vue`` #20779 and ``NodeLifecyclePanel.vue``
#20660 earlier). ``NAMED`` is 0, so any new declaration under a name below fails; ``formatTimeAgo``
stays in the name list although the kit no longer exports one, so a re-introduced copy is still
caught. ``BEHAVIOUR`` is 0 as well; the behavioural detector keeps watching for a copy under any name.

**One number, not a per-file table**, for the reason given in
``slm_raw_setinterval_ratchet_19482_test.py``. The pin is down-only against the base (#19283). The
reach floor guards the scan itself: a moved folder would otherwise read as a clean 0.

**Inline shapes (#19905).** ``new Date(x).toLocaleString()`` is counted with one level of nested parens;
``d.toLocaleString()`` on a date *variable* is left to the BEHAVIOUR detector, because telling it from a
number's needs type information. A locale literal is found anywhere inside a kit formatter call's arguments
(balanced parens), not only before the first ``}``.
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
# Measured on 5b0014f63a plus #20004's migrations; 23 and 20 down to 7 and 3 once the fixed-field
# formatters moved to createDateFormatter / formatLocal* (#19905) and the relative-time ones to the
# kit's createRecencyFormatter (#19606) -- measured on the merged tree, not added up from each side.
# Then 7 and 3 down to 3 and 2 when SecretsManager, ProgressBar, useCaptchaStatus and SettingsView moved,
# and NAMED 3 down to 0 when SecretAuditLog, AlertsMonitor and LLMFallbacksView moved to the kit (#19606).
# BEHAVIOUR 2 down to 1 when NodeLifecyclePanel's formatFullTime moved to createDateFormatter (#19905).
# BEHAVIOUR 1 down to 0 when TerminalWindow's log download took formatISOString (#19905).
NAMED = "local_date_formatter_declarations"
BEHAVIOUR = "local_date_formatter_functions_by_behaviour"
# Four shapes the declaration scan cannot see, because they format a date inline or hand-assemble it
# (#19905). Each is a count over the same files, from comment-stripped text, and each is a pin of its own:
#   inline_date_locale_calls          ``x.toLocaleDateString()`` / ``toLocaleTimeString()`` at a call site
#   inline_date_to_locale_string      ``new Date(v).toLocaleString()`` (a number's ``toLocaleString`` is not one)
#   intl_date_time_format_outside_kit ``new Intl.DateTimeFormat(`` (``Intl.DateTimeFormat()`` for the zone is not)
#   hardcoded_locale_formatters       a fixed locale literal given to a kit formatter or a ``toLocale*String``
#   hand_assembled_date_fields        a date built from ``getMonth()``/``getDate()``/``getHours()``... pieces
#   iso_timestamp_stamp_by_hand       ``toISOString().replace(...)``: the kit's ``isoTimestampStamp`` is the one home (#19905)
#   iso_day_stamp_by_hand             ``toISOString().split('T')[0]`` / ``.slice(0, 10)`` / ``.slice(0, 16)``: the kit's
#                                     ``isoDateStamp`` and ``toDateTimeLocalValue`` are the one home (#19905)
# ``hand_assembled_date_fields`` is 1 on purpose: GanttTimelineView's quarter tick ("Q3 2025") has no
# ``Intl`` equivalent, so it is the one named exception and this pin allows exactly it.
INLINE_LOCALE = "inline_date_locale_calls"
INLINE_TO_LOCALE_STRING = "inline_date_to_locale_string"
INTL_OUTSIDE_KIT = "intl_date_time_format_outside_kit"
HARDCODED_LOCALE = "hardcoded_locale_formatters"
HAND_ASSEMBLED = "hand_assembled_date_fields"
ISO_DAY_STAMP = "iso_day_stamp_by_hand"
ISO_TIMESTAMP_STAMP = "iso_timestamp_stamp_by_hand"
PINS = {
    NAMED: 0,
    BEHAVIOUR: 0,
    INLINE_LOCALE: 0,
    INLINE_TO_LOCALE_STRING: 0,
    INTL_OUTSIDE_KIT: 0,
    HARDCODED_LOCALE: 0,
    HAND_ASSEMBLED: 1,
    ISO_DAY_STAMP: 0,
    ISO_TIMESTAMP_STAMP: 0,
}
_DECLARATION_KEYS = (NAMED, BEHAVIOUR)

_INLINE_LOCALE = re.compile(r"\.toLocale(?:Date|Time)String\s*\(")
# One level of nested parens is allowed (``new Date(a.getTime()).toLocaleString()``). ``d.toLocaleString()`` on a
# date *variable* is not counted here: telling it from a number's needs types, so the BEHAVIOUR detector owns it.
_INLINE_TO_LOCALE_STRING = re.compile(r"new\s+Date\((?:[^()]|\([^()]*\))*\)\s*\.toLocaleString\s*\(")
_INTL_OUTSIDE_KIT = re.compile(r"new\s+Intl\s*\.\s*DateTimeFormat\s*\(")
_FORMATTER_CALL = re.compile(r"create(?:Date|Recency)Formatter\(")
_LOCALE_LITERAL = re.compile(r"\blocale\s*:\s*['\"`]")
_HARDCODED_CALL = re.compile(r"\.toLocale(?:Date|Time)?String\s*\(\s*['\"][a-z]{2}")
_HAND_ASSEMBLED = re.compile(
    r"\$\{[^}`]*\.get(?:Month|Date|Hours|Minutes|Seconds)\(\)"
    r"|\.get(?:Hours|Minutes|Seconds)\(\)\.toString\(\)\.padStart"
)

# Only the CHAINED form is matched: ``x.toISOString().split('T')[0]`` and ``.slice/.substring/.substr(0, 10|16)``
# directly after ``toISOString()`` (whitespace and line breaks allowed). ``const s = d.toISOString(); s.slice(0, 10)``
# is not seen, because telling it from other string slicing needs types.
_ISO_DAY_STAMP = re.compile(
    r"\.toISOString\(\)\s*\.(?:split\(\s*['\"]T['\"]\s*\)\s*\[\s*0\s*\]|(?:slice|substring|substr)\(\s*0\s*,\s*1[06]\s*\))"
)

_ISO_TIMESTAMP_STAMP = re.compile(r"\.toISOString\(\)\s*\.replace\(")


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


def _call_span(text: str, start: int) -> int:
    """Index just past the ``)`` that closes the call whose ``(`` is at ``start - 1``."""
    depth = 1
    for i in range(start, len(text)):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return i + 1
    return len(text)


def _hardcoded_formatter_locales(text: str) -> int:
    """Locale literals inside a kit formatter call's arguments, wherever the key sits in the object."""
    total, pos = 0, 0
    while (m := _FORMATTER_CALL.search(text, pos)) is not None:
        end = _call_span(text, m.end())
        total += len(_LOCALE_LITERAL.findall(text[m.end() : end]))
        pos = end
    return total


def _counts(text: str) -> dict[str, int]:
    """Declarations by name, and the behavioural formatters whose name the list does not hold."""
    text = _COMMENT_LINE.sub("", text)
    by_behaviour = [n for n in date_formatter_names(text) if not _NAMED.match(n)]
    return {
        NAMED: len(_DECLARATION.findall(text)),
        BEHAVIOUR: len(by_behaviour),
        INLINE_LOCALE: len(_INLINE_LOCALE.findall(text)),
        INLINE_TO_LOCALE_STRING: len(_INLINE_TO_LOCALE_STRING.findall(text)),
        INTL_OUTSIDE_KIT: len(_INTL_OUTSIDE_KIT.findall(text)),
        HARDCODED_LOCALE: _hardcoded_formatter_locales(text) + len(_HARDCODED_CALL.findall(text)),
        HAND_ASSEMBLED: len(_HAND_ASSEMBLED.findall(text)),
        ISO_DAY_STAMP: len(_ISO_DAY_STAMP.findall(text)),
        ISO_TIMESTAMP_STAMP: len(_ISO_TIMESTAMP_STAMP.findall(text)),
    }


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
    totals = _measure(sources)
    return sum(totals[key] for key in _DECLARATION_KEYS), len(sources)


def _population(root: Path) -> list[str]:
    return [p.relative_to(root).as_posix() for rel in _ROOTS for p in _sources(root / rel)]


# The scan must reach the population, or a moved folder reads as a clean 0.
REACH = declare(
    "frontend-local-date-formatter-scan",
    discover=_population,
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
        self._w(
            tmp_path,
            "components/B.vue",
            "const formatTime = (ts: number): string => {\n",
        )
        self._w(tmp_path, "composables/c.ts", "  function formatTimestamp(ts: string) {\n")
        self._w(tmp_path, "views/D.vue", "const formatRelativeTime = function (b) {\n")
        self._w(tmp_path, "views/E.vue", "const formatTimeAgo = async (b) => b\n")
        self._w(tmp_path, "views/F.vue", "function formatDateTime(iso: string | null) {\n")
        assert scan(tmp_path)[0] == 6

    def test_it_counts_method_property_multiline_and_generic_forms(self, tmp_path: Path) -> None:
        self._w(
            tmp_path,
            "components/A.vue",
            "const api = {\n  formatDate(d: string) {\n    return 1\n  },\n}\n",
        )
        self._w(
            tmp_path,
            "components/B.vue",
            "const o = {\n  formatTime: (b: number) => b,\n}\n",
        )
        self._w(
            tmp_path,
            "components/C.vue",
            "const formatTimestamp =\n  (ts: string): string => {\n",
        )
        self._w(tmp_path, "components/D.vue", "const formatDateTime = <T,>(s: T) => s\n")
        self._w(
            tmp_path,
            "components/E.vue",
            "const formatTimeAgo: (b: number) => string = (b) => `${b}`\n",
        )
        self._w(
            tmp_path,
            "components/F.vue",
            "class K {\n  private formatDate(d: string) {\n    return d\n  }\n}\n",
        )
        self._w(
            tmp_path,
            "components/G.vue",
            "class L {\n  static formatTime: (b: number) => number = (b) => b\n}\n",
        )
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
        self._w(
            tmp_path,
            "components/C.vue",
            "// function formatDate(b) {\n * function formatTime(b) {\n",
        )
        self._w(tmp_path, "utils/formatHelpers.ts", "function formatDate(d) {\n")
        assert scan(tmp_path) == (0, 1)


def test_a_hand_rolled_formatter_is_found_whatever_it_is_called(tmp_path: Path) -> None:
    """Controls for #20004: the name never decides, the body does."""
    w = TestTheDetectorWorksBeforeItsOutputIsRead()._w
    w(
        tmp_path,
        "components/A.vue",
        "const zzStampify = (v: string) => new Date(v).toLocaleString()\n",
    )
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
    w(
        tmp_path,
        "components/E.vue",
        "const f = (v: string) =>\n  new Date(v)\n    .toLocaleString()\n",
    )
    assert scan(tmp_path)[0] == 5


def test_a_number_a_timezone_probe_a_nested_use_and_a_kit_call_are_not_date_formatters(
    tmp_path: Path,
) -> None:
    w = TestTheDetectorWorksBeforeItsOutputIsRead()._w
    w(tmp_path, "components/A.vue", "const group = (n: number) => n.toLocaleString()\n")
    w(
        tmp_path,
        "components/B.vue",
        "function zone() {\n  return Intl.DateTimeFormat().resolvedOptions().timeZone\n}\n",
    )
    w(
        tmp_path,
        "components/C.vue",
        "const shown = createDateFormatter({ kind: 'time' })\nconst x = (a).toLocaleString()\n",
    )
    w(
        tmp_path,
        "components/D.vue",
        "function outer() {\n  return items.map((n) => n.toLocaleString())\n}\n",
    )
    assert scan(tmp_path)[0] == 0


def _shapes(text: str) -> dict[str, int]:
    return _counts(text)


def test_each_inline_shape_is_counted_under_its_own_key() -> None:
    """Positive controls (#19905): one string per shape, asserted by key."""
    assert _shapes("{{ new Date(x).toLocaleTimeString() }}")[INLINE_LOCALE] == 1
    assert _shapes("const a = d.toLocaleDateString(undefined, { month: 'short' })")[INLINE_LOCALE] == 1
    assert _shapes("const a = new Date(v).toLocaleString()")[INLINE_TO_LOCALE_STRING] == 1
    assert _shapes("const a = new Intl.DateTimeFormat('en')")[INTL_OUTSIDE_KIT] == 1
    assert _shapes("const a = new Intl . DateTimeFormat(undefined, o)")[INTL_OUTSIDE_KIT] == 1
    multi = "const f = createDateFormatter({\n  kind: 'date',\n  locale: 'en-US',\n})"
    assert _shapes(multi)[HARDCODED_LOCALE] == 1
    assert _shapes('const a = createRecencyFormatter({ locale: "en" })')[HARDCODED_LOCALE] == 1
    assert _shapes("d.toLocaleDateString('de-DE')")[HARDCODED_LOCALE] == 1
    after_intl = "createDateFormatter({ intl: { month: 'short' }, locale: 'en-US' })"
    assert _shapes(after_intl)[HARDCODED_LOCALE] == 1
    assert _shapes("createRecencyFormatter({ intl: { a: 1 }, locale: `en-${x}` })")[HARDCODED_LOCALE] == 1
    nested = "createRecencyFormatter({ locale: () => l.value, older: createDateFormatter({ locale: 'en' }) })"
    assert _shapes(nested)[HARDCODED_LOCALE] == 1
    assert _shapes("const a = new Date(a.getTime()).toLocaleString()")[INLINE_TO_LOCALE_STRING] == 1
    assert _shapes("const s = `${d.getMonth() + 1}/${d.getDate()}`")[HAND_ASSEMBLED] == 2
    assert _shapes("const s = h.getHours().toString().padStart(2,'0')")[HAND_ASSEMBLED] == 1
    assert _shapes("const n = `x-${new Date().toISOString().split('T')[0]}.json`")[ISO_DAY_STAMP] == 1
    assert _shapes("const k = d.toISOString().slice(0, 10)")[ISO_DAY_STAMP] == 1
    stamp = "const t = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)"
    assert _shapes(stamp)[ISO_TIMESTAMP_STAMP] == 1
    assert _shapes("const t = d\n  .toISOString()\n  .replace(':', '-')")[ISO_TIMESTAMP_STAMP] == 1
    assert _shapes("const v = new Date(x)\n  .toISOString().slice(0, 16)")[ISO_DAY_STAMP] == 1
    assert _shapes("const d = new Date(x).toISOString()\n  .split('T')[0]")[ISO_DAY_STAMP] == 1


def test_a_number_a_zone_probe_a_live_locale_and_date_arithmetic_are_not_inline_shapes() -> None:
    """Negative controls (#19905)."""
    clean = (
        "const a = n.toLocaleString()\n"
        "const z = Intl.DateTimeFormat().resolvedOptions().timeZone\n"
        "const f = createDateFormatter({ locale: () => locale.value })\n"
        "x.setDate(x.getDate() - 7)\n"
        "const t = d.getTime()\n"
    )
    shapes = _shapes(clean)
    for key in (
        INLINE_LOCALE,
        INLINE_TO_LOCALE_STRING,
        INTL_OUTSIDE_KIT,
        HARDCODED_LOCALE,
        HAND_ASSEMBLED,
        ISO_DAY_STAMP,
        ISO_TIMESTAMP_STAMP,
    ):
        assert shapes[key] == 0, key
    assert _shapes("const a = createDateFormatter({ kind: 'date' })")[HARDCODED_LOCALE] == 0
    live = "createDateFormatter({ intl: { month: 'short' }, locale: () => locale.value })"
    assert _shapes(live)[HARDCODED_LOCALE] == 0
    assert _shapes("const a = d.toLocaleString()")[INLINE_TO_LOCALE_STRING] == 0
    assert _shapes("const a = isoDateStamp(d)")[ISO_DAY_STAMP] == 0
    assert _shapes("const a = isoTimestampStamp()")[ISO_TIMESTAMP_STAMP] == 0
    assert _shapes("const a = d.toISOString()")[ISO_TIMESTAMP_STAMP] == 0
    assert _shapes("const a = s.replace(/x/g, '-')")[ISO_TIMESTAMP_STAMP] == 0
    assert _shapes("const a = d.toISOString().replace(/[:.]/g, '-').slice(0, 19)")[ISO_DAY_STAMP] == 0
    assert _shapes("// new Date(x).toLocaleString()")[INLINE_TO_LOCALE_STRING] == 0


def test_the_inline_shapes_do_not_change_the_declaration_total(tmp_path: Path) -> None:
    w = TestTheDetectorWorksBeforeItsOutputIsRead()._w
    w(tmp_path, "components/A.vue", "<p>{{ new Date(x).toLocaleTimeString() }}</p>\n")
    assert scan(tmp_path)[0] == 0


def test_a_formatter_counts_once_when_it_is_named_and_formats(tmp_path: Path) -> None:
    w = TestTheDetectorWorksBeforeItsOutputIsRead()._w
    w(
        tmp_path,
        "components/A.vue",
        "function formatDate(d: string) {\n  return new Date(d).toLocaleDateString()\n}\n",
    )
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
            "Use formatDate / formatDateTime / formatISOString, createDateFormatter or createRecencyFormatter "
            "(@autobot/ui; formatHelpers re-exports the date ones)."
        )
        assert now[key] == pinned, f"{now[key]} {key}, pin says {pinned}: lower PINS[{key!r}] to {now[key]} (#20004)."


def test_the_pin_was_not_raised_against_the_base() -> None:
    base = base_table(
        repo_root(),
        ("repo_tests/frontend_local_date_formatter_ratchet_19905_test.py",),
        "PINS",
    )
    if not base:
        return  # the guard is new at this base; nothing to compare against yet
    for key, pinned in PINS.items():
        if key in base:  # a measure the base did not have starts at its first measurement (#20004)
            assert pinned <= base[key], f"PINS[{key!r}] rose from {base[key]} to {pinned}; the pin only goes down."


# The kit itself: ``format.ts`` is the one home of the date formatters, and ``schedule/zone.ts`` is
# IANA-zone wall-clock arithmetic (``formatToParts`` into numbers, never display text). Every other kit
# source gets its date text from ``format.ts`` (#19905).
_KIT_SRC = "libs/autobot-ui/src"
_KIT_HOMES = ("/utils/format.ts",)
# ``zone.ts`` is exempt from the Intl shape ONLY (``formatToParts`` wall-clock arithmetic); every other shape still counts there.
_KIT_INTL_EXEMPT = ("/schedule/zone.ts",)
_KIT_SHAPES = (
    ("inline toLocale(Date|Time)String", _INLINE_LOCALE),
    ("new Intl.DateTimeFormat", _INTL_OUTSIDE_KIT),
    ("hand-built ISO day stamp", _ISO_DAY_STAMP),
    ("hand-built ISO timestamp stamp", _ISO_TIMESTAMP_STAMP),
)


def _kit_findings(src: Path) -> list[str]:
    found = []
    for path in sorted(src.rglob("*")):
        rel = "/" + path.relative_to(src).as_posix()
        if path.suffix not in (".ts", ".vue") or _EXCLUDED.search(rel) or rel.endswith(_KIT_HOMES):
            continue
        text = _COMMENT_LINE.sub("", path.read_text(encoding="utf-8"))
        for label, pattern in _KIT_SHAPES:
            if pattern is _INTL_OUTSIDE_KIT and rel.endswith(_KIT_INTL_EXEMPT):
                continue
            if pattern.search(text):
                found.append(f"{rel}: {label}")
        if rel.endswith(_KIT_INTL_EXEMPT):
            text = _INTL_OUTSIDE_KIT.sub("ZoneParts(", text)
            text = re.sub(r"\bIntl\s*\.\s*DateTimeFormat\b", "ZoneParts", text)
        found += [f"{rel}: local date formatter {n}" for n in date_formatter_names(text)]
    return found


def test_the_kit_formats_dates_only_in_format_ts(tmp_path: Path) -> None:
    """Planted control: a kit file that formats a date by hand is found; a kit call is not."""
    (tmp_path / "schedule").mkdir()
    (tmp_path / "schedule" / "bad.ts").write_text(
        "export function fmt(d: Date) { return new Intl.DateTimeFormat('en').format(d) }\n", encoding="utf-8"
    )
    (tmp_path / "schedule" / "stamp.ts").write_text(
        "export const s = new Date().toISOString().slice(0, 10)\n", encoding="utf-8"
    )
    (tmp_path / "schedule" / "ok.ts").write_text(
        "export const f = createDateFormatter({ kind: 'date' })\n", encoding="utf-8"
    )
    planted = _kit_findings(tmp_path)
    assert any("bad.ts: new Intl.DateTimeFormat" in f for f in planted), planted
    assert any("bad.ts: local date formatter fmt" in f for f in planted), planted
    assert any("stamp.ts: hand-built ISO day stamp" in f for f in planted), planted
    assert not any("ok.ts" in f for f in planted), planted
    kit = repo_root() / _KIT_SRC
    assert (kit / "utils" / "format.ts").is_file(), f"{_KIT_SRC} has moved; this guard reads it by path"
    assert (
        _kit_findings(kit) == []
    ), "a kit source formats dates itself; use format.ts (createDateFormatter, isoDateStamp)"


def test_zone_ts_is_exempt_from_the_intl_shape_only(tmp_path: Path) -> None:
    """Planted control: zone arithmetic may use Intl; any other shape in the same file is still found."""
    (tmp_path / "schedule").mkdir()
    zone = tmp_path / "schedule" / "zone.ts"
    zone.write_text(
        "const f = (z: string) => new Intl.DateTimeFormat('en-US', { timeZone: z })\n"
        "export function parts(z: string) { return new Intl.DateTimeFormat('en-US', { timeZone: z }).formatToParts() }\n",
        encoding="utf-8",
    )
    assert _kit_findings(tmp_path) == []
    zone.write_text(
        zone.read_text(encoding="utf-8") + "export const s = new Date().toISOString().slice(0, 10)\n", encoding="utf-8"
    )
    assert any("zone.ts: hand-built ISO day stamp" in f for f in _kit_findings(tmp_path))
    zone.write_text("export function show(d: Date) { return d.toLocaleDateString() }\n", encoding="utf-8")
    found = _kit_findings(tmp_path)
    assert any("zone.ts: inline toLocale" in f for f in found), found
    assert any("zone.ts: local date formatter show" in f for f in found), found
