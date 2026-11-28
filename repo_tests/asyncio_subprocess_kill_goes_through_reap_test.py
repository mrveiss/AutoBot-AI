# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A child that outstays its wait is stopped by `kill_and_reap`, never by a hand-rolled kill (#20924).

``asyncio.wait_for(process.communicate(), timeout=...)`` cancels the wait, not the child. A handler that
calls ``process.kill()`` and returns leaves a zombie, and one that skips the group leaves grandchildren.
`autobot_shared.subprocess_reap.kill_and_reap` is the one implementation (process group, SIGTERM-first
escalation and bounded wait are parameters of it). Hand-rolled shapes had drifted into 40-odd sites.

**What this detects:** every call ``<anything>.kill(...)``, ``.terminate(...)``, ``.send_signal(...)`` or
``.killpg(...)`` (so ``os.kill`` and ``os.killpg`` too) in non-test source of every in-scope file, whatever
the receiver is called: ``proc``, ``child``, ``procs[0]``, ``self._entry.handle``, a helper's ``p`` parameter.
Each hit is keyed by (file, enclosing function qualname, line text) and counted. A hit is either gone,
allow-listed with why it is not an asyncio timeout kill, or pending in a file an open PR owns. The listed
count is exact: a NEW identical call in an allow-listed function raises the count and fails.

**What it does not detect:** a signal sent through an alias (``k = proc.kill; k()``), ``from os import killpg``
and a call built with ``getattr``. Those shapes do not occur in the tree; the exact counts would not see one.

The population is derived twice, from the syntax tree and from the raw text, and compared as sets, so a
detector that silently stops seeing a site fails instead of reporting clean (RATCHET_BASELINES.md).
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared", "autobot-infrastructure", "autobot-npu-worker")
_TEST_FILE = re.compile(r"(^|/)(tests?/|[^/]*_test\.py$|conftest\.py$|test_[^/]*\.py$)")
_SIGNALLING = frozenset({"kill", "terminate", "send_signal", "killpg"})
_TEXT_CALL = re.compile(r"\.(?:kill|terminate|send_signal|killpg)\(")

Key = tuple[str, str, str]  # (file, enclosing function qualname, stripped line text)

#: Sites still hand-rolled in a file an open PR owns: (file, function, line, count). **Only shrinks.** They move onto
#: `kill_and_reap` when that PR lands (same file => one PR, CLAUDE_REVIEW.md#pr-granularity).
_PENDING_ROWS = (
    ("autobot-backend/api/knowledge_population.py", "_fetch_man_page", "proc.kill()", 1),  # open PR #22310
    ("autobot-infrastructure/shared/scripts/utilities/index_all_man_pages.py", "get_all_available_commands", "process.kill()", 1),
    ("autobot-infrastructure/shared/scripts/utilities/index_all_man_pages.py", "_get_man_page_description", "desc_process.kill()", 1),
    ("autobot-infrastructure/shared/scripts/utilities/index_all_man_pages.py", "_get_man_content", "process.kill()", 1),
)  # fmt: skip

_SYNC = "synchronous subprocess.Popen, not an asyncio child"
_DOCKER = "a docker container, not a subprocess"
_USER_SIGNAL = "delivers a signal the user or caller asked for, not a timeout kill"
_OWN_METHOD = "calls this class's own send_signal method; no process is signalled here"
_PTY = "subprocess.Popen on a PTY, not an asyncio child"
_AGG = "subprocess.Popen reader threads, not an asyncio child"
_CANON = "the canonical implementation itself"

#: Calls checked against their code and found not to be an asyncio timeout kill: (file, function, line, count, why).
#: The count is exact, so a new identical call in the same function is a new hit, not a covered one.
_ALLOWED_ROWS = (
    ("autobot-backend/agents/interactive_terminal_agent.py", "InteractiveTerminalAgent.handle_send_signal", "await self.send_signal(signal_type)", 1, _OWN_METHOD),
    ("autobot-backend/agents/interactive_terminal_agent.py", "InteractiveTerminalAgent.send_signal", "self.process.kill()", 1, _USER_SIGNAL),
    ("autobot-backend/agents/interactive_terminal_agent.py", "InteractiveTerminalAgent.send_signal", "self.process.send_signal(signal_num)", 1, _USER_SIGNAL),
    ("autobot-backend/agents/system_command_agent.py", "SystemCommandAgent.send_signal_to_session", "await terminal.send_signal(signal_type)", 1, _OWN_METHOD),
    ("autobot-backend/api/terminal.py", "send_terminal_signal", "success = await session_manager.send_signal(session_id, signal_map[signal_name])", 1, _USER_SIGNAL),
    ("autobot-backend/api/terminal_handlers.py", "TerminalWebSocket._send_signal_to_pty", "success = self.pty_process.send_signal(sig)", 1, _PTY),
    ("autobot-backend/api/terminal_handlers.py", "TerminalManager.send_signal", "success = terminal.pty_process.send_signal(sig)", 1, _PTY),
    ("autobot-backend/desktop_streaming_manager.py", "_terminate_process_safely", "process.terminate()", 1, _SYNC + " (the module also holds an asyncio child: it must not be added here)"),
    ("autobot-backend/desktop_streaming_manager.py", "_terminate_process_safely", "process.kill()", 1, _SYNC),
    ("autobot-backend/gui_controller.py", "GUIController.stop_virtual_display", "self.xvfb_process.terminate()", 1, _SYNC),
    ("autobot-backend/intelligence/streaming_executor.py", "StreamingCommandExecutor.kill_all_processes", "process_info.process.terminate()", 1, "synchronous shutdown sweep; no await available"),
    ("autobot-backend/llc/adapters/subprocess_support.py", "probe_pid", "os.kill(pid, 0)", 1, "signal 0 existence probe, nothing is sent"),
    ("autobot-backend/llc/adapters/subprocess_support.py", "terminate_pid", "os.kill(pid, 0)", 1, "signal 0 existence probe, nothing is sent"),
    ("autobot-backend/llc/adapters/subprocess_support.py", "_signal_target", "os.killpg(pgid, sig)", 1, "signals a detached adapter by recorded pid, not an awaited child"),
    ("autobot-backend/llc/adapters/subprocess_support.py", "_signal_target", "os.kill(pid, sig)", 1, "signals a detached adapter by recorded pid, not an awaited child"),
    ("autobot-backend/secure_sandbox_executor.py", "SecureSandboxExecutor._execute_container_with_timeout", "container.kill()", 1, _DOCKER),
    ("autobot-backend/services/autoresearch/runner.py", "ExperimentRunner.cancel", "self._current_process.kill()", 1, "user cancel(); the running experiment owns the reap"),
    ("autobot-backend/services/docker_task_workspace.py", "TaskWorkspaceManager._stop_container_sync", "container.kill()", 1, _DOCKER),
    ("autobot-backend/services/execution/docker_backend.py", "DockerBackend._execute_cold", "container.kill()", 1, _DOCKER),
    ("autobot-backend/services/execution/docker_backend.py", "DockerBackend.cleanup", "container.kill()", 1, _DOCKER),
    ("autobot-backend/services/execution/modal_backend.py", "ModalBackend._run_in_sandbox", "sandbox.terminate()", 1, "a remote sandbox handle, not a local subprocess"),
    ("autobot-backend/services/process_adapter_service.py", "ProcessAdapterService.signal_process", "proc.send_signal(sig_val)", 1, _USER_SIGNAL),
    ("autobot-backend/services/simple_pty.py", "SimplePTY.resize", "os.killpg(os.getpgid(self.process.pid), signal.SIGWINCH)", 1, "SIGWINCH window-size notice, not a stop"),
    ("autobot-backend/services/simple_pty.py", "SimplePTY.send_signal", "os.killpg(os.getpgid(self.process.pid), sig)", 1, _USER_SIGNAL),
    ("autobot-backend/services/simple_pty.py", "SimplePTY.cleanup", "self.process.terminate()", 1, _PTY),
    ("autobot-backend/services/simple_pty.py", "SimplePTY.cleanup", "self.process.kill()", 1, _PTY),
    ("autobot-backend/system_integration.py", "SystemIntegration.terminate_process", "process.terminate()", 1, "psutil.Process, not an asyncio child"),
    ("autobot-infrastructure/shared/scripts/comprehensive_log_aggregator.py", "ComprehensiveLogAggregator._monitor_journalctl", "proc.terminate()", 1, _AGG),
    ("autobot-infrastructure/shared/scripts/comprehensive_log_aggregator.py", "ComprehensiveLogAggregator.tail_log_file", "proc.terminate()", 1, _AGG),
    ("autobot-infrastructure/shared/scripts/comprehensive_log_aggregator.py", "ComprehensiveLogAggregator.stream_system_logs.monitor_system", "proc.terminate()", 1, _AGG),
    ("autobot-npu-worker/resources/windows-npu-worker/gui/controllers/worker_controller.py", "WorkerController.stop_worker", "self.worker_process.terminate()", 1, "subprocess.Popen in a Windows GUI thread"),
    ("autobot-npu-worker/resources/windows-npu-worker/gui/controllers/worker_controller.py", "WorkerController.stop_worker", "self.worker_process.kill()", 1, "subprocess.Popen in a Windows GUI thread"),
    ("autobot-npu-worker/resources/windows-npu-worker/gui/widgets/benchmark_widget.py", "BenchmarkWidget.stop_benchmark", "self._benchmark_worker.terminate()", 1, "a Qt worker thread, not a subprocess"),
    ("autobot_shared/process_group.py", "process_group_is_dead", "os.killpg(pgid, 0)", 1, "signal 0 existence probe, nothing is sent"),
    ("autobot_shared/process_group.py", "stop_process_group", "os.killpg(process.pid, sig)", 1, "the synchronous Popen group stop (#19496)"),
    ("autobot_shared/subprocess_reap.py", "_signal", "os.killpg(process.pid, sig)", 1, _CANON),
    ("autobot_shared/subprocess_reap.py", "_signal", "process.terminate() if sig == signal.SIGTERM else process.kill()", 2, _CANON),
)  # fmt: skip

_PENDING: dict[Key, int] = {(f, q, t): n for f, q, t, n in _PENDING_ROWS}
_ALLOWED: dict[Key, int] = {(f, q, t): n for f, q, t, n, _why in _ALLOWED_ROWS}

#: Lines where the text derivation finds the call and the tree does not, by design: a docstring quoting it.
#: Naming them keeps the comparison exact rather than a subset check.
_PROSE_ONLY: frozenset[tuple[str, str]] = frozenset(
    {
        ("autobot-backend/llc/adapters/subprocess_support.py", "Uses ``os.kill(pid, 0)`` (signal 0 — existence check, no delivery):"),
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


class _Walker(ast.NodeVisitor):
    """Collect (qualname, line) of every signalling call, tracking the enclosing def/class chain."""

    def __init__(self, lines: list[str]) -> None:
        self.lines, self.scope, self.found = lines, [], []

    def _enter(self, node) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _enter

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr in _SIGNALLING:
            self.found.append((".".join(self.scope) or "<module>", self.lines[node.lineno - 1].strip()))
        self.generic_visit(node)


def signalling_calls(source: str) -> list[tuple[str, str]]:
    """(function qualname, stripped line) of each ``.kill/.terminate/.send_signal/.killpg(...)`` call, any receiver."""
    try:
        tree = parse_cache.parse(source)
    except SyntaxError:
        return []
    walker = _Walker(source.splitlines())
    walker.visit(tree)
    return walker.found


def text_lines(source: str) -> list[str]:
    """The stripped lines a regex finds the call on, comments excluded; the independent second derivation."""
    return [ln.strip() for ln in source.splitlines() if _TEXT_CALL.search(ln) and not ln.lstrip().startswith("#")]


def _scan(root: Path, rels) -> tuple[Counter, set[tuple[str, str]], set[tuple[str, str]]]:
    by_ast: Counter = Counter()
    ast_lines: set[tuple[str, str]] = set()
    by_text: set[tuple[str, str]] = set()
    for rel in rels:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        for qual, line in signalling_calls(text):
            by_ast[(rel, qual, line)] += 1
            ast_lines.add((rel, line))
        by_text |= {(rel, ln) for ln in text_lines(text)}
    return by_ast, ast_lines, by_text


def _populations():
    examined = REACH.examined(_ROOT)
    populations = _scan(_ROOT, examined)
    REACH.completed(len(examined), _ROOT)
    return populations


def _listed() -> Counter:
    return Counter(_PENDING) + Counter(_ALLOWED)


def test_no_unlisted_signalling_call():
    """A hit not covered, or one more than the listed count, is a NEW call: migrate it or list it with why."""
    found, _, _ = _populations()
    listed = _listed()
    grown = {f"{k[0]}::{k[1]}: {k[2]}": (n, listed.get(k, 0)) for k, n in found.items() if n > listed.get(k, 0)}
    assert not grown, (
        f"signalling calls beyond the listed ones (found, listed): {grown}. A timed-out asyncio child is stopped "
        "with `await kill_and_reap(proc)` (autobot_shared.subprocess_reap): it waits for the exit, so no zombie "
        "is left, and takes process_group / terminate_first / bounded for the other shapes (#20924). A call that "
        "is not an asyncio timeout kill goes in _ALLOWED_ROWS with its reason."
    )


def test_the_listed_calls_are_exact():
    """A listed call that left its function (or lost one of its repeats) is a stale entry, not a spare allowance."""
    found, _, _ = _populations()
    stale = {f"{k[0]}::{k[1]}: {k[2]}": (found.get(k, 0), n) for k, n in _listed().items() if found.get(k, 0) < n}
    assert not stale, f"listed calls no longer found (found, listed): {stale}. Lower or delete the stale entries."


def test_pending_and_allowed_are_disjoint():
    assert not set(_PENDING) & set(_ALLOWED), "a call is either pending migration or excluded, not both"


def test_the_two_derivations_agree():
    """The text search and the syntax tree must name the same lines, or the detector has gone blind."""
    _, ast_lines, by_text = _populations()
    assert not ast_lines - by_text, f"tree-only: {sorted(ast_lines - by_text)}: the text derivation has gone blind"
    assert by_text - ast_lines == _PROSE_ONLY, (
        f"text-only now {sorted(by_text - ast_lines)}, recorded {sorted(_PROSE_ONLY)}. A new docstring hit belongs "
        "in _PROSE_ONLY; a recorded one that left means a call was missed or the prose changed."
    )


def test_the_detector_sees_a_hand_rolled_timeout_kill():
    """Control: the shape this guard exists for is found, and the helper call is not."""
    handler = "async def f(proc):\n    try:\n        await proc.communicate()\n    except TimeoutError:\n        proc.kill()\n"
    assert signalling_calls(handler) == [("f", "proc.kill()")]
    assert text_lines(handler) == ["proc.kill()"]
    assert signalling_calls("class C:\n    def m(self):\n        self._proc.terminate()\n") == [
        ("C.m", "self._proc.terminate()")
    ]
    assert signalling_calls("async def f(proc):\n    await kill_and_reap(proc)\n") == []
    assert signalling_calls("proc.kill(9)\n") == [("<module>", "proc.kill(9)")]


def test_the_detector_sees_a_differently_named_receiver():
    """Control: the receiver name does not matter, nor does a subscript, a helper parameter or os.kill."""
    source = (
        "async def _stop(p):\n    p.kill()\n"
        "def g(procs, pid):\n    procs[0].terminate()\n    child.send_signal(15)\n    os.killpg(pid, 9)\n    os.kill(pid, 9)\n"
    )
    assert [line for _, line in signalling_calls(source)] == [
        "p.kill()",
        "procs[0].terminate()",
        "child.send_signal(15)",
        "os.killpg(pid, 9)",
        "os.kill(pid, 9)",
    ]


def test_the_scan_reports_a_planted_site_and_counts_a_repeat(tmp_path):
    """Control for the scan itself: a planted handler is reported, and an identical second call is counted twice."""
    (tmp_path / "planted.py").write_text(
        "async def f(child):\n    child.kill()\n    if child.returncode is None:\n        child.kill()\n",
        encoding="utf-8",
    )
    found, ast_lines, by_text = _scan(tmp_path, ["planted.py"])
    assert found == Counter({("planted.py", "f", "child.kill()"): 2})
    assert ast_lines == by_text == {("planted.py", "child.kill()")}
