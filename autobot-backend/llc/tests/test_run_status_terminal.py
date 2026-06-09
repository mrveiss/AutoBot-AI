# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for LLCRunStatus.is_terminal() (GH#9777)."""

from llc.models.enums import LLCRunStatus


def test_nonterminal_states() -> None:
    assert LLCRunStatus.QUEUED.is_terminal() is False
    assert LLCRunStatus.RUNNING.is_terminal() is False


def test_terminal_states() -> None:
    for status in (
        LLCRunStatus.COMPLETED,
        LLCRunStatus.FAILED,
        LLCRunStatus.INTERRUPTED,
        LLCRunStatus.TIMEOUT,
        LLCRunStatus.CANCELLED,
        LLCRunStatus.RATE_LIMITED,
    ):
        assert status.is_terminal() is True, status


def test_terminal_partition_is_total() -> None:
    # Every status is exactly one of terminal / non-terminal.
    nonterminal = {s for s in LLCRunStatus if not s.is_terminal()}
    terminal = {s for s in LLCRunStatus if s.is_terminal()}
    assert nonterminal == {LLCRunStatus.QUEUED, LLCRunStatus.RUNNING}
    assert nonterminal | terminal == set(LLCRunStatus)
    assert not (nonterminal & terminal)
