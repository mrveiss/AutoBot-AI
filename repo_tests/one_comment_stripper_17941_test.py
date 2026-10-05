# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No new hand-rolled comment stripper (#17941).

The defect class is "a guard keyed on text is satisfied by its own comment".
The *enabler* is that stripping comments was reimplemented in every guard that
needed it, so each new one rediscovered the hazard, re-solved it, or forgot --
and forgetting is silent, because the guard then passes.

#17941 listed seven copies. Scanning for the shape found **31 files**, so the
catalogue was not the population; the duplication was four times wider than the
issue that described it. This guard exists so the number only goes down.

## Why this is an AST guard and not a grep

A text scan for the stripping idiom matches **this file**, which necessarily
spells the idiom it forbids, and every allowlist entry below. That is the
#17941 defect reproducing itself inside its own fix. The detector reads the
syntax tree and looks at call nodes, so prose naming the pattern is data.
"""

from __future__ import annotations

import ast

import pytest
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()

#: Comment markers a hand-rolled stripper tests for.
_MARKERS = frozenset({"#", "//", "/*"})

#: Files that still carry their own comment skip, pending migration to
#: `tools.lint._comment_syntax`. **This list only ever shrinks.** An entry is
#: removed when that file adopts the shared helper; nothing may be added.
#:
#: NOT EVERY ENTRY IS THE SAME DEFECT, and migrating them alike would be an
#: error. Three shapes are mixed in here:
#:
#:   (a) SOURCE SCANNERS -- read a source file looking for a construct. These
#:       carry the #17941 hazard: the file's own comment about the construct
#:       satisfies the search. Migrate these.
#:
#:   (b) FORMAT PARSERS -- read a line-oriented config where a leading `#` is
#:       part of the format (`requirements.txt`, the CodeQL ceiling list, a
#:       distributions list). There is no prose to be fooled by; the concept
#:       is "parse a config line", not "ignore a comment". Forcing these onto
#:       a comment-syntax helper conflates two concepts, which is the error
#:       this module exists to stop, pointed the other way. They need their
#:       own shared parser, or they stay.
#:
#:   (d) DEPENDENCY-CONSTRAINED -- `check_ci_system_package_provisioning`
#:       runs in a CI job that installs linters and NOT the application's
#:       dependencies, and `ci_system_package_provisioning_test` enforces
#:       that with a stdlib-only import check plus a second test keeping its
#:       one exemption (`_scan_helpers`) dependency-free. Importing the shared
#:       helper there means relaxing both guards to buy a straight move that
#:       fixes no bug. The deliberate boundary wins; this entry stays.
#:
#:   (c) COMMENTS AS DATA -- `detect-hardcoded-values_test` extracts a comment
#:       HEADER; `comment_line_number_citations_test`'s whole subject is
#:       comment line numbers. Migrating these would delete their input.
#:
#: So an entry leaving this list must be argued, not batched. The count going
#: down is necessary but not sufficient.
#: The canonical implementation itself. It necessarily tests strings against
#: comment markers -- that is what it is for -- so it is exempt by identity,
#: not pending migration. Kept separate from the shrink list below on purpose:
#: an entry there is a debt that must eventually go, and this one must not.
#: `test_the_shared_helper_is_the_only_exemption` pins that this stays a set of
#: one, so "exempt" cannot quietly become a second place comment logic lives.
_CANONICAL = frozenset({"tools/lint/_comment_syntax.py"})

_PENDING_PRIVATE_STRIPPERS = frozenset(
    {
        "pipeline-scripts/ci_dispatch_watchdog.py",
        "pipeline-scripts/detect-hardcoded-values_test.py",
        "pipeline-scripts/detect_hardcoded_values_audit_test.py",
        "pipeline-scripts/pytest_root_collection_floor_test.py",
        "repo_tests/_redis_backup_harness.py",
        "repo_tests/ansible_inventory_path_exists_test.py",
        "repo_tests/ansible_requirements_parity_test.py",
        "repo_tests/branch_sweep_landing_evidence_test.py",
        "repo_tests/codeql_alert_ceiling_is_wired_15333_test.py",
        "repo_tests/comment_line_number_citations_test.py",
        "repo_tests/declared_distributions.py",
        "repo_tests/git_merge_rejects_pull_only_flags_15938_test.py",
        "repo_tests/hook_suites_run_in_ci_test.py",
        "repo_tests/hooks_path_override_15961_test.py",
        "repo_tests/infra_libs_test_wiring_guard_15051_test.py",
        "repo_tests/mcp_verification_script_coverage_14219_test.py",
        "repo_tests/no_repo_relative_phantom_path_test.py",
        "repo_tests/no_tracked_path_into_worktrees_15203_test.py",
        "repo_tests/phase_validation_paths_and_skips_17089_test.py",
        "repo_tests/redis_config_path_is_canonical_17434_test.py",
        "repo_tests/redis_unit_name_is_canonical_16060_test.py",
        "repo_tests/slm_frontend_shell_publish_test.py",
        "repo_tests/stranded_recorder_entries_test.py",
        "repo_tests/sync_deletions_target_pinning_and_shell_safety_16310_test.py",
        "repo_tests/sys_modules_leak_guard.py",
        "repo_tests/test_dockerignore_test_file_coverage_14127.py",
        "repo_tests/validate_access_control_reporting_test.py",
        "tools/lint/_scan_helpers.py",
        "tools/lint/check_canonical_role_names.py",
        "tools/lint/check_ci_system_package_provisioning.py",
        "tools/lint/check_extension_import_boundaries.py",
        "tools/lint/check_git_toplevel_env_scrubbed.py",
        "tools/lint/check_git_write_env_scrubbed_test.py",
    }
)


def _strips_comments_by_hand(tree: ast.AST) -> bool:
    """True if the module tests a string against a comment marker itself.

    Matches `x.startswith("#")` and its siblings on any receiver, including
    inside a comprehension or an `if`. Reads call nodes, so a docstring or a
    comment naming the idiom -- as this module's own do -- cannot satisfy it.
    """
    # An `assert line.startswith("#")` is a control ASSERTING something is a
    # comment, not logic stripping one -- `git_repo_root_calls_are_guarded`
    # asserts exactly that about its own fixture. Flagging it is a false
    # positive, and a guard with false positives gets muted, which costs more
    # than the copy it would have caught.
    asserted: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            asserted.update(id(child) for child in ast.walk(node))

    for node in ast.walk(tree):
        if id(node) in asserted:
            continue
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "startswith":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and arg.value in _MARKERS:
                return True
            if isinstance(arg, ast.Tuple) and any(
                isinstance(e, ast.Constant) and e.value in _MARKERS for e in arg.elts
            ):
                return True
    return False


def _files_with_private_strippers() -> set[str]:
    found: set[str] = set()
    candidates = tracked_paths(_ROOT, "repo_tests/*.py", "tools/lint/*.py", "pipeline-scripts/*.py")
    # Non-vacuity: an empty sweep satisfies every assertion below by looking at
    # nothing. MEASUREMENT_DISCIPLINE.md -- "nothing found" must not read like
    # "did not look".
    assert len(candidates) > 200, f"only {len(candidates)} files swept -- the patterns or the root are wrong"
    for rel in candidates:
        path = _ROOT / rel
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        if _strips_comments_by_hand(tree):
            found.add(rel)
    return found


def test_no_new_file_strips_comments_by_hand() -> None:
    """The ratchet. A new private copy fails here; a migrated one must be delisted."""
    found = _files_with_private_strippers()
    added = sorted(found - _PENDING_PRIVATE_STRIPPERS - _CANONICAL)

    assert not added, (
        f"{len(added)} file(s) test a string against a comment marker directly instead of using "
        f"`tools.lint._comment_syntax`:\n  " + "\n  ".join(added) + "\n\n"
        "#17941: seven copies were catalogued and thirty-one existed. Each one re-derives "
        "quote handling, or skips it -- and a stripper that misses a `#` inside a string "
        "reintroduces the class one level down. Use the shared helper."
    )


def test_the_pending_list_only_shrinks() -> None:
    """Direction, not agreement (#17970).

    A mirrored pair of hand-kept records detects transcription errors and not
    movement. This compares the record against the LIVE tree, so an entry that
    has been migrated must be deleted here or the guard fails -- which is what
    makes the list a ratchet rather than a note.
    """
    found = _files_with_private_strippers()
    stale = sorted(_PENDING_PRIVATE_STRIPPERS - found)

    assert not stale, (
        f"{len(stale)} entr(y/ies) in `_PENDING_PRIVATE_STRIPPERS` no longer carry a private "
        f"stripper:\n  " + "\n  ".join(stale) + "\n\nDelete them. The list is a ratchet; leaving a "
        "migrated file listed lets a future one be re-added under cover of an entry that is "
        "already spent."
    )


@pytest.mark.parametrize(
    "label,source,expected",
    [
        ("a hash startswith", 'if line.startswith("#"):\n    pass\n', True),
        ("a slash-slash startswith", 'if line.startswith("//"):\n    pass\n', True),
        ("a tuple of markers", 'if line.startswith(("#", "//")):\n    pass\n', True),
        ("startswith on something else", 'if name.startswith("test_"):\n    pass\n', False),
        ("a comment naming the idiom", '# we used to call line.startswith("#") here\nx = 1\n', False),
        ("a docstring naming the idiom", '"""Avoid line.startswith(\\"#\\") -- use the helper."""\nx = 1\n', False),
        ("the marker as a plain string", 'MARKER = "#"\nx = 1\n', False),
    ],
)
def test_the_detector_reads_code_and_not_prose(label: str, source: str, expected: bool) -> None:
    """The contrast set, including the two cases this very file contains.

    The prose rows are not hypothetical: the module docstring above and the
    comments inside `_PENDING_PRIVATE_STRIPPERS` both spell the idiom. A
    text-keyed version of this guard would flag itself and then be muted.
    """
    assert _strips_comments_by_hand(ast.parse(source)) is expected, label


def test_the_shared_helper_is_the_only_exemption() -> None:
    """Exempt-by-identity must stay a set of one.

    The failure mode this forecloses: a second module gets added here because
    it "also legitimately handles comments", and then there are two canonical
    homes, which is the duplication this whole change removed.
    """
    assert _CANONICAL == {"tools/lint/_comment_syntax.py"}, (
        f"the canonical exemption grew to {sorted(_CANONICAL)}. If a second module genuinely "
        "needs to own comment logic, that is a decision to record on #17941, not an entry to add."
    )
    assert (_ROOT / "tools/lint/_comment_syntax.py").exists(), (
        "the canonical module is exempted but does not exist -- the exemption would silently "
        "cover nothing while the guard reported clean"
    )
