# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Offset-to-line lookup must be O(1), not a per-match rescan (#12866).

Scanners resolved each match's line with `content[:start].count("\\n") + 1`,
which slices the file from the start for every match — O(n*m), and both the
slice and str.count run in C, so it holds the GIL with no yield point. That is
the shape of the 12s event-loop stalls reported in #12866; a ThreadPoolExecutor
does not help, because the work never releases the GIL.
"""

import re
import time

import pytest

def _load_line_index():
    """Load by path: the suite stubs the code_intelligence package, whose
    __init__ pulls in autobot_shared and fails under the test harness."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "_line_index_12866",
        Path(__file__).parent.parent / "code_intelligence" / "shared" / "line_index.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.LineIndex


LineIndex = _load_line_index()


@pytest.mark.parametrize(
    "content",
    ["", "a", "a\n", "\n", "a\nb\nc", "x\n\ny\n", "no newline at all", "\n\n\n"],
)
def test_matches_the_original_computation_at_every_offset(content):
    """The replacement must be exactly equivalent, including the edge shapes."""
    idx = LineIndex(content)

    for offset in range(len(content) + 1):
        expected = content[:offset].count("\n") + 1
        assert idx.line_of(offset) == expected, f"offset {offset} of {content!r}"


def test_first_line_is_one():
    assert LineIndex("anything").line_of(0) == 1


def test_offset_after_a_newline_is_the_next_line():
    content = "first\nsecond\n"
    idx = LineIndex(content)

    assert idx.line_of(content.index("second")) == 2


def test_scales_linearly_not_quadratically():
    """The point of the change: cost must not explode with match count."""
    pattern = r'execute\s*\(\s*f["\']'
    small = 'cursor.execute(f"SELECT 1")\n' * 2000
    large = 'cursor.execute(f"SELECT 1")\n' * 8000

    def timed(content):
        matches = list(re.finditer(pattern, content))
        idx = LineIndex(content)
        t0 = time.perf_counter()
        for m in matches:
            idx.line_of(m.start())
        return time.perf_counter() - t0, len(matches)

    t_small, n_small = timed(small)
    t_large, n_large = timed(large)

    assert n_large == 4 * n_small
    # Quadratic would be ~16x. Allow generous headroom for a noisy CI box while
    # still failing loudly if the per-match rescan ever comes back.
    assert t_large < max(t_small * 8, 0.05), f"{n_small}->{n_large} matches took {t_small:.4f}s->{t_large:.4f}s"


def test_the_old_idiom_is_gone_from_the_traced_analyzer():
    """py-spy caught _check_sql_injection mid-stall; it must not regress."""
    from pathlib import Path

    src = (Path(__file__).parent.parent / "code_intelligence" / "security" / "analyzer.py").read_text(encoding="utf-8")

    assert 'content[: match.start()].count' not in src
    assert src.count("LineIndex(content)") == 4, "every checker in this file must build the index once"
