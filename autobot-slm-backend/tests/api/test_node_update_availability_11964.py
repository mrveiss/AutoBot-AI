# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the node-card badge / live-check reconciliation (#11964).

Root cause: the fleet update-summary badge (`NodeCard.vue`) read
`node.code_status` via `_build_node_summaries()`, while the live
"Check for updates" scan (`NodeLifecyclePanel.vue` -> GET
`/nodes/{node_id}/updates`) only queried the `UpdateInfo` system-package
table and never looked at code status at all -- so a node flagged
"code update available" by the badge would always report "no updates"
from the live scan, regardless of its real code_status.

Fix: both paths now compute code-update-availability via the single
`is_code_update_available()` helper in `api/updates.py`, and the live
per-node response carries `code_update_available`/`code_status` so the
frontend can reconcile the cached badge with the fresh scan.
"""

from __future__ import annotations

import ast
import enum
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))


# ---------------------------------------------------------------------------
# CodeStatus real stand-in (#11964)
#
# conftest.py globally stubs models.database as a MagicMock so FastAPI route
# registration in api/* modules doesn't hit config.Settings()/real DB
# metadata. is_code_update_available() does a real string comparison against
# CodeStatus.OUTDATED.value, so that one name must be a REAL enum with the
# production values (models/database.py CodeStatus, Issue #741) rather than
# an auto-generated MagicMock attribute -- otherwise every comparison would
# silently pass/fail by mock identity instead of the actual string contract.
# ---------------------------------------------------------------------------
class CodeStatus(str, enum.Enum):
    UP_TO_DATE = "up_to_date"
    OUTDATED = "outdated"
    CODE_CURRENT_SERVICE_FAILED = "code_current_service_failed"
    UNKNOWN = "unknown"


_database_stub = sys.modules.get("models.database")
if isinstance(_database_stub, MagicMock):
    _database_stub.CodeStatus = CodeStatus


# ---------------------------------------------------------------------------
# models.schemas stand-ins, derived from api/updates.py's own import block
# (not hand-listed -- a static list rots the moment a new schema is added,
# see tests/api/test_collect_outdated_node_ids.py for the same precedent).
# Every name is a plain `dict` (a valid FastAPI response/body type) EXCEPT
# NodeUpdateSummary, which _build_node_summaries() actually instantiates and
# reads attributes off of -- it needs a real attribute-bearing stand-in
# mirroring models/schemas.py's NodeUpdateSummary fields exactly.
# ---------------------------------------------------------------------------


class _NodeUpdateSummaryStub:
    def __init__(
        self,
        node_id: str,
        hostname: str,
        system_updates: int = 0,
        code_update_available: bool = False,
        code_status: str = "unknown",
        total_updates: int = 0,
    ) -> None:
        self.node_id = node_id
        self.hostname = hostname
        self.system_updates = system_updates
        self.code_update_available = code_update_available
        self.code_status = code_status
        self.total_updates = total_updates


def _stub_updates_schemas() -> None:
    schemas_stub = sys.modules.get("models.schemas")
    if not isinstance(schemas_stub, MagicMock):
        return  # real models.schemas module — nothing to do

    updates_src = (_BACKEND_ROOT / "api" / "updates.py").read_text(encoding="utf-8")
    schema_names = {
        alias.name
        for node in ast.walk(ast.parse(updates_src))
        if isinstance(node, ast.ImportFrom) and node.module == "models.schemas"
        for alias in node.names
    }
    for name in schema_names:
        setattr(schemas_stub, name, dict)
    schemas_stub.NodeUpdateSummary = _NodeUpdateSummaryStub


_stub_updates_schemas()


def _load_real_code_status_module():
    """Real-load services/code_status.py (#12428/#12570/#12571).

    api/updates.py now imports is_code_update_available/_build_node_summaries's
    currency derivation from services.code_status (reported_code_status /
    get_latest_code_version) instead of comparing node.code_status raw --
    that module must be REAL, not a MagicMock stub, since it does an actual
    string comparison against CodeStatus.OUTDATED.value (same reasoning as
    the real CodeStatus stand-in above). Registered directly in sys.modules
    so `from services.code_status import ...` resolves without needing the
    `services` parent stub to behave like a real package.
    """
    code_status_py = _BACKEND_ROOT / "services" / "code_status.py"
    spec = importlib.util.spec_from_file_location("services.code_status", code_status_py)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["services.code_status"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_updates_module():
    """Load api/updates.py directly, bypassing api/__init__.py (#11964).

    api/__init__.py eagerly imports every router, pulling in service modules
    that need real settings/secrets unavailable in a sandboxed test run.
    services.* are stubbed here; models.database/models.schemas are patched
    above just enough for FastAPI route registration + the functions under
    test.
    """
    for mod_name in ("services", "services.auth", "services.database", "services.playbook_executor"):
        sys.modules.setdefault(mod_name, MagicMock(unsafe=True))
    _load_real_code_status_module()

    updates_py = _BACKEND_ROOT / "api" / "updates.py"
    spec = importlib.util.spec_from_file_location("_updates_11964_test", updates_py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_updates = _load_updates_module()
is_code_update_available = _updates.is_code_update_available
_build_node_summaries = _updates._build_node_summaries


def _fake_node(
    node_id: str = "node-1",
    hostname: str = "host-1",
    code_status: str | None = None,
    code_version: str | None = "unused-version",
):
    return SimpleNamespace(node_id=node_id, hostname=hostname, code_status=code_status, code_version=code_version)


# ---------------------------------------------------------------------------
# is_code_update_available -- the single canonical source (#11964)
# ---------------------------------------------------------------------------


def test_is_code_update_available_true_when_outdated():
    node = _fake_node(code_status=CodeStatus.OUTDATED.value)
    assert is_code_update_available(node) is True


def test_is_code_update_available_false_when_up_to_date():
    node = _fake_node(code_status=CodeStatus.UP_TO_DATE.value)
    assert is_code_update_available(node) is False


def test_is_code_update_available_false_when_unknown():
    node = _fake_node(code_status=CodeStatus.UNKNOWN.value)
    assert is_code_update_available(node) is False


def test_is_code_update_available_false_when_none():
    node = _fake_node(code_status=None)
    assert is_code_update_available(node) is False


def test_is_code_update_available_false_when_service_failed():
    """CODE_CURRENT_SERVICE_FAILED means code IS current -- not a code update."""
    node = _fake_node(code_status=CodeStatus.CODE_CURRENT_SERVICE_FAILED.value)
    assert is_code_update_available(node) is False


# ---------------------------------------------------------------------------
# _build_node_summaries (fleet-summary badge) agrees with the live-check
# helper for the SAME node -- reconciliation proof for #11964.
# ---------------------------------------------------------------------------


def test_badge_and_live_check_agree_when_outdated():
    """The badge's code_update_available and the live-check's
    is_code_update_available() must return the same answer for a node whose
    code_status is genuinely outdated (#11964 acceptance criterion)."""
    node = _fake_node(node_id="node-x", code_status=CodeStatus.OUTDATED.value)

    summaries = _build_node_summaries([node], updates_by_node={}, global_count=0)
    badge_says_available = summaries[0].code_update_available

    live_check_says_available = is_code_update_available(node)

    assert badge_says_available is True
    assert live_check_says_available is True
    assert badge_says_available == live_check_says_available


def test_badge_and_live_check_agree_when_up_to_date():
    """No false-positive badge (#11964): when code_status is up_to_date,
    both the badge summary and the live-check helper report no code update --
    this is the exact bug scenario (badge true / scan false) inverted to
    prove they now can't disagree."""
    node = _fake_node(node_id="node-y", code_status=CodeStatus.UP_TO_DATE.value)

    summaries = _build_node_summaries([node], updates_by_node={}, global_count=0)
    badge_says_available = summaries[0].code_update_available

    live_check_says_available = is_code_update_available(node)

    assert badge_says_available is False
    assert live_check_says_available is False
    assert badge_says_available == live_check_says_available


def test_badge_clears_after_code_status_transitions_to_up_to_date():
    """After a code-sync/update completes and heartbeat flips code_status to
    up_to_date, re-running the fleet-summary build (the badge's data source)
    must clear code_update_available -- it cannot linger stale (#11964)."""
    node = _fake_node(node_id="node-z", code_status=CodeStatus.OUTDATED.value)
    before = _build_node_summaries([node], updates_by_node={}, global_count=0)
    assert before[0].code_update_available is True

    # Simulate the heartbeat-driven transition once the update lands.
    node.code_status = CodeStatus.UP_TO_DATE.value
    after = _build_node_summaries([node], updates_by_node={}, global_count=0)
    assert after[0].code_update_available is False


# ---------------------------------------------------------------------------
# Agentless stale-stamp derivation (#12571) -- same bug class as #12428/
# #12570: a node that never heartbeats has a frozen node.code_status stamp
# (often up_to_date from enrollment). is_code_update_available/
# _build_node_summaries must derive freshly from code_version vs
# latest_version (via services.code_status) instead of trusting that stamp,
# so GET /nodes/{id}/updates and the #11964 fleet badge agree with #12570's
# GET /nodes and GET /nodes/{id} derivation.
# ---------------------------------------------------------------------------


def test_is_code_update_available_derives_outdated_for_agentless_stale_node():
    """Frozen stamp says up_to_date, but code_version is behind latest --
    passing latest_version must flip the reported status to outdated,
    exactly like #12570's _reported_code_status for GET /nodes/{id}."""
    node = _fake_node(code_status=CodeStatus.UP_TO_DATE.value, code_version="old-sha")

    assert is_code_update_available(node, latest_version="new-sha") is True


def test_is_code_update_available_still_up_to_date_when_versions_match():
    node = _fake_node(code_status=CodeStatus.UP_TO_DATE.value, code_version="new-sha")

    assert is_code_update_available(node, latest_version="new-sha") is False


def test_is_code_update_available_falls_back_to_stamp_when_latest_unknown():
    """No fleet latest_version signal yet -- fall back to the stored stamp,
    same as #12570's _reported_code_status fallback."""
    node = _fake_node(code_status=CodeStatus.OUTDATED.value, code_version="whatever")

    assert is_code_update_available(node, latest_version=None) is True


def test_fleet_badge_derives_outdated_for_agentless_stale_node():
    """The #11964 fleet-update badge (_build_node_summaries) must derive the
    SAME outdated status for an agentless node's frozen up_to_date stamp,
    consistent with #12570's GET /nodes derivation (#12571)."""
    node = _fake_node(node_id="agentless-node", code_status=CodeStatus.UP_TO_DATE.value, code_version="old-sha")

    summaries = _build_node_summaries([node], updates_by_node={}, global_count=0, latest_version="new-sha")

    assert summaries[0].code_status == CodeStatus.OUTDATED.value
    assert summaries[0].code_update_available is True


def test_fleet_badge_and_live_check_agree_for_agentless_stale_node():
    """End-to-end #12571 reconciliation: GET /nodes/{id}/updates's live
    check and the fleet badge's summary must agree for the exact scenario
    #12570 fixed for GET /nodes -- a node whose stamp is frozen up_to_date
    but whose code_version has drifted behind latest_version."""
    node = _fake_node(node_id="agentless-node-2", code_status=CodeStatus.UP_TO_DATE.value, code_version="old-sha")
    latest_version = "new-sha"

    summaries = _build_node_summaries([node], updates_by_node={}, global_count=0, latest_version=latest_version)
    badge_says_available = summaries[0].code_update_available

    live_check_says_available = is_code_update_available(node, latest_version=latest_version)

    assert badge_says_available is True
    assert live_check_says_available is True
    assert badge_says_available == live_check_says_available
