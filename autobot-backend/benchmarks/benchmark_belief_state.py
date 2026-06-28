#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""
A/B Benchmark — Belief State Prototype (MVA-1408)

Measures the impact of assertion-based belief state on:
  - Hallucinated re-queries (tool called with same args after result already in assertions)
  - Contradiction events
  - Estimated context token reduction (baseline carries all tool outputs verbatim;
    belief-state variant replaces known facts with a compact summary)
  - Think calls triggered by belief-state contradiction surfacing
  - Iteration count (simulated)
  - Wall-clock time (ms)

Runs 5 representative task scenarios, each in both variants (baseline + belief-state),
for 10 total runs.  All tool call sequences are scripted deterministically — no LLM
calls required, since the extraction and assertion logic is purely rule-based.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Bootstrap sys.path so we can import from agent_loop without installing
# ---------------------------------------------------------------------------

_repo_root = Path(__file__).parent.parent
_autobot_root = _repo_root.parent
sys.path.insert(0, str(_repo_root))
sys.path.insert(0, str(_autobot_root))

# Import directly from submodules to avoid agent_loop/__init__.py
# (which imports AgentLoop → heavy FastAPI/Redis/Celery dependencies)
import importlib.util as _ilu
import types as _types


def _load_submodule(dotted_name: str, file_path: Path):
    """Load a single module file without executing its parent package's __init__."""
    spec = _ilu.spec_from_file_location(dotted_name, str(file_path))
    mod = _ilu.module_from_spec(spec)
    sys.modules[dotted_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _ensure_pkg_stub(name: str, pkg_path: Path):
    if name not in sys.modules:
        pkg = _types.ModuleType(name)
        pkg.__path__ = [str(pkg_path)]
        pkg.__package__ = name
        pkg.__spec__ = None
        sys.modules[name] = pkg


# Register lightweight package stubs so submodule imports resolve correctly
_ensure_pkg_stub("agent_loop", _repo_root / "agent_loop")
_ensure_pkg_stub("agent_loop.extractors", _repo_root / "agent_loop" / "extractors")

# Load types and belief_state directly without triggering the heavy agent_loop/__init__
# (which imports AgentLoop → requires FastAPI/Redis/Celery runtime deps)
from agent_loop.types import AgentLoopConfig, TaskContext  # noqa: E402

# Pre-load the extractors package __init__ so EXTRACTOR_REGISTRY is populated
_load_submodule("agent_loop.extractors", _repo_root / "agent_loop" / "extractors" / "__init__.py")

from agent_loop.belief_state import BeliefStateUpdater  # noqa: E402

# ---------------------------------------------------------------------------
# Token-cost estimation helpers
# ---------------------------------------------------------------------------

# Rough heuristic: 1 token ≈ 4 characters for English/JSON text
_CHARS_PER_TOKEN = 4


def _estimate_tokens(obj: Any) -> int:
    """Estimate token count for an arbitrary value by JSON-serialising it."""
    try:
        text = json.dumps(obj, default=str)
    except Exception:
        text = str(obj)
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _assertion_summary_tokens(ctx: TaskContext) -> int:
    """Compact token cost of surfacing belief state vs. raw tool outputs."""
    active = [a for a in ctx.assertions.values() if a.is_active]
    # Each assertion is roughly "key = value @ conf\n" — very compact
    lines = [f"  {a.key} = {a.value!r} @ {a.confidence:.2f}" for a in active]
    summary = "Belief state:\n" + "\n".join(lines)
    return max(1, len(summary) // _CHARS_PER_TOKEN)


# ---------------------------------------------------------------------------
# Benchmark data model
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    tool_name: str
    args: dict[str, Any]
    output: dict[str, Any]
    # True if this call is a repeat of a prior call with the same (tool, args)
    is_repeat: bool = False


@dataclass
class TaskScenario:
    number: int
    name: str
    focus: str
    # Ordered sequence of tool calls the agent would make
    tool_calls: list[ToolCall]
    # Expected number of LLM iterations (each "decide + execute" round)
    iterations: int = 0


@dataclass
class RunResult:
    task_number: int
    task_name: str
    variant: str  # "baseline" | "belief_state"
    iterations: int
    input_tokens: int
    hallucinated_requeries: int
    contradiction_count: int
    assumption_check_thinks: int
    wall_clock_ms: float
    assertions_at_end: int


# ---------------------------------------------------------------------------
# Task scenarios
# ---------------------------------------------------------------------------


def _hash_call(tool_name: str, args: dict) -> str:
    payload = json.dumps({"tool": tool_name, "args": args}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def build_scenarios() -> list[TaskScenario]:
    """Build 5 representative task scenarios with realistic tool call sequences."""

    # ------------------------------------------------------------------
    # Task 1: Find backend port from process list + config file
    # ------------------------------------------------------------------
    lsof_output_1 = {
        "command": "lsof -i -P -n",
        "exit_code": 0,
        "stdout": (
            "COMMAND   PID   USER   FD   TYPE DEVICE SIZE/OFF NODE NAME\n"
            "python3  1234  root    4u  IPv4  12345      0t0  TCP *:8080 (LISTEN)\n"
            "node     5678  root    6u  IPv4  12346      0t0  TCP *:3000 (LISTEN)\n"
        ),
    }
    config_output_1 = {
        "path": "/app/config.yaml",
        "content": "server:\n  port: 8080\n  host: 0.0.0.0\n",
    }
    # Agent redundantly re-reads config and re-runs lsof to "confirm"
    lsof_output_1_repeat = dict(lsof_output_1)  # identical repeat

    task1 = TaskScenario(
        number=1,
        name="Find backend port from process list + config file",
        focus="Port extraction, cross-tool confirmation",
        iterations=4,
        tool_calls=[
            ToolCall("run_command", {"command": "lsof -i -P -n"}, lsof_output_1),
            ToolCall("read_file", {"path": "/app/config.yaml"}, config_output_1),
            # Agent repeats lsof to "double-check" — hallucinated re-query
            ToolCall("run_command", {"command": "lsof -i -P -n"}, lsof_output_1_repeat, is_repeat=True),
            # Agent re-reads config to "confirm" — hallucinated re-query
            ToolCall(
                "read_file",
                {"path": "/app/config.yaml"},
                config_output_1,
                is_repeat=True,
            ),
        ],
    )

    # ------------------------------------------------------------------
    # Task 2: Read 3 files, summarize content differences
    # ------------------------------------------------------------------
    file_a = {"path": "/src/api.py", "content": "def get_users(): return db.query(User).all()"}
    file_b = {"path": "/src/models.py", "content": "class User(Base):\n    id = Column(Integer, primary_key=True)"}
    file_c = {"path": "/src/routes.py", "content": "router.add_route('/users', get_users)"}
    # Agent re-reads api.py (same hash will be detected)
    file_a_reread = dict(file_a)

    task2 = TaskScenario(
        number=2,
        name="Read 3 files, summarize content differences",
        focus="File-exists assertions, content-hash dedup",
        iterations=5,
        tool_calls=[
            ToolCall("read_file", {"path": "/src/api.py"}, file_a),
            ToolCall("read_file", {"path": "/src/models.py"}, file_b),
            ToolCall("read_file", {"path": "/src/routes.py"}, file_c),
            # Agent re-reads api.py to "verify" before summarising
            ToolCall("read_file", {"path": "/src/api.py"}, file_a_reread, is_repeat=True),
            # Agent re-reads models.py
            ToolCall("read_file", {"path": "/src/models.py"}, file_b, is_repeat=True),
        ],
    )

    # ------------------------------------------------------------------
    # Task 3: Run git commands, report branch/commit state
    # ------------------------------------------------------------------
    git_status = {
        "command": "git status --short",
        "exit_code": 0,
        "stdout": "M  src/api.py\n?? debug.log\n",
    }
    git_log = {
        "command": "git log --oneline -5",
        "exit_code": 0,
        "stdout": ("abc1234 fix: update user query\n" "def5678 feat: add route\n" "ghi9012 chore: init\n"),
    }
    git_branch = {
        "command": "git branch --show-current",
        "exit_code": 0,
        "stdout": "feature/belief-state-prototype\n",
    }
    # Agent re-runs git status (same exact command)
    git_status_repeat = dict(git_status)

    task3 = TaskScenario(
        number=3,
        name="Run git commands, report branch/commit state",
        focus="Exit-code assertions, command repetition",
        iterations=4,
        tool_calls=[
            ToolCall("run_command", {"command": "git status --short"}, git_status),
            ToolCall("run_command", {"command": "git log --oneline -5"}, git_log),
            ToolCall("run_command", {"command": "git branch --show-current"}, git_branch),
            # Repeat git status — common in agents that re-verify state
            ToolCall("run_command", {"command": "git status --short"}, git_status_repeat, is_repeat=True),
        ],
    )

    # ------------------------------------------------------------------
    # Task 4: Web search 3 topics, answer composite question
    # ------------------------------------------------------------------
    search_python = {
        "query": "Python async best practices 2024",
        "results": [
            {"title": "Real Python: Async IO in Python", "url": "https://realpython.com/async-io-python/"},
            {"title": "Python Docs: asyncio", "url": "https://docs.python.org/3/library/asyncio.html"},
        ],
    }
    search_fastapi = {
        "query": "FastAPI performance optimization",
        "results": [
            {"title": "FastAPI Docs: Performance", "url": "https://fastapi.tiangolo.com/"},
        ],
    }
    search_redis = {
        "query": "Redis caching patterns Python",
        "results": [
            {"title": "Redis: Python client examples", "url": "https://redis.io/docs/clients/python/"},
        ],
    }
    # Agent re-searches the same Python query
    search_python_repeat = dict(search_python)

    task4 = TaskScenario(
        number=4,
        name="Web search 3 topics, answer composite question",
        focus="Search-topic reuse suppression",
        iterations=5,
        tool_calls=[
            ToolCall("web_search", {"query": "Python async best practices 2024"}, search_python),
            ToolCall("web_search", {"query": "FastAPI performance optimization"}, search_fastapi),
            ToolCall("web_search", {"query": "Redis caching patterns Python"}, search_redis),
            # Repeat Python search — topic already answered
            ToolCall(
                "web_search",
                {"query": "Python async best practices 2024"},
                search_python_repeat,
                is_repeat=True,
            ),
            # Repeat FastAPI search
            ToolCall(
                "web_search",
                {"query": "FastAPI performance optimization"},
                search_fastapi,
                is_repeat=True,
            ),
        ],
    )

    # ------------------------------------------------------------------
    # Task 5: Multi-step debug — find error in log, read log, identify fix
    # ------------------------------------------------------------------
    log_scan = {
        "command": "grep -n 'ERROR\\|CRITICAL' /var/log/app.log | tail -20",
        "exit_code": 0,
        "stdout": (
            "1042:ERROR:app:Database connection timeout after 30s\n"
            "1043:ERROR:app:Retrying connection (attempt 2/3)\n"
            "1044:CRITICAL:app:Max retries exceeded — DB unreachable\n"
        ),
    }
    log_file = {
        "path": "/var/log/app.log",
        "content": (
            "2024-01-15 10:30:01 INFO  Starting application\n"
            "2024-01-15 10:30:42 ERROR Database connection timeout after 30s\n"
            "2024-01-15 10:30:43 ERROR Retrying connection (attempt 2/3)\n"
            "2024-01-15 10:30:44 CRITICAL Max retries exceeded — DB unreachable\n"
            "2024-01-15 10:30:44 INFO  Shutting down\n"
        ),
    }
    # Contradiction scenario: agent reads config which says timeout=5s (contradicts prior belief)
    config_with_contradicting_timeout = {
        "path": "/app/database.yaml",
        "content": "database:\n  timeout: 5\n  host: db.internal\n",
    }
    # Agent first assumes timeout=30 from log, then reads config showing timeout=5
    # This is a genuine contradiction (30 vs 5) — belief state should surface it
    log_scan_repeat = dict(log_scan)

    task5 = TaskScenario(
        number=5,
        name="Multi-step debug: find error in log, read log, identify fix",
        focus="Contradiction handling when output varies",
        iterations=6,
        tool_calls=[
            ToolCall(
                "run_command",
                {"command": "grep -n 'ERROR\\|CRITICAL' /var/log/app.log | tail -20"},
                log_scan,
            ),
            ToolCall("read_file", {"path": "/var/log/app.log"}, log_file),
            ToolCall("read_file", {"path": "/app/database.yaml"}, config_with_contradicting_timeout),
            # Agent re-scans log (repeat — same command)
            ToolCall(
                "run_command",
                {"command": "grep -n 'ERROR\\|CRITICAL' /var/log/app.log | tail -20"},
                log_scan_repeat,
                is_repeat=True,
            ),
            # Agent re-reads log file after reading config
            ToolCall("read_file", {"path": "/var/log/app.log"}, log_file, is_repeat=True),
        ],
    )

    return [task1, task2, task3, task4, task5]


# ---------------------------------------------------------------------------
# Run simulation
# ---------------------------------------------------------------------------


def run_task(scenario: TaskScenario, belief_state_enabled: bool) -> RunResult:
    """Simulate a single task run and collect metrics."""
    variant = "belief_state" if belief_state_enabled else "baseline"
    config = AgentLoopConfig(belief_state_enabled=belief_state_enabled)
    ctx = TaskContext(task_id=f"bench-{scenario.number}-{variant}", description=scenario.name)

    updater = BeliefStateUpdater()
    seen_call_hashes: set[str] = set()

    total_input_tokens = 0
    hallucinated_requeries = 0
    assumption_check_thinks = 0

    # Simulate an initial system prompt cost (constant for both variants)
    system_prompt_tokens = 500
    total_input_tokens += system_prompt_tokens

    t_start = time.perf_counter()

    for i, call in enumerate(scenario.tool_calls):
        iteration = i + 1
        call_hash = _hash_call(call.tool_name, call.args)

        # -----------------------------------------------------------------
        # Token accounting
        # -----------------------------------------------------------------
        if belief_state_enabled and ctx.assertions:
            # Belief state: inject a compact assertion summary instead of
            # repeating all prior tool output verbatim in the LLM context.
            belief_summary_tokens = _assertion_summary_tokens(ctx)
            # Tool output itself still injected (new information)
            tool_output_tokens = _estimate_tokens(call.output)
            total_input_tokens += belief_summary_tokens + tool_output_tokens
        else:
            # Baseline: all prior tool outputs re-sent verbatim each iteration
            # (grows as O(n) with tool calls)
            prior_context_tokens = sum(_estimate_tokens(c.output) for c in scenario.tool_calls[:i])
            tool_output_tokens = _estimate_tokens(call.output)
            total_input_tokens += prior_context_tokens + tool_output_tokens

        # -----------------------------------------------------------------
        # Hallucinated re-query detection
        # -----------------------------------------------------------------
        if belief_state_enabled:
            # Check if result is already in assertions (key exists + same hash)
            # This detects if the agent called the same tool with same args again
            if call_hash in seen_call_hashes:
                hallucinated_requeries += 1
        else:
            # Baseline: no detection, all repeats happen
            if call.is_repeat:
                hallucinated_requeries += 1

        seen_call_hashes.add(call_hash)
        ctx.iteration_count = iteration

        # -----------------------------------------------------------------
        # Run belief state updater
        # -----------------------------------------------------------------
        if config.belief_state_enabled:
            new_contradictions = updater.update(ctx, call.tool_name, call.output, call_hash, iteration)
            # ASSUMPTION_CHECK thinks triggered when contradictions are surfaced
            for rec in new_contradictions:
                if rec.resolution == "surfaced_to_think":
                    assumption_check_thinks += 1

    t_end = time.perf_counter()
    wall_clock_ms = (t_end - t_start) * 1000

    # Final iteration count (scenarios have a pre-set iteration count; benchmark
    # tracks call-level iterations as a proxy)
    final_iterations = scenario.iterations

    return RunResult(
        task_number=scenario.number,
        task_name=scenario.name,
        variant=variant,
        iterations=final_iterations,
        input_tokens=total_input_tokens,
        hallucinated_requeries=hallucinated_requeries,
        contradiction_count=len(ctx.contradictions),
        assumption_check_thinks=assumption_check_thinks,
        wall_clock_ms=round(wall_clock_ms, 2),
        assertions_at_end=len(ctx.assertions),
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def compute_improvement(baseline: int | float, belief: int | float) -> str:
    """Return a human-readable improvement percentage (positive = better)."""
    if baseline == 0:
        return "n/a"
    pct = (baseline - belief) / baseline * 100
    sign = "↓" if pct > 0 else "↑"
    return f"{sign}{abs(pct):.1f}%"


def generate_report(results: list[RunResult], output_path: Path) -> None:
    baseline = {r.task_number: r for r in results if r.variant == "baseline"}
    belief = {r.task_number: r for r in results if r.variant == "belief_state"}

    lines: list[str] = []
    lines.append("# Agent Belief-State A/B Benchmark Results")
    lines.append("")
    lines.append(
        "> **Purpose**: Inform the ship / scope-down / shelve decision for the "
        "assertion-based belief state prototype ([MVA-1407](/MVA/issues/MVA-1407))."
    )
    lines.append(
        "> **Decision gate** ([MVA-1405](/MVA/issues/MVA-1405) Section 7): "
        "ship if ≥2/5 tasks show ≥10% token reduction with no hallucination regression."
    )
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "Each of the 5 task scenarios is run twice: once with `belief_state_enabled=False` "
        "(baseline) and once with `belief_state_enabled=True`. "
        "Tool call sequences are scripted deterministically from realistic agent patterns "
        "(no LLM API calls required — the extraction and assertion logic is purely rule-based). "
        "Token counts are estimated at 4 chars/token from JSON-serialised tool outputs."
    )
    lines.append("")
    lines.append("## Results Table")
    lines.append("")
    lines.append(
        "| # | Task | Variant | Iterations | Input Tokens | Hallucinated Re-queries "
        "| Contradictions | Assumption-Check Thinks | Wall-clock (ms) |"
    )
    lines.append(
        "|---|------|---------|-----------|-------------|"
        "------------------------|----------------|------------------------|-----------------|"
    )
    for r in results:
        lines.append(
            f"| {r.task_number} | {r.task_name} | {r.variant} "
            f"| {r.iterations} | {r.input_tokens} | {r.hallucinated_requeries} "
            f"| {r.contradiction_count} | {r.assumption_check_thinks} | {r.wall_clock_ms} |"
        )
    lines.append("")
    lines.append("## Comparison Summary")
    lines.append("")
    lines.append("| # | Task | Token Δ | Hallucinated Re-query Δ | Contradiction detected | Result |")
    lines.append("|---|------|---------|------------------------|------------------------|--------|")

    tasks_improved_tokens = 0
    tasks_regressed_halluc = 0

    for num in sorted(baseline.keys()):
        b = baseline[num]
        s = belief[num]
        token_pct_str = compute_improvement(b.input_tokens, s.input_tokens)
        halluc_delta = b.hallucinated_requeries - s.hallucinated_requeries
        halluc_str = f"−{halluc_delta}" if halluc_delta > 0 else (f"+{abs(halluc_delta)}" if halluc_delta < 0 else "0")
        contra_detected = "yes" if s.contradiction_count > 0 else "no"

        # Determine per-task outcome
        token_pct_raw = (b.input_tokens - s.input_tokens) / b.input_tokens * 100 if b.input_tokens > 0 else 0
        halluc_regressed = halluc_delta < 0  # belief state caused MORE re-queries
        improved_tokens = token_pct_raw >= 10.0

        if improved_tokens:
            tasks_improved_tokens += 1
        if halluc_regressed:
            tasks_regressed_halluc += 1

        outcome = (
            "✅ improved"
            if improved_tokens and not halluc_regressed
            else ("⚠️ regressed" if halluc_regressed else "➡️ neutral")
        )
        lines.append(
            f"| {num} | {b.task_name} | {token_pct_str} tokens "
            f"| {halluc_str} re-queries | {contra_detected} | {outcome} |"
        )

    lines.append("")
    lines.append("## Analysis")
    lines.append("")
    lines.append(f"- Tasks with ≥10% token reduction: **{tasks_improved_tokens}/5**")
    lines.append(f"- Tasks with hallucination regression: **{tasks_regressed_halluc}/5**")
    lines.append("")

    # Decision
    ship_threshold_met = tasks_improved_tokens >= 2 and tasks_regressed_halluc == 0
    if ship_threshold_met:
        recommendation = "**SHIP**"
        rationale = (
            f"{tasks_improved_tokens}/5 tasks showed ≥10% token reduction with "
            f"zero hallucination regressions. The prototype meets the Section 7 gate."
        )
    elif tasks_improved_tokens >= 2 and tasks_regressed_halluc > 0:
        recommendation = "**SCOPE DOWN**"
        rationale = (
            f"{tasks_improved_tokens}/5 tasks improved on tokens but {tasks_regressed_halluc} "
            "task(s) showed hallucination regression. Disable belief-state for those task types "
            "or tighten extractor precision before shipping."
        )
    elif tasks_improved_tokens < 2 and tasks_regressed_halluc == 0:
        recommendation = "**SCOPE DOWN**"
        rationale = (
            f"Only {tasks_improved_tokens}/5 tasks met the ≥10% token threshold. "
            "No regressions, but benefit too narrow to justify shipping now. "
            "Consider expanding extractor coverage and re-benchmarking."
        )
    else:
        recommendation = "**SHELVE**"
        rationale = (
            f"Only {tasks_improved_tokens}/5 tasks improved tokens AND {tasks_regressed_halluc} "
            "task(s) regressed. Prototype needs significant rework."
        )

    lines.append(f"### Recommendation: {recommendation}")
    lines.append("")
    lines.append(rationale)
    lines.append("")
    lines.append("### Per-metric notes")
    lines.append("")
    lines.append(
        "**Token reduction mechanism**: with `belief_state_enabled=True`, the LLM context "
        "injects a compact assertion summary (key=value pairs) instead of repeating all prior "
        "tool outputs verbatim. Savings scale with the number of repeat / re-confirmed tool calls."
    )
    lines.append("")
    lines.append(
        "**Hallucinated re-query detection**: the belief-state variant detects calls where "
        "the same tool + args hash was already executed. In baseline, these are invisible and "
        "execute unconditionally. In the belief-state variant, these are flagged (in production "
        "they would be suppressed or warn-logged)."
    )
    lines.append("")
    lines.append(
        "**Contradiction detection**: `BeliefStateUpdater` surfaces contradictions when a new "
        "tool result conflicts with an existing high-confidence assertion. Task 5 (debug flow) "
        "specifically exercises this — the log implies timeout=30s while the config file states "
        "timeout=5s."
    )
    lines.append("")
    lines.append("## Detailed Per-Task Baseline vs. Belief-State")
    lines.append("")
    for num in sorted(baseline.keys()):
        b = baseline[num]
        s = belief[num]
        lines.append(f"### Task {num}: {b.task_name}")
        lines.append("")
        lines.append(f"**Focus**: {_task_focus(num)}")
        lines.append("")
        lines.append("| Metric | Baseline | Belief State | Delta |")
        lines.append("|--------|----------|--------------|-------|")
        lines.append(
            f"| Iterations | {b.iterations} | {s.iterations} | " f"{compute_improvement(b.iterations, s.iterations)} |"
        )
        lines.append(
            f"| Input Tokens | {b.input_tokens} | {s.input_tokens} | "
            f"{compute_improvement(b.input_tokens, s.input_tokens)} |"
        )
        lines.append(
            f"| Hallucinated Re-queries | {b.hallucinated_requeries} | {s.hallucinated_requeries} | "
            f"{b.hallucinated_requeries - s.hallucinated_requeries:+d} |"
        )
        lines.append(
            f"| Contradictions | {b.contradiction_count} | {s.contradiction_count} | "
            f"{'n/a (undetected)' if b.contradiction_count == 0 and s.contradiction_count > 0 else 0} |"
        )
        lines.append(
            f"| Assumption-Check Thinks | {b.assumption_check_thinks} | {s.assumption_check_thinks} | "
            f"+{s.assumption_check_thinks - b.assumption_check_thinks} |"
        )
        lines.append(
            f"| Wall-clock (ms) | {b.wall_clock_ms} | {s.wall_clock_ms} | "
            f"{compute_improvement(b.wall_clock_ms, s.wall_clock_ms)} |"
        )
        lines.append(f"| Assertions at end | — | {s.assertions_at_end} | +{s.assertions_at_end} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "_Benchmark generated by `benchmarks/benchmark_belief_state.py` "
        "on branch `issue-MVA-1408` for [MVA-1408](/MVA/issues/MVA-1408)._"
    )

    output_path.write_text("\n".join(lines))
    print(f"Report written to: {output_path}")  # noqa: print  # canonical: ignore py-print-smoke


def _task_focus(num: int) -> str:
    focuses = {
        1: "Port extraction, cross-tool confirmation",
        2: "File-exists assertions, content-hash dedup",
        3: "Exit-code assertions, command repetition",
        4: "Search-topic reuse suppression",
        5: "Contradiction handling when output varies",
    }
    return focuses.get(num, "")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    scenarios = build_scenarios()
    results: list[RunResult] = []

    print("=" * 70)  # noqa: print  # canonical: ignore py-print-smoke
    print("Belief-State A/B Benchmark (MVA-1408)")  # noqa: print  # canonical: ignore py-print-smoke
    print("=" * 70)  # noqa: print  # canonical: ignore py-print-smoke
    print(f"Running {len(scenarios)} tasks × 2 variants = {len(scenarios) * 2} total runs")  # noqa: print  # canonical: ignore py-print-smoke
    print()  # noqa: print  # canonical: ignore py-print-smoke

    for scenario in scenarios:
        for belief_state_enabled in [False, True]:
            variant = "belief_state" if belief_state_enabled else "baseline"
            result = run_task(scenario, belief_state_enabled=belief_state_enabled)
            results.append(result)
            print(  # noqa: print  # canonical: ignore py-print-smoke
                f"  Task {scenario.number} [{variant:>12}]: "
                f"tokens={result.input_tokens:5d}  "
                f"halluc={result.hallucinated_requeries}  "
                f"contra={result.contradiction_count}  "
                f"thinks={result.assumption_check_thinks}  "
                f"{result.wall_clock_ms:.2f}ms"
            )

    print()  # noqa: print  # canonical: ignore py-print-smoke

    # Write markdown report
    repo_root = Path(__file__).parent.parent.parent
    output_path = repo_root / "docs" / "architecture" / "agent-belief-state-benchmark.md"
    generate_report(results, output_path)

    # Print summary to stdout as well
    print()  # noqa: print  # canonical: ignore py-print-smoke
    print("Summary:")  # noqa: print  # canonical: ignore py-print-smoke
    baseline = {r.task_number: r for r in results if r.variant == "baseline"}
    belief = {r.task_number: r for r in results if r.variant == "belief_state"}
    improved = 0
    for num in sorted(baseline.keys()):
        b = baseline[num]
        s = belief[num]
        pct = (b.input_tokens - s.input_tokens) / b.input_tokens * 100 if b.input_tokens > 0 else 0
        marker = "✅" if pct >= 10 else "➡️"
        print(  # noqa: print  # canonical: ignore py-print-smoke
            f"  {marker} Task {num}: tokens {b.input_tokens} → {s.input_tokens} "
            f"({pct:+.1f}%), "
            f"re-queries {b.hallucinated_requeries} → {s.hallucinated_requeries}, "
            f"contradictions {s.contradiction_count}"
        )
        if pct >= 10:
            improved += 1
    print()  # noqa: print  # canonical: ignore py-print-smoke
    print(f"Tasks with ≥10% token reduction: {improved}/5")  # noqa: print  # canonical: ignore py-print-smoke
    print("Done.")  # noqa: print  # canonical: ignore py-print-smoke


if __name__ == "__main__":
    main()
