# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for task artifact capture on OBSERVATION events (#4094).
"""

import json

import pytest

from events.stream_manager import InMemoryEventStreamManager
from events.types import (
    ArtifactType,
    ObservationContent,
    TaskArtifact,
    _validate_artifact_serialization,
    build_artifact,
    create_observation_event,
)

# ---------------------------------------------------------------------------
# TaskArtifact unit tests
# ---------------------------------------------------------------------------


class TestTaskArtifact:
    def test_round_trip_dict(self):
        art = TaskArtifact(
            artifact_type=ArtifactType.CODE_DIFF,
            content="--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new",
            label="patch",
            file_path="autobot-backend/foo.py",
        )
        restored = TaskArtifact.from_dict(art.to_dict())
        assert restored.artifact_type == ArtifactType.CODE_DIFF
        assert restored.content == art.content
        assert restored.label == "patch"
        assert restored.file_path == "autobot-backend/foo.py"
        assert not restored.truncated

    def test_content_truncated_when_oversized(self):
        big = "x" * 20_000
        art = TaskArtifact(artifact_type=ArtifactType.TEST_OUTPUT, content=big)
        assert art.truncated is True
        assert len(art.content.encode("utf-8")) <= 16_384

    def test_small_content_not_truncated(self):
        art = TaskArtifact(artifact_type=ArtifactType.COMMAND_OUTPUT, content="ok")
        assert art.truncated is False

    def test_build_artifact_helper(self):
        art = build_artifact(ArtifactType.DEPLOYMENT_LOG, "done", label="deploy")
        assert art.artifact_type == ArtifactType.DEPLOYMENT_LOG
        assert art.label == "deploy"
        assert not art.truncated


# ---------------------------------------------------------------------------
# ObservationContent with artifacts
# ---------------------------------------------------------------------------


class TestObservationContentArtifacts:
    def _make_obs(self, artifacts=None):
        return ObservationContent(
            action_id="act-1",
            tool_name="code_tool",
            success=True,
            artifacts=artifacts or [],
        )

    def test_to_dict_includes_artifacts(self):
        art = build_artifact(ArtifactType.FILE_CHANGE, "new_file.py created")
        obs = self._make_obs([art])
        d = obs.to_dict()
        assert "artifacts" in d
        assert len(d["artifacts"]) == 1
        assert d["artifacts"][0]["artifact_type"] == "file_change"

    def test_from_dict_restores_artifacts(self):
        art = build_artifact(ArtifactType.CODE_DIFF, "diff text", label="my diff")
        obs = self._make_obs([art])
        restored = ObservationContent.from_dict(obs.to_dict())
        assert len(restored.artifacts) == 1
        assert restored.artifacts[0].artifact_type == ArtifactType.CODE_DIFF
        assert restored.artifacts[0].label == "my diff"

    def test_from_dict_missing_artifacts_defaults_to_empty(self):
        d = {
            "action_id": "act-1",
            "tool_name": "tool",
            "success": True,
        }
        obs = ObservationContent.from_dict(d)
        assert obs.artifacts == []

    def test_multiple_artifacts_preserved(self):
        arts = [
            build_artifact(ArtifactType.CODE_DIFF, "diff A"),
            build_artifact(ArtifactType.TEST_OUTPUT, "PASSED 5 tests"),
            build_artifact(ArtifactType.DEPLOYMENT_LOG, "deployed ok"),
        ]
        obs = self._make_obs(arts)
        restored = ObservationContent.from_dict(obs.to_dict())
        assert len(restored.artifacts) == 3
        types = [a.artifact_type for a in restored.artifacts]
        assert ArtifactType.CODE_DIFF in types
        assert ArtifactType.TEST_OUTPUT in types
        assert ArtifactType.DEPLOYMENT_LOG in types


# ---------------------------------------------------------------------------
# create_observation_event helper
# ---------------------------------------------------------------------------


class TestCreateObservationEvent:
    def test_no_artifacts_produces_empty_list(self):
        evt = create_observation_event("act-1", "tool", True, result="ok")
        obs = ObservationContent.from_dict(evt.content)
        assert obs.artifacts == []

    def test_artifacts_carried_in_event_content(self):
        art = build_artifact(ArtifactType.TEST_OUTPUT, "3 passed")
        evt = create_observation_event("act-2", "pytest_runner", True, task_id="t-1", artifacts=[art])
        obs = ObservationContent.from_dict(evt.content)
        assert len(obs.artifacts) == 1
        assert obs.artifacts[0].artifact_type == ArtifactType.TEST_OUTPUT

    def test_event_serializes_and_deserializes(self):
        from events.types import AgentEvent

        art = build_artifact(ArtifactType.CODE_DIFF, "--- a\n+++ b")
        evt = create_observation_event("act-3", "editor", True, artifacts=[art])
        restored = AgentEvent.from_json(evt.to_json())
        obs = ObservationContent.from_dict(restored.content)
        assert len(obs.artifacts) == 1
        assert obs.artifacts[0].artifact_type == ArtifactType.CODE_DIFF


# ---------------------------------------------------------------------------
# InMemoryEventStreamManager.get_task_artifacts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetTaskArtifacts:
    async def test_empty_when_no_observations(self):
        mgr = InMemoryEventStreamManager()
        from events.types import create_plan_event

        evt = create_plan_event("do stuff", [], 0, 1, task_id="t-empty")
        await mgr.publish(evt)
        arts = await mgr.get_task_artifacts("t-empty")
        assert arts == []

    async def test_aggregates_artifacts_from_multiple_observations(self):
        mgr = InMemoryEventStreamManager()
        task_id = "t-agg"

        art1 = build_artifact(ArtifactType.CODE_DIFF, "diff 1")
        art2 = build_artifact(ArtifactType.TEST_OUTPUT, "passed")
        art3 = build_artifact(ArtifactType.DEPLOYMENT_LOG, "deployed")

        evt1 = create_observation_event("a1", "tool", True, task_id=task_id, artifacts=[art1, art2])
        evt2 = create_observation_event("a2", "tool", True, task_id=task_id, artifacts=[art3])

        await mgr.publish(evt1)
        await mgr.publish(evt2)

        arts = await mgr.get_task_artifacts(task_id)
        assert len(arts) == 3
        types = {a.artifact_type for a in arts}
        assert ArtifactType.CODE_DIFF in types
        assert ArtifactType.TEST_OUTPUT in types
        assert ArtifactType.DEPLOYMENT_LOG in types

    async def test_only_returns_artifacts_for_given_task(self):
        mgr = InMemoryEventStreamManager()

        art_a = build_artifact(ArtifactType.CODE_DIFF, "diff task-a")
        art_b = build_artifact(ArtifactType.TEST_OUTPUT, "output task-b")

        await mgr.publish(create_observation_event("x1", "t", True, task_id="task-a", artifacts=[art_a]))
        await mgr.publish(create_observation_event("x2", "t", True, task_id="task-b", artifacts=[art_b]))

        arts_a = await mgr.get_task_artifacts("task-a")
        assert len(arts_a) == 1
        assert arts_a[0].artifact_type == ArtifactType.CODE_DIFF

        arts_b = await mgr.get_task_artifacts("task-b")
        assert len(arts_b) == 1
        assert arts_b[0].artifact_type == ArtifactType.TEST_OUTPUT

    async def test_empty_for_unknown_task(self):
        mgr = InMemoryEventStreamManager()
        assert await mgr.get_task_artifacts("no-such-task") == []

    async def test_observation_without_artifacts_contributes_nothing(self):
        mgr = InMemoryEventStreamManager()
        task_id = "t-noart"
        evt = create_observation_event("a1", "tool", True, task_id=task_id)
        await mgr.publish(evt)
        arts = await mgr.get_task_artifacts(task_id)
        assert arts == []


# ---------------------------------------------------------------------------
# Artifact serialization / round-trip validation (#4178)
# ---------------------------------------------------------------------------


class TestArtifactSerializationValidation:
    """Validate that artifacts serialize to JSON and round-trip without loss."""

    def test_valid_artifact_passes_validation(self):
        art = build_artifact(ArtifactType.CODE_DIFF, "--- a\n+++ b", label="patch")
        # Must not raise
        _validate_artifact_serialization([art])

    def test_multiple_valid_artifacts_pass_validation(self):
        arts = [
            build_artifact(ArtifactType.CODE_DIFF, "diff text"),
            build_artifact(ArtifactType.TEST_OUTPUT, "3 passed"),
            build_artifact(
                ArtifactType.DEPLOYMENT_LOG,
                "deployed ok",
                file_path="/tmp/log",  # nosec B108 - test/controlled code uses tmpdir intentionally
            ),
        ]
        _validate_artifact_serialization(arts)

    def test_empty_list_passes_validation(self):
        _validate_artifact_serialization([])

    def test_artifact_to_dict_is_json_serializable(self):
        art = build_artifact(ArtifactType.CUSTOM, "payload", label="lbl", file_path="/a/b.py")
        serialized = json.dumps(art.to_dict(), ensure_ascii=False)
        restored = json.loads(serialized)
        assert restored["artifact_type"] == "custom"
        assert restored["content"] == "payload"
        assert restored["label"] == "lbl"
        assert restored["file_path"] == "/a/b.py"
        assert restored["truncated"] is False

    def test_round_trip_through_json_preserves_all_fields(self):
        art = build_artifact(
            ArtifactType.FILE_CHANGE,
            "new content",
            label="new file",
            file_path="autobot-backend/new.py",
        )
        serialized = json.dumps(art.to_dict(), ensure_ascii=False)
        restored = TaskArtifact.from_dict(json.loads(serialized))
        assert restored.artifact_type == art.artifact_type
        assert restored.content == art.content
        assert restored.label == art.label
        assert restored.file_path == art.file_path
        assert restored.truncated == art.truncated

    def test_create_observation_event_validates_artifacts(self):
        """create_observation_event must accept clean artifacts without raising."""
        art = build_artifact(ArtifactType.COMMAND_OUTPUT, "exit 0")
        evt = create_observation_event("act-v", "shell", True, artifacts=[art])
        obs = ObservationContent.from_dict(evt.content)
        assert len(obs.artifacts) == 1
        assert obs.artifacts[0].artifact_type == ArtifactType.COMMAND_OUTPUT

    def test_full_event_json_round_trip_with_artifacts(self):
        """Full path: artifact → event → JSON → event → artifact."""
        from events.types import AgentEvent

        art = build_artifact(ArtifactType.TEST_OUTPUT, "5 passed, 0 failed", label="pytest")
        evt = create_observation_event("act-rt", "pytest_runner", True, task_id="t-rt", artifacts=[art])

        json_str = evt.to_json()
        restored_evt = AgentEvent.from_json(json_str)
        obs = ObservationContent.from_dict(restored_evt.content)

        assert len(obs.artifacts) == 1
        r = obs.artifacts[0]
        assert r.artifact_type == ArtifactType.TEST_OUTPUT
        assert r.content == "5 passed, 0 failed"
        assert r.label == "pytest"
        assert r.truncated is False

    def test_truncated_artifact_still_passes_validation(self):
        """Truncated artifacts must still be JSON-serializable."""
        big_content = "x" * 20_000
        art = TaskArtifact(artifact_type=ArtifactType.COMMAND_OUTPUT, content=big_content)
        assert art.truncated is True
        # Validation must not raise even for truncated artifacts
        _validate_artifact_serialization([art])

    def test_artifact_unicode_content_round_trips(self):
        """Unicode characters in content must survive JSON serialization."""
        art = build_artifact(ArtifactType.CUSTOM, "日本語テスト \u2603 emoji \U0001f600")
        serialized = json.dumps(art.to_dict(), ensure_ascii=False)
        restored = TaskArtifact.from_dict(json.loads(serialized))
        assert restored.content == art.content

    def test_create_observation_event_without_artifacts_skips_validation(self):
        """No artifacts → validation is skipped; no error raised."""
        evt = create_observation_event("act-nv", "noop", False, error="oops")
        obs = ObservationContent.from_dict(evt.content)
        assert obs.artifacts == []
        assert obs.error == "oops"
