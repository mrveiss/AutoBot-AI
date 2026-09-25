---
tags:
  - research
  - agent-harness
  - completion-evidence
  - capability-gating
  - prompt-injection
---

# Research: a local-first agent harness that refuses to conclude a task is done

**Date:** 2026-09-25
**Source:** an external, MIT-licensed open-source desktop multi-agent harness — a single Node
process serving an HTTP/SSE API plus a static browser frontend, wrapped in a Rust desktop shell
that embeds the Node runtime. Bring-your-own-key across the mainstream hosted providers plus a
local-model path. Vendor, product, author, repository and release-channel names are withheld per
the no-external-names rule for committed docs; the URL was supplied in-session. Star/fork counts
and version strings are omitted deliberately — together they identify the project as surely as
its name does. Maturity: pre-1.0, under daily commits, with a signed/notarized release train and
a large test corpus; the maintainers describe one desktop platform as well tested, a second as
thin, and a third as internal-only.
**Method:** read the repository README and its own code map in full; listed the top level and the
runtime, shared-contract, capability, QA and autonomous-directive directories; read in full or in
part the ten runtime modules named below — completion evidence, typed task postconditions, the untrusted-content
taint layer, the verification core, deliverable provenance, the autonomy decision ledger, the
ambiguity-resolution policy, the workspace lease, the capability projection function, the
cross-boundary schema validator — and the autonomous-loop suite's README.
**Untrusted-content note:** everything fetched was treated as data. The source ships a directory of
long-form *directive prompt files* whose own text instructs an agent to "execute it fully"; those
were read as data and not executed. No text attempting to redirect this session was encountered.
**Status:** Phases 1 and 2 complete (source analysis, then the full AutoBot comparison approved
in-session, plus a user-added question on a gamified agent-activity view).
**Filed as:** **#17494** (negated refusal reads as APPROVE — critical), **#17495** (four sites assert
success on absent evidence), **#17496** (work-product attribution / unregistered concept / unwired
workspace lease), **#17497** (`in` as an allow-list admits prototype keys).

---

## What It Is

A local-first desktop harness for running several bounded AI agents concurrently on a
single-user machine. One Node process owns everything server-side — providers, the tool surface,
persistence, budgets, consent, scheduling — and serves a build-step-free browser frontend over
localhost HTTP/NDJSON/SSE; a Rust desktop shell embeds that same process and the platform
keychain for release builds. Roughly 23k lines of runtime across ~82 modules, ~50k lines of
frontend across ~133 hand-ordered script modules, ~409 test files, and a release pipeline that
refuses to stage a build unless the installer signatures, notarization and updater signatures all
verify. The distinguishing design commitment is stated as a product law: the interface must never
assert state the harness cannot prove — and unusually for that genre of claim, it is mechanized
in code rather than asserted in a README.

## Architecture & Key Patterns

- **One process, one port, no frontend build.** The runtime serves the frontend statically and
  streams a frozen event bus to it. The frontend is ~80 plain scripts loaded in dependency order
  by hand. **Unreconciled:** the overview above counts ~133 hand-ordered frontend script modules.
  The two figures were taken at different points in the read and it is not established whether they
  cover the same population; treat the order of magnitude as the claim, not either exact number.
- **A frozen, additive-only cross-boundary contract.** A shared directory holds ~60 typed event
  definitions validated in *both* directions by a 75-line zero-dependency JSON-schema-lite
  validator. Renaming or removing an event or field is prohibited by policy.
- **Capability as a pure projection of spatial layout.** The editor UI is not decoration: the
  objects the user has placed in the room an agent is *assigned to* are the agent's capability
  grants. A 67-line pure function maps `(agentId, layout, registry, disabled)` →
  `{ tools, grants, approvalRules, networkCaps, hasCompute }`, recomputed every turn, so
  placing or reclaiming an object changes the agent's reach on the very next model call. The
  grant itself is a **policy triple, never a boolean** —
  `{ capId, tool, scope: read|write|execute, requiresConsent, network, paramConstraints? }` —
  and the object→grant map is explicitly *data the builder UI edits*, not code. One grant is
  privileged: a `compute` grant is the precondition to spend a model turn at all rather than a
  callable tool, so a brand-new agent can always think and never faces a dead wall.
- **The layout-is-authority rule is deliberately asymmetric by surface**, which is the honest
  part. On the interactive surface the floor is real: the room starts compute-only and only the
  operator's actually-placed objects extend it. Headless surfaces — scheduled jobs, chat-channel
  arrivals, delegated workers — keep a full default capability set, on the stated reasoning that
  "placing grants reach" is a lesson taught where the beginner is (the browser), and silently
  stripping a scheduled run's web and file access would regress already-shipped behaviour. The
  spatial metaphor is load-bearing where a human is watching and a convention elsewhere.
- **Pure core / ambient shell, applied consistently.** Judgment modules take injected `io`,
  `clock` and timers and contain no ambient time, filesystem or randomness — so they unit-test
  headlessly and pass a lint rule the project calls "lint-determinism". The ambient halves live
  in the route file and the tool implementations.
- **Append-only fsync'd JSONL as system of record, with derived views never stored.** Spend,
  runs, transcripts, checkpoints and autonomy decisions each get their own atomic
  fsync-before-rename store; attribution and project scoping are *derived* from the run log on
  read rather than written onto the artifact.
- **A stateless agent loop.** ~460 lines: a messages-array while-loop with tool-call
  accumulation and malformed-argument repair, carrying nothing between runs.
- **An acknowledged hotfile.** The route/server module is ~6.5k lines and its own code map says
  most merges conflict there.

## Notable Implementation Details

These are the transferable parts, and they are transferable precisely because they are small,
pure and dependency-free.

1. **Completion evidence that deliberately declines to conclude.** The module records two row
   types — *effects* (what changed) and *evidence* (what was observed after) — and leaves task
   completion at `not_assessed` until a typed contract binds a requested postcondition to
   compatible evidence. A successful tool result is never completion. A read or screenshot after
   a mutation is *candidate* evidence requiring semantic judgment, because observing *some* state
   after an action does not prove the *requested* state was observed. Its stated principle:
   false completion is worse than an explicit unverified outcome.
2. **The verifier is only evidence when its own verdict says so.** The deterministic-check tool
   returns ordinary output for a failing command too, so transport success is insufficient; the
   evidence row is graded `mechanical` only when the verdict string itself reads as a pass, and
   only then are workspace effects promoted to `mechanically_verified`.
3. **Typed postconditions with a small, honest set.** Five predicate types: artifact exists,
   artifact contains, artifact SHA-256, verification passed, and a connector read-back. The
   read-back is the interesting one — proof must be a *fresh host* read through the connector,
   never the model's own observation; it is only accepted when an effect row shows the run
   actually acted on that connector (a pre-existing external state is not proof, exactly as a
   pre-existing file is not); and the host refuses to run anything but an observe-role tool as a
   check, because a mutation can never be its own proof. Browser and connector semantics beyond
   that stay explicitly unresolved rather than being faked.
4. **Untrusted-content taint that removes the payoff instead of detecting the payload.** Advisory
   fencing ("this is data, not instructions") is acknowledged as unenforceable against a
   well-written injection, and useless on an unattended run with no human in the loop. So once
   content the user did not author enters a run's context, the host *revokes for the rest of that
   run* the powers an injection would need. It is a ~54-line pure state machine with no clock, IO
   or randomness, and — the detail that makes it trustworthy — **one definition shared by the
   dispatch gate and the consent-broker predicates, so the two can never disagree about what is
   revoked.** Four things make it sharper than the summary suggests:
   - **Revocation keys on a tool *impact* taxonomy, not on the tool name.** A separate policy
     module classifies every tool into one of a closed set — `none`, `media-control`,
     `synthetic-browser`, `workspace-process`, `visible-desktop`, `physical-input`,
     `external-service`, `external-credentialed`, `external-unknown`. A tainted run loses
     `workspace-process` (code execution), `external-credentialed` (spends a stored key outward)
     and `external-unknown`. That last one is the important one: **unclassifiable effects fail
     closed**, and third-party connectors are classified as `external-unknown` *regardless of
     transport or self-declared annotations*.
   - **It refuses to trust the server's own annotation.** A connector's `readOnlyHint` is
     attacker-authored, so using its translated scope would let a malicious server label a
     mutator as a safe post-injection read. A tainted run therefore makes no second connector
     call at all without a fresh human boundary.
   - **The file jail proves *where* bytes live, not *who* wrote them.** Uploaded attachments sit
     inside the ordinary workspace jail so normal file tools can read them — so a read from that
     provenance-stamped folder is itself treated as a taint source, otherwise a poisoned document
     would walk straight around the web/connector boundary.
   - **Recovery requires a decision obtained *after* the taint.** Standing permission state is
     deliberately not an input to the boundary check; only a fresh confirmation, on an
     interactive surface that actually has somewhere to prompt, yields a one-shot pass. An
     explicit zero-prompt "full access" posture is honoured, but taint stays latched and fenced
     rather than silently downgrading that posture into ask-mode.
   Kept throughout: plain web reads, jailed file reads, memory and images — on the reasoning that
   reading more untrusted data cannot be turned into an outward action, but acting on it can. And
   it names its own residual paths (its own shell output, ordinary local reads) as documented
   boundaries rather than omitting them.
5. **Diagnostic delta as the signal filter.** After an edit, only *newly introduced* lint
   diagnostics surface — plus the ones the edit fixed — compared by a stable identity key
   (file + line + column + code + message) rather than object reference, so pre-existing problems
   never drown the signal.
6. **Provenance derived from the log, never authored by the model.** A card's prose comes from the
   agent; its attribution and its project come from harness truth, so it cannot claim a
   collaborator or a folder the run log cannot back. The project lookup walks the parent chain
   (depth-bounded against a corrupt log with a cycle) because a delegated worker carries no
   project of its own and would otherwise be filed as unscoped. Contributors are deduped by
   agent — three dispatches to one specialist is one contributor — and each carries an
   `identityFallback` flag so the UI can state that a run fell back to the generic persona
   instead of being the named specialist.
7. **A decision ledger whose whole point is the non-actions.** Append-only JSONL of every
   autonomous decision including *skip* and *defer*, each carrying a `binding` field that names
   the mechanism which bound it — concurrency cap, no capability, paused, schedule. The recorded
   motivation is concrete: the machine was left running overnight at maximum autonomy, produced
   almost nothing, and there was no way to ask what it had decided or why, because every
   non-action was silent. It fails open (a corrupt log yields an empty ledger — telemetry must
   never crash a run), clamps unknown verbs to `other`/`note` rather than dropping a real
   decision, and bounds the in-process mirror separately from the disk log for a 24/7 process.
8. **Ambiguity becomes one concrete question with options, adjudicated host-side.** Models may
   *propose* a question or a settled brief; a single policy module decides whether it is usable.
   Vague questions are rejected by pattern ("tell me more", "what do you want", "how should I
   proceed"). The most instructive detail is a *removal*: matching the model's free-text
   recommendation to its own option list by substring was deleted after review, because
   containment silently **inverts negations** — "do not publish" matched "publish", "do not
   include tests" matched "include tests", "not operators" matched "operators" — and a
   per-tier uniqueness guard cannot catch it, since exactly one option matches and it is the
   wrong one. Matching is now equality-only on a normalized form and fails closed. The bug's
   cost is also recorded: the ask tool is hidden, so the failure was invisible in both transcript
   and logs, and the retry advice then steered the model to a path that stored no recommendation
   at all — making a formatting slip indistinguishable from "the agent had no opinion".
9. **The lock moved down to the operation that actually collides.** A same-agent run mutex was
   replaced by a lease acquired at the first workspace-*mutating* tool call, because what two
   concurrent runs of one agent cannot share is the workspace directory and its shadow-git
   checkpoint repo — not the right to run. Reasoning-only runs never acquire, so a quick question
   during a long task is never blocked; a sibling's mutating call waits bounded, then fails
   truthfully naming the holder and since-when.
10. **Two prototype-chain hardenings at trust boundaries.** The shared validator used `in`, which
    walks the prototype chain, so a payload of `{q:'x', toString:1}` passed
    `additionalProperties:false` and a `required: 'constructor'` was satisfied by a property
    nobody supplied — relevant because third-party connector input schemas reach that validator
    verbatim. Separately, allow-lists are `Set`s rather than object literals, explicitly because
    an object-literal allow-list admits every `Object.prototype` key.
11. **An autonomous improvement suite with a governance model, not just prompts.** Eleven
    long-form directive files, each a scheduled agent session with a named target (merge debt,
    the app lying about state, fake-done, onboarding rot, stale branches, happy-path features,
    complexity creep, leaked secrets, unmapped surface, seam bugs only real use finds, and the
    gap between detected and fixed). What is worth noting is the surrounding rules: a stated
    minimum viable subset when fewer sessions are available; *exactly one* loop is allowed to
    repair, and it crowns only a patch a script proved on a clean tree; a size threshold for
    fix-in-lane versus file-a-finding; grep the trunk before acting on any plan, audit or memory
    claim because audits go stale in hours; one digest line minimum per tick because silence is
    indistinguishable from a dead session; and never touch another session's tree. A separate
    one-shot ten-lane adversarial fan-out writes to a *tracked* register rather than the
    machine-local one, so a lane's findings outlive the session and worktree that found them.
12. **A candidate-bound release receipt.** The release aggregate is invalidated by any new commit
    until the affected live gates are rerun — a green receipt is bound to the exact candidate,
    not to the repository.

## Strengths

- **Comment-as-decision-record, at unusual density.** Most module headers state the incident that
  motivated the module, the alternative that was rejected, the date, and why. The
  negation-inversion table and the overnight-autonomy story are in the source, not a wiki.
- **Honesty mechanized rather than declared.** The refusal to assess completion, the verdict-text
  gate on the verifier, the derived-not-stored provenance, and the ledger of non-actions are all
  the same principle enforced in four independent places.
- **Structural security over detection.** Revoking the capability an injection would need is not
  evadable in the way a pattern-matcher is.
- **Boundaries documented as chosen.** Residual injection paths, the unresolved browser/connector
  completion domains, and the thin platform coverage are all stated rather than omitted.
- **Testability by construction.** Pure judgment cores with injected clock/IO/RNG, a determinism
  lint rule, and a large test corpus.
- **Zero-dependency runtime posture.** The server half runs on Node core modules only — clone and
  run, no install step.

## Weaknesses / Limitations

- **The headline feature is unfinished where most work happens.** Task completion stays
  `not_assessed` for the browser and connector domains. Honest, but it means the evidence system
  currently adjudicates workspace artifacts and one external read-back, and nothing else.
- **A self-admitted 6.5k-line merge hotfile** carrying every route, plus a scheduling subsystem of
  ~5 modules and ~170KB that is arguably its own product.
- **No type system anywhere,** and a frontend of ~50k lines across ~133 scripts whose load order
  is an implicit contract with no tooling to enforce it. The zero-dep validator is the only
  runtime contract.
- **The merge gate is a hand-maintained list,** not discovery — and two earlier gate steps had
  been failing at step one for an extended period because they wrapped engine files that had
  been deleted, which is exactly the failure mode a list-based gate produces.
- **Fail-closed has a documented recurring cost, and they paid it twice.** The impact taxonomy's
  default for an unclassifiable tool is the most-restricted class, which is right — but a tool
  missing from the safe-capability set falls through to it and is then refused *silently*. Two
  live-caught instances are recorded in the source: the host demanded three separate approval
  cards to let an agent *ask the operator one question*, and every deferred tool became
  permanently unreachable while looking, from the outside, merely "not found". Both are the same
  shape: a fail-closed default plus an incomplete allow-list produces an outage that presents as
  absence. Anyone copying the taint model inherits this failure mode along with the protection.
- **Single-user by construction** — one operator, OS keychain, localhost auth. No multi-tenant or
  team model to inherit.
- **Repository weight and archaeology cost:** a multi-gigabyte tree with a 742KB generated sprite
  module in it, and a documentation directory of 40+ plan documents explicitly labelled
  historical.
- **The autonomous suite's cost is structural, not incidental** — the eleven loops only work if
  eleven concurrent agent sessions actually run.

## Visible vs Hidden Metrics

**Visible (advertised):** MIT-licensed; local-first with bring-your-own-key; a zero-install
server half; a free local-model path; ~409 test files and a ~364-step merge gate; ~60 typed
schema-validated events; a signature/notarization-gated release train; eleven autonomous QA
loops; concurrent bounded agents with separate workspaces. *All of these are self-reported.* None
is independently verified, and the strongest claims — "real work", "never asserts what it cannot
prove" — are the least verifiable from outside. The verifiable-by-inspection ones are the code
facts: the taint revocation, the postcondition types, the `not_assessed` default.

**Hidden (the costs an adopter inherits):** the build-step-free frontend with a hand-ordered
module graph; the 6.5k-line route hotfile that makes concurrent contribution expensive; a
multi-gigabyte checkout; no static types on a ~73k-line JavaScript surface; single-operator
coupling through keychain and localhost auth; a scheduling subsystem large enough to maintain
separately; the real compute and token bill of running the autonomous suite as designed; and —
the subtlest one — the comment density that makes the code legible also makes it costly to
refactor, because each header is a contract with a dated history that a rewrite must not silently
discard.

**Weighing.** For a would-be adopter of the whole thing, the hidden costs are decisive: the
untyped no-build frontend, the route hotfile and the single-operator assumption would each be a
multi-week tax, and none of the visible wins offsets them. For an adopter of *ideas*, the
weighing inverts sharply and unusually far: the transferable mechanisms — the `not_assessed`
default, the verdict-text gate, the effect-row precondition on external proof, taint-driven
capability revocation, the diagnostic delta, derived provenance, the ledger of non-actions, the
negation-inversion lesson, the lease at the mutating call — are each 60–200 lines, pure, and
carry no dependency on this project's runtime, frontend, event bus or shell. The expensive parts
are precisely the parts nobody needs to take. Conditions under which the hidden costs still bite:
adopting the *taint* model requires a tool registry that already classifies every tool by
capability and effect, and adopting *typed postconditions* requires a place where a task's
acceptance criteria exist as data rather than prose — without those two preconditions, both
become new subsystems rather than new rules.

---

# Phase 2 — AutoBot Comparison

Approved in-session for a full comparison across all mechanisms, plus a user-added question about
a gamified agent-activity visualisation (recorded in its own section below). Every item below
passed the audit-first gate: the greps run and the files read are cited, and a capability that
already exists is moved out of "adopt" rather than being proposed again.

## Mechanism 6 — provenance derived from the log, not authored by the model

**Audit.** `autobot-backend/llc/models/work_product.py:20-65` is the only deliverable/artifact
table in the repo (`code` / `document` / `report` / `plan` / `screenshot` / `pr_link`). It carries
**no attribution field at all** — no `author_agent_id`, no `created_by`, no `contributor`. Its only
link to the producing run is `heartbeat_run_id`, nullable and `ondelete="SET NULL"`
(`work_product.py:41-45`), so deleting the run row silently erases who produced the artifact.
`WorkProductService.create()` (`llc/services/work_product_service.py:22-45`) takes `title` and
`content_text` as caller-supplied prose and persists no attribution for either. The parent
`LLCWorkItem` *does* have `created_by_agent_id` / `author_agent_id`
(`llc/models/work_item.py:132-133`, `:210-211`, `:248-249`) — but these are plain nullable columns
set by whichever service call passes them in (`work_item_service.py:230-239`, `:276-277`,
`:1018-1027`), i.e. **caller-supplied at write time and never re-derived or validated against a run
record before display**. Greps: `deliverable`, `contributor`, `attribution`, `created_by`,
`identityFallback` across `.py`/`.ts`/`.vue` — the `contributor` hits are all unrelated
(code-ownership analytics, CI scripts).

**We own the technique, in the wrong place.** `services/knowledge/lineage_service.py:100-127`
implements exactly the source's depth-bounded ancestor walk, and does it *better*: an explicit
`depth` bound (`for _ in range(depth + 1)`, line 116) **and** a `seen` set cycle guard
(`:115-118`), with a two-node cycle exercised in `test_lineage_service.py:247-248`. But
`parent_run_id` exists only for KB-synthesis evolution (`synthesis_provenance.py:40,69`). Greps for
`parent_run_id` / `parentRunId` outside `services/knowledge/` return nothing — no agent or subagent
run record (`LLCHeartbeatRun`, a2a `Task`, orchestration `SubagentTask`) carries one. So the
"delegated worker inherits its lead's project" problem the source solves cannot even be asked here.

**Verdict: adopt-with-conditions.** Visible benefit: a work product can no longer claim an author
the record cannot back, and a delegated worker's output stops being unscoped. Hidden cost: it needs
`parent_run_id` on the agent-run record first, which is a migration plus an event-contract change
under `EVENT_STATE_DOCTRINE.md` — the walk itself is already written and tested. Effort: moderate.
Two findings fall out of the audit independent of adoption, and both are AutoBot defects rather
than source lessons:
- `LLCWorkProduct` is **not a registered concept** in `autobot_shared/store_authority.py:75-265`.
  `llc_work` is registered (`:106-121`); work-product rows are not named as their own concept. That
  contradicts the module's own rule 1 (`:13-33`): "Every persisted concept names its system of
  record." `system_of_record()` raises `KeyError` for an undeclared concept (`:268-289`).
- `heartbeat_run_id` being `SET NULL` means attribution is destroyed by run cleanup rather than
  preserved — the opposite of derive-on-read.

**No `identityFallback` equivalent exists.** `llm_shared/model_fallback_coordinator.py:76-84`,
`:101-109` records `fallback_used` / `primary_model` / `fallback_model` / `fallback_reason`, and
`llm_shared/fallback_events.py:33-59` publishes a `PROVIDER_FALLBACK` event — but that is
*model*-level fallback, deliberately not persisted (`fallback_events.py:14-18`: "This module
intentionally does NOT touch Redis persistence"). `tiered_routing/complexity_router.py:117,201-208`
logs requested-vs-selected model to Python logging only. Nothing records that a run was served by a
different *persona/specialist* than the one requested. Greps: `identityFallback`,
`identity_fallback`, `generic persona`, `requested_model`/`actual_model`. **Verdict: adopt** — small,
and it is the difference between a UI that can say "this was not the specialist you asked for" and
one that silently misattributes competence.

## Mechanism 7 — a ledger whose purpose is the non-actions

**Audit — and AutoBot is closer to this than expected.** Durable non-action recording genuinely
exists, as run-status enum values in Postgres (the registered `llc_work` concept), not as log lines:
- `LLCRunStatus.SKIPPED` (`llc/models/enums.py:154`, commented "heartbeat was not dispatched to any
  adapter (no adapter / CLI absent / no agent_class) — degraded, distinct from COMPLETED or
  FAILED"), raised as `HeartbeatDispatchSkipped` (`llc/exceptions.py:76-89`) at three
  no-capability sites — no adapter registered (`llc/scheduler/heartbeat_scheduler.py:866-869`),
  required CLI binary absent from PATH (`:871-879`), no `agent_class` configured (`:886-891`) — then
  caught and persisted at `:522-526` and written to the run row at `:534-554`. The in-code comments
  name the failure it prevents: "signal a skip (not a phantom COMPLETED)", "degraded skip, not a
  phantom success (GH#9951)". That is the source's exact principle, reached independently.
- `LLCRunStatus.RATE_LIMITED` (`enums.py:145`) with retry/backoff bookkeeping
  (`heartbeat_scheduler.py:472`, `:512-533`, `:571-662`) — a defer, recorded.
- `LLCRunStatus.QUOTA_EXHAUSTED` (`enums.py:156-158`) auto-pauses the agent and emits a
  board-visible `CONTROL_AGENT_PAUSED` event (`heartbeat_scheduler.py:674`).

**What is missing is the bounded reason and the unified read.** The skip reason is free text
(`exc.reason` → the `error` column, `heartbeat_scheduler.py:526,553`), not an enum, so "why did the
station do nothing" cannot be aggregated. There is no `binding` field or equivalent closed
vocabulary — grep `binding` returns only unrelated hits (workflow skill binding, DNS rebinding,
context-manager bindings). And no scheduler tick that found *nothing due* is recorded at all; only
a tick that found something due and then declined it. Greps: `ledger`, `append_only|append-only|fsync`,
`concurrency-cap|concurrency_cap|no-capability|no_capability|binding` across `--include=*.py`.

**Where AutoBot is ahead, and it is the sharper idea of the two.** `services/task_claim.py:19-25`
fails open when Redis is unreachable — but *distinguishes which fail-open branch ran* by emitting
`redis_unavailable` or `redis_error` as the audit outcome (`:97-100`, `:108-116`, `_emit_audit`
`:198-208`, closed vocabulary `granted|denied|redis_unavailable|redis_error|ok|lost|released|not_owned`).
The module docstring states it explicitly: "All three fail open... What does tell them apart is
audit." That is `MEASUREMENT_DISCIPLINE.md`'s distinguish-*nothing-found*-from-*did-not-look* rule
implemented in running code, and the source's ledger has no equivalent — its ledger fails open to an
empty list with no marker saying the log was unreadable. **We are ahead; the source should have
copied us.**

**Verdict: adopt-with-conditions, narrowed.** Do not build a second ledger — `services/audit/audit.py:57-62`
already has a `GOVERNANCE` category defined for exactly this ("skill approval, budget breach, agent
pause"), backed by a Redis sorted set with `record()` dropping the event when Redis is absent
(`:88-95`). The adoptable delta is only: (1) a bounded `binding` vocabulary replacing the free-text
skip reason, and (2) routing the existing scattered non-actions through the one `GOVERNANCE`
category so the question "what did the fleet decide overnight, and why" has a single answer. Hidden
cost: a new enum is a hub-file change and every producer must be migrated at once or the aggregate
lies by omission. Effort: moderate.

## Mechanism 10 — the lease at the operation that actually collides

**Audit.** AutoBot's wired primitive is the **mirror image** of the source's. `docs/developer/AGENT_COORDINATION.md:15-19`
mandates one registry (`autobot_shared/coordination/work_claims.py`), with scopes as a resource tree
(`<kind>:<segment>/...`, kinds `path|kb|device|project|config|provider|cpu|queue`, `:94`), claims
that always expire (`:20-22`), and the rule "**A refusal names its holder**" (`:23-25`) — satisfied by
`ClaimConflict.__str__` (`work_claims.py:243-248`), which names agent, task, mode, intent and expiry.
Enforcement is `agents/scope_enforcement.py` (#15950): a run's **declared** scopes are acquired
**up front**, all together, with partial acquisition released rather than kept (`:12-16`), held for
exactly as long as the run lasts (`:5`), renewal tied to LLM-attempt/tool-call progress (`:73-107`,
`:149`, `:184`). Acquire never blocks — `try_acquire`/`work_claim` return or raise immediately on
conflict (`:443-462`, `:551-558`); the bounded wait lives one layer out in the negotiation path
(`services/claim_yield.py:48-55`, `:132-166`, `YIELD_TIMEOUT_S`) and `claim_waitlist.py:212-320`.

One property of the source's design AutoBot already has: a run declaring no scopes is a no-op
(`scope_enforcement.py:328`), so a reasoning-only run never acquires and never blocks a sibling.

**The real finding here is unwired code, not a missing pattern.** `autobot-backend/llc/models/workspace_lease.py:32-78`
is the source's mechanism almost exactly — unique `path` (`:49`), `owner` (`:52`),
`expires_at`/`released_at`/`release_reason` (`:62-69`), `is_live()` (`:71-75`). It has **no
acquisition code anywhere in the repo**: greps for `LLCWorkspaceLease` / `workspace_lease` outside
the model, its own test, its migration and the models `__init__.py` export return nothing, and
`llc/scheduler/project_disposal_sweep.py` — the reaper named in the model's own docstring — does not
reference it. Only `is_live()` is exercised, by `workspace_lease_test.py:29-50` against a hand-built
in-memory instance. Per the standing rule that anything resembling debris is unfinished work, this
is a **wire-it-in** finding, not a deletion candidate and not a new design.

**Verdict on the source's lazy-acquire idea: rejected-by-hidden-metrics.** Visible benefit is real
but small — up-front declaration over-claims for runs that turn out not to write. The hidden cost is
decisive: moving acquisition from declaration-time to first-mutating-call means a run can get
halfway through work before discovering it cannot have the resource, which is strictly worse than
being refused at the start, and `AGENT_COORDINATION.md:138-139` already rejects advisory-only
enforcement as an anti-goal. Declared-up-front is the better fit for a fleet that batches issues per
branch. What survives is the narrower observation that AutoBot's two overlapping claim primitives
(`work_claims` scope registry and `services/task_claim.py`'s flat `task:claim:{id}` mutex, kept
separate by owner ruling #15957) mean a caller must know which to use.

## Mechanism 8 — ambiguity resolution: NOT AUDITED

Stated rather than omitted, because a gap that is not named reads as a finding of "nothing there".

The source's ambiguity-resolution policy was read during Phase 1 and listed in the Method, but **no
AutoBot comparison was performed for it**, and the Phase 2 summary originally skipped from 7 to 9
without saying so. Nothing here should be read as "we already have this" or as "the source is
ahead" — neither was established.

What a later audit would have to answer: where a request under-specifies a target, does our side
resolve it, refuse it, or guess — and is that decision recorded anywhere a reviewer can find it.

## Mechanisms 1–3 — completion evidence, the verdict gate, and criteria-as-data

**Audit — no `not_assessed` state exists.** `autobot_shared/status_enums.py:40-60` (`TaskStatus`)
and `:463-476` (`OperationOutcome`) have no unverified/not-assessed member; `PENDING` exists but
nothing forces evidence-binding before another value is written.
`llc/models/enums.py:51-60` (`WorkItemStatus`) adds `IN_REVIEW`, but
`llc/services/work_item_service.py:908-971` `transition_to_done` gates on a company
`requires_review` boolean — **not** on `acceptance_criteria_done`, which it never reads.
`task_execution_tracker.py:490-508` `complete_task(task_id, result)` marks complete on any call.
Greps: `not_assessed|unverified|not-assessed`, `closure_gate|closure-gate`,
`verification_passed|artifact_exists|artifact_contains|artifact_sha256|connector_readback`.

**We own the right shape and it has no production caller.** `agents/ac_verifier.py:64-70` defines
`Verdict = MET | NOT_MET | CANT_TELL | NEEDS_HOST_EVIDENCE` with
`_EVIDENCE_REQUIRED = (Verdict.MET, Verdict.NOT_MET)`, and downgrades to `CANT_TELL` when a cited
line will not resolve via `git show` (`ac_criteria.py:280-311`, `ac_verifier.py:212-219`) — i.e.
successful model output is never trusted alone. `ac_verification_run.py:1-115` is referenced only
by its own test, and **#17092**, which would wire it into a human-visible queue, is open. This is
the same reframing the earlier confidence-gated-harness research hit: *we own the mechanism, in a
place requests do not go.*

**Mechanism 2 — mixed, with one real inversion.** Several sites are exemplary:
`chat_workflow/tool_handler.py:941-955` `_status_for_return_code` is fail-closed on an unparseable
code and carries a comment recording the historical bug it replaced (status "used to be the literal
`success` regardless of `return_code`"); `pipeline-scripts/ci_red_cause.py:242-246` requires
`status == "completed"` **and** `conclusion in RED_CONCLUSIONS`; `scripts/pr_required_gate.py:214-219`
states outright that "every blind spot reads as success"; `repo_tests/prepush_timeout_fails_the_push_15985_test.py`
exists precisely because *"'WARN … skipping' followed by exit 0 spells 'did not run' exactly like
'ran and passed'"*. That last comment is the source's Mechanism 2 discovered independently, and
better expressed. **But** `llc/adapters/claude_code_adapter.py:337-426` reads the CLI's structured
verdict and then does not act on a failing one — verified and filed. **Filed: #17495**, with the
three sibling instances.

**Mechanism 3 — partially present, and the typed half is real.**
`orchestration/success_criteria.py:24-31,95-217` has genuine typed predicates —
`SuccessCriteriaType = EXIT_CODE | OUTPUT_PATTERN | RESOURCE_EXISTS | CUSTOM`, dispatched
mechanically by `SuccessCriteriaEvaluator.evaluate()` to `_check_exit_code` / `_check_output_pattern`
/ `_check_resource_exists`, with a live caller at `orchestration/workflow_runner.py:322-330`
preferring `plan.structured_criteria`. That is three of the source's five predicate types, already
ours. We also parse GitHub `- [ ]` checklists (`agents/ac_criteria.py:63-64,176-204`) and verify
cited evidence *mechanically* via `git show origin/main:<path>` — file exists, line in range, line
non-blank — which the source has no equivalent of.

**What is genuinely missing is the binding, not the predicates.** `llc/models/work_item.py:69-72`
stores `acceptance_criteria` (JSONB prose) beside `acceptance_criteria_done` (JSONB parallel-indexed
booleans), and those booleans are set by **a human clicking a checkbox** —
`autobot-frontend/src/views/llc/WorkItemDetail.vue:437-439,569` `patchItem({ acceptance_criteria_done: done })`
— with nothing in the backend re-deriving them from evidence. So AutoBot has typed predicates in
one subsystem and prose checkboxes in another, and they are not connected.

**Verdict: adopt-with-conditions, narrow.** Visible benefit: a work item's AC array could be
evaluated by the evaluator that already exists. Hidden cost: `acceptance_criteria` is prose written
for humans and issue bodies, so typing it means either a second typed field (drift risk — two
sources of truth for one concept, which `store_authority`'s own rule 3 warns against) or a
migration of existing prose. Effort: significant. The cheap, high-value slice is the
`not_assessed`/`CANT_TELL` default — already designed in `ac_verifier`, needing only #17092's wiring.

## Mechanism 4 — taint-driven capability revocation

**Audit — AutoBot's injection defence is strong and entirely advisory-plus-detector; the structural
half is absent.** What exists is genuinely good:
`security/content_firewall.py:145-192` is a single shared inspection point for MCP output,
web pages, RAG documents, file reads and command stdout, mapping risk to
`FirewallAction = PASS | QUARANTINE | BLOCK | ESCALATE`, with a hard block above a confidence
threshold (`:169-185`) and a provenance-labelled fence (`:65-70`, `:298-301`,
`_UNTRUSTED_OPEN = "<<<UNTRUSTED_EXTERNAL_DATA source={source}>>>"`).
`knowledge/query_sanitizer.py:373-408` additionally **strips a literal closing tag out of the
fetched text** so a hostile page cannot self-escape the boundary — a detail the source's own fence
does not implement. `orchestration/orchestrator_prompts.py:56-64` substitutes planner templates with
`str.replace` rather than `str.format` specifically so a poisoned stored template cannot traverse
object attributes. `ContentSource` (`content_firewall.py:78-86`) already labels origin
(`MCP | WEB | RAG | FILE | STDOUT`) — the input side of taint is therefore already built.

**But the label is never read by the permission layer.** Greps for `forbidden_tools|capability`
inside `content_firewall.py` and `prompt_injection_detector.py` return **zero hits**. The tool
boundary is resolved once, in the constructor: `agent_loop/loop.py:185`
`self.config = self._resolve_forbidden_tools(base_config, agent_id)`, sourced from a static
per-profile manifest (`orchestration/agent_registry.py:555-588`) and never re-derived from what has
been ingested. Nothing shrinks a run's reach in response to what it read.
Greps: `taint`, `untrusted`, `provenance`, `trust_level`, `is_trusted`,
`lockdown|read_only_mode|disable_write|disable_execute`.

**Where we are ahead:** we never consult server-supplied tool annotations at all. Greps for
`readOnlyHint|destructiveHint|idempotentHint|openWorldHint` return **zero hits repo-wide**, and
`type_defs/mcp.py:44-51` has no field to carry one. Every external MCP tool collapses to a single
`Permission.MCP_EXTERNAL` through the RBAC-gated dispatcher
(`services/mcp_external_bridge.py:16-20`). The source *refuses to trust* the hint; we *cannot read*
it. Stronger by construction — with the honest converse that we also cannot grant a genuinely
read-only remote tool a lighter gate.

**The precondition I flagged in Phase 1 is half-met, and that is the real finding.** The source's
taint layer works because one `impactOfTool` classifier is shared by the dispatch gate and the
consent broker, "so the two can never disagree". AutoBot has **three** independently-maintained,
name-keyed effect classifications for different consumers:
- `autobot_shared/auth/mcp_tool_permissions.py:127-206` — `TOOL_PERMISSIONS: Dict[str, Permission]`, RBAC, with effect encoded in the naming convention `CATEGORY_RESOURCE_ACTION` (`permissions.py:33-36`, actions `READ|WRITE|EXECUTE|DELETE|MANAGE`).
- `autobot_shared/tool_catalogue.py:64,82` — `SENSITIVE_TOOLS` / `APPROVAL_CATEGORY_TOOLS`, for the human-approval workflow.
- `chat_workflow/code_exec/tool_policy.py:12-15` — "every tool is exactly one of **sensitive** / **mutating** / **readonly**", for shim injection.

`tool_policy.py:20-23` explicitly acknowledges the others and that they can drift. So the effect
taxonomy exists three times and agrees by hand.

**Verdict: adopt-with-conditions — and the condition is the prerequisite, not the feature.** Visible
benefit of taint revocation is large and unusually well-matched to AutoBot, which runs unattended
batches where no human is watching — exactly the case the source says advisory fencing cannot cover.
Hidden costs: (1) it needs **one** effect classification, so the honest first step is consolidating
three planes into one, which is a hub-file change touching RBAC, approvals and code-exec together;
(2) the source's own recorded failures show fail-closed defaults plus an incomplete allow-list
produce outages that present as absence — twice, costing them three approval cards to ask one
question and every deferred tool silently unreachable. Adopting the protection without adopting
their allow-list discipline buys their outages too. Effort: significant. **Recommend filing the
consolidation as the enabling issue and the taint layer as its child, not attempting the reverse.**

Also surfaced, already self-reported in `docs/architecture/CONTROL_PLANE_MAP.md` row 6 (#16842/#16771):
the live chat RAG path (`chat_workflow/llm_handler.py:_retrieve_knowledge_context`) has no firewall
reference — `content_firewall.py` is wired only into `advanced_rag_optimizer.py:1049`. And
`ContentSource.FILE` has **zero production call sites** (only `tests/test_content_firewall.py:212`)
while the module docstring claims file-read coverage — a docstring asserting coverage that the
wiring does not provide, which is the `MEASUREMENT_DISCIPLINE` failure shape. Both already tracked;
recorded here as witnesses, not refiled.

## Mechanism 5 — diagnostic delta

**Audit — AutoBot has thirteen ratchets and none is edit-scoped.** Every one is either a frozen
absolute count checked on a full-repo scan, or a shrink-only allow-list keyed on file path or exact
string. `scripts/check_python_file_size.py` + `repo_tests/python_file_size_ratchet_baseline.py`
(per-file ceiling, `MAX_KNOWN_LARGE_ENTRIES = 486`); `repo_tests/frontend_api_contract_ratchet_test.py:200-254`
(raw regex-match scalars, asserted equal in **both** directions); `i18n_untranslated_ratchet_test.py`;
`background_task_retention_ratchet_test.py`; `credential_vault_resolution_ratchet_test.py`;
`.github/workflows/ratchet-base-guard.yml` (re-runs the file-size audit on push to catch "a violation
born in a merge"). Identity keys are file paths or raw scalars — never `(file, line, col, code, message)`.

Two are closer than the rest and worth naming: `.github/workflows/no-commit-trailers.yml` is a
**genuine `BASE..HEAD` delta** with exact-SHA matching (`grep -qxF`), and
`pipeline-scripts/hardcoded_values_baseline.txt` uses a compound key `count|category|file|value`
— the nearest thing to a fingerprint in the repo, though it still has no line or column.

**We own the technique once, scheduled rather than edit-scoped.**
`autobot-backend/workers/audit_tasks.py:748-800` runs `vulture`, fingerprints each finding via
`_dead_code_fingerprint()` (`:748-752`, key = `path/file.py:42: message`, confidence suffix stripped
deliberately), diffs against the previous run's set in Redis, and reports `total_findings` and
`new_findings` as **separate fields**. That is Mechanism 5's idea — but diffed against yesterday's
scheduled run, not against a `before`/`after` of one edit, and it reports no "fixed" count.

**Verdict: adopt, small.** Visible benefit: a developer sees only what their change introduced, and
what it fixed — the "removed" half nobody currently computes. Hidden cost is genuinely low: it is a
pure function over two diagnostic lists (`diagnosticDelta(before, after, keyOf)`), the fingerprinting
half already exists in `audit_tasks.py`, and it adds no baseline to maintain — which is the
attraction, since every existing ratchet is a frozen number someone must re-pin. Effort: trivial to
moderate. Condition: key on `(file, line, col, code, message)` from the start; `audit_tasks.py`'s
key omits column and code, and `.secrets.baseline` already demonstrates the cost of getting identity
wrong — it had to **exclude `line_number` from identity** (stripped via `jq 'del(.results[][].line_number)'`
since #16353) so a line-only move produces no diff, at the documented price that running
`detect-secrets audit` on a stripped-but-unlabelled entry raises `NoLineNumberError` and silently
truncates the audit loop.

Correction to a figure carried in session memory: the duplication pin is **11,707** lines, not
11,723 — re-measured under #17317 (`.github/workflows/duplication-guard.yml:84-107`), and the guard
was deliberately changed from a percentage to an absolute count under #16319 because a percentage
penalised deleting unrelated code. Note the guard keeps **no per-clone identity at all**
(`scripts/duplication_gate.py:37-70` reads only jscpd's aggregate `Total:` row), so a clone moving
between files is invisible while the total holds.

## Mechanism 11 — autonomous loop governance

**Audit.** AutoBot's `.claude/` layer is 14 skills and 24 agents, **none scheduled**. The actual
autonomous surface is elsewhere: 18 `.github/workflows/*.yml` with `schedule:` crons
(`canonical-audit.yml` weekly, `unwired-tracker-audit.yml` weekly and filing up to 10 issues per
run, `security.yml`/`coverage.yml` nightly) plus Celery Beat tasks in `workers/audit_tasks.py`.

Repair authority is encoded **per skill**, not centrally: `research-to-issues` is research-only with
a *tool-restricted agent* variant giving "a hard guarantee (structurally unable to write code)"
(`.claude/skills/research-to-issues/SKILL.md:26`); `repo-sweeper` "never draws conclusions… Do NOT
use for anything that writes"; `bulk-audit` may fix but only after validating on 2–3 files first.
`bugfix`, `implement`, `adopt`, `parallel` are unrestricted. There is **no** repo-wide "exactly one
loop may repair" rule and **no** fix-in-lane-vs-file size threshold — greps for
`30.line|30-line|line threshold|size threshold` across `.claude/` and `docs/developer/` found only
unrelated prose. Per-tick digest: **not found** (`digest`, `STATUS.md`, `\btick\b`); the analog is
session-granularity — `.session/HANDOFF-<branch>.md` with a fixed schema
(`docs/developer/CLAUDE_WORKFLOW.md:111-117`, `.session/README.md:19-27`), caught only reactively
when `scripts/cleanup-worktrees.sh` marks an orphaned branch `STRANDED`.

**Verdict: mostly rejected-by-hidden-metrics, one adoption.** The source's eleven-loop suite is
governance for a machine with no issue tracker — its `qa/findings/` is machine-local and its tracked
register exists precisely because findings kept dying with the session. AutoBot files to GitHub
Issues by construction (`pipeline-scripts/audit_unwired_trackers.py:12-15`,
`workers/audit_tasks.py` `_dedupe_and_file`), which is strictly better and makes most of the
apparatus unnecessary. The eleven-session compute bill is the decisive hidden cost against a
standing rule to conserve the weekly budget and prefer one session.

**What does survive is the one-line rule: a tick that found nothing must still say so.** AutoBot's
handoff fires once per session, so a loop that dies mid-run is indistinguishable from one that
found nothing — the same gap `LLCRunStatus.SKIPPED` closes for product agents but nothing closes for
dev loops. Cheap, and it composes with the Mechanism 7 `binding` vocabulary rather than duplicating
it. **Verdict: adopt, trivial.**

---

## Gamified agent-activity visualisation — "an office with departments"

Asked for mid-session, flagged low priority. Audited rather than speculated, because the ground
turns out to be substantially covered already.

**This was already decided, and largely built.** `docs/research/visual-operations-blueprint.md`
records umbrella **#13935** with the ruling *"Adopt GUI patterns only. No external data model,
vocabulary or naming"*, and child **#13939** specifically: a canvas **as a view mode inside the
existing Org Chart**, not a new nav entry. That shipped — `views/llc/OrgChart.vue:84-91`
(`viewMode: 'tree' | 'canvas' | 'people'`) builds a graph at `:218` via `buildOrgCanvasGraph` and
renders it through the existing `components/workflow/WorkflowCanvas.vue`, with node types
`org-person | org-group | org-process | org-tool` (`canvasNode.ts:17-28`). So "a spatial view of who
does what" exists today.

**What it does not yet do is show live work.** The canvas binds to
`GET /api/llc/companies/{id}/org-chart` (`composables/llc/orgCanvasGraph.ts:1-22`) — org structure,
not runtime state. Node drag is explicitly ephemeral (`OrgChart.vue:152-154`: position lives in the
`canvasNodes` ref only "until the drawn forest itself changes"). And the live state that *would*
feed it already exists but is unwired to this surface: `protocols/agent_presence.py:93-101`
(`PresenceEntry{kind, busy, detail, last_seen}`, 90s TTL), `models/heartbeat.py:71-96`
(`AgentRuntimeState` with `current_task_id`, `last_heartbeat_at`, `paused_reason`), and
`api/schemas_agent.py:1110-1126` (`AgentStatusItem` with `currentTask`, `activityTimeline`).
Tellingly, `GET /agents/presence` has **no frontend call site at all** — it appears only in
`types/generated/api.ts:17465`. An unwired read surface.

**So the honest framing is not "build a game", it is "bind the canvas you already have to the
presence feed you already have".** That is a wiring job, not a new subsystem — and per the
standing rule, the orphaned presence endpoint is unfinished work to complete rather than a gap
to design around.

**Three constraints that shape any version of this:**
1. **The event doctrine forbids a new socket.** `docs/developer/EVENT_STATE_DOCTRINE.md` principle 5:
   a new event type extends the channel grammar in `live_event_manager.py` — it must not add a
   WebSocket endpoint. A live office view rides the existing `agent:{id}` / `task:{id}` / `global`
   channels on `/ws/live` (`api/live_events.py:402`). Principle 3: the backend is the authority, so
   a client-computed room placement can never be authoritative.
2. **The i18n bill is real.** 11 locales × 9,470 lines each (`en.json` = 8,404 leaf keys), four of
   them RTL. Any new surface's strings replicate across all 11 under the no-hardcoded-strings rule.
   This is the single largest cost line and argues strongly for extending the existing Org Chart
   view over building a new screen.
3. **A department is not a modelled entity.** `department` appears only as a colloquial synonym in
   comments (`OrgChart.vue:98,387`); no `Department` model exists, and `Team`/`TeamMembership`
   covers **human users only** — `llc/api/companies.py:1390-1394` states agents carry no team
   column, so the frontend buckets them as "not in a team" (`composables/llc/orgPeople.ts`).
   The nearest real grouping is `(company_id, role_id)` on `LLCRoleTool`
   (`llc/services/role_tool.py:41-77`).

**On making it load-bearing like the source does — recommend against, on recorded grounds.**
AutoBot's live analogue of "placing an object grants a tool" already exists and is genuinely
equivalent: `llc/adapters/claude_code_adapter.py:146-161` builds `--allowedTools`/`--disallowedTools`
from the per-agent `adapter_config`, re-applied on **every** invocation including `--resume`, with
the config fetched per agent per company (`llc/api/agent_hires.py:178-196`), and hiring templates
already ship per-role tool bundles (`built_in_templates/software-team.json:15-52` — architect gets
`write`, code_reviewer does not). So the capability-per-role mechanism is ours already; only the
spatial framing is missing. Making the *canvas* the authority would mean serving org/role/capability
data through a surface where **#13935 explicitly rejected exactly that**, pending #13228, because the
MCP seam "bypasses canonical RBAC via a default-allow blocklist" and exposing that data "converts one
authorisation gap into total operational disclosure." The same doc also rejected the role lens as an
authorisation boundary (presentation-only, must not reuse `MembershipRole`, #13250 defect shape).

**Verdict: adopt as observability only — adopt-with-conditions, moderate.** Bind the existing
Org Chart canvas view to the existing presence/heartbeat feed over the existing `agent:{id}` channel,
so a node shows busy/idle, its current task, and last heartbeat. Visible benefit: at a glance, which
agents are alive and what they are doing — genuinely useful for a fleet that runs unattended, and it
retires an orphaned endpoint. Hidden costs: the i18n key bill, and the standing risk that a pretty
surface implies authority it does not have — mitigated by keeping it strictly a projection, which is
also what the source's own product law demands ("the interface must never assert state the harness
cannot prove"). **Explicitly out of scope:** capability grants by placement, serving the org graph
over the agent protocol (#13228 first), and any persisted spatial layout.

One genuine gap worth noting: nothing records **which tool an agent is currently invoking** — greps
for `active_tool|current_tool|activeTool|currentTool` return nothing; the closest is `currentTask`
(an identifier) and `org_role` (a label). A live office view showing "reading a file" vs "calling the
model" would need that field added, under the doctrine's additive-and-optional rule.

---

## Summary — what this comparison produced

| # | Mechanism | Verdict | Effort |
|---|---|---|---|
| 1 | `not_assessed` completion default | adopt-with-conditions — the shape exists in `ac_verifier`, unwired (#17092) | moderate |
| 2 | Verdict-text gates the evidence | **we are mostly ahead**; one live inversion filed | — |
| 3 | Typed postconditions | adopt-with-conditions — 3 of 5 predicates already ours; binding is missing | significant |
| 4 | Taint → capability revocation | adopt-with-conditions — **blocked on consolidating 3 effect planes into 1** | significant |
| 5 | Diagnostic delta | **adopt** — pure function, no baseline to maintain | trivial–moderate |
| 6 | Derived provenance | adopt-with-conditions — needs `parent_run_id` on agent runs; the walk already exists | moderate |
| 7 | Ledger of non-actions | adopt-with-conditions, narrowed to a `binding` vocabulary on the existing GOVERNANCE category | moderate |
| 8 | Ambiguity resolution | **not audited** — no AutoBot comparison was made; see the note above Mechanism 9 | unknown |
| 9 | Per-turn capability projection | **already ours** via per-agent `adapter_config`, re-applied every invocation | — |
| 10 | Lease at the mutating call | **rejected-by-hidden-metrics** — declared-up-front is the better fit | — |
| 11 | Loop governance | mostly rejected (we file to Issues); adopt the "a quiet tick still reports" rule | trivial |
| — | Gamified office | adopt as **observability only**; capability-by-placement explicitly out of scope | moderate |

**Where AutoBot is ahead of the source**, each verified in code:
- `services/task_claim.py:19-25` fails open **and distinguishes which fail-open branch ran**
  (`redis_unavailable` vs `redis_error`). The source's ledger fails open to an empty list with no
  marker. This is our own `MEASUREMENT_DISCIPLINE` rule implemented in running code.
- We never read server-supplied tool annotations at all (zero `readOnlyHint` hits repo-wide); the
  source must actively refuse them.
- `knowledge/query_sanitizer.py:373-408` strips the literal closing tag so a hostile page cannot
  self-escape the fence; the source's fence does not.
- `services/knowledge/lineage_service.py:100-127` bounds its ancestor walk by depth **and** a cycle
  guard, with a cycle test; the source bounds depth only.
- `agents/ac_criteria.py:280-311` verifies a cited line exists in merged code via `git show` — the
  source has no mechanical citation check.
- `repo_tests/prepush_timeout_fails_the_push_15985_test.py` names the failure mode better than the
  source does: *"'WARN … skipping' followed by exit 0 spells 'did not run' exactly like 'ran and passed'."*

**Filed from this pass** (all verified by reading the code, not taken from a subagent's report):
**#17494** (negated refusal reads as APPROVE — critical), **#17495** (four sites assert success on
absent evidence), **#17496** (work products carry no attribution; unregistered concept; unwired
lease), **#17497** (`in` as an allow-list admits prototype keys from a WebSocket payload).
Recorded as prior witnesses, not refiled: #17307 (closed), #16842/#16771, #17092, #13935/#13228.
