# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for WorkflowVersionStore (#2145).

Covers:
- save_version: auto-increment, round-trip, Redis unavailability
- list_versions: newest-first ordering, missing record graceful handling
- get_version: hit and miss
- restore_version: returns data dict
- diff_versions: added / removed / modified steps, missing version
- delete_version: removes record and sorted-set entry
- Pure helpers: _diff_step_lists, _changed_fields, _summary
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from services.workflow_versioning import (
    WorkflowVersionStore,
    _changed_fields,
    _diff_step_lists,
    _summary,
    _utc_now,
)
from tests.fixtures import make_async_redis, patch_async_redis

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_data(steps=None) -> dict:
    """Build a minimal workflow data dict."""
    return {
        "name": "Test Workflow",
        "description": "desc",
        "steps": steps or [{"step_id": "s1", "command": "echo hello", "description": "step1"}],
    }


def _encode(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False)


# Migrated to canonical ``make_async_redis()`` / ``patch_async_redis()`` helpers
# from ``tests.fixtures`` (#7280 / #7264). ``_make_redis()`` and the local
# ``patch(..., new=AsyncMock(return_value=...))`` boilerplate are gone — the
# canonical fixture pre-configures the same defaults this file used (set=True,
# get=None, delete=1, zadd=1, zrevrange=[]). ``zrem`` had a call-only assertion
# (``assert_called_once``) so AsyncMock's auto-created child handles it.


# ---------------------------------------------------------------------------
# save_version
# ---------------------------------------------------------------------------


class TestSaveVersion:
    @pytest.mark.asyncio
    async def test_returns_version_1_for_new_workflow(self) -> None:
        store = WorkflowVersionStore()
        mock_redis = make_async_redis()
        mock_redis.zrevrange.return_value = []

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            version = await store.save_version("wf-1", _make_data())

        assert version == 1

    @pytest.mark.asyncio
    async def test_auto_increments_existing_versions(self) -> None:
        store = WorkflowVersionStore()
        mock_redis = make_async_redis()
        mock_redis.zrevrange.return_value = ["3"]  # highest existing version

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            version = await store.save_version("wf-1", _make_data())

        assert version == 4

    @pytest.mark.asyncio
    async def test_stores_record_and_updates_sorted_set(self) -> None:
        store = WorkflowVersionStore()
        mock_redis = make_async_redis()
        mock_redis.zrevrange.return_value = []

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            await store.save_version("wf-2", _make_data(), notes="initial save")

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        key = call_args.args[0]
        assert "wf-2" in key
        assert ":1" in key

        payload = json.loads(call_args.args[1])
        assert payload["version"] == 1
        assert payload["notes"] == "initial save"
        assert payload["workflow_id"] == "wf-2"

        mock_redis.zadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_redis_unavailable(self) -> None:
        store = WorkflowVersionStore()
        with patch("services.workflow_versioning.get_async_redis_client", new=AsyncMock(return_value=None)):
            result = await store.save_version("wf-x", _make_data())

        assert result is None

    @pytest.mark.asyncio
    async def test_round_trip_data_preserved(self):
        """Data written then read back must be identical."""
        store = WorkflowVersionStore()
        data = _make_data()

        stored: dict = {}

        async def fake_set(key, value) -> None:
            stored[key] = value

        async def fake_get(key):
            return stored.get(key)

        mock_redis = make_async_redis()
        mock_redis.set.side_effect = fake_set
        mock_redis.get.side_effect = fake_get
        mock_redis.zrevrange.return_value = []

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            version = await store.save_version("wf-rt", data, notes="rt")
            assert version == 1

            wv = await store.get_version("wf-rt", 1)

        assert wv is not None
        assert wv.data == data
        assert wv.notes == "rt"
        assert wv.workflow_id == "wf-rt"
        assert wv.version == 1


# ---------------------------------------------------------------------------
# list_versions
# ---------------------------------------------------------------------------


class TestListVersions:
    @pytest.mark.asyncio
    async def test_returns_newest_first(self):
        store = WorkflowVersionStore()
        mock_redis = make_async_redis()
        # zrevrange already returns in descending order (newest first)
        mock_redis.zrevrange.return_value = ["3", "2", "1"]

        def _record(v):
            return _encode(
                {
                    "workflow_id": "wf-order",
                    "version": v,
                    "data": {},
                    "created_at": f"2026-01-0{v}T00:00:00Z",
                    "notes": "",
                }
            )

        mock_redis.get.side_effect = lambda key: _record(int(key.split(":")[-1]))

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            summaries = await store.list_versions("wf-order")

        assert [s["version"] for s in summaries] == [3, 2, 1]

    @pytest.mark.asyncio
    async def test_returns_empty_for_unknown_workflow(self) -> None:
        store = WorkflowVersionStore()
        mock_redis = make_async_redis()
        mock_redis.zrevrange.return_value = []

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            summaries = await store.list_versions("wf-unknown")

        assert summaries == []

    @pytest.mark.asyncio
    async def test_skips_missing_records_gracefully(self) -> None:
        """Sorted-set entry exists but the record key is gone — should not crash."""
        store = WorkflowVersionStore()
        mock_redis = make_async_redis()
        mock_redis.zrevrange.return_value = ["2", "1"]
        # Version 2 record is missing; version 1 record exists.
        record_v1 = _encode(
            {
                "workflow_id": "wf-gap",
                "version": 1,
                "data": {},
                "created_at": "2026-01-01T00:00:00Z",
                "notes": "",
            }
        )
        mock_redis.get.side_effect = lambda key: None if ":2" in key else record_v1

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            summaries = await store.list_versions("wf-gap")

        assert len(summaries) == 1
        assert summaries[0]["version"] == 1

    @pytest.mark.asyncio
    async def test_returns_empty_when_redis_unavailable(self) -> None:
        store = WorkflowVersionStore()
        with patch("services.workflow_versioning.get_async_redis_client", new=AsyncMock(return_value=None)):
            summaries = await store.list_versions("wf-x")

        assert summaries == []

    @pytest.mark.asyncio
    async def test_summary_excludes_data_payload(self) -> None:
        """list_versions must not return the full data payload."""
        store = WorkflowVersionStore()
        mock_redis = make_async_redis()
        mock_redis.zrevrange.return_value = ["1"]
        record = _encode(
            {
                "workflow_id": "wf-sum",
                "version": 1,
                "data": {"name": "X", "steps": []},
                "created_at": "2026-01-01T00:00:00Z",
                "notes": "check",
            }
        )
        mock_redis.get.return_value = record

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            summaries = await store.list_versions("wf-sum")

        assert len(summaries) == 1
        assert "data" not in summaries[0]
        assert summaries[0]["notes"] == "check"


# ---------------------------------------------------------------------------
# get_version
# ---------------------------------------------------------------------------


class TestGetVersion:
    @pytest.mark.asyncio
    async def test_returns_workflow_version_on_hit(self) -> None:
        store = WorkflowVersionStore()
        data = _make_data()
        record = _encode(
            {
                "workflow_id": "wf-get",
                "version": 5,
                "data": data,
                "created_at": "2026-01-05T00:00:00Z",
                "notes": "v5",
            }
        )
        mock_redis = make_async_redis()
        mock_redis.get.return_value = record

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            wv = await store.get_version("wf-get", 5)

        assert wv is not None
        assert wv.workflow_id == "wf-get"
        assert wv.version == 5
        assert wv.data == data
        assert wv.notes == "v5"

    @pytest.mark.asyncio
    async def test_returns_none_on_miss(self) -> None:
        store = WorkflowVersionStore()
        mock_redis = make_async_redis()
        mock_redis.get.return_value = None

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            wv = await store.get_version("wf-miss", 99)

        assert wv is None

    @pytest.mark.asyncio
    async def test_returns_none_when_redis_unavailable(self) -> None:
        store = WorkflowVersionStore()
        with patch("services.workflow_versioning.get_async_redis_client", new=AsyncMock(return_value=None)):
            wv = await store.get_version("wf-x", 1)

        assert wv is None


# ---------------------------------------------------------------------------
# restore_version
# ---------------------------------------------------------------------------


class TestRestoreVersion:
    @pytest.mark.asyncio
    async def test_returns_data_dict_for_existing_version(self) -> None:
        store = WorkflowVersionStore()
        data = _make_data()
        record = _encode(
            {
                "workflow_id": "wf-restore",
                "version": 2,
                "data": data,
                "created_at": "2026-01-02T00:00:00Z",
                "notes": "",
            }
        )
        mock_redis = make_async_redis()
        mock_redis.get.return_value = record

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            restored = await store.restore_version("wf-restore", 2)

        assert restored == data

    @pytest.mark.asyncio
    async def test_returns_none_when_version_missing(self) -> None:
        store = WorkflowVersionStore()
        mock_redis = make_async_redis()
        mock_redis.get.return_value = None

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            restored = await store.restore_version("wf-restore", 99)

        assert restored is None


# ---------------------------------------------------------------------------
# diff_versions
# ---------------------------------------------------------------------------


class TestDiffVersions:
    def _record(self, workflow_id: str, version: int, steps: list) -> str:
        return _encode(
            {
                "workflow_id": workflow_id,
                "version": version,
                "data": {"steps": steps},
                "created_at": "2026-01-01T00:00:00Z",
                "notes": "",
            }
        )

    @pytest.mark.asyncio
    async def test_detects_added_step(self) -> None:
        store = WorkflowVersionStore()
        steps_v1 = [{"step_id": "s1", "command": "ls", "description": "list"}]
        steps_v2 = [
            {"step_id": "s1", "command": "ls", "description": "list"},
            {"step_id": "s2", "command": "pwd", "description": "print dir"},
        ]
        r1 = self._record("wf-diff", 1, steps_v1)
        r2 = self._record("wf-diff", 2, steps_v2)
        mock_redis = make_async_redis()
        mock_redis.get.side_effect = lambda key: r1 if ":1" in key else r2

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            diff = await store.diff_versions("wf-diff", v1=1, v2=2)

        assert diff is not None
        assert len(diff["added"]) == 1
        assert diff["added"][0]["step_id"] == "s2"
        assert diff["removed"] == []
        assert diff["modified"] == []

    @pytest.mark.asyncio
    async def test_detects_removed_step(self) -> None:
        store = WorkflowVersionStore()
        steps_v1 = [
            {"step_id": "s1", "command": "ls", "description": "list"},
            {"step_id": "s2", "command": "pwd", "description": "print dir"},
        ]
        steps_v2 = [{"step_id": "s1", "command": "ls", "description": "list"}]
        r1 = self._record("wf-diff", 1, steps_v1)
        r2 = self._record("wf-diff", 2, steps_v2)
        mock_redis = make_async_redis()
        mock_redis.get.side_effect = lambda key: r1 if ":1" in key else r2

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            diff = await store.diff_versions("wf-diff", v1=1, v2=2)

        assert diff is not None
        assert diff["added"] == []
        assert len(diff["removed"]) == 1
        assert diff["removed"][0]["step_id"] == "s2"
        assert diff["modified"] == []

    @pytest.mark.asyncio
    async def test_detects_modified_step(self) -> None:
        store = WorkflowVersionStore()
        steps_v1 = [{"step_id": "s1", "command": "ls", "description": "old desc"}]
        steps_v2 = [{"step_id": "s1", "command": "ls -la", "description": "old desc"}]
        r1 = self._record("wf-diff", 1, steps_v1)
        r2 = self._record("wf-diff", 2, steps_v2)
        mock_redis = make_async_redis()
        mock_redis.get.side_effect = lambda key: r1 if ":1" in key else r2

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            diff = await store.diff_versions("wf-diff", v1=1, v2=2)

        assert diff is not None
        assert diff["added"] == []
        assert diff["removed"] == []
        assert len(diff["modified"]) == 1
        mod = diff["modified"][0]
        assert mod["step_id"] == "s1"
        assert "command" in mod["changed_fields"]
        assert mod["changed_fields"]["command"]["from"] == "ls"
        assert mod["changed_fields"]["command"]["to"] == "ls -la"

    @pytest.mark.asyncio
    async def test_returns_none_when_version_missing(self) -> None:
        store = WorkflowVersionStore()
        mock_redis = make_async_redis()
        mock_redis.get.return_value = None

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            diff = await store.diff_versions("wf-diff", v1=1, v2=2)

        assert diff is None

    @pytest.mark.asyncio
    async def test_identical_versions_have_empty_diff(self) -> None:
        store = WorkflowVersionStore()
        steps = [{"step_id": "s1", "command": "echo hi", "description": "greet"}]
        r1 = self._record("wf-same", 1, steps)
        r2 = self._record("wf-same", 2, steps)
        mock_redis = make_async_redis()
        mock_redis.get.side_effect = lambda key: r1 if ":1" in key else r2

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            diff = await store.diff_versions("wf-same", v1=1, v2=2)

        assert diff == {"added": [], "removed": [], "modified": []}


# ---------------------------------------------------------------------------
# delete_version
# ---------------------------------------------------------------------------


class TestDeleteVersion:
    @pytest.mark.asyncio
    async def test_returns_true_when_version_exists(self) -> None:
        store = WorkflowVersionStore()
        mock_redis = make_async_redis()
        mock_redis.delete.return_value = 1

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            result = await store.delete_version("wf-del", 3)

        assert result is True
        mock_redis.delete.assert_called_once()
        mock_redis.zrem.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_version_not_found(self) -> None:
        store = WorkflowVersionStore()
        mock_redis = make_async_redis()
        mock_redis.delete.return_value = 0  # key did not exist

        with patch_async_redis("services.workflow_versioning.get_async_redis_client", redis=mock_redis):
            result = await store.delete_version("wf-del", 99)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_redis_unavailable(self) -> None:
        store = WorkflowVersionStore()
        with patch("services.workflow_versioning.get_async_redis_client", new=AsyncMock(return_value=None)):
            result = await store.delete_version("wf-x", 1)

        assert result is False


# ---------------------------------------------------------------------------
# Pure helper unit tests
# ---------------------------------------------------------------------------


class TestDiffStepLists:
    def test_added_steps(self) -> None:
        v1 = [{"step_id": "s1", "command": "a"}]
        v2 = [{"step_id": "s1", "command": "a"}, {"step_id": "s2", "command": "b"}]
        diff = _diff_step_lists(v1, v2)
        assert len(diff["added"]) == 1
        assert diff["added"][0]["step_id"] == "s2"
        assert diff["removed"] == []
        assert diff["modified"] == []

    def test_removed_steps(self) -> None:
        v1 = [{"step_id": "s1", "command": "a"}, {"step_id": "s2", "command": "b"}]
        v2 = [{"step_id": "s1", "command": "a"}]
        diff = _diff_step_lists(v1, v2)
        assert diff["added"] == []
        assert len(diff["removed"]) == 1
        assert diff["removed"][0]["step_id"] == "s2"
        assert diff["modified"] == []

    def test_modified_steps(self) -> None:
        v1 = [{"step_id": "s1", "command": "ls", "description": "old"}]
        v2 = [{"step_id": "s1", "command": "ls -la", "description": "old"}]
        diff = _diff_step_lists(v1, v2)
        assert diff["added"] == []
        assert diff["removed"] == []
        assert len(diff["modified"]) == 1
        assert diff["modified"][0]["changed_fields"]["command"]["from"] == "ls"
        assert diff["modified"][0]["changed_fields"]["command"]["to"] == "ls -la"

    def test_no_changes(self) -> None:
        steps = [{"step_id": "s1", "command": "a"}]
        diff = _diff_step_lists(steps, steps)
        assert diff == {"added": [], "removed": [], "modified": []}

    def test_empty_lists(self) -> None:
        diff = _diff_step_lists([], [])
        assert diff == {"added": [], "removed": [], "modified": []}


class TestChangedFields:
    def test_detects_changed_field(self) -> None:
        s1 = {"command": "ls", "description": "same"}
        s2 = {"command": "ls -la", "description": "same"}
        changed = _changed_fields(s1, s2)
        assert "command" in changed
        assert changed["command"] == {"from": "ls", "to": "ls -la"}
        assert "description" not in changed

    def test_detects_added_field(self) -> None:
        s1 = {"command": "ls"}
        s2 = {"command": "ls", "risk_level": "high"}
        changed = _changed_fields(s1, s2)
        assert "risk_level" in changed
        assert changed["risk_level"]["from"] is None
        assert changed["risk_level"]["to"] == "high"

    def test_detects_removed_field(self) -> None:
        s1 = {"command": "ls", "risk_level": "low"}
        s2 = {"command": "ls"}
        changed = _changed_fields(s1, s2)
        assert "risk_level" in changed
        assert changed["risk_level"]["from"] == "low"
        assert changed["risk_level"]["to"] is None

    def test_no_changes_returns_empty(self) -> None:
        s = {"command": "ls", "description": "desc"}
        assert _changed_fields(s, s) == {}


class TestSummaryHelper:
    def test_strips_data_key(self) -> None:
        record = {
            "workflow_id": "wf-1",
            "version": 3,
            "data": {"name": "X", "steps": []},
            "created_at": "2026-01-01T00:00:00Z",
            "notes": "some note",
        }
        result = _summary(record)
        assert "data" not in result
        assert result["workflow_id"] == "wf-1"
        assert result["version"] == 3
        assert result["notes"] == "some note"
        assert result["created_at"] == "2026-01-01T00:00:00Z"

    def test_handles_missing_keys(self) -> None:
        result = _summary({})
        assert result["workflow_id"] == ""
        assert result["version"] is None
        assert result["notes"] == ""
        assert result["created_at"] == ""


class TestUtcNow:
    def test_returns_iso_string_with_offset_suffix(self) -> None:
        # _utc_now is an alias for autobot_shared.time_utils.utc_timestamp,
        # which returns ISO-8601 with ``+00:00`` offset and microsecond
        # precision per the #5178 datetime migration. Format:
        # ``YYYY-MM-DDTHH:MM:SS.ffffff+00:00``
        from datetime import datetime

        ts = _utc_now()
        assert ts.endswith("+00:00")
        assert "T" in ts
        # Round-trip parse confirms the string is valid ISO-8601 + tz-aware.
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None
