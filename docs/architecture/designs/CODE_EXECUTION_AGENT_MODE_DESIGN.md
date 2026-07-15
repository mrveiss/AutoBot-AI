# Code-Execution Agent Mode — Design (Issue #11523)

**Status:** Draft — awaiting owner approval of the governance section (gate for any implementation issue)
**Umbrella:** #11518 (Task 6) · **Design only — no implementation under this issue**

## 1. Problem

Production chat dispatches tools one per iteration with a full LLM roundtrip each
(`chat_workflow/tool_handler.py::_dispatch_tool_call`, single-`execute_command`
rule from #716). A task that needs N dependent tool calls costs N inferences,
N× latency, and N× context growth. Agent-platform research (#11518) shows
code-execution runtimes — the LLM writes one program that calls many tools with
loops/conditionals, executed in a sandbox — collapse this to a single inference
with large cost/latency reductions.

## 2. Execution surface

### 2.1 Sandbox

Reuse `secure_sandbox_executor.py` (Docker) at security level **HIGH** — no new
sandbox technology (non-goal). Baseline limits (all env-configurable module
constants, never hardcoded): memory 512 MiB, 1.0 CPU, **network disabled**,
wall-clock timeout `AUTOBOT_CODEEXEC_TIMEOUT_SECONDS` (default 120), output
truncation as in `tools/code_interpreter.py` (10 KiB), Redis security-event
logging already built into the executor.

The `code_interpreter` subprocess path is NOT the execution surface — it runs
as the backend OS user with no isolation and stays approval-gated as today.

### 2.2 Tool shims

The generated program imports a generated module `autobot_tools` exposing one
async function per *injectable* tool. Each shim is an RPC stub: it serialises
`(tool_name, params)` over the container's stdio channel to a broker running
in the backend process, which dispatches through the **existing**
`_dispatch_tool_call()` seam — the sandbox never holds credentials, network
access, or direct tool implementations. Results stream back over the same
channel. One broker per script run; concurrency inside the script is permitted
(asyncio), but the broker serialises actual tool execution to preserve
current one-at-a-time semantics in v1.

### 2.3 Injectable vs excluded tools

| Class | Examples | Injectable? |
|---|---|---|
| Read-only retrieval | `web_search`, `scrape_url`, `map_site`, knowledge search, `extract_structured_data` | Yes (v1) |
| Bounded compute | pure-Python transforms inside the script itself | Yes (inherent) |
| State-mutating, reversible | file writes inside a scratch mount | v2, behind separate flag |
| SENSITIVE_TOOLS | `execute_command`, deploy, git push, browser control, `delegate` | **Never** — excluded from the shim module entirely; calling them is unrepresentable, not merely denied |

The injectable list is a declarative allowlist
(`AUTOBOT_CODEEXEC_INJECTABLE_TOOLS`), intersected with the agent's
`allowed_work` and minus `forbidden_work` from `AgentCapabilityRegistry`
(GH#11139) at shim-generation time — per agent, per run.

## 3. Governance (the hard part)

Per-tool approval gates cannot fire meaningfully inside a script (approving 40
micro-calls is worse than what we have). Replacement controls:

1. **Whole-script pre-approval.** The generated program is shown *as the
   approval artifact* through the existing `models/approval.py` state machine
   (type `WORKFLOW_GATE`), exactly like terminal-command approval in
   `tool_handler.py`. The user approves the program text, the shim allowlist
   snapshot, and the resource budget together. Auto-approval only when every
   shimmed tool is in the read-only class AND the session has
   `AUTOBOT_CODEEXEC_AUTOAPPROVE_READONLY=1`.
2. **Static AST check before execution.** Reject on: `import` outside an
   allowlist (`autobot_tools`, `asyncio`, `json`, `re`, `math`, ...),
   `exec`/`eval`/`compile`/`__import__`, attribute access smuggling
   (`getattr(autobot_tools, computed_name)`), and any name matching the
   agent's `forbidden_work` tokens (reuse the token→tool mapping from
   `chat_workflow/delegation.py`). The checker is a hard gate — failure
   returns the violation to the LLM as a tool error, never "best effort".
3. **Runtime enforcement is the broker, not the sandbox.** Even if the AST
   check is bypassed by obfuscation, the only capability channel is the
   broker, which re-validates every incoming call against the same
   allowlist/forbidden_work set and the per-run budget. Defense in depth:
   unrepresentable (no shim) → statically rejected (AST) → dynamically
   rejected (broker).
4. **Budgets.** Per-run caps: tool-call count (`AUTOBOT_CODEEXEC_MAX_TOOL_CALLS`,
   default 50), wall-clock, memory (Docker), cumulative LLM sub-call tokens 0
   in v1 (scripts may not call LLMs). Budget exhaustion aborts the container.
5. **Audit.** The broker writes one Redis security-event per shim call
   (existing executor event stream): run id, agent id, tool, params hash,
   duration, outcome. The approved program text and AST-check verdict are
   stored on the approval record (JSONB context), giving full replayability.

## 4. Failure semantics

- **Result channel (GH#11613):** the shim and the script share the sandbox's
  single stdout, so RPC framing and the script's result must be separated or
  the returned value is polluted by the tool-call transcript. RPC request lines
  are prefixed with a control-char sentinel (`\x1e`, Record Separator — see
  `code_exec/protocol.py`); the executor pump routes only sentinel lines to the
  broker and captures every other stdout line as the script's result. The
  script therefore returns its answer by printing to stdout normally (RPC is
  transparent); `result.stdout` is that captured output, never `container.logs()`.
- **Partial side effects:** v1 shims are read-only, so a mid-script abort
  loses only work, not consistency. This is the main reason v1 excludes
  mutating tools; compensation logic is deferred to v2 and must be designed
  per tool class, not generically.
- **Error propagation:** a shim call that fails raises in-script; the script
  may handle it (that is the point of code mode). An unhandled exception,
  AST rejection, or budget abort returns a structured error result to the
  chat loop as an ordinary failed tool call — the LLM sees it and can retry
  with a corrected program (`AUTOBOT_CODEEXEC_MAX_SCRIPT_RETRIES`, default 1).
- **Streaming progress:** the broker emits a `WorkflowMessage` progress event
  per shim call (throttled) so the UI shows live activity; publish to both
  event buses (RedisEventStreamManager and LiveEventManager) per the known
  dual-bus requirement.
- **Cancellation:** chat-side cancel → broker closes the channel and kills the
  container (existing executor teardown).

## 5. Pilot scope

- **Entry point:** a new `compose` tool registered in the existing dispatch
  seam (`_dispatch_tool_call`), NOT a parallel loop. The orchestrating LLM
  opts in by emitting `compose` with the program as payload; prompt guidance
  advertises it only for multi-tool research/extraction tasks.
- **Flag:** `AUTOBOT_CODEEXEC_ENABLED` (default **false**), plus the
  auto-approve and budget knobs above. Off = zero behavior change.
- **Pilot flows:** web-research aggregation (search → scrape×N → extract →
  synthesize) and knowledge batch extraction — today's worst N-roundtrip
  offenders, all read-only.
- **Success metrics** (compare against matched non-compose sessions):
  LLM inferences per completed task, wall-clock per task, token cost per
  task, script AST/broker rejection rate, approval-to-execution latency.
  Kill criterion: rejection rate > 20 % or no ≥ 30 % inference reduction
  on pilot flows.

## 6. Non-goals

- No new sandbox tech (QuickJS/WASM, gVisor, Firecracker) — Docker executor only.
- No mutating tools, no LLM sub-calls, no network inside the sandbox in v1.
- No replacement of the chat loop or the JSON tool-call protocol; `compose`
  is one additional tool.
- No skill/plugin authoring surface changes.

## 7. Implementation sketch (for the follow-up issues, post-approval)

1. `chat_workflow/code_exec/` package: broker, shim codegen, AST checker
   (~3 modules, each unit-testable without Docker).
2. `_dispatch_tool_call` branch for `compose` + approval wiring.
3. Executor: stdio channel + no-network profile addition to
   `secure_sandbox_executor.py`.
4. Prompt/schema registration of the `compose` tool (advertised only when the
   flag is on and the agent has eligible tools).
5. Tests: AST-checker corpus (allow/deny), broker enforcement (forbidden call
   from inside script), budget abort, end-to-end with a fake docker runner.

## 8. Open questions for owner

1. Is whole-script approval acceptable UX for interactive chat, or should v1
   ship auto-approve-read-only as the default posture?
2. Should `compose` be available to delegated subagents (#11207), or main
   chat agent only in v1? (Recommendation: main agent only.)
3. Python-only scripts in v1, or is TypeScript worth a second runtime later?
