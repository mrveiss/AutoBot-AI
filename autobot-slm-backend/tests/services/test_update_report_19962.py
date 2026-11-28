# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The update report names a failed task, including from a rotated log, and carries no secret (#19962)."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock


def _load_report():
    """Load both modules for real, past the conftest's session-global services stub."""
    root = Path(__file__).resolve().parents[2] / "services"
    saved = {
        name: sys.modules.get(name) for name in ("autobot_shared.logging_manager", "services.self_update_log_reader")
    }
    sys.modules["autobot_shared.logging_manager"] = MagicMock()
    try:
        modules = []
        for stem, name in (
            ("self_update_log_reader", "services.self_update_log_reader"),
            ("update_report", "_ur_19962"),
        ):
            spec = importlib.util.spec_from_file_location(name, root / f"{stem}.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            modules.append(module)
        return modules[1]
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


_report = _load_report()
build_update_report, first_failure = _report.build_update_report, _report.first_failure

_SECRET = "hunter2-very-secret"  # pragma: allowlist secret
_FATAL = "fatal: [node]: FAILED! => " + json.dumps(
    {
        "msg": "non-zero return code",
        "stderr": f"Cannot uninstall uvicorn; password={_SECRET}",
    }  # pragma: allowlist secret
)
_LOG = f"""SELF-UPDATE RUN STARTED 2026-10-30T08:50:00+00:00
PLAY [Play 1 - Update SLM Server First] ****
TASK [earlier task] ****
ok: [node]
TASK [[PLAY 1] SLM | Install Python dependencies] ****
{_FATAL}
PLAY RECAP ****
node : ok=109 changed=17 unreachable=0 failed=1 skipped=77
"""


def test_a_failed_task_in_a_rotated_log_is_named(tmp_path):
    live = tmp_path / "self-update.log"
    live.write_text("", encoding="utf-8")
    (tmp_path / "self-update.log.1").write_text(_LOG, encoding="utf-8")
    report = build_update_report(live, "abc123", [])
    assert report["from_rotated_log"] is True
    assert report["failed_task"] == "[PLAY 1] SLM | Install Python dependencies"
    assert "Cannot uninstall uvicorn" in report["error"]
    assert report["last_stage"] == "Play 1 - Update SLM Server First"
    assert report["failed_hosts"] == 1 and report["finished"] is True
    assert report["target_commit"] == "abc123"


def test_no_secret_leaves_in_the_error_or_a_deploy_run(tmp_path):
    log = tmp_path / "self-update.log"
    log.write_text(_LOG, encoding="utf-8")
    run = types.SimpleNamespace(
        node_id="n1",
        roles=["backend"],
        status="failed",
        started_at=datetime(2026, 10, 30, tzinfo=timezone.utc),
        error=f"password={_SECRET}",  # pragma: allowlist secret
    )
    assert _SECRET not in json.dumps(build_update_report(log, None, [run]))


def test_a_clean_run_names_no_failure_and_a_missing_log_says_so(tmp_path):
    assert first_failure("PLAY [x] ****\nTASK [y] ****\nok: [n]\n") is None
    report = build_update_report(tmp_path / "absent.log", None, [])
    assert report["log_present"] is False and report["failed_task"] is None


_PEM_BEGIN = "-----BEGIN " + "PRIVATE KEY-----"
_PEM_END = "-----END " + "PRIVATE KEY-----"


def test_the_shapes_a_raw_error_can_carry_do_not_leave():
    for leak, secret in (
        ("postgres://admin:%s@db/x" % _SECRET, _SECRET),  # pragma: allowlist secret
        ('{"password": "%s"}' % _SECRET, _SECRET),  # pragma: allowlist secret
        ("%s\n%s\n%s" % (_PEM_BEGIN, _SECRET, _PEM_END), _SECRET),
        ("api_key=%s" % _SECRET, _SECRET),
    ):
        log = "TASK [t] ****\nfatal: [n]: FAILED! => not json " + leak.replace("\n", " ") + "\n"
        failure = first_failure(log)
        assert secret not in failure["error"], leak


def test_redaction_runs_before_the_cut_so_a_secret_at_the_edge_cannot_survive():
    padding = "x" * _report._ERROR_LIMIT
    error = _report._safe("api_key=%s %s" % (_SECRET, padding))
    assert _SECRET not in error and len(error) == _report._ERROR_LIMIT


def test_a_task_name_or_stage_carrying_a_secret_is_redacted(tmp_path):
    """Every value from the log goes through the redactors, not only the error."""
    log = tmp_path / "self-update.log"
    log.write_text(
        f"PLAY [deploy password={_SECRET}] ****\n"  # pragma: allowlist secret
        f"TASK [login token={_SECRET}] ****\n"  # pragma: allowlist secret
        'fatal: [n]: FAILED! => {"msg": "x"}\n',
        encoding="utf-8",
    )
    assert _SECRET not in json.dumps(build_update_report(log, None, []))
