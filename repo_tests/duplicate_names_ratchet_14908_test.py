# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No type name or util filename is implemented twice across the GUIs and the kit (#14908).

Sibling of ``kit_export_shadow_ratchet_14908_test.py``, which guards the kit's *exported
names*. This one guards the two shapes that guard cannot see.

**(a) Type names.** The same ``export type|interface X`` declared in both apps' ``src``, or in
an app and the kit (``libs/autobot-ui``, any file, not only what its index exports). A
re-export (``export type { X } from``) is not a declaration. ``.vue`` files and tests, specs,
stories and generated files are not scanned, as in the sibling guard.

**(b) Util filenames.** The same relative path under both apps' ``src/utils`` where BOTH files
are real implementations. A file that only imports and re-exports ``@autobot/ui`` is the fix,
not the defect, so it is not counted: ``debugUtils.ts`` and ``formatHelpers.ts`` in the SLM
are such files today.

**Two numbers, each exact and down-only against the base** (#19283). Each type pin counts
names (a name declared in three places is one), so lowering it means a name stopped being
declared twice, not that one copy of three went.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table
from repo_tests._reach import declare
from repo_tests.kit_export_shadow_ratchet_14908_test import _COMMENTS, _EXCLUDED

_APPS = ("autobot-frontend/src", "autobot-slm-frontend/src")
_UTILS = tuple(f"{app}/utils" for app in _APPS)
_KIT = "libs/autobot-ui"
_TYPE_DECL = re.compile(r"^[ \t]*export\s+(?:declare\s+)?(?:type|interface)\s+([A-Za-z_$][\w$]*)", re.M)
_MODULE_STMT = re.compile(r"\b(?:import|export)\b[^;'\"]*?\bfrom\s*['\"]([^'\"]+)['\"]\s*;?")
_KIT_SPEC = re.compile(r"^@autobot/ui(/|$)")
_SKIPPED_DIRS = {"node_modules", "dist"}

# Measured on e71921c5fe: 28 type names declared in both apps, 2 declared in an app and the kit
# (RiskTier, ServiceHealth, the two documented in the sibling guard), 1 util filename implemented
# twice (ApiClient.ts). #19910 resolved 14 both-apps names by renaming the one that is a different
# concept, #14908 moved the ApiClient options type into the kit (13 left), and #19910 then moved the
# agent-ledger rows and the permission rule into the kit (one declaration, both apps import it) and
# renamed the different-concept names (Agent, CacheStats, WebResearchSettings, the plugin audit row,
# the TLS upload body). 2 left, each stated in TYPE_EXCEPTIONS with its reason.
PINS = {"type_names_in_both_apps": 1, "type_names_in_app_and_kit": 2, "util_filenames_in_both_apps": 1}

# Stated exceptions: a type name declared in both apps until the audit-entry shape is fixed once.
TYPE_EXCEPTIONS = {
    "AuditQueryResponse": (
        "one backend envelope (`AuditQueryResponse`, entries are untyped dicts so no generated row type exists); the "
        "main copy (types/audit.ts) is typed on the main `AuditEntry` (timestamp string, error_message, user_agent), "
        "which the audit dashboard components read; it moves with AuditLogEntry once that row has one shape"
    ),
}

# Stated exceptions: a util filename implemented in both apps until its own PR lands.
UTIL_EXCEPTIONS = {
    "ApiClient.ts": (
        "both apps carry their own transport; the kit base class replaces both in the ApiClient "
        "consolidation PR (maintainer decision 2026-10-28, waits for the PR holding the SLM copy)"
    ),
}
# formatHelpers.ts is the other expected duplicate. It is NOT counted today because the SLM's copy
# is already a thin re-export of the kit; if it regrows an implementation this guard counts it,
# and it must then be added above with its reason until the formatters PR removes the main copy.


def _ts_files(root: Path) -> list[Path]:
    found = []
    for path in sorted(root.rglob("*.ts")):
        rel = path.relative_to(root)
        if _SKIPPED_DIRS & set(rel.parts) or _EXCLUDED.search("/" + rel.as_posix()):
            continue
        found.append(path)
    return found


def declared_types(roots: list[Path]) -> dict[str, list[str]]:
    """{type name: [files declaring it]} across ``roots``; one entry per file, never per line."""
    out: dict[str, list[str]] = {}
    for root in roots:
        for path in _ts_files(root):
            text = _COMMENTS.sub("", path.read_text(encoding="utf-8"))
            for name in sorted(set(_TYPE_DECL.findall(text))):
                out.setdefault(name, []).append(f"{root.parent.name}/{root.name}/{path.relative_to(root).as_posix()}")
    return out


def is_thin_kit_reexport(text: str) -> bool:
    """True when the file only imports/re-exports ``@autobot/ui`` and implements nothing."""
    text = _COMMENTS.sub("", text)
    specs = _MODULE_STMT.findall(text)
    rest = _MODULE_STMT.sub("", text).strip()
    return bool(specs) and not rest and all(_KIT_SPEC.match(s) for s in specs)


def util_files(utils_dir: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted(utils_dir.rglob("*")):
        rel = path.relative_to(utils_dir)
        if path.suffix not in (".ts", ".js") or path.name.endswith(".d.ts") or not path.is_file():
            continue
        if _SKIPPED_DIRS & set(rel.parts) or _EXCLUDED.search("/" + rel.as_posix()):
            continue
        found[rel.as_posix()] = path
    return found


def duplicate_util_names(first: Path, second: Path) -> list[str]:
    """Relative paths present in both dirs where neither file is a thin kit re-export."""
    a, b = util_files(first), util_files(second)
    return sorted(
        name
        for name in set(a) & set(b)
        if not is_thin_kit_reexport(a[name].read_text(encoding="utf-8"))
        and not is_thin_kit_reexport(b[name].read_text(encoding="utf-8"))
    )


def type_name_overlaps(first: dict[str, list[str]], second: dict[str, list[str]]) -> list[str]:
    return sorted(set(first) & set(second))


class TestTheDetectorsWorkBeforeTheirOutputIsRead:
    def _w(self, root: Path, rel: str, body: str) -> None:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def test_the_same_type_in_two_trees_is_an_overlap(self, tmp_path: Path) -> None:
        self._w(tmp_path / "a", "t.ts", "export interface Row { id: string }\nexport type Only = 1\n")
        self._w(tmp_path / "b", "u.ts", "export type Row = { id: number }\n")
        first, second = declared_types([tmp_path / "a"]), declared_types([tmp_path / "b"])
        assert type_name_overlaps(first, second) == ["Row"]

    def test_declare_generic_multiline_and_indented_forms_all_count(self, tmp_path: Path) -> None:
        self._w(
            tmp_path / "a",
            "t.ts",
            "export declare interface A {}\nexport type B<T> = T[]\nexport\n  interface C {\n}\n  export type $D = 1\n",
        )
        self._w(
            tmp_path / "b",
            "u.ts",
            "export declare interface A {}\nexport type B<T> = T\nexport\n  interface C {\n}\nexport type $D = 2\n",
        )
        first, second = declared_types([tmp_path / "a"]), declared_types([tmp_path / "b"])
        assert type_name_overlaps(first, second) == ["$D", "A", "B", "C"]

    def test_a_reexport_or_a_distinct_name_is_not_an_overlap(self, tmp_path: Path) -> None:
        self._w(tmp_path / "a", "t.ts", "export interface Row { id: string }\n")
        self._w(tmp_path / "b", "u.ts", "export type { Row } from '@autobot/ui'\nexport type Other = 1\n")
        first, second = declared_types([tmp_path / "a"]), declared_types([tmp_path / "b"])
        assert type_name_overlaps(first, second) == []

    def test_tests_and_comments_do_not_declare(self, tmp_path: Path) -> None:
        self._w(tmp_path / "a", "t.test.ts", "export type Row = 1\n")
        self._w(tmp_path / "a", "c.ts", "// export type Row = 1\n/* export type Row = 2 */\n")
        assert declared_types([tmp_path / "a"]) == {}

    def test_two_real_util_files_of_one_name_are_a_duplicate(self, tmp_path: Path) -> None:
        self._w(tmp_path / "a", "x.ts", "export function f() { return 1 }\n")
        self._w(tmp_path / "b", "x.ts", "export function f() { return 2 }\n")
        self._w(tmp_path / "b", "only.ts", "export const g = 1\n")
        assert duplicate_util_names(tmp_path / "a", tmp_path / "b") == ["x.ts"]

    def test_a_thin_kit_reexport_on_either_side_is_not_a_duplicate(self, tmp_path: Path) -> None:
        thin = "// a note\nexport {\n  createLogger,\n  type LogLevel,\n} from '@autobot/ui'\n"
        self._w(tmp_path / "a", "x.ts", "export function f() { return 1 }\n")
        self._w(tmp_path / "b", "x.ts", thin)
        assert duplicate_util_names(tmp_path / "a", tmp_path / "b") == []

    def test_a_reexport_with_a_body_or_another_module_is_still_real(self) -> None:
        assert is_thin_kit_reexport("export { a } from '@autobot/ui'\nimport type { B } from '@autobot/ui'\n")
        assert not is_thin_kit_reexport("export { a } from '@autobot/ui'\nexport const z = 1\n")
        assert not is_thin_kit_reexport("export { a } from './local'\n")
        assert not is_thin_kit_reexport("")


def _type_files(root: Path) -> list[str]:
    found: list[str] = []
    for rel in (*_APPS, _KIT):
        base = root / rel
        if base.is_dir():
            found += [p.relative_to(root).as_posix() for p in _ts_files(base)]
    return found


def _util_files(root: Path) -> list[str]:
    found: list[str] = []
    for rel in _UTILS:
        base = root / rel
        if base.is_dir():
            found += [p.relative_to(root).as_posix() for p in util_files(base).values()]
    return found


TYPE_FILES_REACH = declare(
    "duplicate-type-names-ts-files-scanned-14908",
    discover=_type_files,
    floor=519,  # mid-window: population 544, window (494, 544)
    growth=50,
    what="non-test .ts files in both apps and the kit scanned for repeated type names",
    roots=(*_APPS, _KIT),
)

UTIL_FILES_REACH = declare(
    "duplicate-util-filenames-scanned-14908",
    discover=_util_files,
    floor=56,  # mid-window: population 61, window (51, 61)
    growth=10,
    what="non-test util files in both apps compared by filename",
    roots=_UTILS,
)


def _measure() -> tuple[list[str], list[str], list[str]]:
    root = repo_root()
    TYPE_FILES_REACH.examined(root)
    UTIL_FILES_REACH.examined(root)
    first, second, kit = (declared_types([root / rel]) for rel in (*_APPS, _KIT))
    both = type_name_overlaps(first, second)
    with_kit = sorted(set(type_name_overlaps(first, kit)) | set(type_name_overlaps(second, kit)))
    utils = duplicate_util_names(*(root / rel for rel in _UTILS))
    return both, with_kit, utils


def test_type_names_and_util_filenames_are_not_duplicated_beyond_the_pins() -> None:
    both, with_kit, utils = _measure()
    measured = {
        "type_names_in_both_apps": both,
        "type_names_in_app_and_kit": with_kit,
        "util_filenames_in_both_apps": utils,
    }
    for key, names in measured.items():
        listing = "\n  ".join(names)
        assert len(names) <= PINS[key], f"{key}: {len(names)} > pin {PINS[key]} (#14908). Share one:\n  {listing}"
        assert (
            len(names) == PINS[key]
        ), f"{key}: {len(names)} found, pin says {PINS[key]}: lower PINS (#14908).\n  {listing}"


def test_every_duplicated_util_filename_is_a_stated_exception() -> None:
    utils = _measure()[2]
    assert sorted(utils) == sorted(UTIL_EXCEPTIONS), (
        f"util filenames implemented in both apps {utils} differ from the stated exceptions "
        f"{sorted(UTIL_EXCEPTIONS)} (#14908)"
    )
    assert all(UTIL_EXCEPTIONS.values()), "an exception needs its reason"


def test_every_duplicated_type_name_is_a_stated_exception() -> None:
    both = _measure()[0]
    assert sorted(both) == sorted(
        TYPE_EXCEPTIONS
    ), f"type names declared in both apps {both} differ from the stated exceptions {sorted(TYPE_EXCEPTIONS)} (#19910)"
    assert all(TYPE_EXCEPTIONS.values()), "an exception needs its reason"


def test_the_pins_were_not_raised_against_the_base() -> None:
    base = base_table(repo_root(), ("repo_tests/duplicate_names_ratchet_14908_test.py",), "PINS")
    for key, value in (base or {}).items():
        assert PINS[key] <= value, f"{key} rose against the base (#14908)"
