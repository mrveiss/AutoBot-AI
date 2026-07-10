# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11439: /code-sync/status outdated_nodes must use the live version signal
(code_version != latest, #9996-B), not the heartbeat-lagged code_status stamp
— otherwise has_update=true could coexist with outdated_nodes=0."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

import inspect  # noqa: E402
import types  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

# Same shims as test_collect_outdated_node_ids.py (#10023): stub the
# conflicting multipart package and swap benign dicts in for MagicMock schema
# names so api.code_sync imports under the conftest stub regime.
if "multipart" in sys.modules and not hasattr(sys.modules["multipart"], "multipart"):
    sys.modules.pop("multipart", None)
_mp_stub = types.ModuleType("multipart")
_mp_stub.multipart = types.ModuleType("multipart.multipart")  # type: ignore[attr-defined]
sys.modules.setdefault("multipart", _mp_stub)
sys.modules.setdefault("multipart.multipart", _mp_stub.multipart)  # type: ignore[attr-defined]

_SCHEMA_NAMES = (
    "CodeSyncRefreshResponse",
    "CodeSyncStatusResponse",
    "CodeVersionNotification",
    "CodeVersionNotificationResponse",
    "DriftResolveRequest",
    "DriftResolveResponse",
    "FileDriftReport",
    "FleetSyncJobStatus",
    "FleetSyncNodeStatus",
    "FleetSyncRequest",
    "FleetSyncResponse",
    "NodeSyncRequest",
    "NodeSyncResponse",
    "PendingNodeResponse",
    "PendingNodesResponse",
    "ScheduleCreate",
    "ScheduleResponse",
    "ScheduleRunResponse",
    "ScheduleUpdate",
    # #11303/#11447 additions missing from the sibling's list
    "DriftResolveJobResponse",
    "ComponentSyncJobStatus",
    "UpdateAllRequest",
    "UpdateAllStatusResponse",
    "MarkSyncedResponse",
)
_schemas_stub = sys.modules.get("models.schemas")
if isinstance(_schemas_stub, MagicMock):
    for _name in _SCHEMA_NAMES:
        setattr(_schemas_stub, _name, dict)


def test_status_outdated_count_uses_version_signal_when_latest_known():
    """The version-based branch must gate on latest_version and OR the
    service-failed status (preserving #1605)."""
    import api.code_sync as code_sync_mod

    src = inspect.getsource(code_sync_mod.get_sync_status)
    # version-based currency present and gated on latest_version
    assert "if latest_version:" in src
    assert "Node.code_version != latest_version" in src
    assert "Node.code_version.is_(None)" in src
    # #1605 service-failed still counted as needing attention
    assert "CODE_CURRENT_SERVICE_FAILED" in src
    # legacy status-stamp fallback retained when latest is unknown
    assert "CodeStatus.OUTDATED.value" in src
