# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #17651: the call-graph scan is bounded by time and says what it covered.

The endpoint AST-parses every ``.py`` file under the scan root on every cache
miss -- 6,293 files in this repo -- and was unbounded by #13468's deliberate
decision to default ``AUTOBOT_CALL_GRAPH_MAX_FILES`` to unlimited. nginx's
tightest ``/api/`` ``proxy_read_timeout`` is 60s -- ``shared/docker/nginx/nginx.conf:121``
and ``autobot-frontend/templates/autobot-user.conf:79``, against 300s from
``shared/scripts/install-bare-metal.sh:562`` -- while the route is ``@bounded(120.0)``, so a scan
between those two returns **504 to the browser while the backend keeps working**
and the route's own truncation reporting never reaches the client.

WHY A DEADLINE AND NOT A RESTORED FILE CAP. #13468's objection was the silence,
not the cap -- *"nothing in the response says the result was truncated"*. A
deadline keeps that honesty, because ``files_scanned`` is what was actually read,
while bounding the work; a file count cannot, because the same count costs
different time on different trees.

WHY THESE ASSERT THE RETURNED COUNT. Before this change the caller used
``len(scanned_files)`` -- what the scan was *offered*. A test that only checked
``truncated`` would pass against a scan that stopped early and still claimed to
have read everything, which is the exact dishonesty #13468 exists to prevent.
"""

import time
from pathlib import Path

import pytest

import api.codebase_analytics.endpoints.call_graph as call_graph_mod
from api.codebase_analytics.endpoints.call_graph import _analyze_python_files

_SOURCE = "def alpha():\n    beta()\n\n\ndef beta():\n    pass\n"


def _broken_file(root: Path) -> Path:
    """Write an unparseable module. Sync, because `no-blocking-io-in-async`
    (#7444) rightly refuses `write_text` inside an `async def` body."""
    path = root / "broken.py"
    path.write_text("def (((\n", encoding="utf-8")
    return path


def _tree(root: Path, count: int) -> list[Path]:
    files = []
    for index in range(count):
        path = root / f"mod_{index}.py"
        path.write_text(_SOURCE, encoding="utf-8")
        files.append(path)
    return files


@pytest.mark.asyncio
async def test_an_expired_deadline_analyses_nothing_and_says_so(tmp_path):
    """The bound is checked BEFORE each read, so an already-passed deadline reads none."""
    files = _tree(tmp_path, 5)
    functions, edges = {}, []

    analysed = await _analyze_python_files(files, tmp_path, functions, edges, deadline=time.monotonic() - 1.0)

    assert analysed == 0
    assert functions == {}


@pytest.mark.asyncio
async def test_no_deadline_analyses_every_file(tmp_path):
    """The contrast case. Without it, 'stops at the deadline' is satisfied by a
    scan that never reads anything at all."""
    files = _tree(tmp_path, 5)
    functions, edges = {}, []

    analysed = await _analyze_python_files(files, tmp_path, functions, edges, deadline=None)

    assert analysed == 5
    assert len(functions) == 10  # two defs per file


@pytest.mark.asyncio
async def test_a_far_future_deadline_analyses_every_file(tmp_path):
    """A budget that is not reached must not truncate -- the common case in
    production, where the scan finishes well inside 30s."""
    files = _tree(tmp_path, 5)
    functions, edges = {}, []

    analysed = await _analyze_python_files(files, tmp_path, functions, edges, deadline=time.monotonic() + 3600.0)

    assert analysed == 5


@pytest.mark.asyncio
async def test_the_count_is_what_was_read_not_what_was_offered(tmp_path, monkeypatch):
    """The property the response's honesty rests on, proved with a CONTROLLED clock.

    ``files_scanned`` used to be ``len(scanned_files)``. If the deadline stops
    the scan, that number describes the offer and not the work -- so
    ``truncated`` would read False while most of the tree went unparsed.

    The clock is driven rather than raced. A real short budget -- say 1ms over
    40 tiny files -- collides only when the machine is slow enough, which is a
    flake that passes locally and fails in CI, or the reverse. Here
    the injected clock advances one second per call, so the budget is crossed
    after exactly three checks on every machine.
    """
    files = _tree(tmp_path, 40)
    functions, edges = {}, []

    # Driving `call_graph._now`, NOT `time.monotonic`: the latter is an
    # attribute of the shared `time` module, so asyncio's event loop reads the
    # same counter and eats the sequence. The first version of this test did
    # that and measured 1 file where it expected 3.
    ticks = iter(range(1000))
    monkeypatch.setattr(call_graph_mod, "_now", lambda: float(next(ticks)))

    analysed = await _analyze_python_files(files, tmp_path, functions, edges, deadline=3.0)

    # Checks at t=0,1,2 pass and read a file; the check at t=3 stops the loop.
    assert analysed == 3, f"expected exactly 3 files read before the budget, got {analysed}"
    assert analysed < len(files), "the scan read the whole tree despite the budget"


@pytest.mark.asyncio
async def test_an_unreadable_file_does_not_count_as_analysed(tmp_path):
    """A file that cannot be parsed is skipped and must not inflate the count,
    or `truncated` under-reports the gap."""
    good = _tree(tmp_path, 2)
    broken = _broken_file(tmp_path)
    functions, edges = {}, []

    analysed = await _analyze_python_files(good + [broken], tmp_path, functions, edges, deadline=None)

    assert analysed == 2, "the unparseable file was counted as analysed"
