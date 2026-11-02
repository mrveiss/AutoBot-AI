# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One read-only answer to "what happened in the last update?" (#19962).

Built from the self-update log, through the reader that already survives an SLM restart and log
rotation. Raw Ansible output can still name paths and hosts that no redactor recognises, so the route is
admin-only; each value is redacted whole and only then cut, because a cut inside a secret leaves a fragment
no pattern matches.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from autobot_shared.secret_redaction import redact_content, redact_text
from services.self_update_log_reader import _read_log_text, read_self_update_verdict

_TASK_LINE = re.compile(r"^TASK \[(?P<name>.*?)\] \*+\s*$", re.MULTILINE)
_FAILURE_LINE = re.compile(r"^(?:fatal|failed): \[[^\]]+\]: FAILED! => (?P<detail>.*)$", re.MULTILINE)
_ERROR_LIMIT = 2000


def _safe(text: str) -> str:
    """Both redactors: name-keyed for `name=value`, content-shaped for URLs and key blocks. Then the bound."""
    return redact_content(redact_text(text))[-_ERROR_LIMIT:]


def _error_text(detail: str) -> str:
    """The message in Ansible's failure record, or the raw record when it is not JSON."""
    try:
        record = json.loads(detail)
    except ValueError:
        return detail
    parts = [str(record[key]) for key in ("msg", "stderr") if record.get(key)]
    return "\n".join(parts) or detail


def first_failure(log_text: str) -> dict[str, str] | None:
    """The task that failed first and its error; later failures usually follow from it."""
    failure = _FAILURE_LINE.search(log_text)
    if failure is None:
        return None
    tasks = list(_TASK_LINE.finditer(log_text, 0, failure.start()))
    return {
        "task": _safe(tasks[-1].group("name")) if tasks else "unknown",
        "error": _safe(_error_text(failure.group("detail"))),
    }


def _deploy_run(run: Any) -> dict[str, Any]:
    return {
        "node_id": run.node_id,
        "roles": run.roles or [],
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "error": _safe(run.error) if run.error else None,
    }


def build_update_report(
    log_path: Path, target_commit: str | None, deploy_runs: Iterable[Any], run_alive: bool | None = None
) -> dict[str, Any]:
    """The last update's target, how far it got, its result, what failed, and the role deploys around it."""
    verdict = read_self_update_verdict(log_path, run_alive=run_alive)
    source = _read_log_text(log_path)
    failure = first_failure(source.text) if source.text else None
    return {
        "target_commit": target_commit,
        "run_started_at": verdict.run_started_at,
        "log_present": verdict.log_present,
        "finished": verdict.complete,
        "last_stage": _safe(verdict.plays_seen[-1]) if verdict.plays_seen else None,
        "failed_hosts": verdict.failed_hosts,
        "unreachable_hosts": verdict.unreachable_hosts,
        "from_rotated_log": verdict.from_rotated_log,
        "summary": _safe(verdict.reason or ""),
        "failed_task": failure["task"] if failure else None,
        "error": failure["error"] if failure else None,
        "deploy_runs": [_deploy_run(run) for run in deploy_runs],
    }
