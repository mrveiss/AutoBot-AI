# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every queue task_routes can target must have a consumer in every flavor (#11631).

celery_app.py is heavy and pytest-stubbed (#7766), so this parses source text
instead of importing it. Consumers checked:
  - task_queues in celery_app.py (SSOT — covers the Ansible systemd unit,
    which starts without -Q and therefore consumes exactly this set)
  - docker-compose.yml autobot-worker --queues
  - autobot-infrastructure/shared/scripts/start-celery-worker.sh --queues
"""

import re
from pathlib import Path

import celery_priority as cp

_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent
_CELERY_APP_SRC = (_BACKEND_DIR / "celery_app.py").read_text(encoding="utf-8")

# Default queue — priority-tier routes and every unrouted task land here.
_DEFAULT_QUEUE = "celery"


def _routed_queues() -> set[str]:
    """All queues task_routes can send a task to."""
    queues = set(re.findall(r'\{"queue":\s*"([\w-]+)"\}', _CELERY_APP_SRC))
    # Priority tiers merged into task_routes may pin explicit queues too.
    queues |= {route["queue"] for route in cp.PRIORITY_TASK_ROUTES.values() if "queue" in route}
    queues.add(_DEFAULT_QUEUE)
    return queues


def _task_queues() -> set[str]:
    """Queue names declared in celery_app.py task_queues."""
    return set(re.findall(r'Queue\("([\w-]+)"\)', _CELERY_APP_SRC))


def _queues_flag(text: str, path: str) -> set[str]:
    """Extract the --queues=... consumer list from a launcher file."""
    match = re.search(r"--queues=([\w,-]+)", text)
    assert match, f"no --queues flag found in {path}"
    return set(match.group(1).split(","))


def test_task_queues_covers_all_routed_queues():
    # The systemd unit (autobot-celery.service.j2) starts with no -Q and
    # consumes exactly task_queues — a routed queue missing here is stranded.
    routed, declared = _routed_queues(), _task_queues()
    assert routed <= declared, f"task_routes targets queues missing from task_queues: {routed - declared}"


def test_compose_worker_consumes_all_routed_queues():
    text = (_REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    consumed = _queues_flag(text, "docker-compose.yml")
    missing = _routed_queues() - consumed
    assert not missing, f"docker-compose.yml autobot-worker does not consume routed queues: {missing}"


def test_infra_start_script_consumes_all_routed_queues():
    script = _REPO_ROOT / "autobot-infrastructure/shared/scripts/start-celery-worker.sh"
    consumed = _queues_flag(script.read_text(encoding="utf-8"), str(script))
    missing = _routed_queues() - consumed
    assert not missing, f"start-celery-worker.sh does not consume routed queues: {missing}"


def test_systemd_unit_inherits_task_queues():
    # No -Q/--queues in the unit means it consumes the full task_queues set;
    # if someone adds an explicit flag it must cover every routed queue.
    unit = _REPO_ROOT / "autobot-slm-backend/ansible/roles/backend/templates/autobot-celery.service.j2"
    text = unit.read_text(encoding="utf-8")
    exec_lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    flags = re.search(r"(?:--queues=|-Q )([\w,-]+)", "\n".join(exec_lines))
    if flags:
        missing = _routed_queues() - set(flags.group(1).split(","))
        assert not missing, f"systemd unit --queues does not cover routed queues: {missing}"
