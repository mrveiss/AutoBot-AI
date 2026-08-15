# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Ansible output parsing utilities for slm-backend endpoints."""

import json
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


def _msg_from_result_json(line: str) -> str:
    """``msg`` out of the result dict on a ``fatal:`` line, parsed as JSON.

    Ansible's default callback renders the whole result on one line:
    ``fatal: [host]: FAILED! => {"changed": false, "msg": "...", "rc": 100, ...}``

    Review finding on #14298: a regex ending at ``$`` cannot know where the
    ``msg`` value stops, so whenever ``msg`` is not the last key — which is the
    norm for ``command``/``shell``/``apt``/``pip`` tasks, since ``rc``,
    ``stderr`` and ``stdout`` all sort after it — the captured text ran on into
    the rest of the JSON. The first fix for that, stripping a trailing ``}``,
    was the same mistake one size smaller: it truncated any message whose own
    text ends in a brace.

    Parsing removes both failure modes rather than trading between them.
    """
    start = line.find("{")
    if start == -1:
        return ""
    blob = line[start:]
    try:
        result = json.loads(blob)
    except (ValueError, TypeError):
        return ""
    if not isinstance(result, dict):
        return ""
    msg = result.get("msg")
    return str(msg).strip() if msg else ""


def _msg_from_following_lines(lines: list[str], index: int) -> str:
    """``msg`` from the lines after a ``fatal:``, for the yaml/verbose callback.

    There the dict is pretty-printed, so ``"msg": "..."`` sits alone on its own
    line and ending the capture at ``$`` is correct.
    """
    for j in range(index + 1, min(index + 10, len(lines))):
        msg_match = re.search(r'"?msg"?\s*[:=]\s*["\']?(.+?)["\',]?\s*$', lines[j].strip())
        if msg_match:
            return msg_match.group(1).strip().strip("'\"")
    return ""


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

            # #14298: the message lives on the fatal line itself under the
            # default callback, and on its own line under the yaml/verbose one.
            # Parse the JSON first, fall back to the line scan.
            msg = _msg_from_result_json(line) or _msg_from_following_lines(lines, i)

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
