---
title: "Research: a confidence-gated finite-action agent loop"
created: 2026-09-25
reviewed: 2026-09-25
status: current
tags:
  - research
  - agent-loop
  - orchestration
---

# Research: a confidence-gated finite-action agent loop

- **Source:** the reference harness (URL and vendor withheld per the anonymization rule)
- **Fetched:** 2026-09-25 (read-only via the GitHub contents API; no clone)
- **Phase:** 1 (Source Analysis) — Phase 2 gated on user approval

---

## Source Analysis: a confidence-gated finite-action agent loop over a decision-only model

### What It Is

A permissively licensed package (a low-thousands-of-lines core across a handful of modules, plus a
small protocol server and CLI) that turns a **decision-only model** into an agent loop. The model class
it targets is not a text generator: a vendor's "reflex" model that takes a `state` object plus a
map of typed `questions` and returns, in one forward pass, an answer per question with a full
probability distribution and a confidence — three primitives only (`choice` over ≤255 named
options, `noul` yes/no as a probability, `score` over an ordered scale). It cannot write text,
cannot call a tool, cannot plan, cannot remember. Everything an agent needs beyond "pick one" is
therefore the harness's job, which is the whole design premise.

The loop is: observe the environment → compile the declared action space into that step's
questions → encode goal+observation+bounded history into the state budget → one model call →
gate the answer against a risk-tiered confidence threshold → execute → record. One model round
trip per step, ~200ms, self-reported at ~$0.0002 per completed 5-step run.

**Maturity: pre-alpha, days rather than months old.** A small contributor set with most commits
by one author, an early pre-1.0 version, and a low issue count. There
is a 10-file test suite but **no CI**: `.github/` contains only `images/`. Nothing runs those
tests on push.

### Architecture & Key Patterns

Seven components with hard "never does" boundaries, which is the part that transfers:

| Component | Owns | Never does |
|---|---|---|
| `Environment` | `observe() -> Observation`, `execute(action, params) -> Result` | decide |
| `ActionSpace` | declared actions, each parameter as a finite set, risk tier, `compile()` | grow at run time from model output |
| `StateEncoder` | goal + filtered observation + bounded history within a token budget | send raw dumps |
| `Provider` | one `decide(state, questions)` over the wire, retry on 429/5xx | hold prompts or policy |
| `Gate` | per-risk thresholds, the "nothing clears the bar" outcome | run anything |
| `Controller` | the loop, budgets, termination, stuck detection, cancellation | encode or execute |
| `Trace` | every step whole, distributions included | summarise the distribution away |

Key patterns:

- **Enforcement by omission.** An action whose candidate list is empty this step, or that the
  caller disabled, is simply not in the questions map. The model cannot choose what it was not
  shown (`actions.py`, `compile()`). Refusal is the backstop, not the mechanism.
- **Free text does not compile.** A parameter that is not `choices` / `from: <candidate list>` /
  `flag` / `levels` raises `ActionSpaceError` at *load* time, never at run time
  (`actions.py:73`). The type system encodes the model's limitation.
- **Weakest-link gating, not product.** The gate takes `min()` over the action's own confidence
  and every parameter's probability (`gate.py:65`), compares it to a threshold chosen by the
  action's declared risk (`read` 0.5 / `write` 0.7 / `destructive` 0.9 by default). The question
  is "is there one shaky judgment", not "is the joint probability high".
- **Terminal states are a closed set.** `completed` (goal_reached | finish_insisted |
  environment_terminal), `incomplete` (max_steps | timeout | no_confident_action |
  repeated_action | escalation_requested), `failed` (environment_error | provider_error),
  `cancelled`. `finish` and `escalate` are *actions in the choice set*, not generated prose, so
  the harness always knows why it stopped.
- **Configuration as one versioned YAML.** `version`, `instructions`, `gate`, `encoder`,
  `tunables`, `actions`, `objective`. The trace carries the version that produced it
  (`config.py`, `Run.config_version`).
- **Objective declared by the environment, not the runner.** A tiny predicate DSL (`pass`,
  `failure`, ordered `metrics`, `locus`) that an outer tuning loop reads without knowing
  anything about the domain (`objective.py`).

### Notable Implementation Details

- **The handoff record.** When a run ends `no_confident_action` or `escalation_requested`, the
  controller attaches the refused step's full state, questions, answers, weakest judgment and the
  threshold it missed (`controller.py:174`). That is a structured escalation payload for whoever
  takes over — a bigger model or a human — rather than a log line saying "gave up".
- **Stuck detection by state hash.** The signature `(action, params, sha256(observation.text +
  fields))` compared to the previous step; identical means the action changed nothing, and the run
  ends `repeated_action` (`controller.py:140`). Cheaper and stricter than a step counter.
- **`finish` requires a second opinion from the same call.** The model's chosen `finish` is
  cross-checked against a separate `goal_reached` question answered in the *same* request. Below
  the finish threshold it costs one more step; chosen twice while the goal check stays low, the
  run ends `finish_insisted` — completed, but the trace says the model overrode its own check
  (`controller.py:118`).
- **Ordered, recorded context degradation.** The encoder drops in a fixed order — oldest history
  lines, then clip the observation summary to 2,000 chars, then memory, then history entirely,
  then observation fields largest-first — and appends a human-readable note per drop to the step's
  trace (`encoder.py:60`). What was thrown away is evidence, not a silent truncation.
- **Real-time mode inverts the refusal rule.** An environment can set `realtime: true`; a refused
  or repeated decision then counts as a clock tick rather than a stop, history is clamped to 3
  steps, and a refused *read*-risk action is promoted to run anyway with the trace noting it ran
  below threshold (`controller.py:91`). The reasoning: in a moving world, not deciding is itself a
  decision with consequences.
- **Optional parameters get a meta-question.** For each optional param the compiler emits a second
  `noul` — "does the goal or observation actually say anything about this?" — and falls back to the
  declared default when that is below 0.5. This is how "unspecified" is expressed by a model that
  cannot say "I don't know".
- **MCP servers compile to action spaces.** Tools whose JSON Schema is fully enumerable (enum,
  `oneOf` consts, boolean, bounded integer ≤10 values, or an `x-candidates` extension) become
  actions; everything else is listed **with its reason** rather than silently dropped
  (`tools.py`). Risk tier comes from MCP annotations (`readOnlyHint` → read, `destructiveHint` →
  destructive).
- **A scripted provider for probes.** A fake provider that plays a fixed action sequence with
  every probability at 0.99, so the gate never interferes — a run made to *measure the
  environment* rather than to reach the goal.
- **Environment legibility is the tuning surface, not the gate.** The source documents a measured
  case: an observation that said "packed" but never said "not shipped" put the model at 0.73–0.84
  against a 0.8 destructive gate, failing 2 runs in 5; adding the goal's false predicates
  explicitly ("Shipped: no. Cancelled: no.") moved it to 0.86–0.93, 5 in 5, with **no gate
  change**. Stated rule: state the goal's own predicates every step including the false ones;
  never tune the gate to fit the environment.

### Strengths

- The component boundaries are genuinely enforced, not aspirational — the "never does" column maps
  to code with no back-channel. Swapping environment + action space is the only change needed to
  drive a browser, an MCP server, a local process or a game.
- Every claim about why a run ended is derivable from the trace, which keeps full distributions
  rather than the argmax. "Chose X at 0.73 with Y at 0.27" survives; a summarising view is a view.
- Failure modes are typed and exhaustive, and the two "I couldn't" modes carry a structured
  handoff instead of dying silently.
- Load-time validation of the action space: a declaration the model could not act on fails before
  the first call, with an error naming the fix.
- Unsupported MCP tools are enumerated with reasons — *nothing found* is distinguished from *did
  not look*, which is the discipline we demand of our own guards.
- Small and readable: nine core modules, no framework, `yaml` + `httpx` the only hard deps.

### Weaknesses / Limitations

- **No CI at all.** A 10-file test suite exists and nothing runs it. `.github/` holds images only.
- **Bus factor 1**, days rather than months of history, a pre-1.0 version, and a single-vendor model dependency with
  exactly two hosts for one wire format. `provider_from_env` raises if neither key is set; there
  is no degradation path to a conventional LLM.
- **Declared-but-unwired features.** `two_request` is parsed, stored and serialized, and read by
  nothing — behaviour never changes. Worse: `guards` (the design doc's examples are `is_safe`
  and `needs_human`) are compiled into every request and their answers recorded in the trace, but
  **no consumer reads them** — `gate.judge()` looks only at the action and its parameters. A
  guard called `needs_human` is asked, answered, and ignored.
- **Swallowed error on the trace write.** `except OSError: pass` (`controller.py:181`) — a run
  can believe it persisted its trace when it did not. Exactly the pattern our own rules forbid.
- **Silent narrowing at the option ceiling.** A candidate list over 255 entries is cut to the
  first 255 *in dict order* — arbitrary, unranked — and the count dropped is recorded in a
  side-channel the model never sees (`actions.py:250`). The model then decides confidently over a
  truncated world.
- **The objective DSL fails open.** `_failure_steps` regex-matches four forms and `return out`
  (empty) for anything else. An unparseable or misspelt `failure:` predicate reports **zero
  failures**, indistinguishable from a clean run.
- **Skill text is truncated mid-sentence.** `SKILL_BUDGET_CHARS = 12000`, then `text[:room]`
  (`config.py:70`) with no boundary awareness and no warning surfaced to the caller.
- **Wholly synchronous.** `httpx.Client` (sync), `time.sleep` backoff inside the loop, threads for
  cancellation. Embedding it in an async service means a thread pool per run.
- **The protocol server is hand-rolled** on stdlib `ThreadingHTTPServer` with a static
  `--api-key`, ~570 lines in one file. No TLS, no rate limiting, no auth beyond the shared secret.
- **Calibration is assumed, not demonstrated.** The entire safety story rests on the vendor's
  reported probability being calibrated. The source's own design doc concedes "wrong choice at
  high confidence is still possible", and there is no reliability curve, no threshold-vs-error
  table — despite the design doc promising exactly that ("the error rate at each confidence
  threshold").
- **The gate is not universal**: real-time mode deliberately runs read-risk actions below
  threshold.
- **Honest but narrow boundary on browsers**: a canvas-drawn page gives a DOM observation nothing,
  and the source says so — driving one needs a page-side adapter, not a general environment.

### Visible vs Hidden Metrics

**Visible (all self-reported, single author, a single measurement date):**

- 15 benchmark rows: 3 scenarios × 5 runs, goal met 15/15, mean 199–241ms model latency,
  0.20–1.45s wall, $0.000044–$0.000265 per run.
- A self-run conformance report claiming a full pass against an interop protocol's base class.
- Rapid early attention on a social-coding platform.

**What the visible numbers do not support:** the benchmark environment is the package's own toy
order-fulfilment fixture, deterministic and ≤6 steps; one of the three scenarios completes in a
*single* step. Token counts are byte-identical across all 5 runs of a scenario, so the runs vary
only in provider latency. Crucially, the design doc's headline promise — "the same environment
driven by this loop **and by an LLM harness**, reporting steps to goal, wall time, cost, and the
error rate at each confidence threshold" — is **not** what the report contains. There is no
comparison arm. The 200ms/$0.0002 figures are real but uncontested.

**Hidden costs an adopter inherits:**

- **Model lock-in is total.** The wire format, the three primitives, the 255-option ceiling, the
  32k state cap and the confidence semantics are one vendor's. There is no second implementation
  of this model class to fall back to, and the harness has no abstraction that would let a
  conventional LLM stand in.
- **The action space becomes a maintained artifact.** Every tool, every parameter, every
  enumerable value must be declared and kept in sync with the system it drives. Drift between the
  declaration and reality is silent — the model just never gets offered the action.
- **The environment becomes the tuning surface.** The source's own measured lesson is that fixing
  behaviour means rewriting what the observation *says* — including asserting false predicates
  explicitly every step. That is a per-environment, per-goal authoring burden with no
  generalization, and it is invisible until a run fails at 0.73 against a 0.8 gate.
- **Threshold ownership.** Someone has to own numbers like 0.8-for-destructive and defend them,
  with no calibration data shipped to ground them.
- **Operational load of a second model provider**: another key, another rate limit (the vendor's
  own quotas), another vendor's availability inside the hot path of every step.
- **Learning curve** of a genuinely unusual vocabulary — reflex, noul, weakest judgment, locus,
  probe, handoff, the four channels — which any team reading this code must acquire.
- **Failure mode nobody advertises:** a wrong choice at high confidence passes the gate. Gating
  bounds *uncertain* errors, not *confident* ones, and nothing here detects the latter.

**Weighing.** For AutoBot the visible wins (millisecond, micro-cent decisions) apply only to steps
that are already reducible to "pick one of N enumerated options with no free text". Where that is
true the win is real and large. Where it is not, the hidden cost of forcing a decision into a
finite declared action space exceeds the saving. The decisive observation is that the *mechanisms*
here — risk-tiered confidence gating, enforcement by omission, typed terminal reasons, a
structured handoff on refusal, ordered recorded context degradation, distribution-preserving
traces, environment-declared objectives — are **model-agnostic**. They can be lifted onto any
loop, including one driven by a conventional LLM that reports no probabilities (thresholds would
then need a different confidence source). Adopting the mechanisms carries almost none of the
hidden cost; adopting the *model dependency* carries all of it. That split is the recommendation
this analysis would take into Phase 2.

---

## AutoBot Comparison: the reference harness → AutoBot

**Method.** Six parallel read-only audits over the AutoBot tree (agent-loop termination, action
permission, context compaction, MCP ingestion, escalation/handoff, objective & eval), then every
load-bearing claim below re-verified in this session by direct grep/read. Claims taken from an
audit report and *not* independently re-checked are marked *(reported)*.

**The one fact that reframes everything.** `agent_loop/` is not the production path.
`agent_loop/loop.py:120-126` says so itself — "this class is not instantiated anywhere in
production". Verified: `grep -rn "AgentLoop("` outside tests returns one hit, a docstring usage
example at `agent_loop/__init__.py:28`. The live seam is `chat_workflow/graph.py` (LangGraph)
plus `chat_workflow/tool_handler.py::_dispatch_tool_call`. This is already filed as **#14031**.
So for every mechanism below the question is asked twice: does AutoBot have it, and does it have
it *where requests actually go*.

**Correction to #14031's current text:** the pre-action verifier is no longer unreachable. It has
a production caller at `chat_workflow/tool_dispatch_guards.py:154` `enforce_pre_action_verifier`,
whose own docstring records it as "its first production caller", wired into the dispatch chain at
`chat_workflow/tool_handler.py:3264-3335`. The belief-state half of #14031 was not re-checked.

---

### What We Can Adopt

#### 1. Map MCP tool annotations to a risk tier at ingestion — *adopt-with-conditions, trivial*

- **Applies to:** `type_defs/mcp.py:44-51` (`MCPToolDefinition`), `api/mcp_registry.py:438-462`
  (`_build_tool_entry`), `autobot_shared/auth/mcp_tool_permissions.py`.
- **Already-exists audit:** `grep -rn "readOnlyHint|destructiveHint|idempotentHint|openWorldHint"`
  over `*.py`/`*.ts`/`*.js`, excluding worktrees, venv and `node_modules` → **zero hits
  repo-wide**. `MCPToolDefinition` declares `name`, `description`, `input_schema`, `category`,
  `tags` and no `annotations` field at all. Risk today is hand-declared per tool in
  `mcp_tool_permissions.py`, read at `api/mcp_registry.py:453`. Not covered by any of the six
  tasks in MCP umbrella **#13227**.
- **Visible benefit:** every external MCP server already publishes these hints; a destructive tool
  from a newly-added server would carry a risk signal on arrival instead of defaulting to whatever
  the hand-maintained map happens to say.
- **Hidden cost:** the hints are **server-supplied and advisory**. Trusting `readOnlyHint: true`
  to *lower* a gate hands a malicious server a privilege-escalation lever — the opposite of the
  win. The adoption is only safe in one direction.
- **Verdict:** adopt as a risk **floor-raiser only** — an annotation may escalate a tool's tier,
  never de-escalate it, and the hand-declared `required_permission` stays authoritative. In that
  shape the hidden cost is bounded and the benefit survives.

#### 2. An unsupported tool is reported with its reason, never dropped — *adopt, trivial*

- **Applies to:** `skills/sync/mcp_client.py:133-140`, `services/mcp_aggregation.py:60-68`,
  the external-servers API surface.
- **Already-exists audit:** verified by reading both. `mcp_client.discover_tools` wraps
  `MCPToolDefinition.model_validate(raw)` in `except Exception` and emits
  `logger.warning("MCPClient: could not parse tool %s: %s", ...)` — the tool then simply is not in
  the returned list. `mcp_aggregation.discover_tools_multi_server` logs **every** discovery
  exception as `"skipping unreachable server %s"`, so a schema-parse failure is reported to the
  operator as a network problem. No caller-visible error field on either path *(reported: no
  `tool_errors`/`last_error` on `api/mcp_external_servers.py`)*.
- **Visible benefit:** an operator who adds an MCP server and sees four of its six tools can find
  out why. Today the only record is a backend log line, and the label on it is wrong.
- **Hidden cost:** one new response field plus a UI surface to render it, and the exception text
  must be sanitized before it reaches an operator-facing field — raw tracebacks carry internal
  filesystem paths, which our own rules forbid in outward artifacts.
- **Verdict:** adopt. This is `MEASUREMENT_DISCIPLINE.md`'s *nothing found* vs *did not look*
  applied to tool discovery, and the source is straightforwardly ahead of us here: it enumerates
  every uncompilable tool with its reason and exposes them through a dedicated command.

#### 3. Weakest-link confidence gating on the typed-decision seam — *adopt-with-conditions, blocked on measurement*

- **Applies to:** `llm_shared/decisions.py` and its three live callers —
  `services/claim_verifier.py:35`, `services/autoresearch/scorers.py:28`,
  `agents/ac_verifier.py:55`.
- **Already-exists audit:** the *interface* is already ours and already wired. `decisions.py`
  (#17308, closed) is the same `decide(state, questions)` shape as the source's, with the same
  three primitives — `ChoiceQuestion` / `ScoreQuestion` / `BooleanQuestion` against the source's
  choice / score / noul — one round trip, `"probability"` required on every answer fragment
  (`decisions.py:125,163,198`). What is missing is a **consumer that thresholds it**:
  `claim_verifier.py:305` passes the probability through into a record, `ac_verifier.py:190,210,
  217` stores it on `CriterionResult`, and nothing compares it to anything. Separately, no
  per-action confidence check exists at the dispatch seam *(reported: no confidence hits in
  `tool_dispatch_guards.py` or the `_dispatch_tool_call` path)* — expected, since an ordinary
  tool call carries no probability at all.
- **Visible benefit:** a verdict the model is unsure of stops being consumed as a fact.
- **Hidden cost — decisive.** `decisions.py:88-97` defines `Calibration.SELF_REPORTED` vs
  `MEASURED` and its module docstring states that the local backend reports `SELF_REPORTED` —
  "the number is the model's stated confidence, not a calibrated frequency… Saying otherwise
  would be a claim nobody here has measured". Gating on an unmeasured number does not add a
  safety property, it manufactures the *appearance* of one, which is worse than no gate because
  reviewers stop looking. The source has exactly this problem and, unlike us, ships no marker for
  it and no reliability curve.
- **Verdict:** adopt-with-conditions, **sequenced behind the measurement**. Run
  `scripts/benchmark_decision_backends.py` against a labelled sample to move a backend to
  `Calibration.MEASURED`; only then add the weakest-link rule, and only for answers whose
  calibration is `MEASURED`. Until then the probabilities remain legitimate for *ordering* and
  illegitimate for *gating* — which is what #17308 already decided and what its own acceptance
  criterion says.

#### 4. A typed door from a stalled cheap loop to a stronger tier — *adopt-with-conditions, significant*

- **Applies to:** `llm_shared/tiered_routing/complexity_router.py:121-194`
  (`route_with_escalation`), called from `llm_multi_provider.py:254-257`.
- **Already-exists audit:** the door exists and is wired, but it opens on the wrong signal — it
  scores *input complexity* at request time and pre-routes to a stronger provider above
  `claude_escalation_threshold`. Nothing routes on the agent's own give-up *(reported: no wiring
  from `LoopOutcome.ABSTAINED/STAGNATED/HALTED` to a tier change)*, and `LoopOutcome` lives in the
  dormant loop anyway, so the production turn has no give-up signal to route on (see item 5).
- **Visible benefit:** the run that stalls is precisely the run where a stronger model is worth
  paying for; today it just ends.
- **Hidden cost:** cost amplification at the worst moment. A stalled run has already burned its
  budget; re-running it at the expensive tier doubles the bill on exactly the population most
  likely to stall again. Needs a per-task escalation budget and stall-dedup, neither of which
  exists.
- **Verdict:** adopt-with-conditions, **blocked on item 5** — there is no typed stall signal in
  production to trigger it.

#### 5. A closed, typed set of terminal reasons for the production turn — *adopt-with-conditions, significant*

- **Applies to:** `chat_workflow/graph.py:1511-1532` (`route_after_execution`),
  `chat_workflow/tool_handler.py`, `chat_workflow/tool_dispatch_guards.py`.
- **Already-exists audit:** the dormant loop already has it — `LoopOutcome`
  (`agent_loop/types.py:63-81`: COMPLETED / ABSTAINED / STAGNATED / CANCELLED / HALTED / FAILED /
  TIMED_OUT_WAITING). Production has nothing equivalent. Verified: `route_after_execution` returns
  raw node-name strings (`"persist_conversation"`, `"generate_response"`), and a count of literal
  `"status": "<value>"` assignments across `tool_handler.py` + `tool_dispatch_guards.py` gives
  **ten distinct free-text values** — `error` (17), `success` (11), `schema_error` (3),
  `pending_approval` (2), and one each of `pending_delegation`, `gated`, `executed`, `completed`,
  `ast_rejected`, `approval_required`. Two of those pairs are synonyms carrying different spellings
  (`pending_approval`/`approval_required`, `executed`/`completed`).
- **Visible benefit:** "why did this turn end" becomes answerable from data rather than from
  reading branches, which is the field the eval harness in **#17279** needs in order to compare
  two loops at all.
- **Hidden cost:** this is a cross-cutting change on the hottest production path, over a
  serialized vocabulary the frontend consumes, touching `tool_handler.py` — a hub file. A
  behaviour-preserving refactor with no functional gain is exactly the change that should not be
  made while the test that would prove it changed nothing (#17279) does not yet exist.
- **Verdict:** adopt-with-conditions — take the **vocabulary**, not a rename. Define the enum with
  the existing strings as its values so the wire format is unchanged, then fix the two synonym
  pairs behind it. Sequence after #17279.

#### Rejected by hidden metrics

- **Enforcement by omission for the main tool set.** The source's strongest safety property is
  that an infeasible action is absent from the question map rather than refused after the fact.
  AutoBot is the other way round: `tools/tool_registry.py:893` `get_available_tools()` returns a
  fixed list that reaches every modality agent's system prompt, and all governance runs at
  `_dispatch_tool_call` (`chat_workflow/tool_handler.py:3264-3335` → the ordered guard chain in
  `tool_dispatch_guards.py`) *after* the model has already named the tool *(reported)*. Two narrow
  paths already do filter — `chat_workflow/code_exec/shim_codegen.py:22-31` `injectable_tool_set()`
  strips `forbidden_work` and `SENSITIVE_TOOLS` from the code-interpreter sandbox, and
  `chat_workflow/delegation.py:100-102` `forbidden_to_claude_tools()` converts a profile into
  `--disallowedTools` for a delegated subprocess *(reported)*. **Rejected as a general change:** a
  tool list that varies per turn breaks the stable system-prompt prefix that **#17278** exists to
  protect, so every turn would pay a prefix-cache miss to buy a property the guard chain already
  provides; and a tool that silently vanishes teaches the model nothing, whereas the current
  refusal returns a message it can act on. The source can afford omission because its entire
  question map is rebuilt every step at a few hundred tokens. Ours is not. Keep omission where it
  already is — at sandbox and subprocess boundaries, where the boundary is crossed once.
- **The free-text-impossible action space.** Not transferable in principle: our models generate,
  and forbidding free-text parameters would delete the capability rather than a risk.
- **The model, the wire and the vendor.** Single-vendor, closed-weight, two hosts, no fallback.
  #17308 already recorded the decisive objection when it chose to own the interface and not the
  vendor: a model in this category is documented **by its own vendor** as steerable by adversarial
  content in the state — which is why `decisions.py` explicitly excludes the pre-action verifier
  gate from that seam, the one place where a cheaper steerable classifier would do most harm.

---

### What We Already Do Better

1. **Calibration provenance.** `decisions.py:88-97` ships a `Calibration` enum distinguishing
   `SELF_REPORTED` from `MEASURED`, and `decisions_exclusions_test.py` *enforces* the list of
   seams the decision path must never be used on. The source's entire safety story rests on its
   probabilities being calibrated; it ships no marker, no reliability curve and no measurement,
   while its own design doc concedes a wrong choice at high confidence is possible. We mark the
   gap; it does not.
2. **Repetition detection that survives a legitimate poll.** `autobot_shared/repetition_guard.py:
   51-117` keys on the pair *(call fingerprint, last result hash)* and resets the count the moment
   the result changes *(reported)*. The source compares `(action, params, observation hash)` only
   against the **immediately previous** step (`controller.py:140`), so it both halts a legitimate
   repeated poll and misses a non-adjacent repeat.
3. **Refusal with an argument, not just a number.** `chat_workflow/tool_dispatch_guards.py:154-240`
   runs an adversarial verifier on sensitive calls and, on a soft block, attaches
   `verifier_rationale`, `verifier_refutation_probability` and `verifier_degradation` to the
   `pending_approval` payload. #17306 went further: a block caused by a degraded verifier is
   labelled `degradation=call_failed` rather than `prob=0.00`, because a fail-closed block is not
   a reading of zero. That is precisely the discipline the source's objective DSL breaks (below).
4. **A human who cannot be impersonated.** `api/user_management/human_decider.py:27-36`
   `require_interactive_human()` refuses service keys, run/device JWTs and agent tokens, and
   `classify_author_type()` labels non-human credentials *(reported)*. The source has no human in
   its loop at all — `escalate` is a terminal action that ends the run.
5. **Indexed browser controls *with staleness detection*.** Both projects number the page's
   interactive elements so the model picks an index instead of inventing a selector
   (`autobot-browser-worker/element-index.js`, #11537). Only ours refuses an index chosen against a
   different element count: `resolveElementByIndex` at `:105-110` returns "Page changed since state
   was captured (expected N elements, found M) — call browser_state again before retrying."
6. **Argument-shape-aware command risk.** `secure_command_executor.py` elevates on flag shape
   (`--privileged`, `-v /:`, env-prefix hijacks) with `_RISK_ORDER` taking the strictest across
   chained sub-commands *(reported, and consistent with the prior audit in
   `desktop-worker-harness-approval-and-compaction.md`)*. The source has three flat tiers declared
   per action and cannot express "this action, but not with that argument".
7. **Priority-tiered context allocation that records what it dropped.**
   `context_window_manager.py:88-102` — `ContextAllocation` carries `trimmed` and `dropped` lists
   explicitly so "an overflowing prompt" does not "ship silently degraded", logged by callers at
   `chat_workflow/llm_handler.py:768-779` *(reported)*. Same discipline as the source's encoder,
   over a harder problem: ours allocates across priority tiers, the source drops down one fixed
   list.

**One place the source is ahead on discipline, and it is worth naming:** its objective DSL
(`objective.py`) fails *open* — an unparseable `failure:` predicate returns zero failures,
indistinguishable from a clean run. We have the same class of bug and have already filed it
(**#15826**, "79 of 133 tree-scanning guards can report clean having examined nothing"). Neither
project has solved it; only one of us is tracking it.

---

### Gaps & Opportunities

Ordered by impact. Most of what this comparison surfaced is **already filed** — recorded here as
witnesses, not re-filed, per the one-defect-one-fix rule.

| # | Gap | Status |
|---|---|---|
| 1 | No task-success measurement, so no loop change is falsifiable | **#17279** (umbrella #17271) — witness |
| 2 | No config-version identifier on a run record; prompt edits are silent | **#17277** — witness |
| 3 | A disconnected client leaves the turn running; no total timeout | **#17273** — witness |
| 4 | Approved MCP tool schemas cached, never re-verified against the server | **#13414** — witness |
| 5 | `MCPBridgeManifest.resource_limits` declared, set by no bridge | **#13229** (umbrella #13227) — witness |
| 6 | Plugin capabilities granted but `CapabilityChecker.check()` never called | **#16755**, **#17459** — witness |
| 7 | `AgentLoop` has no production caller (verifier half now resolved) | **#14031** — witness + correction |
| 8 | MCP annotations never ingested — no protocol-native risk signal | **new** |
| 9 | Unparseable MCP tool dropped to a log; any discovery failure labelled "unreachable" | **new** |
| 10 | Two independent hardcoded iteration caps for one budget | **new** |
| 11 | Three timeout fields declared in the loop config and read by nothing | **new** |
| 12 | Ten free-text tool-status spellings, two of them synonym pairs | **new** |

**The four new defects, with the evidence verified in this session:**

- **`chat_workflow/graph.py:1530`** — `if state.get("should_continue") and state.get(
  "iteration_count", 0) < 5:` — a bare literal duplicating `chat_workflow/manager.py:412`
  `MAX_CONTINUATION_ITERATIONS = 5`, which is referenced properly at six other sites in
  `manager.py`. Raising the constant does nothing on the LangGraph path, which is the production
  path. Violates the project's "never hardcode" rule at a live budget.
- **`agent_loop/types.py:190-192`** — `iteration_timeout_ms = 60000`, `tool_timeout_ms = 30000`,
  `total_task_timeout_ms = 600000`. `grep -rn` for all three across the repo returns **only their
  own declaration**. Three named safety budgets that enforce nothing; the comment above them
  ("kept as specific values for tool execution timing") reads as though they do. Same class as
  #17217's declared-controls-that-do-not-execute.
- **MCP discovery is silent about what it rejected** — `skills/sync/mcp_client.py:136-139` drops an
  unparseable tool behind a `logger.warning`; `services/mcp_aggregation.py:66-67` logs *every*
  exception, schema failures included, as `"skipping unreachable server"`. An operator debugging a
  missing tool is told the wrong thing.
- **MCP annotations are never read** — zero hits repo-wide for the four hint names;
  `MCPToolDefinition` has no `annotations` field.

---

### Specific Code/Files Affected

| File | Change |
|---|---|
| `type_defs/mcp.py:44-51` | add an `annotations` field to `MCPToolDefinition` |
| `api/mcp_registry.py:438-462` | map annotations onto a risk floor in `_build_tool_entry`; never below the declared `required_permission` |
| `skills/sync/mcp_client.py:133-140` | return rejected tools with their reason alongside the accepted ones |
| `services/mcp_aggregation.py:60-68` | distinguish transport failure from schema failure in the log and in what is returned |
| `chat_workflow/graph.py:1530` | reference `manager.MAX_CONTINUATION_ITERATIONS` instead of the literal `5` |
| `agent_loop/types.py:190-192` | enforce the three timeouts in `agent_loop/loop.py`, or delete the fields and say where the budget really lives |
| `chat_workflow/tool_handler.py`, `tool_dispatch_guards.py` | a `ToolStatus` enum whose values are the existing ten strings; collapse `pending_approval`/`approval_required` and `executed`/`completed` behind it |
| `llm_shared/decisions.py` + `scripts/benchmark_decision_backends.py` | measure a backend to `Calibration.MEASURED`; only then add a weakest-link gate, and only for `MEASURED` answers |
| `llm_shared/tiered_routing/complexity_router.py:121-194` | after the typed stall signal exists, allow a give-up to open the same door input complexity already opens |

---

## Verdict

The source is six days old, has no CI, and is not adoptable as code at any point. Its value is that
it is a clean, small statement of mechanisms AutoBot mostly already owns — and the comparison is
most useful where it shows us owning a mechanism in the *wrong place*: a typed-decision seam with
probabilities nobody thresholds, a give-up door that opens on input complexity instead of on giving
up, a terminal-reason enum in the loop that does not run and ten free-text strings in the one that
does. Four genuinely new defects, eight findings already filed, one adoption that is simply better
than what we do (report the tool you could not compile, with the reason), and one adoption
correctly blocked on a measurement we have already told ourselves we have not made.
