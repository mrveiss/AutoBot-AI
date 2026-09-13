# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Journal Fetch

Bounded journalctl-over-SSH retrieval of one service's logs from a fleet node,
and the vocabulary a caller needs to tell its three outcomes apart: logs, a
remote failure, and a fetch cut short by its own ceiling.

Split out of ``api/services.py`` (#15620). That module is a router at its
grandfathered file-size ceiling (#14236), and the ratchet forbids raising one,
so this seam becomes a module rather than more lines there. The seam is a real
one either way: everything here answers a single question -- how long the fetch
may take and what the caller is told when it does not finish -- while what
stays behind is the route that maps the answer onto HTTP.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from autobot_shared.env_utils import env_float_clamped

# Stdlib logging, matching every sibling in this package and the module this
# code came from. The SLM backend's conftest stubs `services.*` wholesale, and
# the logging factory is not on the list of modules it loads for real.
logger = logging.getLogger(__name__)

# Module-level constant backed by an env var, never a literal (CLAUDE.md).
# Registered in autobot_shared/env_registry_slm.py, which records what raising
# or lowering it costs (#15620).
JOURNAL_SSH_TIMEOUT_SECONDS = env_float_clamped("AUTOBOT_SLM_JOURNAL_SSH_TIMEOUT_SECONDS", 30.0, 5.0, 600.0)


class JournalFetchTimeout(RuntimeError):
    """The journal fetch was cut short by its own ceiling (#15620).

    A distinct type, not a ``(False, "...")`` tuple, because the string slot of
    that tuple is the same slot the logs themselves travel in: a fetch that
    timed out and a unit that genuinely logged nothing both reached the caller
    as "no text to show", and an operator reads the second explanation for the
    first. Raising instead forces the route to answer differently -- 504, with
    the ceiling named -- so "incomplete" can never render as "empty".
    """


def build_journal_command(service_name: str, lines: int, since: str | None = None) -> str:
    """Build the remote journalctl command (``sudo -n`` for non-interactive)."""
    journal_cmd = f"sudo -n journalctl -u {service_name} -n {lines} --no-pager"
    if since:
        journal_cmd += f" --since='{since}'"
    return journal_cmd


async def fetch_service_journal(ssh_cmd: list[str], service_name: str) -> tuple[bool, str]:
    """Run *ssh_cmd* under the journal-fetch ceiling.

    Returns ``(success, logs_or_error)``. Raises :class:`JournalFetchTimeout`
    when the fetch ran out of time -- never a bare empty-looking success, which
    is what a unit with no journal entries legitimately returns (#15620).
    """
    try:
        process = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=JOURNAL_SSH_TIMEOUT_SECONDS,
        )

        if process.returncode == 0:
            return True, stdout.decode("utf-8", errors="replace")
        error = stderr.decode("utf-8", errors="replace")
        return False, f"Failed to fetch logs: {error[:200]}"

    except asyncio.TimeoutError as exc:
        # wait_for cancels communicate() but leaves the ssh child running, so a
        # slow node would accumulate one orphan per attempt. ProcessLookupError
        # means it exited between the cancellation and here -- the outcome kill
        # was asking for, not an error to report.
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        raise JournalFetchTimeout(
            f"Journal fetch for '{service_name}' did not complete within "
            f"{JOURNAL_SSH_TIMEOUT_SECONDS:g}s. Any logs it had read are incomplete, "
            "not absent -- raise AUTOBOT_SLM_JOURNAL_SSH_TIMEOUT_SECONDS or ask for fewer lines."
        ) from exc
    except Exception as e:
        logger.exception("Get logs error: %s", e)
        return False, "Failed to fetch logs"
