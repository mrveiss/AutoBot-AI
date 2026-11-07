# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pre-push test selection (#16711), driven with fixture changesets.

#16700's changeset held three ``tests/test_*.py`` files and a ``*_test.py`` guard; the
old selection ran only the guard, so a broken assertion in one of the others failed
first in CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autobot_shared.isolated_git import git, make_repo
from tools.lint.prepush_selection import (
    ALWAYS_RUN,
    declared_roots,
    format_selection,
    pytest_settings,
    select,
    tests_naming,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PATTERNS = ("test_*.py", "*_test.py")


def _run(changed, *, present=None, ignores=()):
    """Select for *changed*; every changed path exists unless *present* names the files that do."""
    files = set(changed) if present is None else set(present)
    return select(changed, patterns=_PATTERNS, ignores=ignores, exists=lambda rel: rel in files)


def test_the_16700_changeset_runs_every_test_it_changed():
    """#16711: each tests/test_*.py here was classified as production and never ran."""
    changed = [
        "autobot-backend/tests/test_npu_bootstrap_credential_16657.py",
        "autobot-slm-backend/tests/test_redis_password_provisioned_16627.py",
        "autobot-slm-backend/tests/test_redis_username_plumbing_16626.py",
        "repo_tests/redis_password_literal_guard_test.py",
    ]
    assert _run(changed) == {path: "changed" for path in changed}


def test_the_naming_conventions_come_from_pytest_ini():
    ini = "[pytest]\npython_files = test_*.py *_test.py check_*.py\naddopts =\n    -ra\n    --ignore=vendor/tree\n"
    assert pytest_settings(ini) == (("test_*.py", "*_test.py", "check_*.py"), ("vendor/tree",))
    patterns, _ = pytest_settings((_REPO_ROOT / "pytest.ini").read_text(encoding="utf-8"))
    assert {"test_*.py", "*_test.py"} <= set(patterns)


def test_a_changed_module_still_selects_its_co_located_test():
    module, sibling = "autobot-backend/knowledge/facts.py", "autobot-backend/knowledge/facts_test.py"
    assert _run([module], present={sibling}) == {sibling: f"co-located with {module}"}


def test_a_changed_test_module_is_not_given_a_sibling():
    """A test_*.py is a test; looking for test_x_test.py was the #16711 misclassification."""
    assert _run(["pkg/tests/test_x.py"], present={"pkg/tests/test_x.py", "pkg/tests/test_x_test.py"}) == {
        "pkg/tests/test_x.py": "changed"
    }


def test_an_ignored_or_vanished_test_is_never_selected():
    assert _run(["vendor/tree/x_test.py"], ignores=("vendor/tree",)) == {}
    assert _run(["gone_test.py"], present=set()) == {}
    assert _run(["docs/readme.md"]) == {}


def test_every_selected_test_is_printed_with_its_reason():
    assert format_selection({"a_test.py": "changed", "b_test.py": "co-located with b.py"}) == (
        "a_test.py\tchanged\nb_test.py\tco-located with b.py\n"
    )


# ---------------------------------------------------------------------------
# #17241: tree-scanning guards. Every red on that PR was a guard that scans the
# repository by glob or enumerates every tracked file. Neither rule above can
# reach one: they are co-located with nothing, so the push saw green and CI
# failed ten minutes later, four times.
# ---------------------------------------------------------------------------

_DECLARED = {
    "*.yml": frozenset({"repo_tests/test_deploy_constraint_rewrite_14272.py"}),
    "*.md": frozenset({"repo_tests/doc_sync_hook_resolves_indexer_15845_test.py"}),
}


def test_a_changed_file_runs_the_guards_that_declare_a_matching_glob():
    """The shard-3 and shard-11 reds: an ansible edit and a new research doc."""
    chosen = select(
        ["autobot-slm-backend/ansible/roles/backend/tasks/main.yml"],
        patterns=_PATTERNS,
        ignores=(),
        exists=lambda rel: True,
        declared_globs=_DECLARED,
    )

    assert "repo_tests/test_deploy_constraint_rewrite_14272.py" in chosen
    assert "glob" in chosen["repo_tests/test_deploy_constraint_rewrite_14272.py"]


def test_a_glob_that_does_not_match_selects_nothing():
    """The contrast: matching everything would be as useless as matching nothing."""
    chosen = select(
        ["autobot-backend/api/chat.py"],
        patterns=_PATTERNS,
        ignores=(),
        exists=lambda rel: True,
        declared_globs=_DECLARED,
    )

    assert "repo_tests/test_deploy_constraint_rewrite_14272.py" not in chosen
    assert "repo_tests/doc_sync_hook_resolves_indexer_15845_test.py" not in chosen


def test_adding_a_guard_runs_the_guards_that_police_guards():
    """The shard-2 and shard-8 reds: a new repo_tests file is checked by both."""
    chosen = _run(
        ["repo_tests/ansible_code_source_delegation_17243_test.py"],
        present={
            "repo_tests/ansible_code_source_delegation_17243_test.py",
            "repo_tests/glob_declared_reads_15900_test.py",
            "repo_tests/one_repo_root_spelling_15925_test.py",
        },
    )

    assert "repo_tests/glob_declared_reads_15900_test.py" in chosen
    assert "repo_tests/one_repo_root_spelling_15925_test.py" in chosen


def test_a_non_guard_change_does_not_drag_in_the_guard_police():
    """They run when repo_tests changes, not on every push."""
    chosen = _run(["autobot-backend/api/chat.py"], present={"autobot-backend/api/chat_test.py"})

    assert "repo_tests/glob_declared_reads_15900_test.py" not in chosen


def test_a_renamed_guard_police_entry_fails_open():
    """A stale entry must not block a push; exists() drops it."""
    chosen = _run(["repo_tests/some_new_guard_test.py"], present={"repo_tests/some_new_guard_test.py"})

    assert "repo_tests/glob_declared_reads_15900_test.py" not in chosen
    assert chosen == {"repo_tests/some_new_guard_test.py": "changed"}


def test_the_record_is_parsed_as_data_not_imported():
    """The real record must yield real globs, or the selection silently does nothing."""
    from tools.lint.prepush_selection import GLOB_RECORD, glob_declared_guards

    declared = glob_declared_guards((_REPO_ROOT / GLOB_RECORD).read_text(encoding="utf-8"))

    assert len(declared) >= 10, f"only {len(declared)} globs parsed; the record shape changed"
    assert all(isinstance(guards, frozenset) and guards for guards in declared.values())


def test_an_unparseable_record_degrades_instead_of_breaking_the_push():
    """A syntax error in the record must not make every push fail."""
    from tools.lint.prepush_selection import glob_declared_guards

    assert glob_declared_guards("def broken(:\n") == {}
    assert glob_declared_guards("SOMETHING_ELSE = 1\n") == {}


# ----- #18808 / #16715: guards no sibling or recorded glob reaches ----------------------------

_GUARD = "repo_tests/forks_test.py"


def test_every_push_runs_the_cheap_whole_tree_guards():
    """#18808: the file-size ratchets and their kin fire on the tree's shape, not on a sibling."""
    always = {"repo_tests/size_ratchet_test.py": "whole-tree: sizes"}
    chosen = select(["docs/README.md"], patterns=_PATTERNS, ignores=(), exists=lambda rel: True, always=always)

    assert chosen["repo_tests/size_ratchet_test.py"] == "whole-tree: sizes"


def test_an_empty_changeset_runs_nothing_even_the_whole_tree_guards():
    always = {"repo_tests/size_ratchet_test.py": "whole-tree: sizes"}

    assert select([], patterns=_PATTERNS, ignores=(), exists=lambda rel: True, always=always) == {}


def test_every_always_run_guard_exists():
    """A renamed guard would drop out silently: ``exists`` filters it, so pin the list itself."""
    missing = [g for g in ALWAYS_RUN if not (_REPO_ROOT / g).is_file()]

    assert not missing, f"ALWAYS_RUN names guards that no longer exist: {missing}"


def test_a_guard_runs_when_a_path_under_its_declared_roots_changes():
    """#16691's shape: an ansible template change tripped a guard that scans autobot-slm-backend."""
    roots = {_GUARD: ("autobot-slm-backend", "autobot_shared/")}
    template = "autobot-slm-backend/ansible/roles/redis/templates/redis.conf.j2"
    chosen = select([template], patterns=_PATTERNS, ignores=(), exists=lambda rel: True, roots=roots)

    assert chosen[_GUARD] == f"scans autobot-slm-backend, autobot_shared/; {template} changed"


def test_a_path_outside_every_root_selects_nothing():
    roots = {_GUARD: ("autobot-slm-backend",)}

    assert _GUARD not in select(
        ["docs/README.md"], patterns=_PATTERNS, ignores=(), exists=lambda rel: True, roots=roots
    )


def test_roots_match_as_raw_prefixes_the_way_scope_claims_read_them():
    """A look-alike sibling tree is selected too: over-selecting is the safe direction, and it is
    exactly what `_reach_scope.scope_complaint` counts as inside the root."""
    roots = {_GUARD: ("autobot-slm-backend",)}
    chosen = select(
        ["autobot-slm-backend-extras/x.py"], patterns=_PATTERNS, ignores=(), exists=lambda rel: True, roots=roots
    )

    assert _GUARD in chosen


def test_roots_are_read_from_the_record_as_data():
    record = "REACH_ROOTS = {\n    'repo_tests/forks_test.py': ('autobot-backend', 'autobot_shared/'),\n}\n"

    assert declared_roots(record) == {_GUARD: ("autobot-backend", "autobot_shared/")}
    assert declared_roots("def (:\n") == {}, "an unparseable record selects nothing extra"


def test_a_raw_prefix_root_covers_every_tree_it_prefixes():
    """#19312 review: a root `autobot-` (as scope_complaint reads it) never matched as a directory."""
    roots = {_GUARD: ("autobot-",)}
    chosen = select(["autobot-slm-backend/x.py"], patterns=_PATTERNS, ignores=(), exists=lambda rel: True, roots=roots)

    assert chosen[_GUARD] == "scans autobot-; autobot-slm-backend/x.py changed"


def test_the_real_record_parses_to_every_guard_it_names():
    text = (_REPO_ROOT / "repo_tests" / "_reach_roots_record.py").read_text(encoding="utf-8")

    assert len(declared_roots(text)) >= 80


def test_a_test_that_names_a_changed_file_runs_with_it():
    """#16715 AC1: a template-slicing test names the template; a change to it runs that test."""
    template = "autobot-slm-backend/ansible/roles/x/templates/x.service.j2"
    refs = {template: ["autobot-slm-backend/tests/test_x_unit.py"]}
    chosen = select([template], patterns=_PATTERNS, ignores=(), exists=lambda rel: True, references=refs)

    assert chosen["autobot-slm-backend/tests/test_x_unit.py"] == f"names {template}"


def test_tests_naming_finds_a_path_and_a_unique_basename_but_not_a_shared_one(tmp_path):
    repo = make_repo(tmp_path / "repo")
    files = {
        "roles/a/templates/unique.conf.j2": "x\n",
        "roles/a/tasks/main.yml": "x\n",
        "roles/b/tasks/main.yml": "x\n",
        "tests/test_by_path.py": "P = 'roles/a/templates/unique.conf.j2'\n",
        "tests/test_by_name.py": "P = 'unique.conf.j2'\n",
        "tests/test_main_yml.py": "P = 'main.yml'\n",
        "docs/notes.md": "unique.conf.j2\n",
    }
    for rel, body in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(body, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "fixture")

    found = tests_naming(repo, ["roles/a/templates/unique.conf.j2", "roles/a/tasks/main.yml", "x.py"], _PATTERNS)

    assert found == {"roles/a/templates/unique.conf.j2": ["tests/test_by_name.py", "tests/test_by_path.py"]}


def test_a_search_that_cannot_enumerate_fails_instead_of_selecting_fewer(tmp_path):
    """#19312 review: an empty enumeration returned {} -- fewer tests, in silence."""
    repo = make_repo(tmp_path / "empty")

    with pytest.raises(Exception, match="(?i)enumerat|no tracked|empty"):
        tests_naming(repo, ["roles/a/templates/x.j2"], _PATTERNS)
