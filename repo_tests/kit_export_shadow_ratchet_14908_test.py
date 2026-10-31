# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Neither GUI re-declares a name the shared kit exports (#14908).

**The boundary.** The count is every ``export type|interface|enum|function|const|let|class X``
in a ``.ts`` file under either app's ``src``, excluding tests, specs, stories and generated
contract files, where ``X`` is a name ``libs/autobot-ui/index.ts`` exports. A re-export
(``export { X } from '@autobot/ui'``) is not a declaration, so it is not counted: that is
the fix. ``export * from`` in the kit is followed. ``.vue`` files are not scanned: a
component's ``<script>`` exported no kit name when this was written. The pre-commit cross-GUI hook only compares the two apps with each other, so a copy
that forks the kit in ONE app (the SLM's own ``createLogger``) passed it.

**What stays.** Two names are intentionally the app's own and set the floor:
``RiskTier`` in ``autobot-frontend/src/types/riskTier.ts`` is the generated wire type, with
a compile-time check that it equals the kit's; ``ServiceHealth`` in the SLM's
``types/slm.ts`` keeps its name by the #15401 ruling (the SLM owns that vocabulary).
The rest are forks still to merge, tracked under #14908.

**One number, not a per-name table**, so this module lists no frontend paths beyond the
two documented above (see ``_hardcoded_colour_baseline.py``). Down-only against the base
(#19283) and exact.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table
from repo_tests._reach import declare

# #19834: libs/slm-contract holds the SLM types that used to live in the SLM app's src, so it is
# scanned with the apps; moving a declaration there must not take it out of the count.
_APPS = ("autobot-frontend/src", "autobot-slm-frontend/src", "libs/slm-contract")
_KIT_INDEX = "libs/autobot-ui/index.ts"
_EXCLUDED = re.compile(r"(\.test\.|\.spec\.|\.stories\.|/__tests__/|/generated/|/_generated/)")
_DECL = re.compile(
    r"^export\s+(?:default\s+)?(?:declare\s+)?(?:async\s+)?"
    r"(?:abstract\s+)?(?:type|interface|const\s+enum|enum|function\*?|const|let|class)\s+([A-Za-z_]\w*)",
    re.M,
)
_REEXPORT = re.compile(r"export\s+(?:type\s+)?\{([^}]*)\}\s*from", re.S)
_STAR = re.compile(r"^export\s+\*\s+from\s+['\"](\.[^'\"]+)['\"]", re.M)
_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)

# 9 measured on ee1bfa15dc; 4 after #14908 (BadgeVariant, ButtonVariant, the two
# MetricsSummary and SystemHealth left). Lower it by exactly what a PR removes: #19683 retired
# the SLM debugUtils createLogger (to 3) and #19688 removed the SLM useFocusTrap fork (to 2,
# the FLOOR), the last removable one.
PINS = {"kit_export_shadows": 2}  # #19688 merged the SLM useFocusTrap into the kit; only the FLOOR remains

# RiskTier (generated wire type) and ServiceHealth (#15401), see the docstring.
FLOOR = 2


def _module_file(base: Path, spec: str) -> Path | None:
    target = (base / spec).resolve()
    for candidate in (target.with_suffix(".ts"), target / "index.ts"):
        if candidate.is_file():
            return candidate
    return None


def kit_export_names(index_text: str, base: Path | None = None, _depth: int = 0) -> set[str]:
    """Names a kit module exports; ``export * from`` is followed when ``base`` is its directory."""
    text = _COMMENTS.sub("", index_text)
    names: set[str] = set()
    for group in _REEXPORT.findall(text):
        for part in group.split(","):
            part = re.sub(r"^\s*type\s+", "", " ".join(part.split()))
            if part:
                names.add(part.split(" as ")[-1].strip())
    names |= set(_DECL.findall(text))
    for spec in _STAR.findall(text):
        target = _module_file(base, spec) if base is not None else None
        assert target is not None and _depth < 5, f"cannot follow `export * from '{spec}'`"
        names |= kit_export_names(target.read_text(encoding="utf-8"), target.parent, _depth + 1)
    return names


def scan_shadows(src_roots: list[Path], kit_names: set[str]) -> tuple[list[str], int]:
    hits: list[str] = []
    scanned = 0
    for root in src_roots:
        for path in sorted(root.rglob("*.ts")):
            # Matched inside the scanned root, so a checkout path cannot exclude everything.
            if _EXCLUDED.search("/" + path.relative_to(root).as_posix()):
                continue
            scanned += 1
            for name in sorted(set(_DECL.findall(path.read_text(encoding="utf-8"))) & kit_names):
                hits.append(f"{root.parent.name}/{path.relative_to(root).as_posix()}: {name}")
    return hits, scanned


class TestTheDetectorWorksBeforeItsOutputIsRead:
    def _w(self, root: Path, rel: str, body: str) -> None:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def test_it_reads_the_kit_index_reexports_aliases_and_types(self) -> None:
        index = "export { A, B as C } from './a'\nexport type {\n  D, // a comment\n  type E,\n} from './d'\nexport const F = 1\n"
        assert kit_export_names(index) == {"A", "C", "D", "E", "F"}

    def test_it_follows_export_star_into_a_directory_index(self, tmp_path: Path) -> None:
        self._w(tmp_path, "src/sched/index.ts", "export * from './types'\nexport { nextRun } from './run'\n")
        self._w(tmp_path, "src/sched/types.ts", "export type Weekday = 1\nexport const enum Step { A }\n")
        names = kit_export_names("export * from './src/sched'\n", tmp_path)
        assert names == {"Weekday", "Step", "nextRun"}

    def test_it_counts_declarations_but_not_reexports(self, tmp_path: Path) -> None:
        self._w(tmp_path, "utils/a.ts", "export function createLogger() {}\nexport type Foo = 1\n")
        self._w(tmp_path, "utils/b.ts", "export { createLogger } from '@autobot/ui'\nexport type { Foo } from 'x'\n")
        self._w(tmp_path, "types/c.ts", "export interface Foo {}\n")
        hits, scanned = scan_shadows([tmp_path], {"createLogger", "Foo"})
        prefix = tmp_path.parent.name
        assert hits == [f"{prefix}/types/c.ts: Foo", f"{prefix}/utils/a.ts: Foo", f"{prefix}/utils/a.ts: createLogger"]
        assert scanned == 3

    def test_it_skips_tests_stories_and_generated_files(self, tmp_path: Path) -> None:
        for rel in ("a.test.ts", "b.stories.ts", "__tests__/c.ts", "types/generated/d.ts", "types/_generated/e.ts"):
            self._w(tmp_path, rel, "export type Foo = 1\n")
        assert scan_shadows([tmp_path], {"Foo"}) == ([], 0)

    def test_a_checkout_path_that_looks_like_a_test_excludes_nothing(self, tmp_path: Path) -> None:
        root = tmp_path / "x.test.y" / "src"
        self._w(root, "a.ts", "export type Foo = 1\n")
        assert scan_shadows([root], {"Foo"})[0] == ["x.test.y/a.ts: Foo"]


def _kit_names(root: Path) -> list[str]:
    index = root / _KIT_INDEX
    if not index.is_file():
        return []
    return sorted(kit_export_names(index.read_text(encoding="utf-8"), index.parent))


def _scanned_ts_files(root: Path) -> list[str]:
    found: list[str] = []
    for rel in _APPS:
        src = root / rel
        if not src.is_dir():
            continue
        for path in sorted(src.rglob("*.ts")):
            if not _EXCLUDED.search("/" + path.relative_to(src).as_posix()):
                found.append(path.relative_to(root).as_posix())
    return found


KIT_NAMES_REACH = declare(
    "kit-export-names-14908",
    discover=_kit_names,
    floor=221,  # mid-window: population 231, window (211, 231)
    growth=20,
    what="names the shared kit exports",
)

TS_FILES_REACH = declare(
    "kit-shadow-ts-files-scanned-14908",
    discover=_scanned_ts_files,
    floor=507,  # mid-window: population 532, window (482, 532)
    growth=50,
    what="non-test .ts files scanned for kit-name redeclarations",
    roots=_APPS,
)


def test_neither_gui_redeclares_more_kit_names_than_pinned() -> None:
    root = repo_root()
    kit_names = set(KIT_NAMES_REACH.examined(root))
    roots = [root / rel for rel in _APPS]
    assert all(r.is_dir() for r in roots), f"{_APPS} has moved; this guard reads it by path"
    hits, scanned = scan_shadows(roots, kit_names)
    TS_FILES_REACH.examined(root)
    assert scanned, "no .ts file scanned"
    pinned = PINS["kit_export_shadows"]
    listing = "\n  ".join(hits)
    assert len(hits) <= pinned, (
        f"{len(hits)} app declarations reuse a kit export name, pin allows {pinned} (#14908). "
        f"Import or re-export the kit's instead:\n  {listing}"
    )
    assert (
        len(hits) == pinned
    ), f"{len(hits)} kit-name redeclarations, pin says {pinned}: lower PINS (#14908).\n  {listing}"
    assert len(hits) >= FLOOR, f"{len(hits)} is below the {FLOOR} documented app-owned names; update FLOOR"


def test_the_pin_was_not_raised_against_the_base() -> None:
    base = base_table(repo_root(), ("repo_tests/kit_export_shadow_ratchet_14908_test.py",), "PINS")
    if base:
        assert PINS["kit_export_shadows"] <= base["kit_export_shadows"], "PINS rose against the base (#14908)"
