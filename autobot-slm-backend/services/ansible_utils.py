# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Ansible output parsing utilities for slm-backend endpoints."""

import os
import re
import shutil

from autobot_shared.env_utils import env_int

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

            # #14298: start at the fatal line ITSELF, not the one after it.
            # Ansible's default callback puts the whole result dict on the same
            # line as `fatal: [host]: FAILED! => {...”msg”: ...}`, so scanning
            # from i+1 found the message only in the multi-line (yaml/debug)
            # callback form. A summary that names the task but drops the
            # message is the half that matters least — the task is already in
            # the play, the msg is why it stopped.
            msg = ""
            for j in range(i, min(i + 10, len(lines))):
                msg_match = re.search(r'"?msg"?\s*[:=]\s*["\']?(.+?)["\']?\s*$', lines[j].strip())
                if msg_match:
                    msg = msg_match.group(1).strip().strip("'\"").rstrip("}").strip().strip("'\"")
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


# How much raw output to fall back to when nothing parseable is found. From the
# END of the run: ansible's first lines are its preamble, so a head slice
# reliably returns deprecation warnings and nothing else (#14298).
PLAYBOOK_FAILURE_TAIL_CHARS = env_int("AUTOBOT_PLAYBOOK_FAILURE_TAIL_CHARS", 500)


def summarize_playbook_failure(output: str, tail_chars: int | None = None) -> str:
    """Return the useful part of a failed playbook's output.

    ``_extract_failure_summary`` first — it names the host, the task and the
    ``msg``, which is what an operator needs. When it finds nothing parseable
    (a run that died before any task, a non-ansible error), fall back to the
    **tail**.

    #14298: every caller previously did ``output[:500]``, which is ansible's
    banner. A code-sync node failure reported itself as a DEFAULT_GATHER_SUBSET
    deprecation warning while the actual cause — a pip resolution conflict —
    sat at the end of the output, uncut. That is worse than no message: it
    reads as a diagnosis and points somewhere unrelated.

    Args:
        output: full stdout/stderr of the playbook run.
        tail_chars: fallback size; defaults to PLAYBOOK_FAILURE_TAIL_CHARS.

    Returns:
        A summary, or the tail of the output, or a fixed string when there is
        no output at all.
    """
    summary = _extract_failure_summary(output or "")
    if summary:
        return summary
    text = (output or "").strip()
    if not text:
        return "playbook failed with no output"
    limit = PLAYBOOK_FAILURE_TAIL_CHARS if tail_chars is None else tail_chars
    if len(text) <= limit:
        return text
    return "..." + text[-limit:]
