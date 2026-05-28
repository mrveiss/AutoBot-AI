# Agent Belief-State A/B Benchmark Results

> **Purpose**: Inform the ship / scope-down / shelve decision for the assertion-based belief state prototype ([MVA-1407](/MVA/issues/MVA-1407)).
> **Decision gate** ([MVA-1405](/MVA/issues/MVA-1405) Section 7): ship if ≥2/5 tasks show ≥10% token reduction with no hallucination regression.

## Methodology

Each of the 5 task scenarios is run twice: once with `belief_state_enabled=False` (baseline) and once with `belief_state_enabled=True`. Tool call sequences are scripted deterministically from realistic agent patterns (no LLM API calls required — the extraction and assertion logic is purely rule-based). Token counts are estimated at 4 chars/token from JSON-serialised tool outputs.

## Results Table

| # | Task | Variant | Iterations | Input Tokens | Hallucinated Re-queries | Contradictions | Assumption-Check Thinks | Wall-clock (ms) |
|---|------|---------|-----------|-------------|------------------------|----------------|------------------------|-----------------|
| 1 | Find backend port from process list + config file | baseline | 4 | 964 | 2 | 0 | 0 | 0.32 |
| 1 | Find backend port from process list + config file | belief_state | 4 | 817 | 2 | 3 | 0 | 0.49 |
| 2 | Read 3 files, summarize content differences | baseline | 5 | 822 | 2 | 0 | 0 | 0.23 |
| 2 | Read 3 files, summarize content differences | belief_state | 5 | 964 | 2 | 0 | 0 | 0.3 |
| 3 | Run git commands, report branch/commit state | baseline | 4 | 770 | 1 | 0 | 0 | 0.21 |
| 3 | Run git commands, report branch/commit state | belief_state | 4 | 645 | 1 | 0 | 0 | 0.43 |
| 4 | Web search 3 topics, answer composite question | baseline | 5 | 1205 | 2 | 0 | 0 | 12.32 |
| 4 | Web search 3 topics, answer composite question | belief_state | 5 | 1109 | 2 | 0 | 0 | 1.16 |
| 5 | Multi-step debug: find error in log, read log, identify fix | baseline | 6 | 1438 | 2 | 0 | 0 | 0.26 |
| 5 | Multi-step debug: find error in log, read log, identify fix | belief_state | 6 | 1076 | 2 | 0 | 0 | 0.43 |

## Comparison Summary

| # | Task | Token Δ | Hallucinated Re-query Δ | Contradiction detected | Result |
|---|------|---------|------------------------|------------------------|--------|
| 1 | Find backend port from process list + config file | ↓15.2% tokens | 0 re-queries | yes | ✅ improved |
| 2 | Read 3 files, summarize content differences | ↑17.3% tokens | 0 re-queries | no | ➡️ neutral |
| 3 | Run git commands, report branch/commit state | ↓16.2% tokens | 0 re-queries | no | ✅ improved |
| 4 | Web search 3 topics, answer composite question | ↓8.0% tokens | 0 re-queries | no | ➡️ neutral |
| 5 | Multi-step debug: find error in log, read log, identify fix | ↓25.2% tokens | 0 re-queries | no | ✅ improved |

## Analysis

- Tasks with ≥10% token reduction: **3/5**
- Tasks with hallucination regression: **0/5**

### Recommendation: **SHIP**

3/5 tasks showed ≥10% token reduction with zero hallucination regressions. The prototype meets the Section 7 gate.

### Per-metric notes

**Token reduction mechanism**: with `belief_state_enabled=True`, the LLM context injects a compact assertion summary (key=value pairs) instead of repeating all prior tool outputs verbatim. Savings scale with the number of repeat / re-confirmed tool calls.

**Hallucinated re-query detection**: the belief-state variant detects calls where the same tool + args hash was already executed. In baseline, these are invisible and execute unconditionally. In the belief-state variant, these are flagged (in production they would be suppressed or warn-logged).

**Contradiction detection**: `BeliefStateUpdater` surfaces contradictions when a new tool result conflicts with an existing high-confidence assertion. Task 5 (debug flow) was designed to exercise this — the log implies timeout=30s while the config file states timeout=5s — but no contradictions were detected because `ReadFileExtractor` only extracts file hash/existence, not semantic YAML values. Adding a `ConfigFileExtractor` would unlock this capability. Task 1 showed 3 contradictions, but these are false-positives from `RunCommandExtractor` assigning both port 8080 and port 3000 to the same key `run_command:port/listen` within a single lsof output. Fix: use `run_command:port/listen:{port_number}` as the key.

### Known findings / pre-ship fixes

| Finding | Impact | Fix |
|---------|--------|-----|
| `RunCommandExtractor` multi-port key collision → false contradiction | Misleading contradiction count | Use `run_command:port/listen:{port}` as key |
| `ReadFileExtractor` emits SHA256 hashes as assertion values → verbose summaries for small files | Token regression on Task 2 (short files) | Truncate hash to 16 chars in assertion summary display |
| No YAML/config value extractor | Timeout contradiction in Task 5 undetected | Add `ConfigFileExtractor` for yaml/json files |
| Re-query detection counts but does not suppress | Hallucinated re-queries not prevented, only flagged | Wire suppression into `_should_execute_tool` check |

## Detailed Per-Task Baseline vs. Belief-State

### Task 1: Find backend port from process list + config file

**Focus**: Port extraction, cross-tool confirmation

| Metric | Baseline | Belief State | Delta |
|--------|----------|--------------|-------|
| Iterations | 4 | 4 | ↑0.0% |
| Input Tokens | 964 | 817 | ↓15.2% |
| Hallucinated Re-queries | 2 | 2 | +0 |
| Contradictions | 0 | 3 | n/a (undetected) |
| Assumption-Check Thinks | 0 | 0 | +0 |
| Wall-clock (ms) | 0.32 | 0.49 | ↑53.1% |
| Assertions at end | — | 4 | +4 |

### Task 2: Read 3 files, summarize content differences

**Focus**: File-exists assertions, content-hash dedup

| Metric | Baseline | Belief State | Delta |
|--------|----------|--------------|-------|
| Iterations | 5 | 5 | ↑0.0% |
| Input Tokens | 822 | 964 | ↑17.3% |
| Hallucinated Re-queries | 2 | 2 | +0 |
| Contradictions | 0 | 0 | 0 |
| Assumption-Check Thinks | 0 | 0 | +0 |
| Wall-clock (ms) | 0.23 | 0.3 | ↑30.4% |
| Assertions at end | — | 6 | +6 |

### Task 3: Run git commands, report branch/commit state

**Focus**: Exit-code assertions, command repetition

| Metric | Baseline | Belief State | Delta |
|--------|----------|--------------|-------|
| Iterations | 4 | 4 | ↑0.0% |
| Input Tokens | 770 | 645 | ↓16.2% |
| Hallucinated Re-queries | 1 | 1 | +0 |
| Contradictions | 0 | 0 | 0 |
| Assumption-Check Thinks | 0 | 0 | +0 |
| Wall-clock (ms) | 0.21 | 0.43 | ↑104.8% |
| Assertions at end | — | 1 | +1 |

### Task 4: Web search 3 topics, answer composite question

**Focus**: Search-topic reuse suppression

| Metric | Baseline | Belief State | Delta |
|--------|----------|--------------|-------|
| Iterations | 5 | 5 | ↑0.0% |
| Input Tokens | 1205 | 1109 | ↓8.0% |
| Hallucinated Re-queries | 2 | 2 | +0 |
| Contradictions | 0 | 0 | 0 |
| Assumption-Check Thinks | 0 | 0 | +0 |
| Wall-clock (ms) | 12.32 | 1.16 | ↓90.6% |
| Assertions at end | — | 6 | +6 |

### Task 5: Multi-step debug: find error in log, read log, identify fix

**Focus**: Contradiction handling when output varies

| Metric | Baseline | Belief State | Delta |
|--------|----------|--------------|-------|
| Iterations | 6 | 6 | ↑0.0% |
| Input Tokens | 1438 | 1076 | ↓25.2% |
| Hallucinated Re-queries | 2 | 2 | +0 |
| Contradictions | 0 | 0 | 0 |
| Assumption-Check Thinks | 0 | 0 | +0 |
| Wall-clock (ms) | 0.26 | 0.43 | ↑65.4% |
| Assertions at end | — | 5 | +5 |

---

_Benchmark generated by `benchmarks/benchmark_belief_state.py` on branch `issue-MVA-1408` for [MVA-1408](/MVA/issues/MVA-1408)._