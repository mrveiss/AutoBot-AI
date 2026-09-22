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
        # Greedy to end-of-line, with the trimming done in Python.
        #
        # CodeQL flags the previous pattern as py/polynomial-redos: it ended
        # `(.+?)["\',]?\s*$`, a lazy group followed by an optional class and
        # `\s*$`, which can retry the lazy group at every split point.
        #
        # NOT claimed as an exploitable fix. The attack CodeQL describes needs a
        # line ending in many spaces, and the call above applies `.strip()` first,
        # which removes them before the regex runs — `"msg:a" + " "*4000` is five
        # characters by the time it arrives. Timed both patterns at 1k-8k spaces,
        # stripped and unstripped: no blowup in either.
        #
        # The rewrite stands on being simpler and provably non-backtracking —
        # `(.*)` matches once — not on closing a live hole. Output is identical
        # on the realistic shapes (quoted, unquoted, trailing comma, embedded
        # comma, single quotes, padded), with the trailing comma now stripped in
        # Python where the old pattern excluded it inside the regex.
        msg_match = re.search(r'"?msg"?\s*[:=]\s*(.*)', lines[j].strip())
        if msg_match:
            return msg_match.group(1).strip().strip(",").strip("'\"")
    return ""


# Lines that end a single task's output block. Scanning for ``...ignoring`` stops
# here so one task's ignored failure is never attributed to another's.
_RESULT_BOUNDARY = ("TASK [", "RUNNING HANDLER [", "fatal:", "ok:", "changed:", "skipping:", "PLAY")


def _failure_was_ignored(lines: list[str], index: int) -> bool:
    """True when ansible printed ``...ignoring`` for the ``fatal:`` at *index*.

    A task with ``ignore_errors: true`` still prints a full ``fatal:`` line and
    only then ``...ignoring``. Keying on ``fatal:`` alone therefore reports a task
    that succeeded by design.

    That is the normal first-provision path, not an edge case: both marker reads in
    ``roles/_shared/tasks/sync_deletions.yml`` are ``ignore_errors: true`` because a
    host with nothing deployed yet has no marker to read, so every first run emits
    two ignored failures. Counting them buries the one real failure among them.
    """
    # Scan to the next result boundary, not to a fixed line count. Under the
    # yaml callback one task result can run to hundreds of lines -- a numeric
    # cap would stop inside the result and report an ignored failure as a real
    # one, which is the bug this helper exists to prevent. The boundary list is
    # what bounds the scan; end-of-input bounds the last result.
    for j in range(index + 1, len(lines)):
        stripped = lines[j].strip()
        if not stripped:
            continue
        if stripped.startswith("...ignoring"):
            return True
        if stripped.startswith(_RESULT_BOUNDARY):
            return False
    return False


def _extract_failure_summary(output: str) -> str:
    """Parse Ansible stdout and return a human-readable failure summary.

    Extracts failed hosts, the task that failed, and the error message so
    users see e.g. '<host-ip> failed at "Common | Update apt cache":
    Failed to update apt cache: unknown reason' instead of 'exit code 2'.
    """
    lines = output.splitlines()
    failures: list[str] = []
    failed_hosts: list[str] = []
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

        if line.startswith("fatal:") and not _failure_was_ignored(lines, i):
            host_match = re.search(r"fatal: \[([^\]]+)\]", line)
            host = host_match.group(1) if host_match else "unknown host"
            failed_hosts.append(host)
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

    # Count hosts and failures separately. `failures` holds one entry per `fatal:`
    # line, so reporting its length as a host count made one host failing three
    # tasks read as "3 hosts failed" -- on a two-host run, more hosts than exist.
    host_count = len(dict.fromkeys(failed_hosts))
    failure_count = len(failures)
    if failure_count == host_count:
        noun = "host" if host_count == 1 else "hosts"
        headline = f"{host_count} {noun} failed"
    else:
        f_noun = "failure" if failure_count == 1 else "failures"
        h_noun = "host" if host_count == 1 else "hosts"
        headline = f"{failure_count} {f_noun} on {host_count} {h_noun}"
    return f"{headline} \u2014 " + "; ".join(failures)


def parse_unreachable_hosts(output: str) -> list[str]:
    """Hostnames ansible reported as UNREACHABLE, in order of appearance.

    Ansible distinguishes *unreachable* from *failed*, and the difference is
    the whole answer to "is this node down, or is the deploy broken?" — #14297
    needs it to tell a node that cannot be contacted from one that is merely
    unhealthy.

    Moved here from ``api/updates.py`` (#1816) so ``api/code_sync.py`` can use
    it without importing another api module.
    """
    pattern = re.compile(r"^fatal:\s+\[([^\]]+)\]:\s+UNREACHABLE!", re.MULTILINE)
    return list(dict.fromkeys(m.group(1) for m in pattern.finditer(output or "")))


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
