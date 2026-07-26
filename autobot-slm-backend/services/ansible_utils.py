# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Ansible output parsing utilities for slm-backend endpoints."""

import os
import re
import shutil

# Common install locations checked when ansible-playbook isn't on PATH
# (Issue #12693 — shared between DeploymentService and PlaybookExecutor).
_COMMON_ANSIBLE_PATHS = (
    "/usr/bin/ansible-playbook",
    "/usr/local/bin/ansible-playbook",
    "/opt/ansible/bin/ansible-playbook",
)


def _find_ansible_playbook() -> str:
    """Find the ansible-playbook executable with system PATH.

    Shared by DeploymentService and PlaybookExecutor (Issue #12693, round-2
    of the #12645 dedup umbrella) — both previously carried near-identical
    copies of this search.
    """
    # First try with current PATH
    ansible_path = shutil.which("ansible-playbook")
    if ansible_path:
        return ansible_path

    # Try common system paths if not in current PATH
    for path in _COMMON_ANSIBLE_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    raise FileNotFoundError("ansible-playbook not found. Install Ansible: apt install ansible")


def _extract_failure_summary(output: str) -> str:
    """Parse Ansible stdout and return a human-readable failure summary.

    Extracts failed hosts, the task that failed, and the error message so
    users see e.g. '<host-ip> failed at "Common | Update apt cache":
    Failed to update apt cache: unknown reason' instead of 'exit code 2'.
    """
    lines = output.splitlines()
    failures: list[str] = []
    current_task = ""

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Track both TASK and RUNNING HANDLER lines (#9286)
        if line.startswith("TASK [") or line.startswith("RUNNING HANDLER ["):
            task_match = re.search(r"(?:TASK|RUNNING HANDLER) \[(.+?)\]", line)
            if task_match:
                current_task = task_match.group(1).strip()
        elif line.startswith("RUNNING HANDLER ["):
            # Issue #9286: Track handlers so failure is attributed correctly
            handler_match = re.search(r"RUNNING HANDLER \[(.+?)\]", line)
            if handler_match:
                current_task = handler_match.group(1).strip()

        if line.startswith("fatal:"):
            host_match = re.search(r"fatal: \[([^\]]+)\]", line)
            host = host_match.group(1) if host_match else "unknown host"
            failure_type = "UNREACHABLE" if "UNREACHABLE" in line else "FAILED"

            msg = ""
            for j in range(i + 1, min(i + 10, len(lines))):
                msg_match = re.search(r'"?msg"?\s*[:=]\s*["\']?(.+?)["\']?\s*$', lines[j].strip())
                if msg_match:
                    msg = msg_match.group(1).strip().strip("'\"")
                    break

            task_part = f' at "{current_task}"' if current_task else ""
            msg_part = f": {msg}" if msg else ""
            failures.append(f"{host} {failure_type.lower()}{task_part}{msg_part}")

        i += 1

    if not failures:
        return ""

    count = len(failures)
    noun = "host" if count == 1 else "hosts"
    return f"{count} {noun} failed \u2014 " + "; ".join(failures)
