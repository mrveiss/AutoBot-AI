# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""DependencyAnalyzer classifies tool effects through the catalogue (#18294)."""

import pytest

from tools.parallel.analyzer import DependencyAnalyzer
from tools.parallel.types import DependencyType, ParallelToolCall


def _call(tool: str, **args) -> ParallelToolCall:
    return ParallelToolCall(tool_name=tool, arguments=args)


def _dep(a: ParallelToolCall, b: ParallelToolCall) -> DependencyType:
    return DependencyAnalyzer()._check_dependency(a, b)


def test_the_analyzer_holds_no_effect_tables_of_its_own():
    for attr in ("READ_TOOLS", "WRITE_TOOLS", "STATE_TOOLS"):
        assert not hasattr(DependencyAnalyzer, attr), attr


@pytest.mark.parametrize("remover", ["remove_directory", "delete_directory"])
def test_both_spellings_of_directory_removal_serialise_a_dependent_write(remover):
    assert _dep(_call(remover, path="/a/b"), _call("write_file", file_path="/a/b/x")) == DependencyType.RESOURCE


def test_create_directory_now_orders_a_listing_inside_it():
    """Was STATE-only: a list_dir inside the new directory ran in parallel with its creation."""
    assert _dep(_call("create_directory", path="/a"), _call("list_dir", path="/a/b")) == DependencyType.RESOURCE


def test_create_directory_still_orders_a_file_write_inside_it():
    assert _dep(_call("create_directory", path="/a"), _call("write_file", file_path="/a/x")) != DependencyType.NONE


def test_two_reads_of_one_file_stay_parallel():
    assert _dep(_call("read_file", path="/a"), _call("read_file", path="/a")) == DependencyType.NONE


def test_a_read_then_a_write_of_the_same_file_is_ordered():
    assert _dep(_call("read_file", path="/a"), _call("write_file", path="/a")) == DependencyType.RESOURCE


def test_disjoint_writes_stay_parallel():
    assert _dep(_call("write_file", path="/a"), _call("write_file", path="/b")) == DependencyType.NONE


def test_execute_command_with_a_mutating_command_orders_what_follows():
    assert _dep(_call("execute_command", command="mkdir x"), _call("read_file", path="/z")) == DependencyType.ORDER


def test_parallel_groups_serialise_an_overlapping_pair_and_batch_the_rest():
    calls = [_call("create_directory", path="/a"), _call("list_dir", path="/a"), _call("read_file", path="/z")]
    groups = DependencyAnalyzer().get_parallel_groups(calls)
    assert [[c.tool_name for c in g] for g in groups][0].count("list_dir") == 0
    assert sum(len(g) for g in groups) == 3 and len(groups) == 2
