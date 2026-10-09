#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18098 — one severity ladder, found by MEMBER SET rather than by name.

Sixteen `*Severity(Enum)` classes existed beside the canonical
`autobot_shared.status_enums.Severity`, ten of them exact subsets of it. Nothing could
see them:

* `tools/lint/check_symbol_forks.py` matches by **name**, so a fork under a fresh name
  produces no cluster at all.
* The #6973 pre-commit hook matches the literal token `Status`
  (`/^class[[:space:]]+[A-Za-z_]+Status[[:space:]]*\\([^)]*Enum[^)]*\\)/`); `grep -ci
  severity` on that hook returns 0.
* `repo_tests/enum_union_guard_test.py` pins the canonical's members and the string
  literals, and checks exactly two alias bindings by hardcoded path. None of that
  notices a rival class.

So this guard probes the member set, the way
`enum_union_guard_test.py::test_no_second_command_risk_enum_has_regrown` does for
`CommandRisk`. That immediately found `OptimizationPriority`, which every name-based
sweep had missed because its name says "priority".

Separate file rather than appended to `enum_union_guard_test.py`: that file is
grandfathered at 801 lines and a grandfathered file may not grow. Same reason
`enum_union_guard_severity_literal_shapes_test.py` is its own file, and like it this one
re-derives its scan instead of importing one.
"""

from __future__ import annotations

import ast
import functools
from typing import NamedTuple

import pytest
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

#: The five rungs every exact-subset fork carried.
SEVERITY_SUBSET_PROBE = frozenset({"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"})

#: Scanned roots. `autobot-slm-backend/` is deliberately outside: its two severity
#: enums (`EventSeverity`, `SecurityEventSeverity`) are `(str, Enum)` persisted to
#: indexed `String(16)` columns, so neither is a drop-in alias and both are tracked on
#: the issue instead. Recorded in a test below so "green" is never read as "clean".
SCANNED_ROOTS = ("autobot-backend", "autobot_shared")

#: Exact subsets that are NOT aliased, because something builds an API or report dict
#: key set by ITERATING their members. The sites, by file and the enum each iterates --
#: deliberately not by line, per #15877:
#:
#:   api/code_intelligence.py        `for sev in OptimizationSeverity` (twice),
#:                                   `for sev in SecuritySeverity`,
#:                                   `for sev in PerformanceSeverity`
#:   code_intelligence/testing_pattern_analyzer.py   `for s in TestPatternSeverity`
#:   code_intelligence/llm_pattern_analyzer.py       `for priority in OptimizationPriority`
#:
#: Aliasing these to the ten-rung canonical grows those responses from five keys to ten,
#: against a frontend type that is deliberately the narrow five --
#: `CODE_INTELLIGENCE_SEVERITIES` in `autobot-frontend/src/types/codeIntelligence.ts`,
#: where a value the generated `Severity` does not carry fails to compile. Each is a
#: wire-format decision, not a refactor: #18098's "no serialized value changes, each is a
#: drop-in migration" does not hold for them. `Severity.score_ladder()` is the mechanism
#: if they migrate.
#:
#: `OptimizationPriority` also ranks urgency rather than severity, which is a second
#: question to answer before folding it in.
PENDING_A_WIRE_DECISION = {
    "autobot-backend/code_intelligence/llm_pattern_analysis/types.py::OptimizationPriority": (
        "autobot-backend/code_intelligence/llm_pattern_analyzer.py"
    ),
    "autobot-backend/code_intelligence/performance_analysis/types.py::PerformanceSeverity": (
        "autobot-backend/api/code_intelligence.py"
    ),
    "autobot-backend/code_intelligence/redis_optimizer.py::OptimizationSeverity": (
        "autobot-backend/api/code_intelligence.py"
    ),
    "autobot-backend/code_intelligence/security/constants.py::SecuritySeverity": (
        "autobot-backend/api/code_intelligence.py"
    ),
    "autobot-backend/code_intelligence/testing_pattern_analyzer.py::TestPatternSeverity": (
        "autobot-backend/code_intelligence/testing_pattern_analyzer.py"
    ),
}

CANONICAL = "autobot_shared/status_enums.py::Severity"


@functools.lru_cache(maxsize=1)
def _tracked_python_files() -> tuple[str, ...]:
    # #15926: `tracked_paths` is the one git enumerator -- it builds the pathspec and
    # raises on an empty result, so a guard cannot report clean having enumerated
    # nothing. Three new guards of mine each re-ran `git ls-files` directly, which is
    # what `one_git_enumeration_15926_test` counts and refuses to let grow.
    return tuple(tracked_paths(repo_root(), "*.py"))


#: Every base in the stdlib `enum` module that makes a class an enumeration.
_ENUM_BASES = frozenset({"Enum", "IntEnum", "StrEnum", "IntFlag", "Flag", "ReprEnum"})


def _enum_alias_names(tree: ast.Module) -> frozenset[str]:
    """Local names this module bound to an `enum` base, however the import spelled it.

    `from enum import Enum as E` binds `E`; `from enum import StrEnum` binds `StrEnum`.
    This file first matched the literal tokens "Enum" and "_E", with a test asserting
    exactly `_E` -- so the test passed because it was written to the implementation
    rather than to the hazard, and `as E` walked through the guard untouched.
    """
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "enum":
            aliases.update(alias.asname or alias.name for alias in node.names if alias.name in _ENUM_BASES)
    return frozenset(aliases)


def _is_enum_base(base: ast.expr, aliases: frozenset[str]) -> bool:
    """True when `base` names an enumeration base, dotted, bare, or aliased."""
    text = ast.unparse(base)
    # `enum.Enum`, `e.StrEnum` (import enum as e) and a bare `Enum` all end in the
    # real class name; an `as` alias does not, so it is resolved through the imports.
    return text.rsplit(".", 1)[-1] in _ENUM_BASES or text in aliases


def _class_defs(tree: ast.Module) -> int:
    """Class nodes visited -- the sweep's reach, independent of what it found."""
    return sum(1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef))


def _enums_in_tree(tree: ast.Module) -> list[tuple[str, frozenset[str]]]:
    """Every Enum subclass with its member names.

    Bases are resolved through the module's own `enum` imports, so an alias binding
    cannot hide a fork. Matching the unparsed text against a fixed token list is the
    fail-open shape `enum_union_guard_test.py` shipped once and this file repeated.
    """
    aliases = _enum_alias_names(tree)
    found: list[tuple[str, frozenset[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(_is_enum_base(base, aliases) for base in node.bases):
            continue
        # A member is any plain assignment in the class body, WHATEVER its value
        # expression. Requiring `ast.Constant` missed `INFO = auto()` -- the idiomatic
        # spelling -- so a five-rung ladder written with `auto()` passed this guard
        # entirely. Names starting with `_` are excluded: `_order_` and friends are
        # Enum machinery, not rungs. Annotated assignments are excluded too, because
        # `x: int = 1` in an Enum body is a class attribute rather than a member.
        members = frozenset(
            target.id
            for stmt in node.body
            if isinstance(stmt, ast.Assign)
            for target in stmt.targets
            if isinstance(target, ast.Name) and not target.id.startswith("_")
        )
        if members:
            found.append((node.name, members))
    return found


def _iterates_enum(source: str, name: str) -> bool:
    """True when `source` iterates `name`'s members -- by syntax, not by text.

    The text probe `f"in {name}" in source` is satisfied by a comment, a docstring, or
    an unrelated `if value in SomeList`, so it could not tell a live exemption from a
    stale one. Only a `for` statement or a comprehension over the enum is the reason
    these entries are held back.
    """
    over = {name, f"{name}.__members__"} | {f"{fn}({name})" for fn in ("list", "tuple", "sorted", "reversed")}
    for node in ast.walk(ast.parse(source)):
        iterables: list[ast.expr] = []
        if isinstance(node, (ast.For, ast.AsyncFor)):
            iterables.append(node.iter)
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            iterables.extend(gen.iter for gen in node.generators)
        if any(ast.unparse(it) in over for it in iterables):
            return True
    return False


class _Scan(NamedTuple):
    """The sweep's findings AND its reach, so a floor can bind to the reach."""

    declared: tuple[tuple[str, str, frozenset[str]], ...]
    files_parsed: int
    files_unparsable: tuple[str, ...]
    classes_visited: int


@functools.lru_cache(maxsize=1)
def _scan() -> _Scan:
    root = repo_root()
    declared: list[tuple[str, str, frozenset[str]]] = []
    unparsable: list[str] = []
    parsed = classes = 0
    for rel in _tracked_python_files():
        if not rel.startswith(tuple(f"{r}/" for r in SCANNED_ROOTS)):
            continue
        try:
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            # Counted, not swallowed: a root that stopped parsing is a loss of reach,
            # and the floor below is what notices.
            unparsable.append(rel)
            continue
        parsed += 1
        classes += _class_defs(tree)
        declared.extend((rel, name, members) for name, members in _enums_in_tree(tree))
    return _Scan(tuple(declared), parsed, tuple(unparsable), classes)


def _declared_enums() -> tuple[tuple[str, str, frozenset[str]], ...]:
    return _scan().declared


def test_the_scan_is_not_vacuous() -> None:
    """An empty sweep satisfies every assertion below by looking at nothing.

    The floors bind to the sweep's REACH -- files parsed, class nodes visited -- never
    to the number of enums found. A detector that stopped recognising declarations
    would keep a findings-based floor satisfied while covering less and less.
    """
    scan = _scan()
    assert len(_tracked_python_files()) > 3000, "git ls-files returned almost nothing"
    assert scan.files_parsed > 1000, f"only {scan.files_parsed} files parsed — the roots are wrong"
    assert scan.classes_visited > 2000, f"only {scan.classes_visited} class nodes visited"
    assert not scan.files_unparsable, f"lost reach: {len(scan.files_unparsable)} file(s) failed to parse"
    assert CANONICAL in {f"{rel}::{name}" for rel, name, _ in scan.declared}


#: Synthetic modules the detector MUST see. Every spelling of the base an author can
#: reach for, because the first version of this detector matched two of them by literal
#: token and let the rest through.
_MUST_DETECT = {
    "aliased-enum": "from enum import Enum as E\n\n\nclass R(E):\n    INFO = 'info'\n",
    "underscore-alias": "from enum import Enum as _E\n\n\nclass R(_E):\n    INFO = 'info'\n",
    "dotted": "import enum\n\n\nclass R(enum.Enum):\n    INFO = 'info'\n",
    "module-alias": "import enum as e\n\n\nclass R(e.Enum):\n    INFO = 'info'\n",
    "str-enum": "from enum import StrEnum\n\n\nclass R(StrEnum):\n    INFO = 'info'\n",
    "mixin": "from enum import Enum\n\n\nclass R(str, Enum):\n    INFO = 'info'\n",
    "int-enum-alias": "from enum import IntEnum as I\n\n\nclass R(I):\n    INFO = 1\n",
    "auto-member": "from enum import Enum, auto\n\n\nclass R(Enum):\n    INFO = auto()\n",
    "auto-aliased-base": ("from enum import Enum as E, auto\n\n\nclass R(E):\n    INFO = auto()\n"),
    "call-valued-member": "from enum import Enum\n\n\nclass R(Enum):\n    INFO = compute()\n",
}

#: And the contrast half: modules it must NOT report. A detector that matches
#: everything makes the tree-wide assertion fail somewhere far away, with nothing
#: naming the detector as the cause.
_MUST_NOT_DETECT = {
    "plain-class": "class R:\n    INFO = 'info'\n",
    "unrelated-base": "class R(dict):\n    INFO = 'info'\n",
    "enum-shaped-name-only": "class REnum:\n    INFO = 'info'\n",
    "a-name-containing-enum": "from x import Enumerator\n\n\nclass R(Enumerator):\n    INFO = 'info'\n",
    "no-members": "from enum import Enum\n\n\nclass R(Enum):\n    pass\n",
}


@pytest.mark.parametrize("label", sorted(_MUST_DETECT))
def test_the_detector_sees_every_spelling_of_an_enum_base(label: str) -> None:
    """Matched against synthetic source, so it does not depend on the tree."""
    found = _enums_in_tree(ast.parse(_MUST_DETECT[label]))
    assert found, f"{label}: the detector missed this enum, so a fork spelled this way is invisible"
    assert found[0][0] == "R"


@pytest.mark.parametrize("label", sorted(_MUST_NOT_DETECT))
def test_the_detector_rejects_what_is_not_an_enum(label: str) -> None:
    """The contrast half: without it, a detector that matches everything also passes."""
    assert _enums_in_tree(ast.parse(_MUST_NOT_DETECT[label])) == [], f"{label}: falsely reported as an enum"


def test_the_subset_probe_catches_an_aliased_severity_fork() -> None:
    """End to end on synthetic source: the member-set probe plus the alias resolution.

    This is the exact shape that used to pass the guard -- a five-rung ladder under a
    name no name-based sweep matches, with its base imported under an alias.
    """
    fork = (
        "from enum import Enum as E\n\n\nclass Urgency(E):\n"
        "    INFO = 'info'\n    LOW = 'low'\n    MEDIUM = 'medium'\n"
        "    HIGH = 'high'\n    CRITICAL = 'critical'\n"
    )
    found = _enums_in_tree(ast.parse(fork))
    assert found == [("Urgency", SEVERITY_SUBSET_PROBE)]
    assert SEVERITY_SUBSET_PROBE <= found[0][1], "the probe must match this fork"

    near_miss = fork.replace("    CRITICAL = 'critical'\n", "")
    assert (
        not SEVERITY_SUBSET_PROBE <= _enums_in_tree(ast.parse(near_miss))[0][1]
    ), "control: a four-rung ladder is not an exact subset and must not match"


def test_the_subset_probe_catches_a_ladder_written_with_auto() -> None:
    """`auto()` is the idiomatic spelling, and it used to defeat this guard outright.

    The member scan required `ast.Constant`, so every rung of an `auto()` ladder was
    invisible, the class reported zero members, and it was dropped before the subset
    probe ever saw it. A fork written the ordinary way passed.
    """
    fork = (
        "from enum import Enum, auto\n\n\nclass Urgency(Enum):\n"
        "    INFO = auto()\n    LOW = auto()\n    MEDIUM = auto()\n"
        "    HIGH = auto()\n    CRITICAL = auto()\n"
    )
    found = _enums_in_tree(ast.parse(fork))
    assert found == [("Urgency", SEVERITY_SUBSET_PROBE)], f"auto() ladder not seen: {found}"

    # Control: enum machinery and annotations are not rungs.
    machinery = (
        "from enum import Enum, auto\n\n\nclass R(Enum):\n"
        "    _order_ = 'INFO'\n    _ignore_ = 'x'\n    INFO = auto()\n"
    )
    assert _enums_in_tree(ast.parse(machinery)) == [("R", frozenset({"INFO"}))]


def test_the_iteration_probe_has_a_contrast_pair() -> None:
    """`_iterates_enum` must read syntax, not text — pinned both ways."""
    assert _iterates_enum("for s in Sev:\n    pass\n", "Sev")
    assert _iterates_enum("x = [s for s in Sev]\n", "Sev")
    assert _iterates_enum("x = {s: 0 for s in sorted(Sev)}\n", "Sev")
    assert _iterates_enum("for k in Sev.__members__:\n    pass\n", "Sev")
    # The shapes the old text probe `f"in {name}" in source` accepted as iteration:
    assert not _iterates_enum("# builds keys for every s in Sev\n", "Sev")
    assert not _iterates_enum('"""A docstring mentioning s in Sev."""\n', "Sev")
    assert not _iterates_enum("if value in Sev:\n    pass\n", "Sev")
    assert not _iterates_enum("x = other in Sev\n", "Sev")


def test_no_new_severity_subset_enum_has_regrown() -> None:
    """Catch the next copy of the ladder, by member set rather than by name."""
    found = {f"{rel}::{name}" for rel, name, members in _declared_enums() if SEVERITY_SUBSET_PROBE <= members}
    assert found, "matched no enum at all — the probe is broken, not the tree"
    unexpected = found - set(PENDING_A_WIRE_DECISION) - {CANONICAL}
    assert not unexpected, (
        f"#18098: a severity ladder was re-declared instead of aliased to the canonical: "
        f"{sorted(unexpected)}. If it is a genuinely different scale, add it here with "
        "the reason; if it is a subset, alias it — `AntiPatternSeverity = Severity`."
    )


@pytest.mark.parametrize("entry", sorted(PENDING_A_WIRE_DECISION))
def test_every_pending_entry_still_names_a_real_enum(entry: str) -> None:
    """An allowlist entry stranded by a rename or a migration exempts nothing."""
    declared = {f"{rel}::{name}" for rel, name, _ in _declared_enums()}
    assert entry in declared, (
        f"#18098: {entry} names no enum any more. If it was aliased to the canonical, "
        "drop it from PENDING_A_WIRE_DECISION."
    )


@pytest.mark.parametrize("entry", sorted(PENDING_A_WIRE_DECISION))
def test_every_pending_entry_is_still_an_exact_subset(entry: str) -> None:
    """An exemption whose premise has gone is a stale exemption.

    These are held back because each is an exact subset of the canonical ladder whose
    members are serialized. If one loses a rung it is no longer that thing, the
    subset probe stops matching it, and every other assertion here keeps passing --
    so this is the only place that would ever say so.
    """
    members = [m for rel, name, m in _declared_enums() if f"{rel}::{name}" == entry]
    assert members, f"#18098: {entry} names no enum any more"
    assert SEVERITY_SUBSET_PROBE <= members[0], (
        f"#18098: {entry} no longer carries the five-rung probe set "
        f"(has {sorted(members[0])}). It is not the exact-subset case this list is for: "
        "either it changed shape deliberately — then say so here — or a rung was lost."
    )


@pytest.mark.parametrize("entry", sorted(PENDING_A_WIRE_DECISION))
def test_every_pending_entry_is_still_iterated(entry: str) -> None:
    """The exemption's stated reason must stay true, or the exemption is stale.

    Each of these is held back only because a dict key set is built by iterating its
    members. The day that stops being true it is a plain exact subset and should be
    aliased — and nothing else would ever say so.

    Checked as syntax: the earlier `f"in {name}" in source` text probe was satisfied by
    the very comment explaining the exemption, so it could not go stale.
    """
    name = entry.split("::", 1)[1]
    source = (repo_root() / PENDING_A_WIRE_DECISION[entry]).read_text(encoding="utf-8")
    assert _iterates_enum(source, name), (
        f"#18098: {entry} is exempt because {PENDING_A_WIRE_DECISION[entry]} iterates its "
        "member set, and no `for`/comprehension over it remains. Alias it and drop the exemption."
    )


def test_the_scope_this_guard_does_not_cover_is_recorded() -> None:
    """Stated rather than implied, so "green" is not read as "clean"."""
    scanned = {rel.split("/", 1)[0] for rel, _, _ in _declared_enums()}
    assert scanned <= set(SCANNED_ROOTS)
    assert "autobot-slm-backend" not in scanned, (
        "slm-backend is out of scope on purpose — its two severity enums are "
        "(str, Enum) persisted to indexed columns, so aliasing them is a migration"
    )
