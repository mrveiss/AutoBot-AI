# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Each GUI talks HTTP through ONE client, ``src/utils/ApiClient.ts`` (#12363, #13916).

**The boundary.** Per app (``autobot-frontend``, ``autobot-slm-frontend``), the count is every
HTTP transport that is not the app's ``ApiClient.ts``, in a ``.ts``/``.js``/``.vue`` file under
``src``: a raw ``fetch(`` / ``window.fetch(`` / ``globalThis.fetch(`` call, an ``axios`` value import
or require (a type-only import creates no transport and is not counted, #19659), and a
``new XMLHttpRequest(``. A raw ``fetch`` directly under eslint's reasoned
``no-restricted-syntax`` exemption is exempt; that exemption never covers axios or XHR. Tests, specs, stories, ``__tests__/``, ``e2e/`` and
the msw mocks under ``src/test/mocks`` mock fetch on purpose and are not read; neither are
comment lines. ``fetchWithAuth.ts`` IS counted: by its own header it is a bridge for existing
raw sites, and ``ApiClient.rawRequest()`` is the canonical path for new code.

**Where the canonical client lives (#13916 AC4).** Need to call the backend? Import ``ApiClient``
from ``@/utils/ApiClient`` (both apps); for a non-JSON response use ``ApiClient.rawRequest()``.

**One number per app, exact and down-only.** A per-file table would list frontend paths in a
``repo_tests`` module and make ``python_filter_covers_its_guards_test.py`` run the python suite
on every frontend change (see ``_hardcoded_colour_baseline.py``). Each #12363 phase-2 PR lowers
its app's pin by exactly what it removed; the pin may never rise against the base (#19283).
The price of one number per app: a PR that adds one transport and removes another nets zero
and passes -- a reviewer reads the diff for that, the guard does not.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table
from repo_tests._reach import declare

_THIS = "repo_tests/frontend_single_api_client_12363_test.py"
_CANONICAL = "src/utils/ApiClient.ts"
_SUFFIXES = (".ts", ".js", ".vue")
_EXCLUDED = re.compile(r"(\.test\.|\.spec\.|\.stories\.|/__tests__/|/e2e/|/src/test/mocks/)")
_FETCH = re.compile(r"(?:(?<![\w.])|\b(?:window|globalThis|self)\.)fetch\s*(?:<[^>()]*>\s*)?(?:\?\.)?\(")
_OTHER_TRANSPORT = re.compile(
    r"\bfrom\s+['\"]axios['\"]|\bimport\s+['\"]axios['\"]|\bimport\s*\(\s*['\"]axios['\"]"
    r"|\brequire\(\s*['\"]axios['\"]"
    r"|\bnew\s+XMLHttpRequest\s*\("
)
#: A type-only import or re-export creates no transport (``import type``, ``export type``, or braces
#: holding only ``type`` specifiers); it may span lines.
_TYPE_ONLY_AXIOS = re.compile(
    r"\b(?:import|export)\s+(?:type\s+(?:[\w$]+\s*,?\s*)?(?:\{[^{};]*\}|\*\s+as\s+[\w$]+)?\s*"
    # Specifiers are comma-SEPARATED, never optionally: an optional separator lets the repetition
    # re-split ``type a type b ...`` exponentially (CodeQL, #19666 review).
    r"|\{\s*type\s+[\w$]+(?:\s+as\s+[\w$]+)?(?:\s*,\s*type\s+[\w$]+(?:\s+as\s+[\w$]+)?)*\s*,?\s*\}\s*)"
    r"from\s+['\"]axios['\"]",  # one statement only: the repo writes no semicolons (#19659 review)
    re.DOTALL,
)
_COMMENT = re.compile(r"^\s*(//|\*|/\*|<!--)")
#: The existing per-site exemption (eslint's raw-fetch ban): it must follow a comment giving the reason.
_EXEMPT = re.compile(r"eslint-disable-next-line\s+no-restricted-syntax")
#: A reason is prose: a comment of at least four words that is not itself a lint directive.
_REASON = re.compile(r"^\s*(?://|\*|/\*)\s*(?!eslint|@ts-|prettier)(?:\S+\s+){3,}\S")
#: A trailing ``// ...`` or an inline ``/* ... */`` is not code.
_TRAILING_COMMENT = re.compile(r"/\*.*?\*/|(?<![:'\"\w])//.*$")

# Measured on b07673947b; the SLM's Prometheus/Grafana probes are eslint-exempted with a reason. Lower an app's pin by exactly what a PR removes (#12363 phase 2).
# #12363 step 2: the SLM's main-backend calls moved onto SlmApiClient, 1 -> 0.
PINS = {"autobot-frontend": 14, "autobot-slm-frontend": 0}


def _countable(app: Path, path: Path) -> bool:
    """A non-canonical, non-test source file of *app*."""
    rel = path.relative_to(app).as_posix()
    return path.suffix in _SUFFIXES and rel != _CANONICAL and not _EXCLUDED.search("/" + rel)


def _sources(root: Path) -> list[Path]:
    """Every countable source file of both GUIs."""
    found = []
    for app in PINS:
        src = root / app / "src"
        if src.is_dir():
            found += [p for p in sorted(src.rglob("*")) if p.is_file() and _countable(root / app, p)]
    return found


#: 1,088 files measured on b07673947b across both GUIs; repinned by scripts/repin_reach_floors.py.
#: #19532: the unmounted SettingsPanel, CacheService and settings types retired (1,087); pinned mid-window.
REACH = declare(
    "frontend-http-transports",
    discover=_sources,
    floor=1037,
    growth=100,  # ~9%: ordinary GUI growth between repins must not turn an unrelated PR red
    what="non-test GUI source files",
    roots=tuple(f"{app}/src" for app in PINS),
)


def _without_type_only_imports(text: str) -> str:
    """*text* with each type-only axios import blanked, its newlines kept so line numbers hold."""
    return _TYPE_ONLY_AXIOS.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def _transports(text: str) -> int:
    """Transports in one file; one raw ``fetch`` directly under a REASONED eslint raw-fetch exemption is exempt."""
    lines, total = _without_type_only_imports(text).splitlines(), 0
    for i, line in enumerate(lines):
        code = "" if _COMMENT.match(line) else _TRAILING_COMMENT.sub("", line)
        fetches = len(_FETCH.findall(code))
        if fetches and i >= 2 and _EXEMPT.search(lines[i - 1]) and _REASON.match(lines[i - 2]):
            fetches -= 1  # the exemption is eslint's raw-fetch ban: it covers one fetch, never axios or XHR
        total += fetches + len(_OTHER_TRANSPORT.findall(code))
    return total


def count_transports(app: Path, files: list[Path] | None = None) -> int:
    """Non-canonical HTTP transports under *app*/src (from *files* when the caller already enumerated them)."""
    if files is None:
        files = [p for p in (app / "src").rglob("*") if p.is_file()]
    mine = [p for p in files if p.is_relative_to(app) and _countable(app, p)]
    return sum(_transports(p.read_text(encoding="utf-8")) for p in mine)


class TestTheDetectorWorksBeforeItsOutputIsRead:
    def _w(self, app: Path, rel: str, body: str) -> None:
        target = app / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def test_it_counts_each_transport_shape(self, tmp_path: Path) -> None:
        self._w(tmp_path, "src/views/A.vue", "<script setup>\nconst r = await fetch(url)\n</script>\n")
        self._w(tmp_path, "src/b.ts", "import axios from 'axios'\nwindow.fetch(u); globalThis.fetch(v)\n")
        self._w(tmp_path, "src/c.js", "const ax = require('axios')\nconst x = new XMLHttpRequest()\n")
        assert count_transports(tmp_path) == 6

    def test_it_skips_the_client_tests_mocks_stories_and_comments(self, tmp_path: Path) -> None:
        self._w(tmp_path, _CANONICAL, "const response = await fetch(url, fetchOptions)\n")
        for rel in ("src/a.test.ts", "src/a.spec.ts", "src/a.stories.ts", "src/__tests__/b.ts", "src/e2e/c.ts"):
            self._w(tmp_path, rel, "fetch(u)\n")
        self._w(tmp_path, "src/test/mocks/api-handlers.ts", "fetch(u)\n")
        self._w(tmp_path, "src/d.ts", "// was fetch(u) before #12363\n * fetch(v)\n")
        self._w(tmp_path, "src/E.vue", "<!-- #12105: the gallery owns its own API fetch (useApi) -->\n")
        assert count_transports(tmp_path) == 0

    def test_a_reasoned_eslint_exemption_is_not_counted_and_a_bare_one_is(self, tmp_path: Path) -> None:
        reasoned = "// Prometheus is another service on its own origin.\n// eslint-disable-next-line no-restricted-syntax\nawait fetch(p)\n"
        bare = "const x = 1\n// eslint-disable-next-line no-restricted-syntax\nawait fetch(q)\n"
        self._w(tmp_path, "src/A.vue", reasoned)
        self._w(tmp_path, "src/B.vue", bare)
        assert count_transports(tmp_path) == 1

    def test_it_counts_generic_optional_dynamic_and_bare_import_shapes(self, tmp_path: Path) -> None:
        body = (
            "const r = await fetch<Row[]>(u)\nfetch?.(v)\nself.fetch(w)\n"
            "const ax = await import('axios')\nimport 'axios'\n"
        )
        self._w(tmp_path, "src/a.ts", body)
        assert count_transports(tmp_path) == 5

    def test_a_trailing_or_inline_comment_is_not_code(self, tmp_path: Path) -> None:
        self._w(tmp_path, "src/a.ts", "load() // was fetch(u)\nrun(/* fetch(v) */ x)\n")
        assert count_transports(tmp_path) == 0

    def test_a_directive_or_a_one_word_comment_is_not_a_reason(self, tmp_path: Path) -> None:
        for name, above in (("a", "// eslint-disable-next-line max-len"), ("b", "// TODO")):
            body = f"{above}\n// eslint-disable-next-line no-restricted-syntax\nawait fetch(u)\n"
            self._w(tmp_path, f"src/{name}.ts", body)
        assert count_transports(tmp_path) == 2

    def test_an_exemption_covers_one_call_not_the_whole_line(self, tmp_path: Path) -> None:
        body = "// Grafana is a separate service on its own origin.\n// eslint-disable-next-line no-restricted-syntax\nfetch(a); fetch(b)\n"
        self._w(tmp_path, "src/a.ts", body)
        assert count_transports(tmp_path) == 1

    def test_an_exemption_never_hides_axios_or_xhr(self, tmp_path: Path) -> None:
        reason = "// The probe reaches a separate service on its own origin.\n"
        directive = "// eslint-disable-next-line no-restricted-syntax\n"
        self._w(tmp_path, "src/a.ts", f"{reason}{directive}import axios from 'axios'\n")
        self._w(tmp_path, "src/b.ts", f"{reason}{directive}const x = new XMLHttpRequest()\n")
        assert count_transports(tmp_path) == 2

    def test_a_type_only_import_is_not_a_transport(self, tmp_path: Path) -> None:
        self._w(tmp_path, "src/a.ts", "import type { AxiosRequestConfig } from 'axios'\n")
        self._w(tmp_path, "src/b.ts", "import type {\n  AxiosError,\n  AxiosResponse,\n} from 'axios'\nfetch(u)\n")
        self._w(tmp_path, "src/c.ts", "import { type AxiosError, type AxiosResponse as R } from 'axios'\n")
        self._w(tmp_path, "src/d.ts", "export type { AxiosInstance } from 'axios'\n")
        assert count_transports(tmp_path) == 1  # only b.ts's fetch, still found on its own line

    def test_a_type_import_never_hides_a_later_value_import(self, tmp_path: Path) -> None:
        bodies = (
            "import type { A } from 'x'\nimport axios from 'axios'\n",
            "import type { A } from 'x'\nconst y = 1\nimport axios from 'axios'\n",
            "import type A from 'x'\nimport { create } from 'axios'\n",
            "export type Foo = { a: 1 }\nimport axios from 'axios'\n",
            "<script setup lang=\"ts\">\nimport type { Props } from './p'\nimport axios from 'axios'\n</script>\n",
        )
        for i, body in enumerate(bodies):
            self._w(tmp_path, f"src/m{i}.{'vue' if 'script' in body else 'ts'}", body)
        assert count_transports(tmp_path) == len(bodies)

    def test_a_value_import_beside_a_type_is_a_transport(self, tmp_path: Path) -> None:
        self._w(tmp_path, "src/a.ts", "import axios, { type AxiosError } from 'axios'\n")
        self._w(tmp_path, "src/b.ts", "import { type AxiosError, create } from 'axios'\n")
        assert count_transports(tmp_path) == 2

    def test_a_method_named_fetch_is_not_a_transport(self, tmp_path: Path) -> None:
        self._w(tmp_path, "src/a.ts", "store.fetch(id)\nawait this.fetch()\nprefetch(x)\nrefetch()\n")
        assert count_transports(tmp_path) == 0


def test_each_gui_has_no_more_transports_than_pinned() -> None:
    root = repo_root()
    files = REACH.examined(root)
    for app, pinned in PINS.items():
        assert (root / app / _CANONICAL).is_file(), f"{app}/{_CANONICAL} has moved; this guard reads it by path"
        now = count_transports(root / app, files)
        assert now <= pinned, (
            f"{app}: {now} HTTP transports outside {_CANONICAL}, pin allows {pinned} (#12363). "
            "Call the backend through ApiClient (ApiClient.rawRequest() for a non-JSON response)."
        )
        assert now == pinned, f"{app}: {now} transports, pin says {pinned}: lower PINS to {now} in this PR (#12363)."
    REACH.completed(files)


def test_no_pin_was_raised_against_the_base() -> None:
    base = base_table(repo_root(), (_THIS,), "PINS")
    if not base:
        return  # the guard is new at this base (an unreadable base raises BaseUnavailable instead)
    assert set(base) <= set(
        PINS
    ), f"apps dropped from PINS: {sorted(set(base) - set(PINS))}; an app's pin only goes down"
    raised = {app: (base[app], pin) for app, pin in PINS.items() if app in base and pin > base[app]}
    assert not raised, f"pins rose against the base (base, now): {raised}; a pin only goes down (#12363)."


def test_the_type_only_pattern_stays_linear_on_a_pathological_input() -> None:
    """CodeQL flagged exponential backtracking on many ``type $`` repetitions (#19666 review)."""
    import time

    started = time.perf_counter()
    _TYPE_ONLY_AXIOS.search("import {" + " type $" * 40 + " from 'nowhere'")
    assert time.perf_counter() - started < 1.0
