# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The reconciler's service-restart tracker persists across a backend restart
instead of resetting to zero attempts every time (#16712).

Before this fix `_service_remediation_tracker` was `self`-scoped process
memory: `self._service_remediation_tracker: Dict[tuple, Dict] = {}`. Every
SLM backend restart -- which every update-all deploy causes, in its first
play -- silently wiped it, giving a permanently-failing service three fresh
attempts after every deploy, forever. The count and exhausted flag now live
on `Service.extra_data["remediation"]`, the row already being read/written
every heartbeat, so a fresh `ReconcilerService()` instance (a restart, in
these tests) sees exactly what the row says.

The module is loaded from disk, not imported, because the package conftest
stubs `services.*` and a plain `import services.reconciler` yields a
MagicMock that would satisfy every check here while exercising nothing.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

_SLM_ROOT = Path(__file__).resolve().parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))


def _load_real_reconciler():
    """Load reconciler.py with a REAL ServiceStatus bound onto the stubbed
    models.database (#16712).

    The package conftest stubs `sys.modules["models.database"]` to a
    MagicMock for the whole test session, so `ServiceStatus.FAILED.value`
    inside reconciler.py would otherwise resolve to a MagicMock attribute --
    never equal to the plain string status this test passes, silently
    making `status != ServiceStatus.FAILED.value` true unconditionally.
    `service_status` itself is a standalone module the conftest never
    touches, so the real enum is one import away.
    """
    import service_status  # noqa: PLC0415

    sys.modules.setdefault("models.database", MagicMock())
    sys.modules["models.database"].ServiceStatus = service_status.ServiceStatus

    spec = importlib.util.spec_from_file_location(
        "reconciler_under_service_remediation_16712_test", _SLM_ROOT / "services" / "reconciler.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["reconciler_under_service_remediation_16712_test"] = module
    spec.loader.exec_module(module)
    return module


reconciler = _load_real_reconciler()


class _FakeService:
    """A minimal Service-row stand-in: attribute access and extra_data only."""

    def __init__(self, *, service_name="autobot-backend", extra_data=None):
        self.node_id = "node-1"
        self.service_name = service_name
        self.extra_data = extra_data


def test_read_defaults_to_zero_when_never_attempted():
    service = _FakeService(extra_data=None)

    assert reconciler.read_service_remediation(service) == {
        "count": 0,
        "last_attempt": None,
        "exhausted": False,
    }


def test_write_then_read_round_trips_and_preserves_other_extra_data_keys():
    service = _FakeService(extra_data={"error_message": "boom"})
    now = datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc)

    reconciler.write_service_remediation(service, {"count": 2, "last_attempt": now, "exhausted": False})

    assert service.extra_data["error_message"] == "boom", "an unrelated extra_data key must survive the write"
    assert reconciler.read_service_remediation(service) == {"count": 2, "last_attempt": now, "exhausted": False}


def test_the_tracker_survives_a_fresh_reconciler_instance():
    """Simulates a backend restart: a brand-new ReconcilerService, no carried
    process memory, still sees the count -- because it comes from the row.
    """
    service = _FakeService(extra_data={"remediation": {"count": 3, "last_attempt": None, "exhausted": True}})

    fresh = reconciler.ReconcilerService()
    tracker = reconciler.read_service_remediation(service)

    assert not hasattr(fresh, "_service_remediation_tracker"), "the old process-memory tracker must be gone"
    assert tracker["count"] == 3
    assert tracker["exhausted"] is True


def test_recovery_clears_the_tracker():
    """A service observed no longer FAILED resets its remediation entry on
    the very next heartbeat -- no separate manual step needed.
    """
    service = _FakeService(extra_data={"remediation": {"count": 3, "last_attempt": None, "exhausted": True}})
    svc = reconciler.ReconcilerService()

    svc._update_existing_service(service, {"status": "running"}, "running", "", datetime.now(timezone.utc))

    assert "remediation" not in service.extra_data


def test_an_in_progress_failure_keeps_its_tracker():
    """The control: a service still FAILED must not have its tracker wiped
    by the same heartbeat update that recovery clears it on.
    """
    service = _FakeService(extra_data={"remediation": {"count": 2, "last_attempt": None, "exhausted": False}})
    svc = reconciler.ReconcilerService()

    svc._update_existing_service(service, {"status": "failed"}, "failed", "still down", datetime.now(timezone.utc))

    assert service.extra_data["remediation"]["count"] == 2


def test_reset_service_remediation_tracker_clears_and_commits():
    """The operator-acknowledgement path (api/nodes.py's acknowledge-remediation)."""
    service = _FakeService(extra_data={"remediation": {"count": 3, "last_attempt": None, "exhausted": True}})
    result = MagicMock()
    result.scalars.return_value.all.return_value = [service]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    svc = reconciler.ReconcilerService()

    asyncio.run(svc.reset_service_remediation_tracker(db, "node-1"))

    assert "remediation" not in service.extra_data
    db.commit.assert_awaited_once()


def test_reset_service_remediation_tracker_is_a_noop_when_nothing_to_clear():
    """The control: no commit fires when there is nothing to clear."""
    service = _FakeService(extra_data=None)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [service]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    svc = reconciler.ReconcilerService()

    asyncio.run(svc.reset_service_remediation_tracker(db, "node-1"))

    db.commit.assert_not_awaited()
