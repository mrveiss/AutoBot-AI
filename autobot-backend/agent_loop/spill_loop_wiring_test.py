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

from typing import Any, Dict

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

    def test_the_loop_success_predicate_still_reports_failure(self):
        """The exact expression from `_should_iterate`."""
        spilled = _spill_one({"error": BIG_ERROR})

        all_succeeded = all("error" not in r for r in {"bash": spilled}.values() if isinstance(r, dict))

        assert all_succeeded is False

    def test_the_observation_filter_still_skips_it(self):
        """The exact predicate from `_record_observation_fingerprints`.

        A failed result entering the novelty window corrupts the stagnation
        signal it feeds.
        """
        spilled = _spill_one({"error": BIG_ERROR})

        assert bool(spilled.get("error")) is True

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
    def test_the_spill_root_is_a_cleanup_candidate(self, tmp_path, monkeypatch):
        """Nothing deleted a spilled artifact before this.

        The nightly sweep covers `data/cache` and `data/temp`; the spill root is
        neither, so it grew for the life of the install.
        """
        import constants.path_constants as path_constants
        from tasks.knowledge_tasks import _resolve_cache_directories

        (tmp_path / "tool_output_spill").mkdir()
        (tmp_path / "cache").mkdir()

        # PATH is a frozen dataclass, so the module attribute is swapped rather
        # than a field assigned.
        stub = type("PathStub", (), {"DATA_DIR": tmp_path, "TEMP_DIR": tmp_path / "cache"})()
        monkeypatch.setattr(path_constants, "PATH", stub)

        assert tmp_path / "tool_output_spill" in _resolve_cache_directories()
