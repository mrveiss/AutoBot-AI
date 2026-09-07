# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Glob-declared guard inputs, which the concrete-literal checker cannot see (#15900).

`python_filter_covers_its_guards_test.py` records a guard's input only when that
input resolves to a **concrete file**::

    if not (_REPO_ROOT / candidate).is_file():
        return  # a prefix or a glob, not a file this guard reads

So a guard declaring ``".github/workflows/*.yml"`` contributes nothing. Its
dependency is real; its detection is not — and the checker's green therefore
means "no guard reads an uncovered file *by concrete literal*" while its name
claims the general property.

**Why this is a separate record rather than an expansion of that one.** #15900
costed the obvious fix: teaching `_record` to expand globs turns 27 uncovered
entries into roughly 86, because `.github/workflows/` alone holds 64 files.
`MAX_UNCOVERED_READS` only ever goes down, so expansion forces either a 59-entry
cap raise or widening the filter to `.github/workflows/**` — twelve shards on
almost every pull request. That is a CI-spend decision, and it was being made by
an accident of implementation rather than deliberately.

Recording the **declarations** costs none of that. There are 14 of them across 5
guards, against 59+ expansions, and they are the thing a reader needs: *which
guard depends on which tree*. An undetectable dependency and an absent one are
indistinguishable, and this makes them distinguishable without spending a shard.

The population is **discovered** — every quoted repo-relative string containing
`*` — not a list of the four the issue named. That is how the fifth was found:
`scripts/lib/*.sh` is a real uncovered dependency of
`comment_line_number_citations_test.py` that #15900 does not mention.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from repo_tests._paths import repo_root
from repo_tests.python_filter_covers_its_guards_test import _filter_patterns, _is_covered
from tools.lint._scan_helpers import tracked_paths

REPO_ROOT = repo_root()

#: A repo-relative path mentioned in a guard, containing a glob. Anchored on a
#: quote for the same reason the sibling checker is: an unquoted match picks up
#: prose and import paths, which are not reads of the tree.
_QUOTED_GLOB = re.compile(r"""["']([A-Za-z0-9_.*?\[\]-]+(?:/[A-Za-z0-9_./*?\[\]-]+)*)["']""")


def _is_path_like(candidate: str) -> bool:
    """Whether *candidate* is a repo-relative glob rather than Python syntax.

    Requiring a slash AND `*` missed `"*.toml"`, `"config/?.yml"` and
    `"config/[ab].yml"` (#15994 review). But accepting `?` and `[` naively is
    unusable: brackets are subscripts and type annotations, and a widened regex
    reported `list[Path]`, `os.environ[`, `[Unit]`, `string[]` and
    `github-actions[bot]` as guard dependencies — 44 "uncovered" entries of
    which most were Python source.

    So: a slash means the first segment must be a real directory; without one,
    the string must look like a suffix glob (`*.yml`, `?.min.js`). A bracket
    class is accepted only inside a path that already has a slash.
    """
    if not any(ch in candidate for ch in "*?["):
        return False
    if "[" in candidate and "/" not in candidate and not _SUFFIX_GLOB.match(candidate):
        return False
    if "/" in candidate:
        return (REPO_ROOT / candidate.split("/", 1)[0]).is_dir()
    return bool(_SUFFIX_GLOB.match(candidate))


#: `*.yml`, `?.min.js`, `*requirements*.txt` — a leading glob and a dotted suffix.
_SUFFIX_GLOB = re.compile(r"^[*?][A-Za-z0-9_.*-]*[.][A-Za-z0-9]+$")

#: Glob declarations whose tree the python filter does NOT cover, with the guard
#: that declares each and why it is accepted for now.
#:
#: THIS ONLY SHRINKS. An entry leaves when the filter covers its tree, or when a
#: cheaper route runs that guard on its own trigger. Never add one to make a new
#: uncovered dependency pass — that is the decision this record exists to keep
#: visible rather than to rubber-stamp.
GLOB_DECLARED_UNCOVERED: dict[str, tuple[set[str], str]] = {
    "*.conf": (
        {"repo_tests/slm_frontend_atomic_publish_15610_test.py"},
        "root-relative `*.conf` sweep; the matching files live outside the python filter's trees",
    ),
    "*.conf.j2": (
        {"repo_tests/slm_frontend_atomic_publish_15610_test.py"},
        "root-relative `*.conf.j2` sweep; the matching files live outside the python filter's trees",
    ),
    "*.md": (
        {
            "repo_tests/doc_sync_hook_resolves_indexer_15845_test.py",
            "repo_tests/documented_playbook_invocations_test.py",
            "repo_tests/sdk_docs_paths_test.py",
        },
        "root-relative `*.md` sweep; the matching files live outside the python filter's trees",
    ),
    "*.min.js": (
        {"repo_tests/one_git_enumeration_15926_test.py"},
        "test fixture — a pathspec used against a throwaway repository, not a dependency on this tree",
    ),
    "*.promtool-test.yml": (
        {"repo_tests/promtool_rules_test.py"},
        "root-relative `*.promtool-test.yml` sweep; the matching files live outside the python filter's trees",
    ),
    "*.sh": (
        {
            "repo_tests/ansible_inventory_path_exists_test.py",
            "repo_tests/deployment_script_scan.py",
            "repo_tests/embedded_python_dependency_declared_test.py",
            "repo_tests/one_git_enumeration_15926_test.py",
            "repo_tests/shell_lib_sources_resolve_test.py",
            "repo_tests/shell_lib_test.py",
            "repo_tests/slm_frontend_shell_publish_test.py",
        },
        "root-relative `*.sh` sweep; the matching files live outside the python filter's trees",
    ),
    "*.ts": (
        {"repo_tests/slm_frontend_calls_reach_served_routes_test.py"},
        "root-relative `*.ts` sweep; the matching files live outside the python filter's trees",
    ),
    "*.vue": (
        {"repo_tests/slm_frontend_calls_reach_served_routes_test.py"},
        "root-relative `*.vue` sweep; the matching files live outside the python filter's trees",
    ),
    "*.yaml": (
        {"repo_tests/hook_suites_run_in_ci_test.py", "repo_tests/infra_libs_test_wiring_guard_15051_test.py"},
        "root-relative `*.yaml` sweep; the matching files live outside the python filter's trees",
    ),
    "*.yml": (
        {
            "repo_tests/access_control_enforcement_provisioning_test.py",
            "repo_tests/ansible_inventory_mapping_renders_anywhere_test.py",
            "repo_tests/ansible_manifest_resolution.py",
            "repo_tests/ansible_pip_isolation_test.py",
            "repo_tests/documented_playbook_invocations_test.py",
            "repo_tests/frontend_duplicate_typecheck_compile_guard_test.py",
            "repo_tests/hook_suites_run_in_ci_test.py",
            "repo_tests/infra_libs_test_wiring_guard_15051_test.py",
            "repo_tests/job_name_names_what_it_runs_test.py",
            "repo_tests/pip_relative_editable_needs_chdir_test.py",
            "repo_tests/python_interpreter_role_rename_test.py",
            "repo_tests/required_context_complements_test.py",
            "repo_tests/test_agent_venv_isolation_14278.py",
            "repo_tests/test_ci_import_smoke_paths_14252.py",
            "repo_tests/test_deploy_constraint_rewrite_14272.py",
            "repo_tests/workflow_action_version_regression_test.py",
            "repo_tests/workflow_closed_reference_guard_test.py",
            "repo_tests/workflow_concurrency_guard_test.py",
        },
        "root-relative `*.yml` sweep; the matching files live outside the python filter's trees",
    ),
    "*_test.sh": (
        {"repo_tests/shell_lib_test.py"},
        "root-relative `*_test.sh` sweep; the matching files live outside the python filter's trees",
    ),
    "*package.json": (
        {"repo_tests/npm_test_scripts_run_in_ci_test.py"},
        "root-relative `*package.json` sweep; the matching files live outside the python filter's trees",
    ),
    "*requirements*.txt": (
        {"repo_tests/declared_distributions_test.py", "repo_tests/dependabot_requirements_coverage_test.py"},
        "root-relative `*requirements*.txt` sweep; the matching files live outside the python filter's trees",
    ),
    ".github/actions/**": (
        {"repo_tests/code_quality_guard_reach_test.py"},
        "CI metadata tree; covering it runs twelve shards on almost every pull request (#15900)",
    ),
    ".github/actions/*/action.yml": (
        {"repo_tests/python_version_declaration_drift_test.py"},
        "CI metadata tree; covering it runs twelve shards on almost every pull request (#15900)",
    ),
    ".github/workflows/*.yaml": (
        {"repo_tests/python_version_declaration_drift_test.py"},
        "CI metadata tree; covering it runs twelve shards on almost every pull request (#15900)",
    ),
    ".github/workflows/*.yml": (
        {
            "repo_tests/comment_line_number_citations_test.py",
            "repo_tests/python_filter_covers_its_guards_test.py",
            "repo_tests/python_version_declaration_drift_test.py",
        },
        "CI metadata tree; covering it runs twelve shards on almost every pull request (#15900)",
    ),
    "?.min.js": (
        {"repo_tests/one_git_enumeration_15926_test.py"},
        "test fixture — a pathspec used against a throwaway repository, not a dependency on this tree",
    ),
    "scripts/lib/*.sh": (
        {"repo_tests/comment_line_number_citations_test.py"},
        "tree `scripts/` is outside the python filter; the per-tree trade #15900 declines to make wholesale",
    ),
}

#: Floor on guards PARSED, not on declarations found. A findings floor is
#: satisfied by finding nothing, which is also what a collapsed sweep reports.
_MIN_GUARDS_PARSED = 180


def glob_declarations_in(source: str) -> set[str]:
    """Repo-relative glob declarations mentioned in *source*."""
    return {m.group(1) for m in _QUOTED_GLOB.finditer(source) if _is_path_like(m.group(1))}


def _probe_path(glob: str) -> str:
    """A concrete path the *glob* would match, for the filter's own matcher."""
    return glob.replace("**/", "").replace("**", "x").replace("*", "x")


def _declared() -> tuple[dict[str, set[str]], int]:
    """Every glob declaration in `repo_tests`, and the number of guards parsed."""
    declarations: dict[str, set[str]] = {}
    parsed = 0
    for rel in tracked_paths(REPO_ROOT, "repo_tests/*.py"):
        # THIS module is excluded, and for the opposite reason to #15990's census.
        # There the guard counted invocations, so skipping itself hid a real
        # bypass. Here the record's own KEYS are quoted glob strings, so scanning
        # this file rediscovers every entry from the record itself — and
        # `test_the_record_only_shrinks` could then never fire, because an entry
        # stays "declared" after its dependent guard stops declaring it. A record
        # that reads itself cannot go stale, which is the same as not checking.
        if Path(rel).name == Path(__file__).name:
            continue
        try:
            source = (REPO_ROOT / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        parsed += 1
        for glob in glob_declarations_in(source):
            declarations.setdefault(glob, set()).add(rel)
    return declarations, parsed


def test_every_uncovered_glob_declaration_is_recorded() -> None:
    """A glob into a tree the filter misses must be written down, not silent."""
    declarations, parsed = _declared()
    assert parsed >= _MIN_GUARDS_PARSED, (
        f"the sweep parsed {parsed} guards, below the floor of {_MIN_GUARDS_PARSED} — "
        "a shrunken population reports 'no uncovered globs' for the same reason a covered tree does"
    )
    patterns = _filter_patterns()
    uncovered = {g for g in declarations if not _is_covered(_probe_path(g), patterns)}

    unrecorded = sorted(uncovered - set(GLOB_DECLARED_UNCOVERED))
    assert not unrecorded, (
        "these guards declare a glob into a tree the python filter does not cover, and the "
        "dependency is recorded nowhere — so the guard silently does not run when that tree "
        "changes (#15900):\n  " + "\n  ".join(f"{g}  <- {', '.join(sorted(declarations[g]))}" for g in unrecorded)
    )


def test_the_record_only_shrinks() -> None:
    """A resolved entry must be deleted, so the record cannot rot into a wish list."""
    declarations, _ = _declared()
    patterns = _filter_patterns()
    uncovered = {g for g in declarations if not _is_covered(_probe_path(g), patterns)}

    stale = sorted(set(GLOB_DECLARED_UNCOVERED) - uncovered)
    assert not stale, (
        "these entries are no longer uncovered — the filter reaches them now, or the guard "
        "stopped declaring them. Delete them from GLOB_DECLARED_UNCOVERED:\n  " + "\n  ".join(stale)
    )


def test_the_record_names_exactly_the_guards_that_declare_each_glob() -> None:
    """Bidirectional, because a name that is merely plausible is not evidence.

    The first version asserted only that the reason string contained
    `_test.py`, so an entry could name an unrelated guard and pass (#15994
    review) — a record that is wrong in a way nothing detects is worse than one
    that is absent, because a maintainer deciding how to cover the dependency
    trusts it.

    Guards are structured data now, and both directions are checked: every guard
    discovered for a glob must be recorded, and every recorded guard must still
    declare it.
    """
    declarations, _ = _declared()
    for glob, (recorded, _reason) in GLOB_DECLARED_UNCOVERED.items():
        discovered = declarations.get(glob, set())
        assert discovered, f"{glob}: recorded, but no guard declares it any more — delete the entry"
        assert recorded == discovered, (
            f"{glob}: the record names {sorted(recorded)} but the guards declaring it are "
            f"{sorted(discovered)}. Recorded-but-not-declaring: {sorted(recorded - discovered)}; "
            f"declaring-but-not-recorded: {sorted(discovered - recorded)}"
        )


def test_every_record_entry_carries_a_reason() -> None:
    """A reason recording only that a decision happened is not a reason."""
    for glob, (_guards, reason) in GLOB_DECLARED_UNCOVERED.items():
        assert len(reason) > 25, f"{glob}: reason too thin to act on — {reason!r}"


def test_the_detector_reports_a_glob_declaration() -> None:
    """Positive control: the shape this guard exists to see."""
    assert glob_declarations_in('paths = (".github/workflows/*.yml",)') == {".github/workflows/*.yml"}


@pytest.mark.parametrize(
    "source",
    [
        'x = "a concrete/file.yml"',
        'x = "not_a_path"',
        'x = "no-such-tree-here/*.yml"',
    ],
    ids=["concrete-file", "bare-word", "unknown-tree"],
)
def test_the_detector_ignores_what_is_not_a_glob_into_this_tree(source: str) -> None:
    """The contrasts. Without them, "detect globs" is satisfied by reporting every string.

    A concrete literal is the SIBLING checker's job and must not be duplicated
    here; a bare word is not a path; a path into a directory this repository does
    not have is prose, not a read.
    """
    assert glob_declarations_in(source) == set()


@pytest.mark.parametrize(
    "declaration",
    ['x = "*.toml"', 'x = "scripts/?.sh"', 'x = ".github/workflows/*.yml"', 'x = "*requirements*.txt"'],
    ids=["root-suffix", "question-mark", "path-with-star", "embedded-star"],
)
def test_the_detector_accepts_every_supported_glob_form(declaration: str) -> None:
    """Root-relative and `?`-bearing forms, which the first version required a slash and `*` for.

    The review's illustrative `"config/?.yml"` is replaced by `"scripts/?.sh"`:
    a path whose first segment is not a real directory is prose, not a read, and
    this repository has no `config/`. Using it would have asserted the detector
    accepts a shape it correctly rejects.
    """
    assert glob_declarations_in(declaration), f"missed: {declaration}"


@pytest.mark.parametrize(
    "source",
    [
        "x: list[Path] = []",
        'x = os.environ["HOME"]',
        'x = "[Unit]"',
        'x = "string[]"',
        'x = "github-actions[bot]"',
        'x = "[A-Za-z_][A-Za-z0-9_]*"',
    ],
    ids=["annotation", "subscript", "ini-section", "ts-type", "bot-name", "regex"],
)
def test_the_detector_rejects_python_syntax_that_merely_contains_brackets(source: str) -> None:
    """The reason `?` and `[` could not simply be added to the character class.

    A naive widening reported all six of these as guard dependencies — 44
    "uncovered" entries, mostly Python source. Brackets are subscripts and type
    annotations far more often than they are pathspecs.
    """
    assert glob_declarations_in(source) == set()


def test_the_record_cannot_rediscover_itself() -> None:
    """This module is outside its own sweep, so its keys are not declarations.

    Without the exclusion, every entry stays discovered forever — the record
    reads its own keys back and `test_the_record_only_shrinks` can never fire.
    A record that cannot go stale is not being checked.
    """
    declarations, _ = _declared()
    own = {g for g, guards in declarations.items() if any(Path(__file__).name in x for x in guards)}
    assert not own, f"this module's own strings entered the population: {sorted(own)}"
