# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for ansible_utils._extract_failure_summary (Issue #9286).

The slm-backend root conftest stubs ``services.ansible_utils`` as a MagicMock
(it is imported at module level by api/setup_wizard.py, #11794), so a bare
``from services.ansible_utils import ...`` here would bind the stub instead of
the real parser.  Load the real file directly, like the sibling
drift_checker_test.py does.
"""

import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).parent / "ansible_utils.py"
_spec = importlib.util.spec_from_file_location("ansible_utils_under_test", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_extract_failure_summary = _mod._extract_failure_summary


def test_regular_task_failure():
    """Regular task failures are attributed correctly."""
    output = """
TASK [backend : Backend | Check cognition_seed.yaml exists (#4679)] ****
fatal: [00-SLM-Manager]: FAILED! => {
  "msg": "File not found"
}
"""
    result = _extract_failure_summary(output)
    assert "00-SLM-Manager" in result
    assert "backend : Backend | Check cognition_seed.yaml exists (#4679)" in result
    assert "File not found" in result


def test_handler_failure_attribution():
    """Handler failures should show the handler name, not the last task (#9286)."""
    output = """
TASK [backend : Backend | Check cognition_seed.yaml exists (#4679)] ****
ok: [00-SLM-Manager]

RUNNING HANDLER [backend : restart backend] *****
fatal: [00-SLM-Manager]: FAILED! => {
  "msg": "Unable to restart service autobot-backend: Job for autobot-backend.service failed because the control process exited with error code."
}

PLAY RECAP *****
00-SLM-Manager             : ok=5    changed=2    unreachable=0    failed=1    skipped=0    rescued=0    ignored=0
"""
    result = _extract_failure_summary(output)

    assert "restart backend" in result
    assert "cognition_seed.yaml" not in result
    assert "00-SLM-Manager" in result
    assert "failed" in result.lower()


def test_task_failure_attribution():
    """Regular task failures should still work correctly."""
    output = """
TASK [backend : Backend | Install dependencies] ****
fatal: [worker-01]: FAILED! => {
  "msg": "pip install failed"
}

PLAY RECAP *****
worker-01                  : ok=3    changed=0    unreachable=0    failed=1
"""
    result = _extract_failure_summary(output)

    assert "Install dependencies" in result
    assert "worker-01" in result
    assert "pip install failed" in result


def test_multiple_failures():
    """Multiple host failures should all be reported."""
    output = """
TASK [common : Update apt cache] ****
fatal: [host-01]: FAILED! => {
  "msg": "Failed to update apt cache"
}
fatal: [host-02]: FAILED! => {
  "msg": "Network timeout"
}

PLAY RECAP *****
"""
    result = _extract_failure_summary(output)

    assert "2 hosts failed" in result
    assert "host-01" in result
    assert "host-02" in result
    assert "Update apt cache" in result


def test_one_host_failing_several_tasks_is_not_several_hosts():
    """N failures on one host must never be reported as N hosts.

    The pre-existing multi-failure test uses two hosts with one failure each, so
    failure count and host count coincide and a conflated counter reads correct.
    This is the case that discriminates them.
    """
    output = """
TASK [backend : Slurp marker] ****
fatal: [node-a]: FAILED! => {"msg": "file not found: /opt/x/.marker"}

TASK [backend : Slurp legacy marker] ****
fatal: [node-a]: FAILED! => {"msg": "file not found: /opt/x/.deployed_commit"}

TASK [backend : Create filtered requirements] ****
fatal: [node-a]: FAILED! => {"msg": "non-zero return code"}

PLAY RECAP *****
"""
    result = _extract_failure_summary(output)

    assert "3 failures on 1 host" in result
    assert "3 hosts failed" not in result, "failure events were counted as hosts"


def test_ignored_failures_are_not_reported():
    """A task ansible ignored by design is not a failure.

    ignore_errors: true still prints a full `fatal:` line and only then
    `...ignoring`. Both marker reads in sync_deletions.yml rely on this, so every
    first provision emits two of them.
    """
    output = """
TASK [backend : Slurp marker] ****
fatal: [node-a]: FAILED! => {"msg": "file not found: /opt/x/.marker"}
...ignoring

TASK [backend : Create filtered requirements] ****
fatal: [node-a]: FAILED! => {"msg": "non-zero return code"}

PLAY RECAP *****
"""
    result = _extract_failure_summary(output)

    assert "1 host failed" in result
    assert "non-zero return code" in result
    assert ".marker" not in result, "an ignored failure was reported as a failure"


def test_a_run_whose_only_failures_were_ignored_reports_nothing():
    """A deploy that succeeded must not be presented as a failed one."""
    output = """
TASK [backend : Slurp marker] ****
fatal: [node-a]: FAILED! => {"msg": "file not found: /opt/x/.marker"}
...ignoring

TASK [backend : Slurp legacy marker] ****
fatal: [node-a]: FAILED! => {"msg": "file not found: /opt/x/.deployed_commit"}
...ignoring

PLAY RECAP *****
"""
    assert _extract_failure_summary(output) == ""


def test_ignoring_is_not_borrowed_from_a_later_task():
    """A real failure must not be silenced by the NEXT task's ...ignoring."""
    output = """
TASK [backend : Create filtered requirements] ****
fatal: [node-a]: FAILED! => {"msg": "non-zero return code"}

TASK [backend : Optional probe] ****
fatal: [node-a]: FAILED! => {"msg": "probe missing"}
...ignoring

PLAY RECAP *****
"""
    result = _extract_failure_summary(output)

    assert "non-zero return code" in result, "a real failure was silenced"
    assert "probe missing" not in result
    assert "1 host failed" in result


def test_unreachable_host():
    """Unreachable hosts should be reported as 'unreachable' not 'failed'."""
    output = """
TASK [Gathering Facts] ****
fatal: [10.0.0.5]: UNREACHABLE! => {
  "msg": "Failed to connect to the host via ssh"
}
"""
    result = _extract_failure_summary(output)

    assert "unreachable" in result.lower()
    assert "10.0.0.5" in result


def test_no_failures():
    """No failures should return empty string."""
    output = """
TASK [backend : Start service] ****
ok: [host-01]

PLAY RECAP *****
host-01                    : ok=10   changed=3   unreachable=0   failed=0
"""
    result = _extract_failure_summary(output)

    assert result == ""


def test_handler_then_task_failure():
    """When both handler and task fail, should track the correct one for each."""
    output = """
TASK [backend : Copy config] ****
ok: [host-01]

RUNNING HANDLER [backend : restart service] *****
fatal: [host-01]: FAILED! => {
  "msg": "Service restart failed"
}

TASK [backend : Verify deployment] ****
fatal: [host-01]: FAILED! => {
  "msg": "Deployment verification failed"
}
"""
    result = _extract_failure_summary(output)

    assert "restart service" in result
    assert "Verify deployment" in result or "verification" in result.lower()


def test_missing_error_message():
    """Should handle failures without a clear error message."""
    output = """
TASK [backend : Complex operation] ****
fatal: [host-01]: FAILED! => {
  "changed": false
}
"""
    result = _extract_failure_summary(output)

    assert "host-01" in result
    assert "Complex operation" in result
    assert "failed" in result.lower()
