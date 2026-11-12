#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The skips the pre-board guard lane accepts, each reviewed against evidence (#21359).

Split from ``preboard_guard_lane_report.py``: the verdict logic stays small, this file is data.

An entry joins only with evidence, never by guess: the skip reason observed in the ``-rs`` summary of
the python suite's own shards (ci.yml prints it) -- run 43181148822 on the head of #21361, eight shards,
443 distinct ``SKIPPED`` lines, 60 of them under the lane's roots in 22 test files -- and a class decided
by comparing the lane's setup with the suite's (both call ``./.github/actions/setup-python-suite``,
both start the same Redis service; the lane checks out the full history, the suite two commits):

* ``covered-by-suite-only`` -- the lane skips it, the train's suite RUNS it (a tool or a session only the
  suite has). Removed by #21360, which moves that setup into a composite action both workflows call.
* ``equivalent-to-suite`` -- the suite skips it identically on the same runner image and the lane's
  environment is the same for that test, so the train exercises nothing more than the lane. It is either
  a guard that skips on every CI run (a defect, tracked by #21371, which removes the entry) or a skip
  that is correct by design (the follow-up says why).

``source_marker`` is text that must stay in ``file``; :func:`stale_entries` fails an entry whose file is
gone or whose marker is gone, so a list entry cannot outlive the skip it names. A skip not listed here
makes the lane's verdict ``red``: add an entry only after reading what the test skips on.

Suite skips that the lane does NOT list, on purpose: tests that read git history (the suite's checkout is
shallow and skips them, the lane's is not, so it runs them), and the backend's live-service tests (the
lane does not run the backend tree).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

#: The lane skips it and the train's suite runs it (the suite provides a tool or session the lane does not).
COVERED_BY_SUITE_ONLY = "covered-by-suite-only"

#: The suite skips it identically on the same runner image: the train exercises nothing more than the lane.
EQUIVALENT_TO_SUITE = "equivalent-to-suite"

SKIP_CLASSES = (COVERED_BY_SUITE_ONLY, EQUIVALENT_TO_SUITE)

#: Removes every ``covered-by-suite-only`` entry, by moving the skipped check into a composite action.
FOLLOW_UP = "#21360"

#: Removes every entry for a guard that skips on every CI run (tracked: the guard is to run or to fail).
SILENT_GUARD = "#21371"

#: What a follow-up looks like: an issue that removes the entry, or ``by design: <why>``.
BY_DESIGN = "by design: "
FOLLOW_UP_FORM = re.compile(r"#\d+|by design: \S.+")


class AllowedSkip(NamedTuple):
    """One reviewed skip: where, the start of its reason, the text proving it exists, class, follow-up, why."""

    file: str
    reason_prefix: str
    source_marker: str
    skip_class: str
    follow_up: str
    why: str


def _covered(file: str, reason_prefix: str, source_marker: str, why: str) -> AllowedSkip:
    return AllowedSkip(file, reason_prefix, source_marker, COVERED_BY_SUITE_ONLY, FOLLOW_UP, why)


def _silent(file: str, reason_prefix: str, source_marker: str, why: str) -> AllowedSkip:
    return AllowedSkip(file, reason_prefix, source_marker, EQUIVALENT_TO_SUITE, SILENT_GUARD, why)


def _by_design(file: str, reason_prefix: str, source_marker: str, why: str) -> AllowedSkip:
    return AllowedSkip(file, reason_prefix, source_marker, EQUIVALENT_TO_SUITE, BY_DESIGN + why, why)


#: ``covered-by-suite-only`` -- the check needs a service or a binary the suite's python-shard job
#: provides and this workflow does not. The suite's own ``-rs`` shows NO promtool skip (it installs the
#: binary and sets AUTOBOT_REQUIRE_PROMTOOL=1); for the two ChromaDB modules it shows the "stubbed" skip
#: in the shared session of all eight shards AND a dedicated session (ci.yml, shard 1) that runs both
#: files and fails if one is skipped -- so the suite runs them, and they stay in this class.
_COVERED = (
    # Reason derived from the test source: the suite never skips it.
    _covered(
        "repo_tests/promtool_rules_test.py",
        "promtool not found at",
        "promtool not found at",
        "promtool is installed by ci.yml's python-shard job only",
    ),
    # Observed in the suite's shared session (all eight shards).
    _covered(
        "repo_tests/backup_embeddings_on_real_chroma_19647_test.py",
        "chromadb is stubbed, not the real library",
        "chromadb is stubbed, not the real library",
        "the suite runs it in its own session",
    ),
    _covered(
        "repo_tests/chromadb_missing_key_serving_where_18820_test.py",
        "chromadb is stubbed, not the real library",
        "chromadb is stubbed, not the real library",
        "the suite runs it in its own session",
    ),
    # Reason derived from the test source (importorskip): the suite's runner has the library.
    _covered(
        "repo_tests/backup_embeddings_on_real_chroma_19647_test.py",
        "could not import 'chromadb'",
        'importorskip("chromadb")',
        "the suite runs it in its own session",
    ),
    _covered(
        "repo_tests/chromadb_missing_key_serving_where_18820_test.py",
        "could not import 'chromadb'",
        'importorskip("chromadb")',
        "the suite runs it in its own session",
    ),
)

#: ``equivalent-to-suite``, a guard that never runs on the CI runner: a defect (#21371) the lane tolerates
#: because the train's suite skips it identically. Each reason is verbatim from the suite's ``-rs``.
_SILENT_GUARDS = (
    _silent(
        "autobot_shared/editable_install_layout_test.py",
        "autobot_shared has no pip distribution metadata in this interpreter",
        "no pip distribution metadata",
        "CI puts the package on PYTHONPATH instead of pip install -e",
    ),
    _silent(
        "autobot_shared/python_floor_test.py",
        "python3.10 not installed",
        'reason="python3.10 not installed"',
        "the runner has no python3.10",
    ),
    _silent(
        "repo_tests/workflow_closed_reference_guard_test.py",
        "gh could not resolve the repository slug",
        "gh could not resolve the repository slug",
        "no token reaches gh in the test step",
    ),
    _silent(
        "repo_tests/ansible_free_form_args_20693_test.py",
        "could not import 'ansible.parsing.splitter'",
        'importorskip("ansible.parsing.splitter")',
        "the ansible package is not installed",
    ),
    _silent(
        "tools/lint/check_decorator_order_test.py",
        "libcst not installed",
        'reason="libcst not installed; install with: pip install libcst"',
        "the libcst package is not installed",
    ),
)

#: ``equivalent-to-suite``, correct by design. Verbatim from the suite's ``-rs`` (pytest words an empty
#: parametrization ``got empty parameter set for (<argnames>)``, so the marker is the parametrize line).
_BY_DESIGN = (
    _by_design(
        "repo_tests/deployment_script_imports_resolve_test.py",
        "got empty parameter set for (entry, issue)",
        '@pytest.mark.parametrize("entry,issue", sorted(_KNOWN_BROKEN.items()))',
        "the exemption list is empty, so no stale-exemption check applies",
    ),
    _by_design(
        "repo_tests/deployment_script_reporting_test.py",
        "got empty parameter set for (rel, issue)",
        '"rel,issue", sorted(_KNOWN_FABRICATING.items())',
        "the exemption list is empty, so no stale-exemption check applies",
    ),
    _by_design(
        "repo_tests/dpkg_tests_installed_state_not_knowledge_17387_test.py",
        "got empty parameter set for (line)",
        '"line", sorted(_KNOWLEDGE_IS_THE_RIGHT_QUESTION)',
        "the exemption list is empty, so no stale-exemption check applies",
    ),
    _by_design(
        "repo_tests/first_party_imports_resolve_test.py",
        "got empty parameter set for (entry, issue)",
        '"entry,issue", sorted(_KNOWN_BROKEN.items())',
        "the exemption list is empty, so no stale-exemption check applies",
    ),
    _by_design(
        "repo_tests/first_party_symbols_bound_test.py",
        "got empty parameter set for (entry, issue)",
        '"entry,issue", sorted(_KNOWN_BROKEN.items())',
        "the exemption list is empty, so no stale-exemption check applies",
    ),
    _by_design(
        "repo_tests/hard_optional_dependency_declared_test.py",
        "got empty parameter set for (entry, issue)",
        '"entry,issue", sorted(_KNOWN_UNDECLARED.items())',
        "the exemption list is empty, so no stale-exemption check applies",
    ),
    _by_design(
        "repo_tests/infra_script_imports_resolve_test.py",
        "got empty parameter set for (entry, issue)",
        '"entry,issue", sorted(_KNOWN_BROKEN.items())',
        "the exemption list is empty, so no stale-exemption check applies",
    ),
    _by_design(
        "repo_tests/severity_enum_fork_guard_18098_test.py",
        "got empty parameter set for (entry)",
        '"entry", sorted(PENDING_A_WIRE_DECISION)',
        "the pending list is empty, so no stale-entry check applies",
    ),
    _by_design(
        "repo_tests/meta_path_guards_are_not_precached_14913_test.py",
        "autobot-backend/llc/scheduler/lazy_import_test.py: known, tracked by",
        '"autobot-backend/llc/scheduler/lazy_import_test.py": "#14913"',
        "a known finding tracked by #14913",
    ),
    _by_design(
        "repo_tests/meta_path_guards_are_not_precached_14913_test.py",
        "autobot-backend/llc/services/lazy_import_test.py: known, tracked by",
        '"autobot-backend/llc/services/lazy_import_test.py": "#14913"',
        "a known finding tracked by #14913",
    ),
    _by_design(
        "repo_tests/pytest_testpaths_cover_every_test_dir_15183_test.py",
        "#15476: testpaths does not reach",
        "#15476: testpaths does not reach",
        "a known uncovered ini tracked by #15476",
    ),
    _by_design(
        "repo_tests/import_hermeticity_test.py",
        "the sweep runs in CI; set AUTOBOT_IMPORT_HERMETICITY_SWEEP=1",
        "the sweep runs in CI; set",
        "the per-module sweep runs in its own workflow, one interpreter per module",
    ),
    *(
        _by_design(
            "repo_tests/request_schema_fields_are_read_15966_test.py",
            f"{model} has no tracked unread field",
            "has no tracked unread field",
            "the known-unread ratchet is empty, so no model has a field to re-check",
        )
        for model in ("StatusUpdate", "CostEvent", "CommentBody", "WorkProduct", "HeartbeatReport", "AgentWikiEntryIn")
    ),
)

#: The lane's reviewed skips, grouped by class above. 5 + 5 + 18 entries.
SKIP_ALLOWLIST: tuple[AllowedSkip, ...] = (*_COVERED, *_SILENT_GUARDS, *_BY_DESIGN)


def _entry_problems(entry: AllowedSkip, root: Path) -> list[str]:
    """What is wrong with one entry: its form, its file, its marker."""
    problems = []
    if entry.skip_class not in SKIP_CLASSES:
        problems.append(f"{entry.file}: unknown class {entry.skip_class!r}")
    if not entry.reason_prefix or not FOLLOW_UP_FORM.fullmatch(entry.follow_up) or not entry.why:
        problems.append(f"{entry.file}: needs a reason prefix, a follow-up (#N or 'by design: ...') and a why")
    if entry.skip_class == COVERED_BY_SUITE_ONLY and entry.follow_up != FOLLOW_UP:
        problems.append(f"{entry.file}: a covered-by-suite-only skip is removed by {FOLLOW_UP}")
    path = root / entry.file
    if not path.is_file():
        problems.append(f"{entry.file}: the file no longer exists; delete the entry")
    elif entry.source_marker not in path.read_text(encoding="utf-8"):
        problems.append(f"{entry.file}: no longer holds {entry.source_marker!r}; delete the entry")
    return problems


def stale_entries(allowlist: tuple[AllowedSkip, ...], root: Path) -> list[str]:
    """Every problem with *allowlist* read against the tree at *root*; empty when each entry still names a skip."""
    return [problem for entry in allowlist for problem in _entry_problems(entry, root)]
