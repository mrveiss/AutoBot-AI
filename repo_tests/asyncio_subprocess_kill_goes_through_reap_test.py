# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A child that outstays its wait is stopped by `kill_and_reap`, never by a hand-rolled kill (#20924).

``asyncio.wait_for(process.communicate(), timeout=...)`` cancels the wait, not the child. A handler that
calls ``process.kill()`` and returns leaves a zombie, and one that skips the group leaves grandchildren.
`autobot_shared.subprocess_reap.kill_and_reap` is the one implementation (process group, SIGTERM-first
escalation and bounded wait are parameters of it). Hand-rolled shapes had drifted into 40-odd sites.

**What this detects:** a call ``<x>.kill()`` or ``<x>.terminate()`` with no arguments whose receiver's last
name contains ``proc`` or ``process`` (``proc``, ``self._proc``, ``entry.proc``, ``self.xvfb_process``) in
non-test source. Each one is either gone or listed with why it is not an asyncio timeout kill.

**What it does not detect:** a receiver named otherwise (``child.kill()``), a kill through ``os.kill``,
``send_signal`` or ``killpg``, and a Popen child. The second population below bounds the first miss: every
kill-shaped call on any receiver in a file that starts an asyncio subprocess must already be in the first.

The population is derived twice, from the syntax tree and from the raw text, and compared as sets, so a
detector that silently stops seeing a site fails instead of reporting clean (RATCHET_BASELINES.md).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared", "autobot-infrastructure", "autobot-npu-worker")
_TEST_FILE = re.compile(r"(^|/)(tests?/|[^/]*_test\.py$|conftest\.py$|test_[^/]*\.py$)")
_RECEIVER = re.compile(r"(?i)proc")  # matches proc, process, _proc, worker_process
_TEXT_CALL = re.compile(r"\b\w*(?i:proc)\w*\.(?:kill|terminate)\(\)")
_ANY_CALL = re.compile(r"\b[\w.]+\.(?:kill|terminate)\(\)")
_STARTS_ASYNC_CHILD = re.compile(r"create_subprocess_(?:exec|shell)")

#: Sites still hand-rolled in a file an open PR owns, with how many distinct call lines. **Only shrinks.** The sites move
#: onto `kill_and_reap` when that PR lands (same file => one PR, CLAUDE_REVIEW.md#pr-granularity).
_PENDING = {
    "autobot-backend/api/knowledge_population.py": 1,  # open PR #22310 edits this file
    "autobot-infrastructure/shared/scripts/utilities/index_all_man_pages.py": 2,  # open PR #22310
}

#: Calls checked against their code and found not to be an asyncio timeout kill: file -> (lines, why).
#: Keyed by the line text, not a count, so a removed call and a new one in one file are told apart.
_NOT_AN_ASYNCIO_TIMEOUT_KILL = {
    "autobot_shared/subprocess_reap.py": (("process.terminate() if sig == signal.SIGTERM else process.kill()",), "the canonical implementation itself"),
    "autobot-backend/agents/interactive_terminal_agent.py": (("self.process.kill()",), "the user's own `kill` signal request, not a timeout"),
    "autobot-backend/services/autoresearch/runner.py": (("self._current_process.kill()",), "user cancel(); the running experiment owns the reap"),
    "autobot-backend/intelligence/streaming_executor.py": (("process_info.process.terminate()",), "synchronous shutdown sweep; no await available"),
    "autobot-backend/desktop_streaming_manager.py": (("process.terminate()", "process.kill()"), "subprocess.Popen, not an asyncio child"),
    "autobot-backend/gui_controller.py": (("self.xvfb_process.terminate()",), "subprocess.Popen, not an asyncio child"),
    "autobot-backend/services/simple_pty.py": (("self.process.kill()", "self.process.terminate()"), "subprocess.Popen on a PTY"),
    "autobot-backend/system_integration.py": (("process.terminate()",), "psutil.Process, not an asyncio child"),
    "autobot-infrastructure/shared/scripts/comprehensive_log_aggregator.py": (("proc.terminate()",), "subprocess.Popen reader threads"),
    "autobot-npu-worker/resources/windows-npu-worker/gui/controllers/worker_controller.py": (
        ("self.worker_process.kill()", "self.worker_process.terminate()"),
        "subprocess.Popen in a Windows GUI thread",
    ),
}  # fmt: skip

#: Files whose only text hit is prose (a docstring quoting the call). The text derivation sees them and the
#: tree does not, by design; naming them keeps the comparison exact rather than a subset check.
_PROSE_ONLY = frozenset(
    {
        ("autobot-slm-backend/services/playbook_executor.py", "Review on #14524 (round 2): a lone ``proc.kill()`` only reaches"),
        ("autobot-slm-backend/services/playbook_executor.py", "than _run_git's original bare ``proc.kill()``: an orphan, not just a"),
    }
)  # fmt: skip


def _source_files(root: Path) -> list[str]:
    try:
        paths = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [p for p in paths if p.endswith(".py") and not _TEST_FILE.search(p)]


def _all_python(root: Path) -> int:
    try:
        return sum(1 for p in tracked_paths(root, *_ROOTS) if p.endswith(".py"))
    except EmptyEnumeration:
        return 0


REACH = declare(
    "asyncio-subprocess-kill-through-reap",
    discover=_source_files,
    reference=_all_python,
    min_fraction=0.3,
    what="non-test python source",
    roots=_ROOTS,
)


def _receiver_name(node: ast.expr) -> str:
    return node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")


def kill_lines(source: str) -> list[str]:
    """The stripped source line of each argument-less ``.kill()``/``.terminate()`` on a process-named receiver."""
    try:
        tree = parse_cache.parse(source)
    except SyntaxError:
        return []
    lines = source.splitlines()
    found: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr in ("kill", "terminate") and not node.args and not node.keywords:
            if _RECEIVER.search(_receiver_name(node.func.value)):
                found.append(lines[node.lineno - 1].strip())
    return found


def text_lines(source: str, call: re.Pattern = _TEXT_CALL) -> list[str]:
    """The stripped lines a regex finds the call on, comments excluded; the independent second derivation."""
    return [ln.strip() for ln in source.splitlines() if call.search(ln) and not ln.lstrip().startswith("#")]


def _scan(root: Path, rels) -> tuple[set[tuple[str, str]], set[tuple[str, str]], set[tuple[str, str]]]:
    by_ast: set[tuple[str, str]] = set()
    by_text: set[tuple[str, str]] = set()
    other_receivers: set[tuple[str, str]] = set()
    for rel in rels:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        by_ast |= {(rel, ln) for ln in kill_lines(text)}
        by_text |= {(rel, ln) for ln in text_lines(text)}
        if _STARTS_ASYNC_CHILD.search(text):
            other_receivers |= {(rel, ln) for ln in text_lines(text, _ANY_CALL)}
    return by_ast, by_text, other_receivers


def _populations():
    examined = REACH.examined(_ROOT)
    populations = _scan(_ROOT, examined)
    REACH.completed(len(examined), _ROOT)
    return populations


def _unexplained(by_ast: set[tuple[str, str]]) -> dict[str, int]:
    """Hand-rolled calls per file that no exclusion accounts for."""
    counts: dict[str, int] = {}
    for rel, line in by_ast:
        if line not in _NOT_AN_ASYNCIO_TIMEOUT_KILL.get(rel, ((), ""))[0]:
            counts[rel] = counts.get(rel, 0) + 1
    return counts


def test_no_hand_rolled_kill_of_an_asyncio_child():
    by_ast, _, _ = _populations()
    grown = {rel: n for rel, n in _unexplained(by_ast).items() if n > _PENDING.get(rel, 0)}
    assert not grown, (
        f"hand-rolled .kill()/.terminate() on a subprocess: {grown}. A timed-out child is stopped with "
        "`await kill_and_reap(proc)` (autobot_shared.subprocess_reap); it waits for the exit, so no zombie "
        "is left, and takes process_group / terminate_first / bounded for the other shapes (#20924)."
    )


def test_the_pending_list_only_shrinks():
    by_ast, _, _ = _populations()
    unexplained = _unexplained(by_ast)
    stale = {rel: (n, unexplained.get(rel, 0)) for rel, n in _PENDING.items() if unexplained.get(rel, 0) < n}
    assert not stale, f"migrated sites still listed (listed, found): {stale}. Lower or delete their _PENDING entries."
    assert not set(_NOT_AN_ASYNCIO_TIMEOUT_KILL) & set(_PENDING), "a file is either pending or excluded, not both"


def test_the_exclusions_are_exact():
    by_ast, _, _ = _populations()
    gone = {
        rel: [ln for ln in lines if (rel, ln) not in by_ast]
        for rel, (lines, _why) in _NOT_AN_ASYNCIO_TIMEOUT_KILL.items()
    }
    gone = {rel: lines for rel, lines in gone.items() if lines}
    assert not gone, f"excluded calls no longer in their files: {gone}. Delete the stale exclusion."


def test_the_two_derivations_agree():
    """The text search and the syntax tree must name the same calls, or the detector has gone blind."""
    by_ast, by_text, _ = _populations()
    assert not by_ast - by_text, f"tree-only: {sorted(by_ast - by_text)}: the text derivation has gone blind"
    assert by_text - by_ast == _PROSE_ONLY, (
        f"text-only now {sorted(by_text - by_ast)}, recorded {sorted(_PROSE_ONLY)}. A new docstring hit belongs "
        "in _PROSE_ONLY; a recorded one that left means a call was missed or the prose changed."
    )


def test_a_kill_on_any_receiver_in_an_asyncio_file_is_a_known_population_member():
    """Bound the receiver-name miss: `child.kill()` beside `create_subprocess_exec` cannot slip past unseen."""
    by_ast, _, other = _populations()
    unseen = other - by_ast - _PROSE_ONLY
    assert not unseen, f"kill-shaped calls on receivers the detector does not name: {sorted(unseen)}"


def test_the_detector_sees_a_hand_rolled_timeout_kill():
    """Control: the shape this guard exists for is found, and the helper call is not."""
    handler = "try:\n    await asyncio.wait_for(proc.communicate(), 1)\nexcept asyncio.TimeoutError:\n    proc.kill()\n    await proc.wait()\n"
    assert kill_lines(handler) == ["proc.kill()"]
    assert text_lines(handler) == ["proc.kill()"]
    assert kill_lines("self._proc.terminate()\n") == ["self._proc.terminate()"]
    assert kill_lines("await kill_and_reap(proc)\n") == []
    assert kill_lines("container.kill()\n") == []
    assert kill_lines("proc.kill(9)\n") == []


def test_the_scan_reports_a_planted_site(tmp_path):
    """Control for the scan itself, not discovery and parsing separately: a planted handler is reported."""
    (tmp_path / "planted.py").write_text(
        "async def f(proc):\n    try:\n        await proc.communicate()\n    except TimeoutError:\n        proc.kill()\n",
        encoding="utf-8",
    )
    by_ast, by_text, _ = _scan(tmp_path, ["planted.py"])
    assert by_ast == by_text == {("planted.py", "proc.kill()")}
    assert _unexplained(by_ast) == {"planted.py": 1}
