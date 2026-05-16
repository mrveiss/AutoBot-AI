# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for WorkflowSerializer and WorkflowSharingService (#2165).

Covers:
- Export of active and completed workflows
- Export round-trip (export then import produces equivalent workflow)
- Import validation: schema version, missing fields, step validation
- Sharing: create/revoke share, visibility rules, clone
- Redis unavailability is handled gracefully (returns None / False)
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.workflow_automation.models import (
    ActiveWorkflow,
    AutomationMode,
    WorkflowStep,
)
from services.workflow_serializer import SCHEMA_VERSION, WorkflowSerializer
from services.workflow_sharing_service import (
    WorkflowSharingService,
    _strip_workflow_payload,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_step(step_id: str = "step_1", command: str = "echo hello") -> WorkflowStep:
    return WorkflowStep(
        step_id=step_id,
        command=command,
        description="A test step",
        risk_level="low",
    )


def _make_workflow(
    workflow_id: str = "wf-test",
    steps: list | None = None,
) -> ActiveWorkflow:
    return ActiveWorkflow(
        workflow_id=workflow_id,
        name="Test Workflow",
        description="Workflow for testing",
        session_id="sess-1",
        steps=steps or [_make_step()],
        automation_mode=AutomationMode.SEMI_AUTOMATIC,
        owner_id="owner-1",
    )


def _make_manager(workflow: ActiveWorkflow | None = None) -> MagicMock:
    manager = MagicMock()
    wf = workflow or _make_workflow()
    manager.active_workflows = {wf.workflow_id: wf}
    manager.completed_workflows = {}
    return manager


# ---------------------------------------------------------------------------
# WorkflowSerializer.export_workflow
# ---------------------------------------------------------------------------


class TestExportWorkflow:
    @pytest.mark.asyncio
    async def test_exports_active_workflow(self) -> None:
        wf = _make_workflow()
        manager = _make_manager(wf)
        serializer = WorkflowSerializer(manager)

        doc = await serializer.export_workflow(wf.workflow_id)

        assert doc is not None
        assert doc.schema_version == SCHEMA_VERSION
        assert doc.workflow_id == wf.workflow_id
        assert doc.name == wf.name
        assert len(doc.steps) == 1
        assert doc.steps[0].command == "echo hello"

    @pytest.mark.asyncio
    async def test_exports_completed_workflow(self) -> None:
        wf = _make_workflow(workflow_id="wf-done")
        manager = MagicMock()
        manager.active_workflows = {}
        manager.completed_workflows = {wf.workflow_id: wf}
        serializer = WorkflowSerializer(manager)

        doc = await serializer.export_workflow("wf-done")

        assert doc is not None
        assert doc.workflow_id == "wf-done"

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_workflow(self) -> None:
        manager = _make_manager()
        serializer = WorkflowSerializer(manager)

        doc = await serializer.export_workflow("wf-does-not-exist")

        assert doc is None

    @pytest.mark.asyncio
    async def test_export_metadata_contains_owner(self) -> None:
        wf = _make_workflow()
        manager = _make_manager(wf)
        serializer = WorkflowSerializer(manager)

        doc = await serializer.export_workflow(wf.workflow_id)

        assert doc.metadata.get("original_owner_id") == "owner-1"

    @pytest.mark.asyncio
    async def test_to_dict_is_json_serialisable(self) -> None:
        wf = _make_workflow()
        manager = _make_manager(wf)
        serializer = WorkflowSerializer(manager)

        doc = await serializer.export_workflow(wf.workflow_id)
        serialised = json.dumps(doc.to_dict())  # Must not raise

        assert '"schema_version"' in serialised


# ---------------------------------------------------------------------------
# WorkflowSerializer.validate_import
# ---------------------------------------------------------------------------


class TestValidateImport:
    def _valid_payload(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "exported_at": "2026-01-01T00:00:00Z",
            "workflow_id": "wf-orig",
            "name": "My Workflow",
            "description": "Desc",
            "automation_mode": "semi_automatic",
            "steps": [
                {
                    "step_id": "s1",
                    "command": "ls",
                    "description": "List files",
                    "risk_level": "low",
                }
            ],
            "metadata": {},
        }

    def _serializer(self) -> WorkflowSerializer:
        return WorkflowSerializer(MagicMock())

    def test_valid_document_has_no_issues(self) -> None:
        issues = self._serializer().validate_import(self._valid_payload())
        assert issues == []

    def test_wrong_schema_version_reported(self) -> None:
        payload = self._valid_payload()
        payload["schema_version"] = "99.0"
        issues = self._serializer().validate_import(payload)
        assert any("schema_version" in i for i in issues)

    def test_missing_name_reported(self) -> None:
        payload = self._valid_payload()
        del payload["name"]
        issues = self._serializer().validate_import(payload)
        assert any("name" in i for i in issues)

    def test_missing_steps_reported(self) -> None:
        payload = self._valid_payload()
        del payload["steps"]
        issues = self._serializer().validate_import(payload)
        assert any("steps" in i for i in issues)

    def test_non_list_steps_reported(self) -> None:
        payload = self._valid_payload()
        payload["steps"] = "not a list"
        issues = self._serializer().validate_import(payload)
        assert any("steps" in i for i in issues)

    def test_step_missing_command_reported(self) -> None:
        payload = self._valid_payload()
        payload["steps"][0].pop("command")
        issues = self._serializer().validate_import(payload)
        assert any("command" in i for i in issues)

    def test_step_bad_risk_level_reported(self) -> None:
        payload = self._valid_payload()
        payload["steps"][0]["risk_level"] = "galaxy-brained"
        issues = self._serializer().validate_import(payload)
        assert any("risk_level" in i for i in issues)

    def test_invalid_automation_mode_reported(self) -> None:
        payload = self._valid_payload()
        payload["automation_mode"] = "turbo_mode"
        issues = self._serializer().validate_import(payload)
        assert any("automation_mode" in i for i in issues)

    def test_step_bad_timeout_reported(self) -> None:
        payload = self._valid_payload()
        payload["steps"][0]["timeout_seconds"] = -5
        issues = self._serializer().validate_import(payload)
        assert any("timeout_seconds" in i for i in issues)

    def test_non_dict_payload_reported(self) -> None:
        issues = self._serializer().validate_import("not a dict")  # type: ignore[arg-type]
        assert any("JSON object" in i for i in issues)


# ---------------------------------------------------------------------------
# WorkflowSerializer.import_workflow
# ---------------------------------------------------------------------------


class TestImportWorkflow:
    def _valid_payload(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "exported_at": "2026-01-01T00:00:00Z",
            "workflow_id": "wf-orig",
            "name": "Imported Workflow",
            "description": "Imported",
            "automation_mode": "semi_automatic",
            "steps": [
                {
                    "step_id": "s1",
                    "command": "echo imported",
                    "description": "Echo",
                    "risk_level": "low",
                }
            ],
            "metadata": {},
        }

    @pytest.mark.asyncio
    async def test_creates_new_workflow_on_valid_payload(self) -> None:
        manager = MagicMock()
        manager.active_workflows = {}
        manager.completed_workflows = {}
        manager.create_automated_workflow = AsyncMock(return_value="wf-new-123")
        serializer = WorkflowSerializer(manager)

        new_id = await serializer.import_workflow(self._valid_payload(), owner_id="user-1")

        assert new_id == "wf-new-123"
        manager.create_automated_workflow.assert_called_once()
        call_kwargs = manager.create_automated_workflow.call_args
        assert call_kwargs.kwargs["name"] == "Imported Workflow"
        assert call_kwargs.kwargs["owner_id"] == "user-1"

    @pytest.mark.asyncio
    async def test_returns_none_on_invalid_payload(self) -> None:
        manager = MagicMock()
        manager.active_workflows = {}
        manager.completed_workflows = {}
        serializer = WorkflowSerializer(manager)

        new_id = await serializer.import_workflow({"schema_version": "0.0", "name": "", "steps": []}, owner_id="user-1")

        assert new_id is None

    @pytest.mark.asyncio
    async def test_round_trip_preserves_step_data(self):
        """Export then import produces a workflow with the same step commands."""
        original_step = _make_step(step_id="s1", command="apt update")
        wf = _make_workflow(steps=[original_step])
        manager = MagicMock()
        manager.active_workflows = {wf.workflow_id: wf}
        manager.completed_workflows = {}
        captured_steps = {}

        async def _capture(**kwargs):
            captured_steps["steps"] = kwargs["steps"]
            return "wf-imported"

        manager.create_automated_workflow = _capture
        serializer = WorkflowSerializer(manager)

        export_doc = await serializer.export_workflow(wf.workflow_id)
        assert export_doc is not None

        new_id = await serializer.import_workflow(data=export_doc.to_dict(), owner_id="new-owner")

        assert new_id == "wf-imported"
        assert len(captured_steps["steps"]) == 1
        assert captured_steps["steps"][0].command == "apt update"

    @pytest.mark.asyncio
    async def test_uses_provided_session_id(self) -> None:
        manager = MagicMock()
        manager.active_workflows = {}
        manager.completed_workflows = {}
        manager.create_automated_workflow = AsyncMock(return_value="wf-xyz")
        serializer = WorkflowSerializer(manager)

        await serializer.import_workflow(self._valid_payload(), owner_id="u1", session_id="sess-custom")

        call_kwargs = manager.create_automated_workflow.call_args
        assert call_kwargs.kwargs["session_id"] == "sess-custom"


# ---------------------------------------------------------------------------
# WorkflowSharingService.share_workflow
# ---------------------------------------------------------------------------


class TestShareWorkflow:
    def _make_sharing(self) -> tuple[WorkflowSharingService, MagicMock]:
        wf = _make_workflow()
        manager = _make_manager(wf)
        serializer = WorkflowSerializer(manager)
        sharing = WorkflowSharingService(serializer)
        return sharing, manager

    @pytest.mark.asyncio
    async def test_returns_share_id_for_public_share(self) -> None:
        sharing, manager = self._make_sharing()
        mock_redis = AsyncMock()
        with patch(
            "services.workflow_sharing_service.get_async_redis_client",
            return_value=mock_redis,
        ):
            share_id = await sharing.share_workflow(workflow_id="wf-test", owner_id="owner-1", public=True)

        assert share_id is not None
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_share_id_for_targeted_share(self) -> None:
        sharing, _ = self._make_sharing()
        mock_redis = AsyncMock()
        with patch(
            "services.workflow_sharing_service.get_async_redis_client",
            return_value=mock_redis,
        ):
            share_id = await sharing.share_workflow(
                workflow_id="wf-test",
                owner_id="owner-1",
                target_user_id="user-2",
            )

        assert share_id is not None
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_target_or_public(self) -> None:
        sharing, _ = self._make_sharing()
        share_id = await sharing.share_workflow(workflow_id="wf-test", owner_id="owner-1")
        assert share_id is None

    @pytest.mark.asyncio
    async def test_returns_none_when_redis_unavailable(self) -> None:
        sharing, _ = self._make_sharing()
        with patch("services.workflow_sharing_service.get_async_redis_client", new=AsyncMock(return_value=None)):
            share_id = await sharing.share_workflow(workflow_id="wf-test", owner_id="owner-1", public=True)
        assert share_id is None

    @pytest.mark.asyncio
    async def test_returns_none_when_workflow_not_found(self) -> None:
        manager = MagicMock()
        manager.active_workflows = {}
        manager.completed_workflows = {}
        serializer = WorkflowSerializer(manager)
        sharing = WorkflowSharingService(serializer)

        share_id = await sharing.share_workflow(workflow_id="wf-missing", owner_id="owner-1", public=True)
        assert share_id is None


# ---------------------------------------------------------------------------
# WorkflowSharingService.unshare_workflow
# ---------------------------------------------------------------------------


class TestUnshareWorkflow:
    @pytest.mark.asyncio
    async def test_deletes_existing_share(self) -> None:
        sharing = WorkflowSharingService(MagicMock())
        share_id = str(uuid.uuid4())
        record = json.dumps({"workflow_id": "wf-test"})
        mock_redis = AsyncMock()
        mock_redis.get.return_value = record

        with patch(
            "services.workflow_sharing_service.get_async_redis_client",
            return_value=mock_redis,
        ):
            result = await sharing.unshare_workflow(share_id)

        assert result is True
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_share_not_found(self) -> None:
        sharing = WorkflowSharingService(MagicMock())
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        with patch(
            "services.workflow_sharing_service.get_async_redis_client",
            return_value=mock_redis,
        ):
            result = await sharing.unshare_workflow("nonexistent-share")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_redis_unavailable(self) -> None:
        sharing = WorkflowSharingService(MagicMock())
        with patch("services.workflow_sharing_service.get_async_redis_client", new=AsyncMock(return_value=None)):
            result = await sharing.unshare_workflow("any-share")
        assert result is False


# ---------------------------------------------------------------------------
# WorkflowSharingService.list_shared
# ---------------------------------------------------------------------------


class TestListShared:
    def _build_record(
        self,
        share_id: str,
        public: bool = False,
        owner_id: str = "owner-1",
        target_user_id: str | None = None,
    ) -> str:
        return json.dumps(
            {
                "share_id": share_id,
                "workflow_id": "wf-test",
                "owner_id": owner_id,
                "public": public,
                "target_user_id": target_user_id,
                "created_at": "2026-01-01T00:00:00Z",
                "workflow": {},
            }
        )

    @pytest.mark.asyncio
    async def test_returns_public_shares_to_any_user(self) -> None:
        sharing = WorkflowSharingService(MagicMock())
        share_id = "share-pub-1"
        record = self._build_record(share_id, public=True)

        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, [f"autobot:workflow_share:{share_id}"]))
        mock_redis.get = AsyncMock(return_value=record)

        with patch(
            "services.workflow_sharing_service.get_async_redis_client",
            return_value=mock_redis,
        ):
            shares = await sharing.list_shared(user_id="stranger")

        assert len(shares) == 1
        assert shares[0]["share_id"] == share_id
        assert "workflow" not in shares[0]

    @pytest.mark.asyncio
    async def test_returns_targeted_share_to_target_user(self) -> None:
        sharing = WorkflowSharingService(MagicMock())
        share_id = "share-target-1"
        record = self._build_record(share_id, target_user_id="user-2")

        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, [f"autobot:workflow_share:{share_id}"]))
        mock_redis.get = AsyncMock(return_value=record)

        with patch(
            "services.workflow_sharing_service.get_async_redis_client",
            return_value=mock_redis,
        ):
            shares = await sharing.list_shared(user_id="user-2")

        assert len(shares) == 1

    @pytest.mark.asyncio
    async def test_hides_targeted_share_from_other_user(self) -> None:
        sharing = WorkflowSharingService(MagicMock())
        share_id = "share-priv-1"
        record = self._build_record(share_id, target_user_id="user-2")

        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, [f"autobot:workflow_share:{share_id}"]))
        mock_redis.get = AsyncMock(return_value=record)

        with patch(
            "services.workflow_sharing_service.get_async_redis_client",
            return_value=mock_redis,
        ):
            shares = await sharing.list_shared(user_id="user-3")

        assert shares == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_redis_unavailable(self) -> None:
        sharing = WorkflowSharingService(MagicMock())
        with patch("services.workflow_sharing_service.get_async_redis_client", new=AsyncMock(return_value=None)):
            shares = await sharing.list_shared(user_id="anyone")
        assert shares == []


# ---------------------------------------------------------------------------
# WorkflowSharingService.clone_workflow
# ---------------------------------------------------------------------------


class TestCloneWorkflow:
    def _make_sharing_with_export(self, export_doc: dict) -> WorkflowSharingService:
        """Return a sharing service whose serializer will accept the export doc."""
        manager = MagicMock()
        manager.active_workflows = {}
        manager.completed_workflows = {}
        manager.create_automated_workflow = AsyncMock(return_value="wf-cloned")
        serializer = WorkflowSerializer(manager)
        return WorkflowSharingService(serializer)

    def _valid_export_doc(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "exported_at": "2026-01-01T00:00:00Z",
            "workflow_id": "wf-orig",
            "name": "Cloned",
            "description": "Cloned workflow",
            "automation_mode": "semi_automatic",
            "steps": [
                {
                    "step_id": "s1",
                    "command": "echo clone",
                    "description": "step",
                    "risk_level": "low",
                }
            ],
            "metadata": {},
        }

    @pytest.mark.asyncio
    async def test_clones_shared_workflow(self) -> None:
        export_doc = self._valid_export_doc()
        sharing = self._make_sharing_with_export(export_doc)
        share_id = "share-abc"
        record = json.dumps(
            {
                "share_id": share_id,
                "workflow_id": "wf-orig",
                "owner_id": "owner-1",
                "public": True,
                "target_user_id": None,
                "workflow": export_doc,
            }
        )
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=record)

        with patch(
            "services.workflow_sharing_service.get_async_redis_client",
            return_value=mock_redis,
        ):
            new_id = await sharing.clone_workflow(share_id, new_owner_id="user-2")

        assert new_id == "wf-cloned"

    @pytest.mark.asyncio
    async def test_returns_none_when_share_not_found(self) -> None:
        sharing = self._make_sharing_with_export({})
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch(
            "services.workflow_sharing_service.get_async_redis_client",
            return_value=mock_redis,
        ):
            result = await sharing.clone_workflow("missing-share", new_owner_id="user-2")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_redis_unavailable(self) -> None:
        sharing = self._make_sharing_with_export({})
        with patch("services.workflow_sharing_service.get_async_redis_client", new=AsyncMock(return_value=None)):
            result = await sharing.clone_workflow("any-share", new_owner_id="u")
        assert result is None


# ---------------------------------------------------------------------------
# Pure helper tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_strip_workflow_payload_removes_workflow_key(self) -> None:
        record = {"share_id": "s1", "name": "Test", "workflow": {"steps": []}}
        stripped = _strip_workflow_payload(record)
        assert "workflow" not in stripped
        assert stripped["share_id"] == "s1"

    def test_strip_workflow_payload_no_mutation(self) -> None:
        record = {"share_id": "s2", "workflow": {"steps": []}}
        _strip_workflow_payload(record)
        assert "workflow" in record  # original is unchanged
