# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reading playbook output without losing the line that explains the failure.

Split out of playbook_executor.py, which is at its grandfathered size ceiling
and may not grow (#14236). It is also the right seam on its own: this is stream
decoding, and the executor is orchestration.
"""

from __future__ import annotations

import asyncio
import logging

from autobot_shared.env_utils import env_int_clamped

logger = logging.getLogger(__name__)

#: Read limit for one line of playbook output. asyncio's StreamReader defaults
#: to 64 KiB, and one ansible `fatal:` line carries the entire task result as
#: JSON -- for a `pip install` task that includes pip's whole stderr, which goes
#: past 64 KiB routinely. Env-backed rather than literal so an operator hitting
#: an even larger line can raise it without a deploy.
PIPE_LINE_LIMIT = env_int_clamped(
    "AUTOBOT_PLAYBOOK_PIPE_LINE_LIMIT",
    default=10 * 1024 * 1024,
    min_v=64 * 1024,
    max_v=128 * 1024 * 1024,
)

#: Appended to a line that had to be cut at the limit, so a truncated line is
#: never mistaken for a complete one by a reader or by the progress parser.
OVERLONG_LINE_MARKER = "  [... truncated at AUTOBOT_PLAYBOOK_PIPE_LINE_LIMIT ...]"


async def iter_pipe_lines(process: asyncio.subprocess.Process):
    """Yield decoded lines from a live child stdout pipe (Issue #880, #3033).

    A single ansible line can be enormous. A `fatal:` result embeds the whole
    task result as one JSON line, and when the task is `pip install` that
    includes pip's entire stderr. Past the read limit this used to raise
    `ValueError: Separator is found, but chunk is longer than limit`, nothing
    caught it, the generator died mid-run, and the operator saw that
    ValueError INSTEAD OF the pip failure that caused it.

    `readuntil`, not `readline`, and that is the whole trick. On overrun
    `readline` CLEARS THE BUFFER before re-raising as a bare ValueError --
    the oversized line is destroyed by the stdlib, so nothing downstream can
    recover it however carefully it catches. `readuntil` raises
    `LimitOverrunError` with the buffer intact and `consumed` pointing at how
    much is readable, so the head of the line survives.
    """
    stream = process.stdout
    if not stream:
        return
    while True:
        try:
            line = await stream.readuntil(b"\n")
        except asyncio.LimitOverrunError as exc:
            # Buffer intact: take the readable head, then discard the rest of
            # THIS line so the next iteration starts on a clean boundary.
            head = await stream.read(exc.consumed)
            await _discard_to_newline(stream)
            logger.error(
                "playbook output line exceeded the %d-byte read limit; kept the first %d bytes, "
                "discarded the remainder of that line. The run continues -- but if this line was "
                "a `fatal:` result, its tail held the failure detail.",
                PIPE_LINE_LIMIT,
                len(head),
            )
            if head:
                yield head.decode("utf-8", errors="replace").rstrip() + OVERLONG_LINE_MARKER
            continue
        except asyncio.IncompleteReadError as exc:
            # EOF without a trailing newline: the last line is still output.
            if exc.partial:
                yield exc.partial.decode("utf-8", errors="replace").rstrip()
            break
        if not line:
            break
        yield line.decode("utf-8", errors="replace").rstrip()


async def _discard_to_newline(stream: asyncio.StreamReader) -> None:
    """Consume the remainder of a line that was too long to read.

    Without this the next `readuntil` re-raises on the same unterminated
    tail and the reader spins instead of advancing.
    """
    while True:
        try:
            await stream.readuntil(b"\n")
            return
        except asyncio.LimitOverrunError as exc:
            await stream.read(exc.consumed)
        except asyncio.IncompleteReadError:
            return
