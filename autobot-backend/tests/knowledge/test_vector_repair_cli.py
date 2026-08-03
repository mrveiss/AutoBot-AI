# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Argument handling of the #13277 repair CLI.

The CLI is the last line of defence against an accidental unscoped write, so
the refusals are tested directly. Nothing here touches Redis, ChromaDB or the
knowledge base — only pure argument resolution and validation.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from knowledge.vector_repair import NO_REDIS_CONTENT, FactOutcome, RepairReport

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "repair_kb_vector_index.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("repair_kb_vector_index", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = _load_cli()


def _args(argv):
    return cli._build_parser().parse_args(argv)


def _report(**kwargs) -> RepairReport:
    return RepairReport(**kwargs)


def test_dry_run_is_the_default():
    assert _args(["--fact-id", "fact-a"]).apply is False


def test_scope_flags_combine_and_deduplicate(tmp_path):
    ids_file = tmp_path / "ids.txt"
    ids_file.write_text("fact-b\n\n# a comment\nfact-a\nfact-b\n", encoding="utf-8")

    args = _args(["--fact-id", "fact-a", "--fact-ids-file", str(ids_file)])

    assert cli._resolve_fact_ids(args) == ["fact-a", "fact-b"]


def test_no_scope_resolves_to_census_sentinel():
    assert cli._resolve_fact_ids(_args(["--census"])) is None


def test_missing_ids_file_is_a_usage_error(tmp_path):
    args = _args(["--fact-ids-file", str(tmp_path / "absent.txt")])

    with pytest.raises(SystemExit) as excinfo:
        cli._resolve_fact_ids(args)

    assert excinfo.value.code == cli.EXIT_USAGE


@pytest.mark.parametrize(
    "argv",
    [
        ["--apply"],
        ["--census", "--apply"],
        ["--census", "--apply", "--fact-id", "fact-a"],
    ],
)
def test_apply_without_an_explicit_scope_is_refused(argv):
    """No implicit "repair everything": every write run must name its facts."""
    args = _args(argv)

    with pytest.raises(SystemExit) as excinfo:
        cli._validate(args, cli._resolve_fact_ids(args))

    assert excinfo.value.code == cli.EXIT_USAGE


def test_census_with_a_scope_is_refused():
    args = _args(["--census", "--fact-id", "fact-a"])

    with pytest.raises(SystemExit) as excinfo:
        cli._validate(args, cli._resolve_fact_ids(args))

    assert excinfo.value.code == cli.EXIT_USAGE


def test_empty_invocation_is_refused():
    args = _args([])

    with pytest.raises(SystemExit) as excinfo:
        cli._validate(args, cli._resolve_fact_ids(args))

    assert excinfo.value.code == cli.EXIT_USAGE


@pytest.mark.parametrize("argv", [["--census"], ["--fact-id", "fact-a"], ["--fact-id", "fact-a", "--apply"]])
def test_valid_invocations_pass_validation(argv):
    args = _args(argv)
    cli._validate(args, cli._resolve_fact_ids(args))


def test_clean_apply_run_exits_zero():
    report = _report()

    assert cli._exit_code(report, apply_changes=True) == cli.EXIT_OK


def test_unrepaired_facts_exit_non_zero():
    report = _report(outcomes=[FactOutcome("fact-a", NO_REDIS_CONTENT, "gone")])

    assert cli._exit_code(report, apply_changes=True) == cli.EXIT_FAILURES


def test_facts_left_without_a_vector_exit_non_zero():
    """No failure record, but the fact is absent — this must not read as success.

    An interrupted earlier run leaves exactly this shape: nothing failed during
    *this* run, yet the fact still has no row in the index.
    """
    report = _report(unreachable_after=["fact-a"])

    assert report.failures == []
    assert cli._exit_code(report, apply_changes=True) == cli.EXIT_FAILURES


def test_dry_run_is_not_failed_by_pre_existing_damage():
    """A census reports damage; it has not been asked to fix it."""
    report = _report(unreachable_after=["fact-a"])

    assert cli._exit_code(report, apply_changes=False) == cli.EXIT_OK


def test_ids_file_is_written_utf8(tmp_path):
    target = tmp_path / "nested" / "affected.txt"

    cli._write_ids(target, ["fact-a", "fact-b"])

    assert target.read_text(encoding="utf-8") == "fact-a\nfact-b\n"
