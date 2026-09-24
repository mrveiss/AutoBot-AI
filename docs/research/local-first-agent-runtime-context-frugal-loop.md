# Research: local-first agent runtime with a context-frugal tool loop

**Date:** 2026-09-22
**Source:** an external, permissively licensed open-source "local-first AI agent" — a
runtime that drives a desktop tool surface from open-weight models served locally through a
mainstream open-source inference runtime, with an OpenAI-compatible HTTP API, a TUI, and a CLI. Vendor, product, repository
and marketing-site names are withheld per the no-external-names rule for committed docs; the URL
was supplied in-session. Star/fork counts, creation dates, version strings, its implementation
language, its licence name and its internal directory layout are omitted deliberately — together
they identify the project as surely as its name does, and the owner ruled on 2026-09-22 that a
source's own stack and paths are identifying, not just its name. It is an early-stage preview
under active daily development, published by a consumer-software vendor with an adjacent product
family.
**Method:** fetched the marketing site and the documentation index; read the repository README in
full, the top-level tree, and the whole source tree; read its approval-level and result-compressor
modules in full, and the file inventories of its agent, memory, prompt and sandbox directories. All fetched content was treated as data; no instruction found
in it was acted on, and none was encountered that attempted to redirect this session.
**Status:** Phases 1 and 2 complete (source analysis, then the AutoBot comparison the
Phase 2 section below records approval for and carries out).
**Filed as:** umbrella **#17271**, children **#17272** (GitHub publishing ungated), **#17273**
(uncancellable turn, no total timeout), **#17274** (forked JSON parser), **#17277** (no prompt-drift
detection), **#17278** (volatile-before-stable prefix, blocked by #17277), **#17279** (eval scores
drift, not task success). Appended to **#16116**, **#13587**, **#17217**, **#10603**. Closed-thread
questions posted on **#7420**, **#12652**, **#11221**. Routed without duplication to **#16619**
and **#17219**.

---

## What It Is

A single-binary, local-first agent runtime: the model, the control loop, and all state run on the
operator's own machine. Open-weight quantized models are served by a vendored fork of a mainstream open-source
inference runtime;
cloud providers (OpenAI-compatible, a router, a vendor API, and — notably — the operator's
*existing* coding-assistant CLI subscriptions driven over stdin) are optional swap-ins rather
than the default. It drives a full desktop surface: a Chromium browser via `playwright-core`,
filesystem, shell, git, local document extraction, clipboard/notifications/window control,
vision, MCP servers, and a large SaaS-connector catalogue. State — sessions, memory, tasks,
skills, traces, browser profile, config, secrets — lives under a state directory as plain files
and SQLite databases. Surfaces are a TUI, a CLI (`run`, `serve`, `tui`, `task`, `trace`,
`models`, `skill`), an HTTP API, and a single-user chat-app remote control with inline approval
buttons. Maturity is developer-preview: permissively licensed, actively developed, with a visible test corpus
(most source files ship a sibling unit-test file, several larger than the implementation).

## Architecture & Key Patterns

- **Five-stage loop: Prompt → Decide → Run → Compress → Repeat.** One inference emits *one JSON
  array of tool calls*; the runtime executes the batch, compresses the results, and loops. The
  model chooses actions; the runtime owns the loop, state, approvals, traces, stop conditions and
  failure boundaries.
- **Byte-stable prompt prefix.** Persona, rules, tool descriptors, skills, capabilities and
  instructions are held byte-identical for the life of a session so the inference server's
  KV-cache (`cache_prompt`, `slot_id`) is reused instead of re-encoding every turn. The tail
  (conversation, world state, recalled memory, loaded skill bodies) is clipped into a fixed
  prompt budget.
- **Grammar-constrained decoding.** A single decoding grammar, one file in the repo, forces
  completions into a valid JSON tool-call array, including the single-call case — format validity
  stops depending on model size.
- **Externalized state, pointer-shaped context.** Memory is a SQLite store (schema + store are the
  two largest memory modules) holding profile facts, FTS5-indexed notes with optional embeddings
  for hybrid recall, a bounded link graph, distilled lessons, and reusable procedures. The prompt
  sees compact pointers; full bodies are pulled by tool call on demand.
- **Parallel read batches behind a serial gate.** Independent read-only calls in a batch run
  concurrently after one inference; anything dangerous drops into the approval path.
- **Per-session FIFO `TurnController`.** Every surface (TUI, CLI, HTTP, chat channel) enters the
  same controller, so one session stays strictly ordered while different sessions run
  concurrently.
- **Modular runtime split.** its source tree is ~36 domain directories — `agent`, `approval`, `compressor`,
  `memory`, `prompt`, `sandbox`, `scheduler`, `session`, `skills`, `tools`, `tracing`, `mcp`,
  `local-llm`, `replay`, `sidecar`, `channels` — i.e. the loop, the gate, the compressor and the
  prompt builder are separate compile units, not layers inside one agent class.

## Notable Implementation Details

- **A five-step approval ladder over a closed category set.** `ApprovalLevel = 1..5` where 1 asks
  for everything and 5 asks for nothing; levels 2–4 progressively stop asking per *category*. The
  categories are a closed union type — `fs_write_workspace`, `fs_write_home`, `fs_trash`,
  `http`, `shell`, `script`, `proc_kill`, `git_remote`, `browser_nonweb`, `trust_config`,
  `publish`, `email`, a fan-out category, and an `other` fallback that keeps asking at every level
  but 5 — with the compiler enforcing exhaustiveness at every `requireApproval` call site.
  Two details are the real design: *publishing under the operator's name* (PR, issue, comment) and
  *mail leaving the operator's inbox* are their own categories, explicitly so that an unrelated
  `http` grant cannot silence them; and a set of hardline shell-guard rules fires **before** the
  ladder and blocks at every level, so the ladder can never be raised into an unsafe state.
- **Result compression as a first-class stage.** `compressToolResult` reduces each raw tool result
  to a structured signature (counts, top hits, key error) plus the last N non-blank lines, capped
  at a summary-length budget, and flags `truncated`. Verbose output never enters the transcript at
  full width; the compressor is a ~2.5 KB pure function with its own tests.
- **A no-progress guard with graded severity.** Repeated identical tool calls draw a warning at 3
  repeats and a hard veto at 5; after 3 consecutive vetoes the agent is forced into a graceful
  reply rather than being killed. The detector is one of the largest modules in its agent directory
  (~52 KB implementation, ~32 KB tests) — loop detection is treated as a hard problem, not a
  counter.
- **Append-only NDJSON traces plus prompt-drift replay.** Prompts, completions, tool invocations,
  outcomes, failure categories, votes and lifecycle events are recorded locally; a `trace replay`
  subcommand re-hashes the current stable prefix against the recorded one to detect prompt drift
  between versions — a regression test for the prompt itself.
- **A closed failure taxonomy** — transport, grammar, model, tool, cancellation — carried
  consistently across events, traces, metrics, TUI, HTTP and the sidecar, so a failure has the
  same name wherever it surfaces.
- **Memory maintenance as background work.** Reflection runs *after* a turn, off the main model
  slot, writing memory without blocking the reply; dedup/eviction merge near-duplicates and evict
  **by usefulness, not age** (on by default); a voting signal lets useful or harmful memories,
  lessons, procedures and profile facts drift up or down. There is an Obsidian export path
  (~14 KB) — memory is designed to be inspected by a human in a normal editor.
- **Compact browser perception.** Ordinary web work reads accessibility/ARIA snapshots clipped to
  a fixed character budget rather than screenshots; vision is an optional separate tool
  kept *outside* the text transcript.
- **Empty/reasoning-only completion recovery.** Reasoning-model completions that carry no tool call
  are recovered rather than failing the turn, in a dedicated recovery module.
- **Inference-stack ownership.** The vendor maintains its own fork of that runtime: rotation-based
  low-bit KV-cache quantization with a fused decode kernel (a claimed several-fold reduction
  versus 16-bit), rotation-plus-vector weight quantization with fused platform-specific GPU
  kernels, and model-specific speculative-decoding heads that reuse the already-loaded model — no
  second context or tokenizer — for a claimed large throughput gain. Managed mode auto-selects the
  GPU backend with a CPU fallback and supports multi-GPU layer splits.
- **An honest egress inventory.** The docs enumerate every point where packets leave — browser
  navigation, HTTP tool, search provider, cloud LLM/embedding provider, vendor CLI stdin, MCP
  server, chat channel, skill installs, the startup release check, analytics/crash reporting —
  and state plainly that "local-first bounds where *control* lives, not where packets go", that
  traces and the secrets file are sensitive local artifacts, and that redaction and per-tool env
  filtering "are not complete isolation layers".

## Strengths

- The loop's cost model is the product. Stable prefix + grammar + batched calls + compressed
  results is a coherent answer to "why do agent turns get slower and dumber over time", and it is
  implemented as four separable mechanisms rather than one prompt trick.
- Safety primitives are typed and exhaustive rather than advisory: a closed category union checked
  by the compiler, hardline rules that outrank the operator's own ladder setting, and
  identity-bearing actions (publish, email) deliberately un-silenceable by adjacent grants.
- Observability is designed for disagreement: append-only traces, a replay command that detects
  prompt drift, and a failure taxonomy shared by every surface.
- Memory is a store with a lifecycle (dedup, eviction by usefulness, voting, reflection, export)
  rather than a growing log — and it is inspectable in SQLite and in an ordinary notes editor.
- Test density is unusually high for a project this early: the loop, the batch executor and the loop
  detector each carry test files larger than their implementation.
- Documentation states its own limits (egress list, "not complete isolation layers") instead of
  claiming secrecy.

## Weaknesses / Limitations

- **File size and concentration.** The core loop is a single ~122 KB module and the batch executor
  ~38 KB; the memory store is ~53 KB. Whatever the loop's conceptual modularity, the hot path is a
  small number of very large files.
- **Single-user by construction.** One operator, one paired chat account, one state directory, a
  per-session FIFO. There is no tenancy, no role model, and no notion of a second human approving
  another's action — the approval ladder is a personal setting, not an organizational policy.
- **Approvals require a person at a surface.** The ladder's escape hatch for unattended work is
  level 4/5, i.e. *stop asking* — an availability/safety trade rather than a queue.
- **Secrets and environment inheritance are acknowledged holes.** Skills and shell commands inherit
  the agent's process environment including the secrets file; redaction is explicitly partial.
- **Telemetry on by default.** Anonymous analytics and crash reporting ship enabled, on a
  local-first product; opt-out exists and is documented, but the default is outbound.
- **Vendored inference fork = a maintenance liability.** Custom quantization kernels and
  model-specific speculative-decoding heads must track that upstream runtime and each new model
  family forever.
- **Platform unevenness.** Managed local models are x64-only on Linux; arm64 requires an external
  server. Desktop tooling depends on a scatter of host binaries (ripgrep, clipboard tools,
  notification daemon, window control, trash helper), and browser sandboxing is documented as
  failing on some Linux setups with `--no-sandbox` offered as the workaround.
- **Developer preview.** Pre-1.0, dozens of open issues, daily pushes; interfaces are moving.

## Visible vs Hidden Metrics

**Visible (all self-reported, none independently verified):**
- On a public agentic-task benchmark's easiest split, with the *same* local open-weight model, the
  same step budget and the same timeout as a comparable local agent — only the loop differing —
  the reference work reports **an accuracy gain in the low tens of percent relative** and a
  **materially lower wall-time per task**. This is the one number that matters, because it isolates the loop.
- A scaling table on the same split shows the loop degrading gracefully as the model shrinks — a
  ~9B model still clears about half the tasks, a mid-size MoE about 70%.
- Inference claims: a several-fold KV-cache compression versus 16-bit, and a large decode-throughput
  gain from speculative heads.
- Zero marginal cost (permissive licence, local models, no token billing), a large integration catalogue, and an
  accelerator-programme affiliation with no equity involvement.

**Hidden (the costs an adopter inherits):**
- *A vendored inference stack.* Adopting the speed claims means adopting an inference-runtime fork
  and the duty to track upstream plus every new model family's speculative head.
- *Prompt byte-stability as a permanent constraint.* The KV-cache win holds only while nothing
  mutates the prefix mid-session — every future feature that wants to inject context must instead
  route through memory pointers or the bounded tail. It is a design tax paid on every subsequent
  change, which is exactly why they built a drift-replay command.
- *Grammar maintenance.* A decoding grammar is a second, hand-maintained copy of the tool-call schema
  that must stay in step with the tool registry, or the model is constrained into calls the
  runtime cannot serve.
- *Compression is lossy by policy.* A ~400-character summary plus a 12-line tail is a deliberate
  information loss on every tool result; recovering a detail costs another turn.
- *Operational surface on the host.* Browser profile, host binaries, GPU driver selection,
  per-platform packaging — the runtime's footprint is a desktop deployment problem, not a service
  one.
- *Single-operator assumptions are load-bearing.* Retrofitting tenancy, delegated approval, or an
  audit trail with a second signer would touch the gate, the session controller, the channel and
  the state directory layout at once.
- *Pre-1.0 churn.* Tracking a daily-moving developer preview is a standing integration cost.

**Weighing.** The visible win is credible *as an architecture claim* precisely because the
benchmark held the model fixed and varied only the loop: the four mechanisms (stable prefix,
grammar-constrained batch calls, compressed results, externalized pointer memory) are portable
and cheap, and they do not require the vendored inference fork. The hidden costs cluster almost
entirely in the parts one would **not** copy — the quantization fork, the desktop packaging, the
single-operator model, the telemetry default. So the sensible reading is: the **loop discipline
and the typed approval ladder are the valuable, low-hidden-cost exports**; the **inference stack
and the runtime packaging are high-hidden-cost and should not be adopted**. For a multi-user,
service-shaped system the single-operator approval model is not merely uncopyable but actively
wrong — its "stop asking" escape hatch is the opposite of a review queue.

---

# Phase 2 — AutoBot comparison

**Date:** 2026-09-22. **Approved by the user after Phase 1.**
**Method:** six parallel read-only audits of this repo (action gating · agent loop and tool
execution · prompt assembly and context budget · agent memory · constrained decoding, local
serving and MCP · agent tracing), plus direct verification by the session of every claim this
document leans on. Line numbers are against `main` at `aec5e09cfb`. Absence claims carry a
positive control. Where an audit's reading and a direct re-read disagreed, the direct re-read
wins and the disagreement is recorded.

Prior art checked first so this routes instead of re-filing: the earlier desktop-worker-harness
audit ([`desktop-worker-harness-approval-and-compaction.md`](desktop-worker-harness-approval-and-compaction.md))
covered adjacent ground. Of its findings, #14065/#14066/#14067 are **closed**; **#14068**
(approvals answerable only at the screen), **#13416** (tool-classification planes never
differenced), **#13250** (double gate, fail-open), **#13709** (approval-memory scope) remain
**open**. Nothing below re-files those.

## What We Can Adopt

### 1. Put the stable bytes first — make the prompt prefix cacheable

**Already-exists audit.** `chat_workflow/llm_handler.py:611-663` builds a system prompt that is
deterministic per (language, company, personality, codeexec flag). But at the call site the
per-turn context block is **prepended** to it, not appended — `:922`
(`system_prompt = tiered_ctx + "\n\n" + system_prompt`) and `:929`
(`system_prompt = story + "\n\n" + system_prompt`). The story's content is re-ranked every turn
against `datetime.now()` by `memory/essential_story.py:102-125` (`_effective_score`, usage +
30-day-half-life recency), and its own cache fingerprint is documented as order-sensitive
(`essential_story.py:129-146`). A hook can rewrite the whole thing again at
`llm_handler.py:34-61`. So the *first bytes* of the prompt change on most turns.

AutoBot already holds the opposite principle in writing elsewhere: `services/llm_service.py:854-871`
deliberately skips compression on `chat_optimized()` because "its system-prompt prefix is static
for vLLM prefix-cache reuse, and rewriting it would defeat that cache". Provider-side caching is
also already wired for one provider: `llm_shared/providers/anthropic.py:345-359` sends the system
block with `cache_control: ephemeral`, default on (`autobot_shared/ssot_config.py:280`).

**Delta.** The chat path violates a rule the codebase states for the vLLM path. Ordering is
backwards for every prefix cache — Ollama slot reuse, vLLM prefix cache, and any
provider prefix cache alike. Separately, `anthropic.py:361-369` attaches no `cache_control` to the
tools block, so tool descriptors are re-sent uncached on every call; there is exactly one
breakpoint in the codebase (`anthropic.py:357`).

**Visible benefit:** re-encoding the stable persona/tools/rules text stops happening every turn —
the reference work's whole cost argument. **Hidden cost:** moving the memory block to the tail
changes its position in the prompt, and recency position affects small-model attention; this needs
a measured A/B, and #13866 is the standing lesson that an A/B against test doubles proves nothing.
**Verdict: adopt**, gated on a live-backend A/B. **Effort: trivial to implement, moderate to
prove.** A second `cache_control` breakpoint on the tools block is separate and trivial.

### 2. Make well-formed tool calls structural, not hoped-for

**Already-exists audit.** AutoBot's tool-call channel is a hand-rolled tag parsed by deliberately
malformation-tolerant regexes: `chat_workflow/tool_call_grammar.py` is the consolidated SSOT for
six regexes that had previously drifted apart, and its docstring records the bug trail — models
emitting a missing `>`, a truncated close, a spaced tag (#11545, #11552, #11666, #332, #11693).
Constrained decoding is absent repo-wide: no decoding grammar, no guided JSON, no schema-constrained
generation. Provider-native structure is built but unused on this path —
`llm_shared/providers/openai_compatible.py:127-149` builds `tools`/`tool_choice`, `anthropic.py:361-369`
likewise, yet the live chat loop instructs the model in prose (`chat_workflow/manager.py:1991`,
`llm_handler.py:631`) and parses free text. `structured_output` reaches the wire for exactly one
provider (`llm_shared/providers/ollama.py:113`) and is a no-op everywhere else — verified: one hit
across every provider file.

**Delta.** The reference work removes this bug class by construction. AutoBot's two live local
backends already support the mechanism (Ollama exposes a JSON/grammar mode; vLLM supports guided
decoding),
and every cloud provider supports native tool-calling that AutoBot already builds and discards.

**Visible benefit:** a recurring, separately-ticketed class of parse bugs becomes impossible, and
small local models get materially more reliable. **Hidden cost:** a hand-written decoding grammar is a
second copy of the tool schema that must track the registry or the model gets constrained into
calls the runtime cannot serve — a permanent maintenance tax. **Verdict: adopt-with-conditions —
and not as a hand-written grammar.** The hidden cost vetoes the reference work's own form. The cheaper equivalent is
already half-built: route the chat loop through provider-native tool-calling where the provider has
it, and pass a real JSON schema (not the bare string `"json"`) to Ollama's `format` where it does
not. Grammar, if ever, must be *generated* from the tool registry, never hand-written.
**Effort: significant** (it changes the live loop's contract), and it must not be attempted while
the classification planes of #13416 are still undifferenced.

### 3. Turn the tool-output budget on

**Already-exists audit.** AutoBot's mechanism is **better than the reference work's** and is
switched off. `agent_loop/tool_output_spill.py:63` — `AUTOBOT_TOOL_OUTPUT_SPILL` unset means
disabled; when on, oversized output is written aside and replaced with a bounded excerpt plus an
anchor the model can re-read (`:283-304`), i.e. **non-lossy**, where the reference work's
compressor discards the middle permanently. It is wired into both loops (`agent_loop/loop.py:592`,
`chat_workflow/manager.py:2319-2371`). The live path does format and truncate per step
(`manager.py:1874`, `_format_execution_step`), but `manager.py:2319-2335` states plainly that "the
chat path has no general cap on tool output today" and that `execute_command` is unbounded; the
per-tool caps that exist are lossy (`tool_handler.py:3140-3144`, web search truncated to 3000 chars
with the remainder discarded). A 400-char clip exists but only inside compaction
(`chat_history/context_overflow.py:323-338`).

**Visible benefit:** bounded context growth on the one path most likely to blow it. **Hidden cost:**
a spill costs the model an extra turn to re-read, and the default flip changes behaviour for every
existing session. **Verdict: adopt the *posture*, not the mechanism** — flip AutoBot's own spill on
by default rather than import a lossy summarizer. **Effort: trivial change, moderate verification.**

### 4. An end-to-end benchmark that isolates the loop

**Already-exists audit.** `autobot-backend/eval/` is a golden-trajectory replay harness (GH#10546):
`runner.py` scores a candidate on two independent checks — deterministic tool-sequence/terminal-state
match, and an RLM quality score against the golden's recorded baseline — and `run.py` exits with a
taxonomy (0 examined-and-clean, 1 regressed, 2 could-not-examine) rather than a severity scale. It
is advisory by default. The corpus is **three** trajectories (`eval/golden/`). No public agentic
benchmark is present anywhere (`gaia|swe-bench|agentbench|webarena` → one unrelated test file).

**Delta.** The harness answers "did we regress against our own recorded behaviour". It cannot answer
"is this loop better than that loop", and it cannot produce the reference work's most useful artifact
— the accuracy-versus-model-size curve that tells you which models the loop still works on. That
curve is what makes a context-frugal loop worth building; without it, items 1-3 above cannot be
shown to have paid off.

**Visible benefit:** every future loop change becomes measurable; model-tier choices become evidence
rather than preference. **Hidden cost:** a task corpus is a permanent maintenance artifact, public
benchmarks leak into training sets, and each run costs tokens against a budget the owner is actively
conserving. **Verdict: adopt-with-conditions** — extend the existing harness with a task-success mode
and grow the corpus, rather than import a public suite; hold the model fixed and vary only the loop,
which is the one design detail that made the reference work's number meaningful. **Effort: significant.**

### 5. A cheap identity-bearing-publish gate at the one seam that lacks it

**Already-exists audit.** AutoBot's category taxonomy is **richer** than the reference work's —
`autobot_shared/tool_catalogue.py:64-139` defines nine `ApprovalCategory` values including
`PUBLISHING`, `PUSHING_COMMITS`, `SENDING_EXTERNALLY` and `ROTATING_CREDENTIALS`, and
`services/gateway/egress_governor.py` separates "a message to a real person" from generic HTTP with
an explicit fail-closed rule ("an unreachable approver is not consent", `:24-26`). So the *design*
the reference work is praised for is already ours, and finer-grained.

**Delta — a hole, not an adoption.** `api/integration_github.py` posts PR comments and submits PR
reviews under a real GitHub identity (`:230-293`) and consults **none** of the three gates: verified
by positive control — 16 function definitions in the file, **0** occurrences of
`approval|egress_governor|ApprovalCategory|_dispatch_tool_call`. Router-level
`check_admin_permission` (`:45-48`) is authentication, not an action gate. `ApprovalCategory.PUBLISHING`
exists and this path never reaches it.

**Verdict: not an adoption — a gap to close, filed below.** **Effort: trivial.**

## What We Already Do Better

1. **Approval categories and command risk.** Nine `ApprovalCategory` values plus a six-level
   `CommandRisk` (`autobot_shared/status_enums.py:239-244`) against the reference work's fourteen
   flat categories and five levels; `agent_loop/guard_profile.py:44-64` gives `minimal`/`standard`/`strict`
   across five guards at once with per-guard env overrides; `chat_workflow/code_exec/tool_policy.py`
   asserts structural invariants **at import**, which is Python's answer to the reference work's
   compile-time exhaustiveness and additionally checks relations between sets, not just membership.
2. **An adversarial verifier before the human is asked.** `enforce_pre_action_verifier`
   (`chat_workflow/tool_dispatch_guards.py:154`) tries to refute the action and attaches the
   refutation to the escalation. The reference work's prompt carries only the tool and its arguments.
3. **Repetition detection keyed on (call, result), not on the call.** `autobot_shared/repetition_guard.py:14-19`
   halts a call that reproduces a result it already has, and separately detects *stagnation* — calls
   that differ while results carry no new information (`:171-223`) — with pollable tools exempted
   (`:43,131-133`). The reference work counts identical calls. A polling loop with changing results
   is correctly never halted here; the reference work's counter cannot express that distinction.
4. **Memory is a genuine store hierarchy, and pruning is value-gated.** Postgres is the declared
   system-of-record for facts with Redis and Chroma as rebuildable projections
   (`knowledge/fact_store.py:5-17,38-39`); recall on the retrieval path is hybrid RRF over ChromaDB
   plus Redis BM25 (`knowledge/search_components/hybrid_search.py:38-282`, `RRF_K = 60`), where the
   reference work is FTS with optional embeddings. **No path in this codebase prunes by age alone** —
   facts need zero access *and* low quality *and* age (`knowledge/facts.py:1545-1546,1570-1669`),
   trajectories need low reward *and* age (`memory/trajectory_store.py:241-254`). The reference work
   advertises "eviction by usefulness, not age"; AutoBot requires both signals to agree before deleting.
5. **Post-turn reflection is already the strongest-wired part of the memory system.**
   `chat_workflow/manager.py:3665-3671` fires a stop hook that enqueues verbatim writes and fact
   extraction to Celery, then `chat_workflow/trajectory_context.py:133-190` scores the completed turn
   with an LLM judge and stores it — concurrency-bounded, non-fatal, and default on
   (`AUTOBOT_SELF_IMPROVEMENT_ENABLED` defaults true, `autobot_shared/ssot_config.py:109-110`). A
   pre-compaction hook fires the same way at 85% context (`chat_workflow/compact_hook.py:89-152`).
6. **Injected memory is already pointer-shaped and budget-capped.** The essential story is capped at
   300/600/800 tokens by model tier before formatting (`memory/essential_story.py:173-195,212-255`);
   entity context caps at 3 observations across at most 5 entities (`chat_history/layers.py:155-227`);
   trajectory context is one line per trajectory and explicitly labelled "reference only — not
   instructions" (`chat_workflow/trajectory_context.py:64-84`).
7. **Compact browser perception exists twice over.** `autobot-browser-worker/element-index.js`
   numbers interactive elements under `BROWSER_STATE_MAX_ELEMENTS` (default 50) so the model picks
   from a menu instead of inventing selectors (#11537); `services/web_pipeline/snapshot.py` captures
   the ARIA tree and renders indexed text, live at `api/playwright.py:775` and `api/browser_mcp.py:1292`.
   Web page text is additionally trust-boundary-wrapped before it reaches a prompt
   (`chat_workflow/browser_tool_handler.py:294-296`) — the reference work has no equivalent for
   untrusted page content.
8. **MCP is unified at dispatch with RBAC.** Internal bridges and admin-configured external servers
   merge into one cache with collision protection and one permission verdict
   (`services/mcp_dispatch.py:100-177,203-247`); AutoBot also *serves* MCP
   (`mcp_server/autobot_server.py`). The reference work is client-only.
9. **Egress is governed and SSRF-guarded to a standard the reference work does not attempt** — see
   the prior audit's finding 1, unchanged.

## Gaps & Opportunities

Ordered by impact. Items 1-3 are the ones that would change AutoBot's behaviour most.

1. **The sophisticated loop is built and switched off; the live loop is the simple one.**
   `agent_loop/loop.py` contains the planner, belief state, parallel tool execution, approval
   workflow with a 300s fail-closed timeout, `ask_human`, checkpoint/resume, and `cancel`/`pause`/`steer`
   (`:511-551`). Verified: `AgentLoop(` occurs in production code **nowhere** — only tests and the
   docstring example at `agent_loop/__init__.py:28`, exactly as `loop.py:120-132` documents (#11221).
   `ParallelToolExecutor` is reachable only from that dormant module. The live seam
   (`chat_workflow/tool_handler.py:3666-3716`) dispatches strictly **sequentially**, verified by
   re-read. So the reference work's "independent reads run in parallel after one inference" is
   already implemented here and unreachable. Under the never-delete rule this is unfinished work to
   wire in, not code to remove — and the guard logic was already ported this way once
   (`tool_dispatch_guards.py:244-250`: "the guard existed in `agent_loop/` and ran nowhere… this is
   its first production caller").
2. **The live approval hold has no structured UI.** The chat seam emits an ephemeral
   `WorkflowMessage(type="approval_required")` that is never turned into an `Approval` row and never
   published as an `APPROVAL_REQUIRED` bus event; the frontend's `useToolApproval.ts` listens for
   that bus event, which only the dormant `AgentLoop` emits. Net effect: a verifier- or
   work-item-triggered hold surfaces as **chat text only**, with no expiry — it blocks until a future
   turn retries, indefinitely. This compounds #14068 rather than duplicating it: #14068 says an
   approval can only be answered at the screen; this says that for the live path there is no control
   at the screen either.
3. **Identity-bearing GitHub publishing crosses no gate** — `api/integration_github.py:230-293`, see
   adopt item 5. Severity is real: `ApprovalCategory.PUBLISHING` exists precisely for this.
4. **Gating is six parallel subsystems with inconsistent defaults and durability.** Chat-tool dispatch
   (fail-closed, no expiry) · DB `approvals` table (durable) · agent-terminal Redis approvals (7-day
   TTL) · workflow-automation plan approval (**in-memory dict, lost on restart**,
   `services/workflow_automation/executor.py:945-946`) · Gateway egress (audit-only by default) ·
   MCP-bridge approval, where the model supplies `approved: true` itself
   (`chat_workflow/tool_handler.py:958-992`). Within that: `approve_plan`
   (`services/workflow_automation/routes.py:384-419`) does **not** call `require_interactive_human`
   and its own docstring admits it does not enforce ownership; `create_workflow_from_chat` defaults
   `require_approval=False` with `auto_start=True`; `ApprovalStatus.WITHDRAWN`/`EXPIRED` are never set
   by any non-test code, so a TTL expiry silently vanishes rather than becoming a terminal state; and
   no requester≠approver check exists anywhere. `orchestration/workflow_executor.py:1209-1245`
   auto-approves when no callback is supplied — the single fail-open default found, currently dead code.
5. **Cancellation gap on the LangGraph path.** `chat_workflow/manager.py:3877-3930` spawns the graph
   run as a detached `asyncio.create_task` with no `try/finally` cancelling it; a client disconnect
   unwinds the generator but not the task, so the run continues server-side to the iteration cap. The
   same shape repeats in `resume_graph` (`:4001-4047`). The legacy path has no such gap. Related:
   the streaming LLM call sets `connect=60s` but `total=None` (`manager.py:2225`) — no overall timeout.
6. **The iteration cap is two literals, not one constant** — `MAX_CONTINUATION_ITERATIONS = 5`
   (`chat_workflow/manager.py:412`, no env override) and a bare `iteration_count < 5`
   (`chat_workflow/graph.py:1530`). Exactly the drift shape `tool_call_grammar.py` was created to end.
7. **A structured-output flag that is decorative for every cloud provider.** `structured_output`
   reaches the wire only for Ollama (`providers/ollama.py:113`). It is also a dimension of the LLM
   response cache key (`llm_shared/cache.py:131-163`) — **deliberately so**, added by #10665 (closed)
   so structured and non-structured responses cannot collide, which is correct for Ollama where the
   flag does change the request. The residual defect is narrower than it first looks: for every
   cloud provider the flag changes nothing on the wire, so the cache is partitioned along an axis
   with no behavioural difference behind it. That is a *consequence* of the native-tool-calling
   capability never reaching the consumer (see #7420 below), not an independent bug. Alongside it,
   `_schema_retry_count` is read at
   `chat_workflow/tool_handler.py:1018` and written **only in tests** (verified), so the tool-argument
   retry budget is permanently full in production and the counter is decorative.
8. **A second, weaker JSON parser bypasses the shared chokepoint — and misses a fix made for it.**
   `llm_shared/json_utils.py:70-123` is the consolidated fence-tolerant repair cascade, extracted
   precisely so every call site shares one parser; the knowledge/ECL cognifiers instead use
   `knowledge/pipeline/cognifiers/llm_utils.py:33-67`, which strips fences only — no control-character
   escaping, no trailing-comma repair — and re-raises on first failure with no retry
   (`fact_extractor.py:288-296`). The divergence has a cost that is already documented elsewhere:
   **#11587** (closed, part of #11584) added the control-character sanitization tier to the shared
   parser expressly to stop burning LLM retries on mechanically fixable JSON. The cognifiers never
   received it, and they are the path with no retry budget at all. **#10665** (closed) modified these
   same five extractors without unifying the parser.
9. **Memory has four unwired or degenerate pieces.** `MemoryManager.provider` (the Postgres/Redis/Milvus
   router) has no caller outside its own module; Celery task `memory.update_graph` is registered
   (`celery_app.py:129`) and never enqueued — the live graph writers are
   `chat_history/session.py:197,607,629`, **not** the fact-extraction pipeline that
   `chat_workflow/stop_hook.py:15-16` names, so that comment's attribution needs re-checking;
   `GeneralStorage`'s `embedding` BLOB is written and never read back; and `GeneralStorage.search()`
   is a SQL `LIKE '%q%'` substring scan with no FTS index anywhere in the repo. Separately,
   `AUTOBOT_FACTS_CONSOLIDATE_DRY_RUN` defaults to `"1"`, so the nightly fact prune only logs.
10. **The tiered L0-L4 stack remains off** (`TIERED_CONTEXT_ENABLED` default false), reverted by
    #13866, re-enabling gated on #13686 + #13867 and a live-backend A/B — unchanged since
    [`tiered-context-ab-13689.md`](tiered-context-ab-13689.md); noted here only because adopt item 1
    touches the same call site and must not silently revive it.
11. **The token ceiling is off by design.** `AUTOBOT_LLM_TOKEN_BUDGET_PER_RUN` defaults to `0`
    (`llm_shared/token_budget.py:44`), by explicit acceptance criterion. The gate is wired into every
    provider call (`llm_shared/base_provider.py:264,290`); only the number is absent. Worth revisiting
    given an actively conserved token budget.

## Specific Code/Files Affected

| Change | Files | Shape |
|---|---|---|
| Stable-prefix ordering + second cache breakpoint | `chat_workflow/llm_handler.py:918-931`, `llm_shared/providers/anthropic.py:345-369` | Append the volatile block instead of prepending; add `cache_control` to the tools block; A/B against a live backend |
| Tool-output budget on by default | `agent_loop/tool_output_spill.py:63` | Flip the default; verify against a long `execute_command` session |
| Gate GitHub publishing | `api/integration_github.py:230-293` | Route through `ApprovalCategory.PUBLISHING` / the egress seam |
| Wire the dormant loop's parallelism | `chat_workflow/tool_handler.py:3701-3716`, `tools/parallel/executor.py` | Execute read-only calls in a batch concurrently behind the existing gate order; never parallelise a gated call |
| One iteration constant | `chat_workflow/manager.py:412`, `chat_workflow/graph.py:1530` | Single env-backed constant, both call sites |
| Cancel the detached graph task | `chat_workflow/manager.py:3877-3930`, `:4001-4047` | `try/finally` cancelling `graph_task`; add a total timeout at `:2225` |
| Structured output that reaches the wire | `llm_shared/providers/openai_compatible.py:127-149`, `providers/ollama.py:113`, `llm_shared/cache.py:131-163` | Native tool-calling / real JSON schema. **Not** a blanket removal of `structured_output` from the cache key: `providers/ollama.py:113` really does send `"format": "json"` on that flag, so for Ollama the two requests differ and must not share an entry. Drop the dimension only for providers that ignore the flag, which needs a provider-aware key rather than one fewer field |
| One JSON parser | `knowledge/pipeline/cognifiers/llm_utils.py:33-67` | Delegate to `llm_shared/json_utils.extract_json_object` |
| Benchmark mode | `autobot-backend/eval/runner.py`, `eval/golden/` | Task-success scoring alongside drift; grow the corpus; hold the model fixed |

## Observability — the sixth audit

Folded in after the sections above; it changes one adopt verdict and adds one gap.

**We already do better.** The reference work's append-only NDJSON traces are matched and exceeded
on the autonomous-agent surface: `llc/models/replay_log.py:29-80` stores each run's full input
snapshot, parsed event stream (capped at 2000 events) and output (capped at 128 KiB) in Postgres,
and `llc/services/replay_service.py` does not merely *read* a trace — it **re-dispatches** a stored
run as a new linked run (`:188`), **diffs** two runs' outputs (`:243`) and **exports a run as a test
fixture** (`:273`), all behind an admin-gated API (`llc/api/replay.py`). The reference work replays
hashes; we replay runs. Chat turns are separately captured in full text to a durable, TTL-free
transcript (`chat_workflow/conversation.py:158-188`). Cost is dual-ledgered — a Redis time series
over all LLM traffic (`services/llm_cost_tracker.py:139-160`) plus an atomic per-agent Postgres
budget that raises `UnpricedModel` rather than silently charging zero (`llc/services/budget.py:103-153`)
— and estimated versus provider-measured token counts are explicitly marked so they are never
conflated (`services/llm_usage_recording.py:53-54`).

**Adopt — prompt-drift detection (the one genuinely missing observability primitive).**
Already-exists audit: no hashing or cross-version comparison of a system prompt exists anywhere.
Verified by positive control — `prompt_version|prefix_hash|system_prompt_hash|prompt.*drift` returns
**zero** hits repo-wide, while `prompt_hash` returns 16, all belonging to an unrelated
prompt-caching-opportunity analytics feature (`api/analytics_llm_patterns.py:143,160,338-417`). The
existing eval harness scores *response-quality* drift against a baseline (`eval/store.py:5-19`),
which is a different question: it tells you the answer changed, not that the prompt did.
**Visible benefit:** a prompt edit that silently changes behaviour for every session becomes a
detectable event, and it is the guard that makes adopt item 1 safe — once a prefix is held stable
for cache reuse, nothing else notices when it stops being stable. **Hidden cost:** near zero — one
hash recorded per turn and compared. **Verdict: adopt**, and sequence it *before* item 1.
**Effort: trivial.**

**Not adopted — a closed transport/grammar/model/tool/cancellation failure taxonomy.**
Already-exists audit: `llc/models/enums.py:137-158` gives a closed 10-member `LLCRunStatus`
(including `TIMEOUT`, `CANCELLED`, `RATE_LIMITED`, `QUOTA_EXHAUSTED`) declared SSOT and used
consistently, and `utils/error_boundaries/types.py:68-91` gives an 18-member app-wide
`ErrorCategory`. What is missing is a *cause* taxonomy under a bare `FAILED` — the reason is a
free-form `error: str` (`llc/adapters/base.py:29`, `llc/models/heartbeat_run.py:63`). The reference
work's five-kind taxonomy would be a **third** enum overlapping two existing closed ones, and this
repo's own recorded lesson (#13416, four unreconciled classification planes) is that adding a plane
costs more than it buys. **Rejected by hidden metrics**; the correct form is to make the existing
`FAILED` reason a bounded vocabulary, not to introduce a new parallel enum.

**Two further gaps found in our own code.**

- **`services/audit_logger.py` advertises a property it does not implement.** Its docstring calls
  the system "tamper-resistant" (`:9`); positive control — 34 function definitions in the file, and
  `tamper|hash_chain|hmac|signature|prev_hash` matches **once**, that docstring line. No hash
  chaining, no signing. The LLC activity log is honest about the same limitation
  (`llc/services/activity_log.py:1-9` says append-only is a service-layer convention), but the
  migration creates a plain table with no trigger or revoked grant, so neither trail is tamper-evident
  in the cryptographic sense. A claim in a docstring is a claim.
- **Cost never reaches the trace.** `llm_shared/base_provider.py:214` fans out every response to the
  observer registry with a hard-coded `0.0` cost, so OTEL and LangFuse spans always show a free call
  while the real number sits in two ledgers the span does not link to.

## Verdict

The reference work is not adoptable as code — single-operator desktop shape, a vendored inference
fork, a competing provider abstraction, and a codebase this early. What survived the weighing is four designs and one
posture:

| # | Item | Verdict | Effort |
|---|---|---|---|
| 1 | Prompt-drift detection (hash the prefix, compare) | adopt — **do this first** | trivial |
| 2 | Stable bytes first, volatile last; second cache breakpoint | adopt, gated on a live-backend A/B | trivial / moderate to prove |
| 3 | Tool-output budget on by default (our spill, not their compressor) | adopt the posture | trivial |
| 4 | Structure the tool-call channel — native tool-calling and real JSON schema, **not** hand-written grammar | adopt-with-conditions | significant |
| 5 | Loop-isolating benchmark mode on the existing eval harness | adopt-with-conditions | significant |
| — | Five-level approval ladder, typed categories, usefulness-based eviction, compact browser view, pointer-shaped memory, trace capture | **already ours, and finer-grained** | — |
| — | Vendored quantization fork, desktop packaging, single-operator approval model, telemetry-on-by-default, a third failure-kind enum | **rejected by hidden metrics** | — |

**The audit's more valuable output is what it found in our own code**, as with the previous
comparative audit. Eleven items, none of them the reference work's: the sophisticated agent loop
built and never instantiated (with parallel execution, cancel/pause/steer and a fail-closed approval
timeout all unreachable); the live approval hold that surfaces as chat text with no UI and no expiry;
identity-bearing GitHub publishing that crosses no gate; six gating subsystems with inconsistent
durability, defaults and approver checks; a detached graph task no disconnect cancels; a duplicated
iteration literal; a structured-output flag that splits the response cache while changing nothing;
a retry counter nothing increments; a second weaker JSON parser; four unwired memory pieces; and an
audit logger whose docstring claims a property the file does not implement.

**Confidence.** High on the AutoBot side: every claim is a file read at a cited line, every absence
claim carries a positive control, and the four load-bearing ones (`AgentLoop` never instantiated,
sequential dispatch, the GitHub gate hole, volatile-first prefix ordering) were re-read directly by
the session rather than taken from an audit. Medium on the reference-work side: its marketing page,
documentation index, README and six source modules were read; its benchmark numbers are
self-reported and were not reproduced. One correction during the audit: an early reading had the
ARIA snapshot renderer down as unwired; following the call chain found two live call sites, and the
real delta is that its output is returned unbudgeted.

## Findings and where they went

Every finding was searched against open **and** closed issues before any filing decision. Search
terms and their result counts are recorded so a nil result is distinguishable from an unsearched
one; each "no match" below was searched under at least two phrasings.

### Already filed — do NOT re-file

| Finding | Existing issue | Fit |
|---|---|---|
| `services/audit_logger.py` documents tamper-resistance it does not implement | **#17219** (open) | **Exact** — the issue quotes `audit_logger.py:10-11` by line and names two further writers with the same defect (`security_layer.py:669-679`). Our positive control (34 defs, one `tamper` match) corroborates it; nothing to add. |
| Tool-output spill is off by default | **#16619** (open) | **Exact** — "the tool-output spill is still off by default — verify it on a live run, then flip". Adopt item 3 is this issue. Sits under umbrella #16617. |
| Pre-action verifier and belief state unreachable | **#14031** (open, child of #13587) | Exact for that slice of the dormant loop. |
| Agent cannot ask a question mid-task | **#13592** (open, child of #13587) | Covers `ask_human`. |
| `/tasks/{id}/steer` route has no consumer | **#16993** (open) | Covers the steer half of cancel/pause/steer. |
| Tiered L0–L4 stack off, layers unreachable | **#13685** umbrella, **#13686**, **#13867** | Unchanged; adopt item 2 touches the same call site and must not revive it silently. |
| Approval answerable only at the screen | **#14068** (open) | Related to but distinct from the hold-has-no-UI finding below. |
| Tool-approval planes never differenced / gated twice / scope key | **#13416**, **#13250**, **#13709** (all open) | Unchanged from the prior audit. |

### Three closed threads whose condition is still live

**#7420** (closed COMPLETED 2026-05-16) audited "chat LLM does not expose MCP tools as native
function tools", confirmed the gap, and spawned **#7910** (Anthropic + OpenAI-compatible native
function calling) and **#7911** (Ollama native function calling) — both also **closed**.

The provider half landed and is real: `llm_shared/providers/openai_compatible.py:137-139`,
`anthropic.py:361-369`, `ollama.py:122-136`, `mistral.py:123-131`, `bedrock.py:212-216` all build
`tools`/`tool_choice`. **Nothing populates the field.** Verified by positive control: three
`LLMRequest(` construction sites exist (`services/llm_service.py:237,339,599`) and not one passes a
`tools` argument; every `tools=[...]` elsewhere in the backend is skill-manifest metadata, not an
LLM request. The live chat loop still injects a `<TOOL_CALL>` tag in prose
(`chat_workflow/manager.py:1991`, `llm_handler.py:631`) and parses it with tolerant regexes.

So #7420's original implication — the chat LLM does not use native function calling — is **still
true**, while the three issues that were meant to end it are closed. This is the
"declared control that does not execute" shape of umbrella **#17217** applied to a capability
rather than a control, and it is why adopt item 4 is a *wire-in*, not new construction.

**The same shape twice more.**

- **#12645** (umbrella, closed COMPLETED) / **#12652** (closed COMPLETED 2026-08-01) —
  "converge internal forks onto canonical reusable implementations" / "parallel chat-workflow
  drivers over the same tool-dispatch seam". #12652 names `MAX_CONTINUATION_ITERATIONS`, the
  LangGraph successor, and `async_chat_workflow.py` as the third parallel entry, by name. Today:
  `async_chat_workflow.py` still exists, `MAX_CONTINUATION_ITERATIONS` still has 7 references in
  `chat_workflow/manager.py`, `chat_workflow/graph.py:1530` still carries a bare `< 5` literal
  instead of the constant, and the legacy loop is still the live fallback
  (`manager.py:3860-3869`). The convergence did not land and the thread closed anyway — which is
  why the duplicated-iteration-literal finding is a **residual of #12652**, not a new observation.
- **#11221** (closed COMPLETED 2026-07-10) — "AgentLoop is never instantiated — decide wire vs port
  vs document". The guards were ported and the rest documented; parallel tool execution,
  checkpoint/resume and cancel/pause remain unreachable, tracked by nothing.

Three independent threads, each closed as completed, each with its condition still true in the
code. This is the exact failure mode **#17218** ("fail when a declared control has no production
call path") proposes a CI guard for, and it is the strongest argument in this audit for building
that guard before filing anything else.

### No existing issue found — new

Searched phrasings are given; all returned nil on both states.

| Finding | Searches run |
|---|---|
| Identity-bearing GitHub publishing (`api/integration_github.py:230-293`) crosses no gate while `ApprovalCategory.PUBLISHING` exists | "integration_github pull request comment", "publishing approval category gate", "github integration agent posts comment" |
| Detached `graph_task` no disconnect cancels (`chat_workflow/manager.py:3877-3930`, `:4001-4047`); LLM call has `total=None` (`:2225`) | "graph task cancel client disconnect", "LangGraph cancellation stream", "cancel in-flight chat generation stop button", "LLM request no total timeout" |
| Iteration cap is two literals (`manager.py:412`, `graph.py:1530`) | "MAX_CONTINUATION_ITERATIONS iteration limit" |
| `structured_output` is decorative for every cloud provider (the cache dimension itself is a deliberate #10665 decision, not a defect) | "structured_output response_format provider", "structured_output cache key" |
| Cognifiers bypass the shared JSON parser and so never got #11587's sanitization tier | "json parser duplicate cognifiers", "extract_json_object", "parse_llm_json_response" |
| No prompt-drift detection anywhere (adopt item 1) | "prompt drift hash system prompt", "essential story prompt prefix cache" |
| Volatile block prepended ahead of the stable prefix (adopt item 2) | "essential story prompt prefix cache" |
| Eval harness cannot measure task success or model scaling (adopt item 5) | "eval golden trajectory corpus benchmark" |

### Residual on an existing thread — append, don't duplicate

- **The dormant loop's remaining unreachable capabilities.** **#11221** ("decide wire vs port vs
  document") was closed COMPLETED on 2026-07-10, resolved by porting the *guards* to the live seam
  and documenting the rest. Children #14031, #13592 and #16993 carry the verifier/belief-state,
  ask-human and steer slices. Still covered by nothing: **parallel tool execution**
  (`ParallelToolExecutor`, reachable only from the dormant module while the live seam dispatches
  sequentially at `tool_handler.py:3701`), **checkpoint/resume**, and **cancel/pause**. Belongs as a
  child of **#13587**, whose thesis is exactly "the best guard machinery is not on the production
  path".
- **The live approval hold has no structured surface.** #14068 says an approval can only be answered
  at the screen; #17220 says the work-item gate is inert without a work item. Neither says what this
  audit found: when the gate *does* fire, the hold is an ephemeral chat message — never an
  `Approval` row, never an `APPROVAL_REQUIRED` bus event, while the frontend's `useToolApproval.ts`
  listens only for the event the dormant loop emits (#4959/#5014 wired it there) — and it has no
  expiry. Child of #17217 or #13587.
- **Tool-argument retry budget never decrements.** **#16116** already disputes a neighbouring
  docstring claim in the same region (`agent_loop/loop.py:147-149` says schema self-correction is
  unported; it shipped in #4482). The complement belongs on that thread: it shipped, and
  `_schema_retry_count` is written by no production code, so `retries_left` at
  `chat_workflow/tool_handler.py:1018` is permanently `max_schema_retries`.
- **Memory's unwired pieces** — `MemoryManager.provider` router uncalled, `memory.update_graph`
  registered (`celery_app.py:129`) and never enqueued, `GeneralStorage.embedding` write-only,
  `GeneralStorage.search()` a `LIKE` scan with no FTS index repo-wide, facts consolidation shipping
  `AUTOBOT_FACTS_CONSOLIDATE_DRY_RUN=1`. Umbrella **#10603** ("wire built-but-disconnected
  machinery") is the right parent; **#12551** (self-improving memory epic) is adjacent.
- **Gating subsystem inconsistencies.** #13250, #13416, #17220, #17225 and #16950 cover parts. Not
  covered: plan approvals held in a plain instance dict and lost on restart
  (`services/workflow_automation/executor.py:945-946`); `approve_plan`
  (`routes.py:384-419`) not calling `require_interactive_human` and admitting in its own docstring
  that it does not enforce ownership; `ApprovalStatus.WITHDRAWN`/`EXPIRED` set by no non-test code;
  no requester≠approver check anywhere; `api/terminal_handlers.py:1080-1088` blocking nothing at
  `STANDARD`; and the MCP bridge asking the *model* to supply `approved: true`
  (`chat_workflow/tool_handler.py:958-992`).
