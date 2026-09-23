# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An ansible line too long to read must not replace the failure it carries.

Reported from a live provisioning run. The operator saw:

    backend : Install filtered backend requirements
    fatal: [...]: FAILED! => {"changed": false, "cmd": [".../pip3", "install", ...],
                              "msg": "\\n:stderr: ER
    Error: Separator is found, but chunk is longer than limit

Two failures stacked, and the second hid the first. `pip install` failed, and
ansible reported it the way it reports everything -- one `fatal:` line holding
the entire task result as JSON, pip's whole stderr inside it. That line was past
asyncio's default 64 KiB StreamReader limit, so `readline()` raised
`ValueError: Separator is found, but chunk is longer than limit`. Nothing caught
it. The reader died, and the ValueError stood in for the pip error it had just
swallowed -- the actual cause was never written down anywhere.

That is the failure mode this repository's measurement rule exists to forbid: a
reader that cannot read must say so, not substitute its own error for the
evidence it was carrying.

These tests drive the REAL `iter_pipe_lines` against a REAL StreamReader with a
small limit. A mocked stream cannot reproduce this: the bug lives in what the
stdlib raises when the buffer is exceeded, so the buffer has to be exceeded.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

_SLM_ROOT = Path(__file__).resolve().parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))


def _load_real_playbook_executor():
    spec = importlib.util.spec_from_file_location(
        "playbook_output_stream_under_test", _SLM_ROOT / "services" / "playbook_output_stream.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["playbook_executor_under_overlong_test"] = module
    spec.loader.exec_module(module)
    return module


stream_mod = _load_real_playbook_executor()


class _FakeProcess:
    """Just enough of asyncio.subprocess.Process for the line iterator."""

    def __init__(self, stdout: asyncio.StreamReader) -> None:
        self.stdout = stdout


async def _collect(lines: list[bytes], limit: int) -> list[str]:
    """Build the reader INSIDE the loop and drain it through the real iterator.

    `asyncio.StreamReader(...)` constructed outside a running loop calls
    `get_event_loop()`, which raises once a previous `asyncio.run()` has closed
    the loop -- so a reader built at call time passes alone and fails in a suite.
    """
    reader = asyncio.StreamReader(limit=limit)
    for line in lines:
        reader.feed_data(line)
    reader.feed_eof()
    return [line async for line in stream_mod.iter_pipe_lines(_FakeProcess(reader))]


def test_a_line_past_the_limit_does_not_kill_the_reader() -> None:
    """The reported bug: one huge line ended the whole run.

    The line after it is the one that matters -- ansible's recap, the next
    task, anything the operator still needed.
    """
    limit = 4096
    huge = b'fatal: [node]: FAILED! => {"msg": "' + b"E" * (limit * 3) + b'"}\n'
    out = asyncio.run(
        _collect([b"TASK [backend : Install filtered backend requirements]\n", huge, b"PLAY RECAP\n"], limit)
    )
    assert any(
        "PLAY RECAP" in line for line in out
    ), "the reader stopped at the over-long line; everything after it was lost"


def test_the_overlong_line_is_salvaged_not_dropped() -> None:
    """A line too big to read is still evidence.

    Dropping it silently would trade one wrong answer for another -- the run
    would survive and the failure would still be invisible.
    """
    limit = 4096
    huge = b'fatal: [node]: FAILED! => {"msg": "pip could not build wheel for ' + b"x" * (limit * 3) + b'"}\n'
    out = asyncio.run(_collect([huge, b"PLAY RECAP\n"], limit))
    salvaged = [line for line in out if "fatal:" in line]
    assert salvaged, "the over-long line was dropped entirely"
    assert "pip could not build wheel for" in salvaged[0], "the salvaged head lost the part that names the cause"


def test_a_truncated_line_says_it_was_truncated() -> None:
    """Never let a cut line read as a complete one."""
    limit = 4096
    out = asyncio.run(_collect([b"x" * (limit * 3) + b"\n"], limit))
    assert out and out[0].endswith(stream_mod.OVERLONG_LINE_MARKER)


def test_ordinary_lines_are_untouched() -> None:
    """A fix that mangles the normal path is not a fix."""
    out = asyncio.run(_collect([b"TASK [one]\n", b"ok: [node]\n", b"PLAY RECAP\n"], 4096))
    assert out == ["TASK [one]", "ok: [node]", "PLAY RECAP"]


def test_two_overlong_lines_in_a_row_both_survive() -> None:
    """The salvage must consume the rest of the line it gave up on.

    If it does not, the next readline() re-raises on the same unterminated
    tail and the reader spins instead of progressing.
    """
    limit = 4096
    huge = b"y" * (limit * 3) + b"\n"
    out = asyncio.run(_collect([huge, huge, b"PLAY RECAP\n"], limit))
    assert any("PLAY RECAP" in line for line in out), "the reader did not recover from two consecutive long lines"


def test_no_fragment_of_the_long_line_leaks_as_its_own_line() -> None:
    """The discard exists for this, and only a shape test catches it.

    Without it the unread tail surfaces as a separate yielded line -- an empty
    one here -- sitting between the truncated line and the next real one. It
    does not crash and it does not spin; it quietly feeds the progress parser a
    line ansible never emitted.
    """
    limit = 4096
    huge = b"fatal: BOOM " + b"x" * (limit * 3) + b"\n"
    out = asyncio.run(_collect([huge, b"PLAY RECAP\n"], limit))
    assert len(out) == 2, f"expected the truncated line and PLAY RECAP, got {len(out)}: {[o[:20] for o in out]}"
    assert out[1] == "PLAY RECAP"


def test_the_configured_limit_is_far_above_asyncios_default() -> None:
    """64 KiB is what broke; the point of the constant is to clear it by a lot."""
    assert stream_mod.PIPE_LINE_LIMIT >= 1024 * 1024
    assert stream_mod.PIPE_LINE_LIMIT > asyncio.streams._DEFAULT_LIMIT * 8


def test_the_subprocess_is_spawned_with_that_limit() -> None:
    """Raising the constant is useless if the spawn does not pass it.

    Read from the source rather than by spawning ansible: the constant and the
    spawn are two places, and this is the one that silently stays at 64 KiB.
    """
    src = (_SLM_ROOT / "services" / "playbook_executor.py").read_text(encoding="utf-8")
    spawn = src[src.index("asyncio.create_subprocess_exec(") :]
    spawn = spawn[: spawn.index(")\n")]
    assert "limit=PIPE_LINE_LIMIT" in spawn, "create_subprocess_exec does not pass the raised limit"


# ---------------------------------------------------------------------------
# The SECOND call site (#17317 review). api/infrastructure.py runs the same
# pip-heavy provisioning playbooks from POST /api/execute, and had the same
# unguarded `readline` against a default-limit pipe. Its failure mode was the
# worse of the two: the bare ValueError was swallowed by `_run_playbook`'s
# broad `except Exception`, so the operator was told "Internal server error"
# rather than shown the pip failure.
#
# Both halves are asserted, because either one alone leaves the bug live: a
# raised limit the spawn never passes, or a shared reader the spawn starves at
# 64 KiB.
# ---------------------------------------------------------------------------


def _infrastructure_source() -> str:
    return (_SLM_ROOT / "api" / "infrastructure.py").read_text(encoding="utf-8")


def test_the_execute_endpoint_spawn_also_carries_the_limit() -> None:
    """The endpoint's own subprocess must not stay at asyncio's 64 KiB default."""
    src = _infrastructure_source()
    spawn = src[src.index("asyncio.create_subprocess_exec(") :]
    spawn = spawn[: spawn.index(")\n")]
    assert "limit=PIPE_LINE_LIMIT" in spawn, (
        "api/infrastructure.py spawns ansible without the raised limit, so its " "reader still meets a 64 KiB pipe"
    )


def test_the_execute_endpoint_reads_through_the_shared_iterator() -> None:
    """No second hand-rolled reader: the defect was one call site's private loop.

    Asserted on the BEHAVIOUR (`readline` on the process pipe), not on the
    helper's name -- renaming `_stream_process_output` must not silently retire
    this check.
    """
    src = _infrastructure_source()
    assert "iter_pipe_lines" in src, "api/infrastructure.py does not use the shared reader"
    assert "process.stdout.readline()" not in src, (
        "api/infrastructure.py still reads the pipe with readline(), which CLEARS "
        "the buffer on overrun and destroys the line that explains the failure"
    )
