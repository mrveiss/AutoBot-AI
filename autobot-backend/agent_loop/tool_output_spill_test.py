# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Spill and anchor for oversized tool output (#13692, step 1).

Tool output entered context whole and stayed. These pin the contract: over the
threshold it is written aside and replaced by a bounded excerpt plus a
resolvable anchor; under it, nothing changes at all.
"""

import json
from unittest.mock import patch

import pytest

from agent_loop import tool_output_spill as spill

TASK = "task-42"


@pytest.fixture(autouse=True)
def _spill_root(tmp_path, monkeypatch):
    # #13865: the root is resolved through the canonical data path rather than a
    # module constant, so the env override is what a test sets.
    monkeypatch.setenv("AUTOBOT_TOOL_OUTPUT_SPILL_ROOT", str(tmp_path / "spill"))
    monkeypatch.setattr(spill, "SPILL_ENABLED", True)
    monkeypatch.setattr(spill, "SPILL_THRESHOLD_CHARS", 100)
    monkeypatch.setattr(spill, "SPILL_EXCERPT_CHARS", 20)
    # The run is bound by the agent loop, never passed as a tool argument.
    spill.bind_task(TASK)
    yield
    spill.bind_task(None)


class TestOffDefault:
    def test_disabled_returns_the_result_untouched(self, monkeypatch):
        """AC: behind a flag, default off (#12555 precedent)."""
        monkeypatch.setattr(spill, "SPILL_ENABLED", False)
        big = "x" * 10_000

        value, spilled = spill.spill_if_oversized(TASK, "bash", big)

        assert value is big
        assert spilled is False

    def test_the_module_default_is_off(self):
        """Read from the environment at import time, not hardcoded on."""
        import importlib

        with patch.dict("os.environ", {}, clear=True):
            reloaded = importlib.reload(spill)
            assert reloaded.SPILL_ENABLED is False


class TestUnderThresholdIsUntouched:
    def test_small_output_passes_through_identically(self):
        small = "ok"

        value, spilled = spill.spill_if_oversized(TASK, "bash", small)

        assert value is small
        assert spilled is False

    def test_a_run_that_never_trips_the_threshold_is_unchanged(self):
        results = {"bash": "ok", "read": {"lines": 3}}

        rewritten, count = spill.spill_results(TASK, results)

        assert rewritten == results
        assert count == 0


class TestSpillAndAnchor:
    def test_oversized_output_is_replaced_by_excerpt_and_anchor(self):
        big = "A" * 500

        value, spilled = spill.spill_if_oversized(TASK, "bash", big)

        assert spilled is True
        assert value["excerpt"] == "A" * 20
        assert value["omitted_chars"] == 480
        assert value["anchor"].startswith("autobot:spill:task-42:bash:")

    def test_the_full_output_is_retrievable_via_the_anchor(self):
        """AC: the agent can retrieve the full output within the same run."""
        big = "B" * 500

        value, _ = spill.spill_if_oversized(TASK, "bash", big)

        assert spill.read_spilled(value["anchor"]) == big

    def test_context_payload_is_far_smaller_than_the_original(self):
        big = "C" * 50_000

        value, _ = spill.spill_if_oversized(TASK, "bash", big)

        assert len(json.dumps(value)) < len(big) / 10

    def test_non_string_results_are_serialised_then_spilled(self):
        big = {"rows": ["D" * 50 for _ in range(20)]}

        value, spilled = spill.spill_if_oversized(TASK, "query", big)

        assert spilled is True
        assert "D" in value["excerpt"]

    def test_an_identical_result_reuses_its_anchor(self):
        big = "E" * 500

        first, _ = spill.spill_if_oversized(TASK, "bash", big)
        second, _ = spill.spill_if_oversized(TASK, "bash", big)

        assert first["anchor"] == second["anchor"]


class TestAnchorSafety:
    def test_a_tool_name_with_traversal_cannot_escape_the_spill_root(self):
        """The anchor is hashed into a path, never used as one."""
        value, spilled = spill.spill_if_oversized(TASK, "../../etc/passwd", "F" * 500)

        assert spilled is True
        path = spill._artifact_path(value["anchor"]).resolve()
        assert ".." not in str(path)
        # Resolved containment, not a string prefix: "/tmp/spillEVIL" satisfies
        # startswith("/tmp/spill") while sitting outside the root entirely.
        assert spill._spill_root().resolve() in path.parents

    def test_an_unknown_anchor_returns_none(self):
        assert spill.read_spilled("autobot:spill:nope:nope:deadbeef") is None

    def test_a_foreign_anchor_shape_is_refused(self):
        assert spill.read_spilled("/etc/passwd") is None
        assert spill.read_spilled("") is None
        assert spill.read_spilled(None) is None


class TestNonFatal:
    def test_a_write_failure_keeps_the_full_output(self, monkeypatch):
        """AC: spill failure is non-fatal — the turn completes.

        Losing the offload is always better than losing the observation.
        """
        big = "G" * 500
        monkeypatch.setattr(spill.Path, "mkdir", _raise)

        value, spilled = spill.spill_if_oversized(TASK, "bash", big)

        assert value is big
        assert spilled is False


class TestBatch:
    def test_only_oversized_entries_are_spilled(self):
        results = {"small": "ok", "big": "H" * 500}

        rewritten, count = spill.spill_results(TASK, results)

        assert count == 1
        assert rewritten["small"] == "ok"
        assert rewritten["big"]["spilled"] is True


def _raise(*_args, **_kwargs):
    raise OSError("disk full")


class TestRunScopedWindowedRead:
    """#13754: the anchor is a bearer token, so reads must be run-scoped.

    And a re-read must be a seek, not an undo — returning the whole artifact
    would put back exactly what the offload removed.
    """

    def test_a_window_is_returned_not_the_whole_artifact(self):
        big = "I" * 500

        value, _ = spill.spill_if_oversized(TASK, "bash", big)
        window = spill.read_spilled_window(value["anchor"], offset=0, limit=50)

        assert window["found"] is True
        assert len(window["content"]) == 50
        assert window["total_chars"] == 500
        assert window["has_more"] is True

    def test_paging_reaches_the_end(self):
        big = "".join(str(i % 10) for i in range(300))

        value, _ = spill.spill_if_oversized(TASK, "bash", big)
        first = spill.read_spilled_window(value["anchor"], offset=0, limit=200)
        second = spill.read_spilled_window(value["anchor"], offset=200, limit=200)

        assert first["content"] + second["content"] == big
        assert second["has_more"] is False

    def test_an_anchor_from_another_run_is_refused(self):
        """The security case: a leaked anchor must not read another run."""
        big = "J" * 500

        value, _ = spill.spill_if_oversized(TASK, "bash", big)

        assert spill.read_spilled(value["anchor"], task_id="someone-elses-run") is None
        spill.bind_task("someone-elses-run")
        assert spill.read_spilled_window(value["anchor"])["found"] is False

    def test_the_owning_run_still_reads_it(self):
        big = "K" * 500

        value, _ = spill.spill_if_oversized(TASK, "bash", big)

        assert spill.read_spilled(value["anchor"], task_id=TASK) == big

    def test_a_missing_anchor_reports_not_found_rather_than_raising(self):
        window = spill.read_spilled_window("autobot:spill:x:y:deadbeef")

        assert window["found"] is False


class TestTheExcerptNamesARealTool:
    def test_the_instruction_matches_the_registered_tool_name(self):
        """The excerpt tells the model what to call; that name must exist.

        Naming a capability the agent cannot invoke is worse than saying
        nothing — it invites a call that will fail.
        """
        from tools.tool_registry import ToolRegistry

        value, _ = spill.spill_if_oversized(TASK, "bash", "L" * 500)

        assert "read_spilled_output" in value["note"]
        # #13865: `hasattr` was the original assertion here, and it passes for
        # any unwired method — the tool was undispatchable for the whole life of
        # #13763 while this test stayed green. Membership in the list the model
        # is actually offered is the property that matters.
        assert "read_spilled_output" in ToolRegistry().get_available_tools()

    @pytest.mark.asyncio
    async def test_the_named_tool_is_dispatchable(self, tmp_path, monkeypatch):
        """The note is only actionable if `execute_tool` can route the call.

        Dispatch normalises `read_spilled_output` to `readspilledoutput`; with no
        entry in the table the call fell through to `Unknown tool`.
        """
        from tools.tool_registry import ToolRegistry

        monkeypatch.setattr(spill, "SPILL_ENABLED", True)
        monkeypatch.setenv("AUTOBOT_TOOL_OUTPUT_SPILL_ROOT", str(tmp_path))
        spill.bind_task(TASK)
        value, _ = spill.spill_if_oversized(TASK, "bash", "PAYLOAD" * 2000)

        result = await ToolRegistry().execute_tool("read_spilled_output", {"anchor": value["anchor"]})

        assert result.get("status") != "error", result
        assert "Unknown tool" not in str(result.get("result", ""))
        assert result["result"]["found"] is True
