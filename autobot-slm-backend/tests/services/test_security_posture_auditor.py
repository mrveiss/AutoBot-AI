# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the fleet security-posture auditor (GH#11224).

Covers:
- _is_public_address: wildcard/public vs loopback vs unknown (conservative).
- _scan_node_ports: flags sensitive+public ports only; ignores loopback,
  unknown address, non-sensitive ports, and malformed entries.
- SENSITIVE_PORTS sanity: expected-public ports absent; datastores HIGH+.
- _build_security_event: metadata-only, correct fields.
- audit_fleet_security_posture: creates events and dedups against open findings.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_slm_root = Path(__file__).parent.parent.parent
if str(_slm_root) not in sys.path:
    sys.path.insert(0, str(_slm_root))

# The slm-backend conftest stubs `models`/`services` as MagicMocks for API tests,
# but this module's logic depends on the real SecurityEventSeverity enum. Load the
# real models.database (self-contained: stdlib + sqlalchemy only), swap it in while
# executing the auditor, then restore the stub so sibling test files are unaffected.
_real_md_spec = importlib.util.spec_from_file_location("models.database", _slm_root / "models" / "database.py")
_real_md = importlib.util.module_from_spec(_real_md_spec)
_orig_md = sys.modules.get("models.database")
sys.modules["models.database"] = _real_md
_real_md_spec.loader.exec_module(_real_md)
try:
    # Load by file path so importing does not trigger the `services` package
    # __init__ (auth → autobot_shared), which is unavailable in unit tests.
    _spec = importlib.util.spec_from_file_location(
        "security_posture_auditor", _slm_root / "services" / "security_posture_auditor.py"
    )
    spa = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(spa)
finally:
    if _orig_md is not None:
        sys.modules["models.database"] = _orig_md
    else:
        sys.modules.pop("models.database", None)


class TestIsPublicAddress:
    @pytest.mark.parametrize("addr", ["0.0.0.0", "*", "::", "192.168.1.5", "10.0.0.2", "0.0.0.0 "])
    def test_public(self, addr):
        assert spa._is_public_address(addr) is True

    @pytest.mark.parametrize("addr", ["127.0.0.1", "::1", "localhost", "127.0.1.1", None, ""])
    def test_not_public(self, addr):
        assert spa._is_public_address(addr) is False


class TestScanNodePorts:
    def test_flags_public_sensitive_port(self):
        findings = spa._scan_node_ports([{"port": 6379, "address": "0.0.0.0", "process": "redis"}])
        assert len(findings) == 1
        assert findings[0]["service"] == "redis"
        assert findings[0]["severity"] == "high"

    def test_ignores_loopback(self):
        assert spa._scan_node_ports([{"port": 6379, "address": "127.0.0.1"}]) == []

    def test_ignores_unknown_address_conservatively(self):
        assert spa._scan_node_ports([{"port": 6379, "address": None}]) == []
        assert spa._scan_node_ports([{"port": 6379}]) == []

    def test_ignores_non_sensitive_port(self):
        assert spa._scan_node_ports([{"port": 8080, "address": "0.0.0.0"}]) == []

    def test_ignores_malformed_entries(self):
        assert spa._scan_node_ports([None, "nope", 123]) == []

    def test_none_list(self):
        assert spa._scan_node_ports(None) == []

    def test_mixed_list_returns_only_exposed_sensitive(self):
        findings = spa._scan_node_ports(
            [
                {"port": 6379, "address": "0.0.0.0"},  # exposed redis  -> flag
                {"port": 5432, "address": "127.0.0.1"},  # loopback pg    -> skip
                {"port": 443, "address": "0.0.0.0"},  # expected pub   -> skip
                {"port": 2375, "address": "10.0.0.9"},  # docker api     -> flag
            ]
        )
        ports = sorted(f["port"] for f in findings)
        assert ports == [2375, 6379]


class TestSensitivePortsSanity:
    def test_expected_public_ports_absent(self):
        for p in (22, 80, 443):
            assert p not in spa.SENSITIVE_PORTS

    def test_docker_api_is_critical(self):
        assert spa.SENSITIVE_PORTS[2375][1] == "critical"

    def test_datastores_are_high(self):
        for p in (5432, 6379, 3306, 27017):
            assert spa.SENSITIVE_PORTS[p][1] == "high"


class _RecordingEvent:
    """Stand-in for the SecurityEvent model (stubbed by the slm conftest).

    Records constructor kwargs as attributes so tests can assert on the fields
    the auditor populates without depending on the real SQLAlchemy model.
    """

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class TestBuildSecurityEvent:
    def test_metadata_only_fields(self, monkeypatch):
        monkeypatch.setattr(spa, "SecurityEvent", _RecordingEvent)
        finding = {
            "port": 6379,
            "address": "0.0.0.0",
            "service": "redis",
            "severity": "high",
            "process": "redis-server",
        }
        ev = spa._build_security_event("node-7", finding)
        assert ev.event_type == "port_exposure"
        assert ev.category == "network_exposure"
        assert ev.severity == "high"
        assert ev.target_node_id == "node-7"
        assert ev.target_resource == "0.0.0.0:6379"
        assert ev.raw_data["port"] == 6379 and ev.raw_data["service"] == "redis"
        # metadata only — no secret value fields
        assert "secret" not in (ev.description or "").lower()


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, nodes):
        self._nodes = nodes
        self.added = []

    async def execute(self, _stmt):
        return _FakeResult(self._nodes)

    def add(self, obj):
        self.added.append(obj)


class _FakeSessionCtx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


class _Node:
    def __init__(self, node_id, listening_ports):
        self.node_id = node_id
        self.listening_ports = listening_ports


class TestAuditFleet:
    @pytest.mark.asyncio
    async def test_creates_events_and_dedups(self, monkeypatch):
        nodes = [
            _Node("node-a", [{"port": 6379, "address": "0.0.0.0"}, {"port": 5432, "address": "0.0.0.0"}]),
            _Node("node-b", [{"port": 6379, "address": "127.0.0.1"}]),  # loopback → nothing
        ]
        session = _FakeSession(nodes)
        monkeypatch.setattr(spa, "SecurityEvent", _RecordingEvent)
        monkeypatch.setattr(spa, "_get_session", lambda: _FakeSessionCtx(session))

        # node-a already has an open exposure for redis(6379) → only 5432 is new.
        async def _fake_open(_db, node_id):
            return {6379} if node_id == "node-a" else set()

        monkeypatch.setattr(spa, "_open_exposure_ports", _fake_open)

        created = await spa.audit_fleet_security_posture()

        assert created == 1
        assert len(session.added) == 1
        assert session.added[0].raw_data["port"] == 5432
