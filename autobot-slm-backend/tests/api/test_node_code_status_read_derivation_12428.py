# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test: GET /nodes/{id} code_status must agree with
GET /code-sync/status's outdated_nodes count (#12428).

Root cause: the per-node ``code_status`` column is only ever written by
``_update_heartbeat_code_status``, which runs solely on a heartbeat. An
agentless node (e.g. role ``vnc``, no slm-agent enrolled -> last_heartbeat
stays ``None``) never heartbeats, so its stamp freezes at whatever it was
set to (often ``up_to_date`` at enrollment) even after ``code_version``
drifts behind the fleet's ``latest_version`` -- disagreeing with
``outdated_nodes`` (api/code_sync.py ``get_sync_status``), which always uses
the live ``code_version != latest_version`` signal.

Fix: ``get_node``/``list_nodes`` now derive the reported ``code_status`` on
every read via ``_derive_code_status``/``_reported_code_status`` -- the same
live signal, computed fresh instead of trusting the frozen stamp.

Follows the real-module-swap pattern from test_nodes_list_timeout_10913.py
(#11737): the slm-backend root conftest stubs sqlalchemy/models.database/
models.schemas as MagicMocks for import-time safety, so api.nodes is
imported inside ``_real_modules_swapped()`` to get the real FastAPI/pydantic
machinery ``NodeResponse.model_validate`` needs.
"""

from __future__ import annotations

import contextlib
import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

_SLM_ROOT = Path(__file__).parent.parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))

_SQLALCHEMY_MODULES = ("sqlalchemy", "sqlalchemy.ext", "sqlalchemy.ext.asyncio", "sqlalchemy.orm")


def _is_sqlalchemy_key(name: str) -> bool:
    return name == "sqlalchemy" or name.startswith("sqlalchemy.")


def _load_real_module(name: str, path: Path):
    """Exec *path* under canonical *name* (registered so relative imports work)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _build_real_modules() -> dict:
    """One-time real sqlalchemy + models.database/models.schemas/
    services.code_status snapshot.

    Mirrors tests/api/test_nodes_list_timeout_10913.py's setup: the root
    conftest stubs these as MagicMocks for import-time safety, so the real
    packages are loaded once here and swapped in on demand.

    services.code_status (#12571) must be real-loaded AFTER the real
    models.database, since api.nodes now imports its derive_code_status/
    get_latest_code_version/reported_code_status from there instead of
    defining them inline (#12428/#12570) -- a stub CodeStatus enum would
    break the string comparisons the derivation logic depends on.
    """
    saved = {name: mod for name, mod in sys.modules.items() if _is_sqlalchemy_key(name)}
    saved.update(
        {name: sys.modules.get(name) for name in ("models.database", "models.schemas", "services.code_status")}
    )
    for name in list(saved):
        sys.modules.pop(name, None)
    try:
        for name in _SQLALCHEMY_MODULES:
            importlib.import_module(name)
        importlib.import_module("sqlalchemy.dialects.sqlite")
        _load_real_module("models.database", _SLM_ROOT / "models" / "database.py")
        _load_real_module("models.schemas", _SLM_ROOT / "models" / "schemas.py")
        _load_real_module("services.code_status", _SLM_ROOT / "services" / "code_status.py")
        return {name: mod for name, mod in sys.modules.items() if _is_sqlalchemy_key(name)} | {
            "models.database": sys.modules["models.database"],
            "models.schemas": sys.modules["models.schemas"],
            "services.code_status": sys.modules["services.code_status"],
        }
    finally:
        for name in [n for n in sys.modules if _is_sqlalchemy_key(n)]:
            del sys.modules[name]
        sys.modules.pop("models.database", None)
        sys.modules.pop("models.schemas", None)
        sys.modules.pop("services.code_status", None)
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)


_REAL_MODULES = _build_real_modules()


@contextlib.contextmanager
def _real_modules_swapped():
    """Temporarily put the real sqlalchemy/models modules into sys.modules."""
    saved = {name: sys.modules.get(name) for name in _REAL_MODULES}
    sys.modules.update(_REAL_MODULES)
    try:
        yield
    finally:
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)


def _load_nodes_module():
    """Import the real ``api.nodes`` module under the real-module swap."""
    with _real_modules_swapped():
        sys.modules.pop("api.nodes", None)
        return importlib.import_module("api.nodes")


_NODES = _load_nodes_module()
CodeStatus = _NODES.CodeStatus


def _fake_node(
    node_id: str = "b9a29e04",
    code_version: str | None = "abc123",
    code_status: str | None = CodeStatus.UP_TO_DATE.value,
    last_heartbeat=None,
) -> SimpleNamespace:
    """A SimpleNamespace with every attribute NodeResponse.model_validate
    (from_attributes=True) needs — mirrors an agentless (or heartbeating)
    node row."""
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=1,
        node_id=node_id,
        hostname="vnc-node",
        ansible_name="vnc-node",
        ip_address="10.0.0.5",
        status="degraded",
        roles=["vnc"],
        detected_roles=[],
        ssh_user="autobot",
        ssh_port=22,
        auth_method="key",
        cpu_percent=0.0,
        memory_percent=0.0,
        disk_percent=0.0,
        last_heartbeat=last_heartbeat,
        agent_version=None,
        os_info=None,
        code_version=code_version,
        code_status=code_status,
        created_at=now,
        updated_at=now,
        a2a_card=None,
        service_summary=None,
        extra_data=None,
    )


def _mock_result(value):
    """A db.execute(...) result stub whose scalar_one_or_none() returns *value*."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


# ---------------------------------------------------------------------------
# _derive_code_status / _reported_code_status — pure-function coverage
# ---------------------------------------------------------------------------


class TestDeriveCodeStatus:
    def test_up_to_date_when_versions_match(self):
        assert _NODES._derive_code_status("abc", "abc") == CodeStatus.UP_TO_DATE.value

    def test_outdated_when_versions_differ(self):
        assert _NODES._derive_code_status("abc", "def") == CodeStatus.OUTDATED.value

    def test_outdated_when_code_version_none_but_latest_known(self):
        """Agentless node that never synced still can't claim up_to_date."""
        assert _NODES._derive_code_status(None, "def") == CodeStatus.UNKNOWN.value

    def test_none_when_latest_unknown(self):
        """Falls back (caller keeps stored stamp) when there's nothing to compare against."""
        assert _NODES._derive_code_status("abc", None) is None

    def test_service_failed_preserved_when_versions_match(self):
        assert (
            _NODES._derive_code_status("abc", "abc", was_service_failed=True)
            == CodeStatus.CODE_CURRENT_SERVICE_FAILED.value
        )

    def test_service_failed_ignored_when_versions_differ(self):
        """Version mismatch is definitive -- outdated wins over a stale
        service-failed flag."""
        assert _NODES._derive_code_status("abc", "def", was_service_failed=True) == CodeStatus.OUTDATED.value


class TestReportedCodeStatus:
    def test_agentless_node_never_reports_up_to_date_when_behind(self):
        """Core #12428 acceptance criterion: last_heartbeat=None,
        code_version behind latest -> must NOT report up_to_date, even
        though the frozen DB stamp says up_to_date."""
        node = _fake_node(code_version="old-sha", code_status=CodeStatus.UP_TO_DATE.value, last_heartbeat=None)
        reported = _NODES._reported_code_status(node, latest_version="new-sha")
        assert reported != CodeStatus.UP_TO_DATE.value
        assert reported == CodeStatus.OUTDATED.value

    def test_current_node_still_reports_up_to_date(self):
        node = _fake_node(
            code_version="new-sha", code_status=CodeStatus.UP_TO_DATE.value, last_heartbeat=datetime.now(timezone.utc)
        )
        reported = _NODES._reported_code_status(node, latest_version="new-sha")
        assert reported == CodeStatus.UP_TO_DATE.value

    def test_falls_back_to_stored_stamp_when_latest_unknown(self):
        node = _fake_node(code_version="new-sha", code_status=CodeStatus.OUTDATED.value)
        reported = _NODES._reported_code_status(node, latest_version=None)
        assert reported == CodeStatus.OUTDATED.value


# ---------------------------------------------------------------------------
# get_node endpoint — end-to-end agreement with outdated_nodes' live signal
# ---------------------------------------------------------------------------


class TestGetNodeDerivesCodeStatus:
    @pytest.mark.asyncio
    async def test_agentless_node_reports_outdated_not_up_to_date(self):
        """The exact #12428 scenario: node_id b9a29e04-style agentless node,
        last_heartbeat=None, code_version behind latest_version. get_node
        must report a non-up_to_date status -- consistent with
        outdated_nodes, which would count this node (code_version !=
        latest_version)."""
        node = _fake_node(code_version="old-sha", code_status=CodeStatus.UP_TO_DATE.value, last_heartbeat=None)
        latest_setting = SimpleNamespace(value="new-sha")

        mock_db = AsyncMock()
        mock_db.execute.side_effect = [_mock_result(node), _mock_result(latest_setting)]

        resp = await _NODES.get_node(node_id="b9a29e04", db=mock_db, _={"admin": True, "role": "admin"})

        assert resp.code_status != CodeStatus.UP_TO_DATE.value
        assert resp.code_status == CodeStatus.OUTDATED.value

    @pytest.mark.asyncio
    async def test_current_node_reports_up_to_date(self):
        """A node whose code_version matches latest_version still reports
        up_to_date -- the derivation must not regress the common case."""
        node = _fake_node(
            code_version="new-sha",
            code_status=CodeStatus.UP_TO_DATE.value,
            last_heartbeat=datetime.now(timezone.utc),
        )
        latest_setting = SimpleNamespace(value="new-sha")

        mock_db = AsyncMock()
        mock_db.execute.side_effect = [_mock_result(node), _mock_result(latest_setting)]

        resp = await _NODES.get_node(node_id="current-node", db=mock_db, _={"admin": True, "role": "admin"})

        assert resp.code_status == CodeStatus.UP_TO_DATE.value

    @pytest.mark.asyncio
    async def test_404_when_node_missing(self):
        from fastapi import HTTPException

        mock_db = AsyncMock()
        mock_db.execute.side_effect = [_mock_result(None)]

        with pytest.raises(HTTPException) as exc_info:
            await _NODES.get_node(node_id="missing", db=mock_db, _={"admin": True, "role": "admin"})

        assert exc_info.value.status_code == 404
