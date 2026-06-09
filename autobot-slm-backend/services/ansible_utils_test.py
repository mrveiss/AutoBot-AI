# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for ansible_utils._extract_failure_summary (Issue #9286)."""

from services.ansible_utils import _extract_failure_summary


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
