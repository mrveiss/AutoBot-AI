# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the Application-log viewer API (#11302).

GET /monitoring/app-logs tails an allowlisted application-log file on a
managed node via the guarded execute primitives from api.nodes_execution
(#3406) — never a shell, never a user-supplied path.

Covers:
- Non-allowlisted `service` -> HTTP 400 with no execute-helper call attempted.
- Server-side filename mapping means path traversal via `service` is impossible.
- Secret patterns (tokens, passwords, Authorization headers) are redacted.
- Pagination bounds (page/per_page) are honoured.
- severity and q (text) filters narrow the result set.
- A missing log file (non-zero tail exit) yields an empty result, not HTTP 500.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Path setup — allow importing without full app initialisation
# ---------------------------------------------------------------------------

_backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(_backend_root))

# Stub heavy dependencies before importing the module under test. Mirrors the
# approach in api/nodes_execution_test.py — monitoring.py pulls in config,
# real DB models, and the auth/db service layers, none of which are needed to
# unit-test the app-logs slice.
_models_stub = MagicMock()
for _name in (
    "Deployment",
    "DeploymentStatus",
    "EventSeverity",
    "MaintenanceWindow",
    "Node",
    "NodeEvent",
    "NodeStatus",
    "Service",
    "ServiceStatus",
):
    setattr(_models_stub, _name, MagicMock())
sys.modules.setdefault("models.database", _models_stub)

_config_stub = MagicMock()
_config_stub.settings = MagicMock(prometheus_url="http://localhost:9090")
sys.modules.setdefault("config", _config_stub)


def _fake_require_permission(_permission):
    async def _dependency():
        return {"sub": "test-admin"}

    return _dependency


_auth_stub = MagicMock()
_auth_stub.require_permission = _fake_require_permission
_auth_stub.get_current_user = AsyncMock(return_value={"sub": "test-admin"})
sys.modules.setdefault("services.auth", _auth_stub)
sys.modules.setdefault("services.database", MagicMock())
sys.modules.setdefault("sqlalchemy", MagicMock())
sys.modules.setdefault("sqlalchemy.ext.asyncio", MagicMock())

# api.nodes_execution helpers are the reused execution primitives (#3406).
# Stubbed here at import time; individual tests monkeypatch the bound
# references on the loaded monitoring module to control behaviour per-case.
sys.modules.setdefault("api", MagicMock())
_nodes_execution_stub = MagicMock()
_nodes_execution_stub._is_local_ip = MagicMock(return_value=True)
_nodes_execution_stub._require_online_node = AsyncMock()
_nodes_execution_stub._run_command = AsyncMock(return_value=(0, "", ""))
_nodes_execution_stub._run_via_ssh = AsyncMock(return_value=(0, "", ""))
sys.modules.setdefault("api.nodes_execution", _nodes_execution_stub)

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("monitoring", Path(__file__).parent / "monitoring.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_resolve_app_log_filename = _mod._resolve_app_log_filename
# Redaction is now the canonical autobot_shared util (#12242); monitoring calls it directly.
from autobot_shared.security.redaction import redact_text as _redact_app_log_line  # noqa: E402

_parse_app_log_line = _mod._parse_app_log_line
_filter_app_log_entries = _mod._filter_app_log_entries
_paginate_app_log_entries = _mod._paginate_app_log_entries
_tail_app_log_file = _mod._tail_app_log_file
_get_app_logs_core = _mod._get_app_logs_core
AppLogEntry = _mod.AppLogEntry
_APP_LOG_SERVICE_FILES = _mod._APP_LOG_SERVICE_FILES


def _fmt_now() -> str:
    """Format the current UTC time as a log-line timestamp prefix (avoids
    hardcoded dates going stale relative to the `hours` cutoff filter)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]


def _make_node(node_id="node-1", ip="10.0.0.5"):
    node = MagicMock()
    node.node_id = node_id
    node.ip_address = ip
    node.ssh_user = "autobot"
    node.ssh_port = 22
    return node


# ---------------------------------------------------------------------------
# _resolve_app_log_filename — server-side allowlist, no user-supplied path
# ---------------------------------------------------------------------------


class TestResolveAppLogFilename:
    @pytest.mark.parametrize(
        "service,expected",
        [
            ("backend", "backend-error.log"),
            ("celery", "celery-error.log"),
            ("celery-beat", "celery-beat-error.log"),
            ("chromadb", "chromadb-error.log"),
        ],
    )
    def test_known_services_map_to_fixed_filenames(self, service, expected):
        assert _resolve_app_log_filename(service, None) == expected

    def test_mcp_bridge_default_instance(self):
        assert _resolve_app_log_filename("mcp-bridge", None) == "mcp-bridge-default-error.log"

    def test_mcp_bridge_explicit_instance(self):
        assert _resolve_app_log_filename("mcp-bridge", "worker1") == "mcp-bridge-worker1-error.log"

    @pytest.mark.parametrize(
        "bad_instance",
        ["../../etc/passwd", "worker/1", "worker;rm -rf", "a" * 65],
    )
    def test_mcp_bridge_rejects_unsafe_instance(self, bad_instance):
        with pytest.raises(HTTPException) as exc_info:
            _resolve_app_log_filename("mcp-bridge", bad_instance)
        assert exc_info.value.status_code == 400

    def test_mcp_bridge_empty_instance_falls_back_to_default(self):
        """An empty-string instance is treated as 'not provided' (falsy) -> default."""
        assert _resolve_app_log_filename("mcp-bridge", "") == "mcp-bridge-default-error.log"

    @pytest.mark.parametrize(
        "service",
        ["../../etc/shadow", "backend/../../etc/passwd", "nginx", "unknown-service", ""],
    )
    def test_non_allowlisted_service_rejected(self, service):
        """A service not in the map is rejected with HTTP 400 — no file is ever read."""
        with pytest.raises(HTTPException) as exc_info:
            _resolve_app_log_filename(service, None)
        assert exc_info.value.status_code == 400
        assert "Unknown service" in exc_info.value.detail

    def test_allowlist_only_contains_fixed_basenames(self):
        """No allowlist entry contains a path separator or traversal token."""
        for filename in _APP_LOG_SERVICE_FILES.values():
            assert "/" not in filename
            assert ".." not in filename


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


class TestRedaction:
    def test_token_kv_is_redacted(self):
        line = "ERROR auth failed token=abc123SECRET456 for user bob"
        redacted = _redact_app_log_line(line)
        assert "abc123SECRET456" not in redacted
        assert "token=***" in redacted

    def test_password_kv_is_redacted(self):
        line = "connecting with password=hunter2! to db"
        redacted = _redact_app_log_line(line)
        assert "hunter2!" not in redacted
        assert "password=***" in redacted

    def test_authorization_header_is_redacted(self):
        line = "Authorization: Bearer eyJabc.def.ghi more text after"
        redacted = _redact_app_log_line(line)
        assert "eyJabc.def.ghi" not in redacted
        assert "Bearer" not in redacted
        assert "***" in redacted

    def test_non_secret_line_is_unchanged(self):
        line = "2026-07-23 10:00:00,123 INFO worker started successfully"
        assert _redact_app_log_line(line) == line

    def test_parsed_entry_message_is_redacted(self):
        entry = _parse_app_log_line("ERROR api_key=super-secret-value request failed", 1)
        assert "super-secret-value" not in entry.message
        assert entry.severity == "ERROR"


# ---------------------------------------------------------------------------
# Line parsing (timestamp/severity best-effort)
# ---------------------------------------------------------------------------


class TestParseAppLogLine:
    def test_parses_iso_timestamp_and_level(self):
        entry = _parse_app_log_line("2026-07-23 10:00:00,123 - worker - ERROR - boom", 5)
        assert entry.line_number == 5
        assert entry.severity == "ERROR"
        assert entry.timestamp is not None
        assert entry.timestamp.year == 2026

    def test_warn_normalised_to_warning(self):
        entry = _parse_app_log_line("2026-07-23T10:00:00Z WARN disk usage high", 1)
        assert entry.severity == "WARNING"

    def test_unparseable_line_has_none_timestamp_and_severity(self):
        entry = _parse_app_log_line("garbled line with no structure at all", 1)
        assert entry.timestamp is None
        assert entry.severity is None
        assert entry.message == "garbled line with no structure at all"


# ---------------------------------------------------------------------------
# Filtering — severity / q / hours(cutoff)
# ---------------------------------------------------------------------------


class TestFilterAppLogEntries:
    def _entries(self):
        now = datetime.now(timezone.utc)
        return [
            AppLogEntry(line_number=1, timestamp=now, severity="ERROR", message="disk full on /var"),
            AppLogEntry(line_number=2, timestamp=now, severity="INFO", message="heartbeat ok"),
            AppLogEntry(
                line_number=3,
                timestamp=now - timedelta(hours=5),
                severity="ERROR",
                message="stale error before cutoff",
            ),
            AppLogEntry(line_number=4, timestamp=None, severity="WARNING", message="unknown-time warning"),
        ]

    def test_severity_filter(self):
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = _filter_app_log_entries(self._entries(), "error", None, cutoff)
        assert all(e.severity == "ERROR" for e in result)
        assert len(result) == 2

    def test_q_text_filter(self):
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = _filter_app_log_entries(self._entries(), None, "disk", cutoff)
        assert len(result) == 1
        assert "disk full" in result[0].message

    def test_hours_cutoff_excludes_stale_entries(self):
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        result = _filter_app_log_entries(self._entries(), None, None, cutoff)
        messages = [e.message for e in result]
        assert "stale error before cutoff" not in messages
        # Unknown-timestamp entries are kept (best-effort — never dropped blind)
        assert "unknown-time warning" in messages


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestPaginateAppLogEntries:
    def test_pagination_bounds(self):
        entries = [AppLogEntry(line_number=i, message=f"line {i}") for i in range(1, 251)]
        page1, total = _paginate_app_log_entries(entries, page=1, per_page=100)
        assert total == 250
        assert len(page1) == 100
        assert page1[0].line_number == 1

        page3, total3 = _paginate_app_log_entries(entries, page=3, per_page=100)
        assert total3 == 250
        assert len(page3) == 50
        assert page3[0].line_number == 201

        page_out_of_range, _ = _paginate_app_log_entries(entries, page=10, per_page=100)
        assert page_out_of_range == []


# ---------------------------------------------------------------------------
# _tail_app_log_file — missing file is empty, not an exception
# ---------------------------------------------------------------------------


class TestTailAppLogFile:
    @pytest.mark.asyncio
    async def test_missing_file_returns_empty_list(self, monkeypatch):
        node = _make_node()
        monkeypatch.setattr(_mod, "_is_local_ip", lambda ip: True)
        monkeypatch.setattr(
            _mod,
            "_run_command",
            AsyncMock(return_value=(1, "", "tail: cannot open '/var/log/autobot/backend-error.log': No such file")),
        )
        lines = await _tail_app_log_file(node, "backend-error.log")
        assert lines == []

    @pytest.mark.asyncio
    async def test_existing_file_returns_lines(self, monkeypatch):
        node = _make_node()
        monkeypatch.setattr(_mod, "_is_local_ip", lambda ip: True)
        monkeypatch.setattr(
            _mod,
            "_run_command",
            AsyncMock(return_value=(0, "line one\nline two\nline three", "")),
        )
        lines = await _tail_app_log_file(node, "backend-error.log")
        assert lines == ["line one", "line two", "line three"]

    @pytest.mark.asyncio
    async def test_remote_node_uses_ssh_helper(self, monkeypatch):
        node = _make_node(ip="10.0.0.9")
        monkeypatch.setattr(_mod, "_is_local_ip", lambda ip: False)
        ssh_mock = AsyncMock(return_value=(0, "remote line", ""))
        monkeypatch.setattr(_mod, "_run_via_ssh", ssh_mock)
        lines = await _tail_app_log_file(node, "celery-error.log")
        assert lines == ["remote line"]
        ssh_mock.assert_awaited_once()
        args = ssh_mock.await_args.args
        assert args[0] == "10.0.0.9"
        assert "tail" in args[3]


# ---------------------------------------------------------------------------
# get_app_logs endpoint — end-to-end with mocked execute helper (no real SSH)
# ---------------------------------------------------------------------------


class TestGetAppLogsEndpoint:
    @pytest.mark.asyncio
    async def test_non_allowlisted_service_rejected_before_any_node_lookup(self, monkeypatch):
        require_online_mock = AsyncMock()
        monkeypatch.setattr(_mod, "_require_online_node", require_online_mock)

        with pytest.raises(HTTPException) as exc_info:
            await _get_app_logs_core(
                db=MagicMock(),
                node_id="node-1",
                service="totally-not-a-real-service",
            )
        assert exc_info.value.status_code == 400
        require_online_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_seeded_token_is_redacted_in_response(self, monkeypatch):
        node = _make_node()
        now = _fmt_now()
        monkeypatch.setattr(_mod, "_require_online_node", AsyncMock(return_value=node))
        monkeypatch.setattr(_mod, "_is_local_ip", lambda ip: True)
        monkeypatch.setattr(
            _mod,
            "_run_command",
            AsyncMock(return_value=(0, f"{now} ERROR token=leaked-secret-value auth failed", "")),
        )

        response = await _get_app_logs_core(
            db=MagicMock(),
            node_id="node-1",
            service="backend",
            hours=24,
        )
        assert response.total == 1
        assert "leaked-secret-value" not in response.entries[0].message
        assert "token=***" in response.entries[0].message

    @pytest.mark.asyncio
    async def test_pagination_query_params_applied(self, monkeypatch):
        node = _make_node()
        raw = "\n".join(f"{_fmt_now()} INFO line {i}" for i in range(30))
        monkeypatch.setattr(_mod, "_require_online_node", AsyncMock(return_value=node))
        monkeypatch.setattr(_mod, "_is_local_ip", lambda ip: True)
        monkeypatch.setattr(_mod, "_run_command", AsyncMock(return_value=(0, raw, "")))

        response = await _get_app_logs_core(
            db=MagicMock(),
            node_id="node-1",
            service="backend",
            hours=24,
            page=2,
            per_page=10,
        )
        assert response.total == 30
        assert response.page == 2
        assert response.per_page == 10
        assert len(response.entries) == 10

    @pytest.mark.asyncio
    async def test_severity_filter_applied(self, monkeypatch):
        node = _make_node()
        now = _fmt_now()
        raw = f"{now} ERROR boom one\n{now} INFO all good\n{now} ERROR boom two"
        monkeypatch.setattr(_mod, "_require_online_node", AsyncMock(return_value=node))
        monkeypatch.setattr(_mod, "_is_local_ip", lambda ip: True)
        monkeypatch.setattr(_mod, "_run_command", AsyncMock(return_value=(0, raw, "")))

        response = await _get_app_logs_core(
            db=MagicMock(),
            node_id="node-1",
            service="backend",
            severity="error",
            hours=24,
        )
        assert response.total == 2
        assert all(e.severity == "ERROR" for e in response.entries)

    @pytest.mark.asyncio
    async def test_q_filter_applied(self, monkeypatch):
        node = _make_node()
        now = _fmt_now()
        raw = f"{now} INFO disk usage high\n{now} INFO heartbeat ok"
        monkeypatch.setattr(_mod, "_require_online_node", AsyncMock(return_value=node))
        monkeypatch.setattr(_mod, "_is_local_ip", lambda ip: True)
        monkeypatch.setattr(_mod, "_run_command", AsyncMock(return_value=(0, raw, "")))

        response = await _get_app_logs_core(
            db=MagicMock(),
            node_id="node-1",
            service="backend",
            q="disk",
            hours=24,
        )
        assert response.total == 1
        assert "disk usage high" in response.entries[0].message

    @pytest.mark.asyncio
    async def test_missing_log_file_returns_empty_not_500(self, monkeypatch):
        node = _make_node()
        monkeypatch.setattr(_mod, "_require_online_node", AsyncMock(return_value=node))
        monkeypatch.setattr(_mod, "_is_local_ip", lambda ip: True)
        monkeypatch.setattr(
            _mod,
            "_run_command",
            AsyncMock(return_value=(1, "", "tail: cannot open: No such file or directory")),
        )

        response = await _get_app_logs_core(
            db=MagicMock(),
            node_id="node-1",
            service="backend",
        )
        assert response.total == 0
        assert response.entries == []
