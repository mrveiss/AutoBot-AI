# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The spill's effect on the loop's own decisions (#13865).

Every test for #13692 exercised the spill module in isolation, and the defect it
shipped was a *shape* regression at the boundary: the excerpt dict replacing a
tool result dropped the keys the loop classifies by, so a large tool **failure**
was read as a success.

Module-only tests could not catch that, because both sides were individually
correct. These test the seam.
"""

import contextlib
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest

from agent_loop import tool_output_spill as spill

TASK = "task-wiring"
BIG_ERROR = "Traceback (most recent call last):\n" + ("  File 'x.py', line 1\n" * 1200)


@pytest.fixture(autouse=True)
def _spill_on(tmp_path, monkeypatch):
    monkeypatch.setattr(spill, "SPILL_ENABLED", True)
    monkeypatch.setenv("AUTOBOT_TOOL_OUTPUT_SPILL_ROOT", str(tmp_path))
    spill.bind_task(TASK)
    yield
    spill.bind_task(None)


def _spill_one(result: Any) -> Dict[str, Any]:
    rewritten, count = spill.spill_results(TASK, {"bash": result})
    assert count == 1, "precondition: the payload must be large enough to spill"
    return rewritten["bash"]


class TestTheSpillAlwaysShrinks:
    """The one property the module exists to provide.

    Nothing asserted it, and the first version of the error-classification fix
    copied the error value verbatim — so a spilled `{"error": <26KB traceback>}`
    entered context at 30,023 chars where not spilling was 27,649, while the
    note claimed the output had been truncated.
    """

    @pytest.mark.parametrize(
        "original",
        [
            {"error": BIG_ERROR},
            {"status": "success", "output": "K" * 40000},
            {"success": True, "rows": ["R" * 100] * 400},
            "K" * 40000,
            # Non-str classification values. The second version of the fix
            # bounded only `str`, so each of these still GREW — and a
            # structured error is the standard shape for HTTP, API and
            # subprocess tool failures, so it was the mainline case.
            {"error": {"code": 500, "message": "boom", "trace": ["F" * 100] * 300}},
            {"status": {"phase": "failed", "log": "Z" * 30000}},
            {"success": False, "error": ["E" * 100] * 300},
            {"error": b"B" * 30000},
            # Non-ASCII: `_serialise` uses ensure_ascii=False, so measure the
            # same way rather than through json.dumps' escaping.
            {"error": "\u90e8\u7f72\u5931\u6557" * 8000},
        ],
    )
    def test_what_enters_context_is_smaller_than_what_it_replaces(self, original):
        """The one property the module exists to provide.

        Stated as "spilled OR smaller", because declining to spill is a valid
        outcome — the module measures its own replacement and keeps the original
        when the swap would not help. Asserting "always spills" would force back
        the bug this guards.

        Measured with `_serialise`, which is what actually enters context —
        `json.dumps` escapes non-ASCII and would flatter the assertion.
        """
        rewritten, count = spill.spill_results(TASK, {"bash": original})
        spilled = rewritten["bash"]

        assert count == 0 or len(spill._serialise(spilled)) < len(spill._serialise(original))

    @pytest.mark.parametrize(
        ("threshold", "payload"),
        [
            # Control-char density: `_serialise` returns a str raw, but the
            # excerpt slice is JSON-escaped, so a dense payload inverted at the
            # DEFAULT configuration (8,001 -> 12,282 chars).
            (8000, "\x01" * 8001),
            (8000, ("\x01" * 6 + "abcd") * 801),
            # Small thresholds, where the hardcoded overhead estimate is wrong by
            # 2-6x once the classification markers are re-escaped.
            (1500, {"error": {"m": 'a"b' * 400}, "status": "failed", "success": False}),
            (2000, {"error": {"m": 'a"b' * 400}, "status": "failed", "success": False}),
            (3000, {"error": {"m": 'a"b' * 400}, "status": "failed", "success": False}),
        ],
    )
    def test_the_invariant_holds_across_configurations(self, threshold, payload, tmp_path, monkeypatch):
        """No constant can be right, so the module must measure.

        Overhead ranges 286-1710 chars with tool-name length and escaping, and
        an estimate that is low turns every threshold in a band into a growth
        case — which is how this defect survived three fixes.
        """
        monkeypatch.setattr(spill, "SPILL_THRESHOLD_CHARS", threshold)
        monkeypatch.setattr(spill, "SPILL_EXCERPT_CHARS", max(1, threshold - 1000))

        rewritten, count = spill.spill_results(TASK, {"bash": payload})
        spilled = rewritten["bash"]

        assert count == 0 or len(spill._serialise(spilled)) < len(spill._serialise(payload))

    @pytest.mark.parametrize(
        "falsy",
        [{"error": None}, {"success": False}, {"status": 0}],
        ids=["error-none", "success-false", "status-zero"],
    )
    def test_falsy_classifications_stay_falsy(self, falsy):
        """`_record_observation_fingerprints` tests truthiness, so stringifying
        a scalar would turn `None`/`False` into the truthy `"None"`/`"False"`
        and invert the decision."""
        original = {**falsy, "output": "K" * 40000}
        key = next(iter(falsy))

        spilled = _spill_one(original)

        assert bool(spilled[key]) is bool(falsy[key])


class TestAFailureStaysAFailure:
    """`_should_iterate` decides success with `"error" not in result`.

    The excerpt payload carried no `error` key, so a spilled failure satisfied
    that test and the loop continued on an error it believed had succeeded.
    """

    def test_a_large_error_result_keeps_its_error_key(self):
        assert len(BIG_ERROR) > spill.SPILL_THRESHOLD_CHARS

        spilled = _spill_one({"error": BIG_ERROR})

        assert spilled["spilled"] is True
        assert "error" in spilled, "a spilled failure must still read as a failure"

    def test_the_preserved_error_is_a_marker_not_the_payload(self):
        """Preserving the classification must not re-import the payload."""
        spilled = _spill_one({"error": BIG_ERROR})

        assert len(spilled["error"]) < len(BIG_ERROR)
        assert len(spilled["error"]) <= spill._CLASSIFICATION_MARKER_CHARS

    def test_a_large_success_is_not_turned_into_a_failure(self):
        """The mirror case — the fix must not invent an error key."""
        spilled = _spill_one({"status": "success", "output": "K" * 40000})

        assert "error" not in spilled
        assert spilled["status"] == "success"

    def test_a_plain_string_result_is_unaffected(self):
        """Strings carry no classification, so nothing is preserved or invented."""
        spilled = _spill_one("K" * 40000)

        assert spilled["spilled"] is True
        assert "error" not in spilled


class TestTheLoopActuallyCallsIt:
    """Drives `AgentLoop`, rather than copying its predicates.

    The first version of this file asserted against expressions *transcribed*
    from `loop.py`. Deleting the spill from the loop entirely left all 36 tests
    green — the file claimed to test the seam and tested neither side of it.
    These fail if the wiring is removed.
    """

    @pytest.fixture
    def loop(self):
        from agent_loop.loop import AgentLoop

        return AgentLoop(event_stream=AsyncMock())

    @pytest.mark.asyncio
    async def test_the_loop_binds_the_run_before_tools_execute(self, loop):
        """Binding after execution left iteration 1 scoped to the previous run."""
        spill.bind_task(None)

        loop._init_task_context("run-A", "do a thing", {})

        assert spill.current_task_id() == "run-A"

    @pytest.mark.asyncio
    async def test_a_finished_run_releases_its_binding(self, loop):
        """Without this, a second run in the same asyncio context inherits the
        first run's binding and can read its artifacts."""
        loop._init_task_context("run-A", "x", {})
        assert spill.current_task_id() == "run-A"

        with patch.object(loop, "_execute_main_loop", new=AsyncMock(return_value={"status": "completed"})):
            with patch.object(loop, "_clear_run_checkpoint", new=AsyncMock()):
                with contextlib.suppress(Exception):
                    await loop.run_task("run-A", "x")

        # Asserted on every terminal path, including failure — the `finally`
        # is what makes a second run in this context safe.
        assert spill.current_task_id() is None, "the run binding outlived the run"

    @pytest.mark.asyncio
    async def test_oversized_results_are_offloaded_by_the_loop(self, loop):
        """The seam itself: the loop must route results through the spill."""
        loop._init_task_context("run-A", "x", {})

        out = await loop._offload_oversized_results({"bash": "K" * 40000})

        assert out["bash"]["spilled"] is True
        assert out["bash"]["anchor"].startswith("autobot:spill:run-A:")

    @pytest.mark.asyncio
    async def test_the_iteration_routes_its_results_through_the_spill(self, loop):
        """Drives `_execute_iteration_phases` itself.

        The direct `_offload_oversized_results` test above cannot see the *call
        site* being deleted — only this one can, which is the difference
        between testing a helper and testing the wiring.
        """
        from agent_loop.types import IterationResult

        loop._init_task_context("run-A", "x", {})
        loop._iteration_count = 1

        with patch.object(loop, "_analyze_events", new=AsyncMock(return_value={"events": []})):
            with patch.object(loop, "_select_tools", new=AsyncMock(return_value=[{"name": "bash", "args": {}}])):
                with patch.object(loop, "_execute_tools", new=AsyncMock(return_value={"bash": "K" * 40000})):
                    out = await loop._execute_iteration_phases(IterationResult(iteration_number=1))

        assert out.tool_results["bash"]["spilled"] is True, "the iteration did not route results through the spill"

    @pytest.mark.asyncio
    async def test_a_resumed_run_also_releases_its_binding(self, loop):
        """The mirror of `test_a_finished_run_releases_its_binding`.

        `resume_run` bound the run and never released it, reopening the
        cross-run read on the resume path. Deleting the bind left all 44 tests
        green — it had no coverage in either direction.
        """
        from agent_loop.types import TaskContext

        # Built by the real serialiser, not hand-written: a hand-made dict fails
        # the version check and the test then passes for the wrong reason.
        source = TaskContext(task_id="run-R", description="x", metadata={})
        source.iteration_count = 1
        snapshot = source.to_snapshot()

        with patch.object(loop, "load_run_snapshot", new=AsyncMock(return_value=snapshot)):
            with patch.object(loop, "_execute_main_loop", new=AsyncMock(side_effect=RuntimeError("boom"))):
                with contextlib.suppress(Exception):
                    await loop.resume_run("run-R")

        assert spill.current_task_id() is None, "a resumed run's binding outlived it"

    @pytest.mark.asyncio
    async def test_no_run_context_means_no_spill(self, loop):
        """The removed "unknown" fallback put every context-less run into one
        shared namespace, collapsing the read-side run check."""
        loop._current_context = None
        original = {"bash": "K" * 40000}

        out = await loop._offload_oversized_results(original)

        assert out is original


class TestRunScopingIsServerSide:
    def test_a_read_without_a_bound_run_is_refused(self):
        """An anchor alone must not be a bearer token."""
        value = _spill_one("K" * 40000)
        spill.bind_task(None)

        assert spill.read_spilled_window(value["anchor"])["found"] is False

    def test_echoing_the_anchors_own_task_id_does_not_grant_access(self):
        """The anchor embeds its run id in plaintext.

        While `task_id` was a tool argument, splitting the anchor on ":" and
        passing field 2 back defeated the check entirely.
        """
        value = _spill_one("K" * 40000)
        embedded = value["anchor"].split(":")[2]
        assert embedded == TASK, "precondition: the anchor exposes its run id"

        spill.bind_task("a-different-run")

        assert spill.read_spilled_window(value["anchor"])["found"] is False

    def test_the_owning_run_can_read_it(self):
        value = _spill_one("PAYLOAD" * 8000)

        window = spill.read_spilled_window(value["anchor"])

        assert window["found"] is True
        assert window["content"]


class TestTheWindowStaysAWindow:
    def test_a_huge_limit_is_capped(self):
        """Returning the whole artifact would undo the offload."""
        value = _spill_one("K" * 400000)

        window = spill.read_spilled_window(value["anchor"], limit=99999999)

        assert window["limit"] <= spill.SPILL_MAX_WINDOW_CHARS
        assert len(window["content"]) <= spill.SPILL_MAX_WINDOW_CHARS
        assert window["has_more"] is True

    @pytest.mark.parametrize("bad", ["all", None, {}, "12x"])
    def test_a_model_authored_window_argument_cannot_raise(self, bad):
        """offset/limit arrive from a tool call, so they are arbitrary."""
        value = _spill_one("K" * 40000)

        window = spill.read_spilled_window(value["anchor"], offset=bad, limit=bad)

        assert isinstance(window, dict)


class TestConfigParsingCannotBreakTheImport:
    def test_a_malformed_threshold_falls_back(self, monkeypatch):
        """These are read at module scope, and `agent_loop.loop` imports this
        module — an unparseable value took the agent loop down at import, with
        the feature switched off."""
        monkeypatch.setenv("AUTOBOT_TOOL_OUTPUT_SPILL_THRESHOLD", "8k")

        assert spill._int_env("AUTOBOT_TOOL_OUTPUT_SPILL_THRESHOLD", 8000) == 8000


class TestArtifactsAreSwept:
    """Nothing deleted a spilled artifact before this — the nightly sweep covers
    `data/cache` and `data/temp`, and the spill root is neither."""

    def test_an_operator_chosen_root_is_never_swept(self, tmp_path):
        """The sweep recursively unlinks by mtime alone, and every other
        candidate is AutoBot-owned by construction. An operator pointing the
        root at a shared scratch directory or a mounted volume would otherwise
        have unrelated files deleted on the first run — immediately, since
        pre-existing files are already older than the TTL."""
        from tasks.knowledge_tasks import _resolve_cache_directories

        # the autouse fixture sets AUTOBOT_TOOL_OUTPUT_SPILL_ROOT
        assert spill.sweepable_spill_root() is None
        assert spill._spill_root() not in _resolve_cache_directories()

    def test_the_default_root_is_swept_once_it_exists(self, tmp_path, monkeypatch):
        """The AutoBot-owned default is safe to sweep, and must be — otherwise
        the directory grows for the life of the install."""
        import constants.path_constants as path_constants
        from tasks.knowledge_tasks import _resolve_cache_directories

        monkeypatch.delenv("AUTOBOT_TOOL_OUTPUT_SPILL_ROOT", raising=False)
        stub = type(
            "PathStub",
            (),
            {
                "DATA_DIR": tmp_path,
                "TEMP_DIR": tmp_path / "cache",
                "get_data_path": staticmethod(lambda *p: tmp_path.joinpath(*p)),
            },
        )()
        monkeypatch.setattr(path_constants, "PATH", stub)

        assert spill.sweepable_spill_root() is None, "not a candidate before the spill creates it"

        (tmp_path / "tool_output_spill").mkdir()
        (tmp_path / "cache").mkdir()

        assert spill.sweepable_spill_root() == tmp_path / "tool_output_spill"
        assert tmp_path / "tool_output_spill" in _resolve_cache_directories()
