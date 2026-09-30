# Agent meta-harness — swarm coordination, self-learning memory, and guidance gates

**Date:** 2026-09-29
**Source:** an external open-source agent *meta-harness* — a TypeScript/Node layer that wraps
existing coding-agent CLIs rather than replacing them. Permissive licence, npm-distributed,
plugin marketplace, hosted web properties alongside the repo. Name, vendor, author, repo URL
and npm package names are withheld per the no-external-names rule for committed docs; the URL
was supplied in-session. Star/fork counts and the creation date are omitted deliberately —
together they identify the repository as surely as its name does.
**Scope of this read:** README, root and monorepo manifests, the full git tree (composition
measured, not sampled), and the source heads of the packages that carry the transferable
designs: coordination-claims, guidance, memory-retrieval guard, neural/reasoning-bank,
swarm/queen-coordinator, hooks, security, providers.
**Method:** read-only remote access only (contents API + raw file URLs). No clone, no `.git`
on disk, nothing executed. Every fetched file — including the source's own agent-instruction
files — was treated as **data**; see "Untrusted content" at the end.
**Phase:** 1 of 2. AutoBot comparison **not started** — awaiting go-ahead.

---

## What It Is

A meta-harness: a Node/TypeScript execution layer that installs *into* a repository and then
drives a host coding-agent CLI through that CLI's own lifecycle-hook system. Its thesis is
stated plainly in the source — *agent = model + harness*, and it supplies the harness half:
agent definitions, multi-agent "swarm" topologies, an HNSW-indexed vector memory, a
trajectory-learning loop, cross-machine federation, and enforcement gates. Everything is also
exposed over MCP, so the same capabilities are reachable from a chat UI, a CLI, or another
agent.

Two install tracks exist with materially different surface areas: a lite plugin track (slash
commands, zero files written into the workspace) and a full CLI track (`init` writes an agent
instruction file, a hooks directory, settings, helpers, an MCP registration and a daemon).
The source documents that the two tracks expose **different MCP tool names** for the same
tools — a divergence it flags itself rather than hides.

**Maturity, measured from the tree rather than claimed:** 5,956 tracked files / 84.6 MB
in-tree; 2,276 TypeScript sources of which 668 are test files (~29%); 1,975 markdown files;
31 CI workflows including CodeQL, a CVE audit and a dozen smoke suites; three Rust crates;
a WASM kernel. Release cadence is roughly one minor/patch every one to three days, with the
30-day commit window saturating a 100-item API page. Open-issue count is four-figure. This is
an actively developed, high-velocity, single-vision project — not a stabilised platform.

## Architecture & Key Patterns

- **Harness-as-hooks.** The enforcement layer is the *host agent's* hook system, not prompt
  text. The gates module states the design rationale in one line: *"The model can forget. The
  hook does not."* Rules that must hold are compiled into hook-time gates (destructive-op
  confirmation, tool allowlist, diff-size threshold, secret-pattern redaction).
- **Monorepo of ~25 scoped packages** under one namespace, with the newer ones laid out
  domain / application / infrastructure / api (DDD-ish). Older packages are flat. Three Rust
  crates cover the federation peer, a watermarking primitive, and an agent-interop layer.
- **MCP as the universal interface.** Memory, claims, federation, swarm control and dev tools
  are all published as MCP tools — the README variously cites ~210 and 314 tools across five
  server groups plus an in-browser WASM tool gallery.
- **Vector memory as the shared substrate.** An HNSW-indexed embedded store backs not just
  recall but audit records, compliance events, reasoning patterns and plan history. One index,
  many consumers.
- **Event sourcing for coordination.** Work claiming, handoff and stealing are modelled as
  domain events with an explicit rules module — not as lock files or ad-hoc status fields.
- **Provider abstraction** over five model vendors plus a local-inference provider and an
  own-stack provider, behind one manager with routing.

## Notable Implementation Details

1. **Claims: coordination as an event-sourced domain.** A dedicated package models work
   ownership with an explicit status lattice (`active | paused | handoff-pending |
   review-requested | blocked | stealable | completed`), a claimant type (`human | agent`),
   enumerated steal reasons (`timeout | overloaded | blocked | voluntary | rebalancing |
   abandoned | priority-change`) and handoff reasons (`capacity | expertise | shift-change |
   escalation | voluntary | rebalancing`). Work stealing has a **contest window** — a stolen
   claim can be disputed rather than silently reassigned. 17 MCP tools cover the lifecycle,
   including load-balancing and swarm-rebalance operations. The interesting part is not the
   feature list but the decision to make *abandonment* and *contested takeover* first-class
   states instead of leaving them to convention.

2. **A guidance package that treats the rule set as a compiled artifact.** It carries a
   compiler, an authority module, coherence checking, gates, a conformance kit, an adversarial
   module, an evolution module, and a **run ledger**. The ledger logs every run as an event
   against a minimum schema and then scores it with two classes of evaluator: *objective* —
   tests pass, lint pass, forbidden-dependency scan, forbidden-command scan, required plan
   sections present — and *subjective* — reviewer rating, architecture compliance. Violations
   are ranked. In effect, the project's own governing document is an executable artifact with
   a pass/fail record per run, rather than prose the model is asked to remember.

3. **A retrieval guard between the vector index and the context window.** Top-K HNSW results
   are screened *before* assembly into agent context. Three details stand out. (a) It
   explicitly **refuses to re-implement** the injection-pattern library, wrapping the project's
   existing tool-output guardrail instead — the module comment says so outright. (b) Oversized
   chunks are flagged or dropped but **never truncated**, with the stated reason that
   truncation would let an attacker pad a payload past the guardrail's own scan window. That is
   a failure mode most implementations get wrong by default. (c) It cites a memory-poisoning
   result (93–100% undefended attack success, 0% behind a certified content guard) as the
   motivation. It ships **off by default**, behind two environment flags.

4. **A four-step trajectory-learning loop.** Retrieve (top-k with MMR diversity) → judge
   (LLM-as-judge over the trajectory) → distill (extract strategy memories) → consolidate
   (dedup, **contradiction detection**, prune stale patterns). Contradiction detection at the
   consolidation step is the non-obvious piece: most memory layers append and dedup, few check
   whether the new memory disagrees with a stored one.

5. **Federation with explicit trust arithmetic.** Peers start untrusted; identity is proven by
   mTLS plus an ed25519 challenge-response. Trust is a published weighted formula
   (`0.4×success + 0.2×uptime + 0.2×threat + 0.2×integrity`) and is **asymmetric** — upgrades
   require accumulated history, downgrades are immediate. Outbound messages pass a 14-type PII
   detection pipeline whose action is chosen per trust level: BLOCK / REDACT / HASH / PASS.
   Untrusted peers are not excluded, they are *degraded*: they see discovery data, not memory.

6. **Background workers as standing daemons**, including a channel guard and a
   **memory-poison forensics** worker — i.e. the vector store is treated as an attack surface
   with both a preventive control and a post-hoc investigative one.

7. **An honestly-framed benchmark.** The headline ANN-vs-brute-force claim is stated *with its
   crossover point and its losing region*: ~1.9× at one corpus size, ~3.2–4.7× at another,
   recall@10 ~0.99, and explicitly "ties/loses at small N", with the benchmark script and an
   audit linked. Self-reported, but this is the strongest form of self-report.

## Strengths

- **Enforcement sits below the model.** Gates fire at hook time; the model's cooperation is not
  a dependency. This is the single most transferable idea in the source.
- **Reuse discipline where it is hardest.** A security-adjacent module that declines to fork
  the pattern library and wraps the shared guardrail instead is rare, and the comment explains
  why.
- **Coordination states cover the unhappy path.** Abandonment, contested steal, handoff-pending
  and review-requested are modelled, not improvised.
- **Adversarial thinking in the memory layer**, including the no-truncation rule and a
  forensics worker.
- **Very high documentation and ADR density** — decisions are written down and referenced by
  number from the code.
- **Test presence is real**, not decorative: ~29% of TypeScript files are tests, backed by 31
  CI workflows.

## Weaknesses / Limitations

- **Surface area is the dominant cost.** ~210–314 MCP tools (the two figures appear in the same
  README), 35 plugins, two install tracks with divergent tool names. The README's own
  reassurance — *"you don't need to learn 314 MCP tools"* — is an admission, not a mitigation:
  every registered tool is tokens in every request that lists it.
- **The install writes into your repository.** The full track creates an agent instruction file,
  hooks, settings, helpers and a daemon. A harness that edits the files your own agent policy
  lives in is a coupling, not an integration.
- **A 71 KB agent-instruction file** ships at the root. Whatever its content quality, that is a
  recurring per-turn context tax on every agent run in the repo.
- **Hygiene debt is visible in the tree**: 33 committed `tmp.json` files; compiled `.js`,
  `.d.ts` and `.map` artifacts committed *alongside* their `.ts` sources inside `src/`
  (the federation hub is the clearest case); two lockfiles for two different package managers
  at the root; ~8 MB of image assets including a 5.3 MB animated GIF.
- **Documentation approaches parity with code** — 1,975 markdown files against 2,276 TypeScript
  files. Rationale spread across hundreds of numbered ADRs is discoverable by number and
  undiscoverable by question.
- **The backlog outruns the release train.** A four-figure open-issue count against a
  one-to-three-day release cadence means throughput is not the constraint and triage is.
- **Key defences default to off.** The retrieval guard — the control the project itself argues
  is the difference between 93–100% and 0% attack success — requires two environment flags to
  become active, and a third to actually drop rather than merely annotate. The security claim
  and the shipped default disagree.
- **Mid-rename.** Two brand namespaces coexist in the tree, in import paths, package names and
  CLI examples, so documentation and code do not consistently agree on what a thing is called.
- **Headline capabilities live off-repo.** The planner UI, the chat UI and the live agent
  dashboard are hosted properties; the repo holds a subset with its own deployment story.

## Visible vs Hidden Metrics

**Visible — what is advertised.** Very large social proof (counts withheld here); "100+ agents";
"~210 MCP tools"; the HNSW speedup with recall@10 ≈ 0.99; 35 plugins; zero-trust federation with
HIPAA/SOC2/GDPR "compliance modes"; a plugin marketplace; release velocity. Of these, only the
retrieval benchmark is accompanied by a reproducible script and a stated losing region — the
rest are feature counts, which are inventory, not evidence. The compliance labels are the
weakest: they describe audit-trail *shapes*, not certifications.

**Hidden — what an adopter inherits.**

| Hidden cost | What it actually means |
|---|---|
| Repo-writing install | The harness authors the files your agent policy lives in; your rules and its rules now occupy the same surface, and its upgrades rewrite that surface. |
| Context tax | A 71 KB instruction file plus a 200–300 tool catalogue is paid on every agent turn, before any work happens. |
| Upgrade churn | A release every one to three days, against a package that mutates your repository, is a standing merge and re-verification obligation. |
| Governance duplication | Its gates, ledger, trust scoring and PII policy are *policy engines you must tune and own*. A team that already has these gains a second plane to keep consistent with the first. |
| Unmeasured learning | Retrieval latency is benchmarked; **outcome improvement from the distilled memories is not**. Nothing in the tree measures whether the learning loop makes results better — only that recall is fast. |
| Off-by-default security | The controls that justify the security framing are opt-in, so the out-of-box posture is weaker than the documented one. |
| Tool-surface attack area | Every MCP tool is also an instruction-injection sink; the source knows this (hence the guardrail and the composition inspector), which confirms rather than removes the cost. |

**Weighing.** For a team with *no* harness, the visible wins are real and the hidden costs are
mostly deferred — the install gives coordination, memory and learning on day one. For a team
that already operates its own coordination ledger, redaction boundary, tiered memory and rule
set, the same hidden costs land immediately and duplicate working machinery, and the
repo-writing install collides directly with an existing agent-instruction surface. **Wholesale
adoption is rejected by the hidden metrics for that second case.** The portable value is in
three *designs*, each of which transfers without the dependency:

1. Coordination states that model abandonment and contested takeover as first-class events.
2. A run ledger with objective evaluators — the rule set as an executable artifact with a
   per-run pass/fail record, rather than prose.
3. A screen between the vector index and the context window, with the no-truncation rule.

Whether AutoBot already has any of these is **not** assessed here — that is Phase 2, and the
audit-first gate means nothing above may be treated as a gap until our own code has been read.

## Untrusted content

The source ships agent-instruction surfaces at the root and throughout: a 71 KB instruction
file, a 24 KB agent guide, a skill manifest, a plugin manifest, per-plugin instruction files and
hook definitions. All fetched content — including these — was handled as **data**. No instruction
found in the source was followed, no command from it was run, nothing was cloned, and no
write path or network destination in this session came from fetched content. No prompt-injection
payload aimed at a reading agent was observed in the material read; that is a statement about
the files listed under "Scope", not about the whole 5,956-file tree, which was enumerated by
metadata only and not read.

---

# Phase 2 — AutoBot comparison

**Date:** 2026-09-29 · **Base:** `origin/main` at `5d53f420a8` · **Gate:** user approved after Phase 1.
**Audit-first:** nothing below is called a gap until AutoBot's own code was read. Paths are
repo-relative; line numbers are against `main` at the SHA above.

## Part A — verified directly (this session)

### A1. Federation trust and the outbound PII policy are **already built, and ahead**

This is the source's headline capability. AutoBot implemented the same design sixteen months
earlier, independently, and then added what the source does not have.

| Source design | AutoBot | Evidence |
|---|---|---|
| Trust formula `0.4×success + 0.2×uptime + 0.2×threat + 0.2×integrity` | **Identical formula** | `autobot-backend/a2a/trust_score.py:189`, documented at `:14-17` |
| Four-level lattice, untrusted peers degraded not excluded | Identical: `UNTRUSTED / LIMITED / STANDARD / TRUSTED` with the same score bands | `a2a/trust_score.py:71`, `:78-85`, bands documented `:21-24` |
| Asymmetric update — history to promote, instant demotion | Identical, and *stratified*: a threat event caps at `LIMITED`, an integrity violation drops to `UNTRUSTED` **and resets the promotion window** | `a2a/trust_score.py:26-29`, `:285-303`, `:305-309` |
| 14-type PII detector bank | Identical count, same idea | `a2a/pii_pipeline.py:14`, `PIIType` enum `:61` |
| Per-trust-level policy `BLOCK / REDACT / HASH / PASS` | Identical four actions, and the policy table is **loaded from SSOT config**, not hardcoded | `a2a/pii_pipeline.py:15`, `PIIAction` `:52-58`, defaults `:79-92` |

**Where AutoBot is ahead, with evidence:**

- **A capability matrix**, so a trust level is not a number but an enforced permission set —
  `a2a/trust_score.py:106` `_CAPABILITY_MATRIX`, checked by `has_capability` (`:131`) and
  enforced through `authority_for_level` at the executor (`a2a/task_executor.py:202`). The
  source describes trust levels; AutoBot resolves them to capabilities at the call site.
- **The PII block feeds back into trust.** An inbound payload blocked by the pipeline is
  recorded as a *threat event* — `a2a/task_executor.py:243-249` — so a peer that repeatedly
  sends PII is demoted automatically. The source's PII pipeline and trust scorer are described
  as separate concerns; AutoBot closes the loop between them.
- **An audit DB with admin grant and revocation** — `a2a/trust_score.py:218` (audit DB path),
  `:349` `grant(..., actor=...)` recording who granted, `:233` `_revoke_grant`. Consistent with
  the standing rule that credential/authority changes leave a durable paper trail.
- **A redaction-boundary doctrine.** `a2a/pii_pipeline.py:31-33` points at
  `docs/developer/REDACTION_BOUNDARY.md` and instructs the reader to add a detector to an
  existing redactor rather than start an eighth. The source ships its PII pipeline with no
  equivalent statement of which module owns which shape of the problem.

**Provenance check, so this is not read as adoption:** `a2a/trust_score.py` first landed
`2026-05-26` (`df432fe65a`, GH#7358), with the PII pipeline from #7355. No prior research doc
in `docs/research/` mentions `trust_score` or `TrustLevel` (grep: zero hits). Convergent
design, not a prior port.

**Verdict: no adoption. Parity on the design, AutoBot ahead on enforcement and auditability.**
The source's federation section is a *confirmation* that this design is the one to have, which
is worth something — but it contains no delta to take.

### A2. MMR diversity on retrieval — already built

The source's retrieve step advertises "top-k with MMR diversity". AutoBot has had it since
#10600: `autobot-backend/advanced_rag_optimizer.py:563` `_diversify_results`, invoked from
`:631`, `:728` (MMR pass on reranked results) and `:905` `_diversify_and_rerank`, with an
`mmr_lambda` trade-off parameter documented at `:142`.

**Verdict: no adoption — already exists.**

### A3. Contradiction detection at consolidation — exists, but as a *scan*, not *inline*

The source's non-obvious step is contradiction detection during memory consolidation. AutoBot
has contradiction detection, in two places, and neither runs inline at fact-store time:

- `autobot-backend/services/knowledge/contradiction_detector.py` — a semantic detector that
  groups facts and LLM-judges pairs within each group, returning a `ContradictionReport`
  (`:90`) persisted to Redis, surfaced at `GET /lint/report`
  (`knowledge/schemas/maintenance.py:323-328`). This is a **maintenance sweep**.
- `autobot-backend/judges/multi_agent_arbitrator.py:203` — contradiction detection *between
  agent responses* (#620), a different question entirely.

AutoBot's consolidation path, `knowledge/facts.py:1570` `consolidate_facts`, is explicitly
**delete-only pruning** of dead facts, with an instrumentation epoch, a per-run circuit
breaker and `dry_run=True` by default (`:1579-1594`). It does not compare a new fact against
stored ones.

**Where AutoBot is ahead:** the source prunes "old patterns" at consolidation with no described
safeguard. AutoBot's prune refuses to run unconfigured, refuses a flood, defaults to dry-run,
and never touches owned/verified/pinned/curated facts — which is the standing *no agent deletes
data on its own* rule implemented rather than asserted.

**The delta is real but small:** scan-then-report finds a contradiction eventually; inline
check finds it at write time, when the writer is still available to be told. **Verdict:
adopt-with-conditions, low priority** — and only if it can be added to the existing detector
rather than as a second contradiction path (`REDACTION_BOUNDARY`-style single-owner rule
applies by analogy).

### A4. Claim verification and grounding — built, registered, and not called

The source has no analogue of this; AutoBot's is more developed *and* is the familiar
built-but-disconnected shape.

- `autobot-backend/services/claim_verifier.py` — verifies claims against the KB via RAG,
  escalates to a research agent when KB evidence is insufficient, caches verdicts in Redis.
- `autobot-backend/api/knowledge_grounding.py` — `POST /api/ground-response`,
  `POST /api/verify-claim`, `GET /api/kb-conflicts`, conflict resolution (Tier 4, #4070).
- The router **is** registered: `initialization/router_registry/core_routers.py:67,384-387`.
- But: no backend module calls `claim_verifier` outside its own file and tests (grep across
  `autobot-backend/` and `autobot_shared/` returns only the quarantine docstring reference at
  `knowledge/quarantine.py:26` and the `decisions` seam tests), and the frontend has **only
  generated types** for these four routes (`autobot-frontend/src/types/generated/api.ts:10090,
  10149, 10201, 10259`) — no hand-written call site.

This **confirms open issue #16533** ("Post-generation grounding check for RAG answers") rather
than discovering anything: the grounding machinery exists and the answer path does not use it.
Recorded as a witness on #16533, not filed again — one defect, one home.

### A5. A mirrored hidden cost, worth naming

Phase 1 faulted the source for shipping its retrieval guard **off by default** behind two env
flags. AutoBot has the same shape in at least one place: `llm_shared/token_budget.py:56`
`TOKEN_BUDGET_PER_RUN` defaults to `0`, and `:71` documents that `0` disables the gate. The
criticism is fair in both directions. This is an observation, not a filing — whether a budget
gate *should* default on is a product decision, unlike a security control.

## Part B — the retrieval screen: AutoBot has it, applied at the wrong layer

**The source's design:** screen each retrieved chunk *at the retrieval boundary*, before
assembly, annotating or dropping per chunk, and never truncating an oversized one.

**AutoBot's design:** screen the *assembled context string* at each assembly site.

### B1. What exists, and where it is ahead

`autobot-backend/security/content_firewall.py:343` `inspect_rag_context` → `:145` `inspect` →
`security/prompt_injection_detector.py` with `strict_mode=True` (`content_firewall.py:133`).
On the chat path it is applied **twice**: `services/knowledge/service.py:571` and `:749` via
`services/knowledge/rag_firewall.py:66` `inspect_and_quarantine`, then again after the
compression rebuild at `service.py:135`. A repo guard enforces it:
`repo_tests/chat_knowledge_service_firewall_guard_test.py:76`.

Three ways AutoBot's is **stronger than the source's**:

- **On by default.** The source's guard needs `CLAUDE_FLOW_RETRIEVAL_GUARD=true` plus a second
  flag to drop rather than annotate. AutoBot's runs unconditionally on the chat path.
- **Fail-closed.** `services/knowledge/service.py:96` — "firewall blocks either string →
  `("", [])` — never a partial context". The source's default is annotate-and-pass.
- **Untrusted delimiting.** `security/content_firewall.py:64-70` `_UNTRUSTED_OPEN` /
  `_UNTRUSTED_CLOSE` / `_SYSTEM_NOTE`, applied at `:298-301` on both PASS (`:218`) and
  QUARANTINE (`:229`). The source flags chunks in a return value; AutoBot marks them in the
  prompt the model actually reads.

**Verdict: no adoption of the mechanism — ours is better. The source's contribution is the
placement argument, below.**

### B2. The structural finding — AutoBot made this argument for writes and not for reads

Open issue **#17649** argues, about the *write* side, that `sanitize_fact_content` is "a
chokepoint only for writers that choose to pass through it", quoting
`knowledge/ingest_sanitize.py:12`: *"a writer cannot skip a defence it does not know about."*
It measures 26 direct vector-store writers, 0 of which sanitize.

**The identical argument holds on the read side and nobody has made it.** The firewall is
applied at *assembly sites*, so an assembler that does not call it emits bare text. There are
five distinct assemblers and one dispatcher:

| Assembler | file:line |
|---|---|
| `build_grounded_context` | `services/knowledge/service.py:37` |
| `_build_context_parts` / `get_optimized_context` | `advanced_rag_optimizer.py:978` / `:1036` |
| `_format_results` (agentic) | `knowledge/search_components/agentic_search.py:377` |
| `_assemble_context` (CAG) | `services/cag_service.py:77` |
| `_build_kag_context` | `services/retrieval_dispatcher.py:80` |
| dispatcher | `services/retrieval_dispatcher.py:115` `get_context` |

**Four of them reach a prompt without inspection** — verified by reading the code, not inferred:

1. **Content appended *after* the firewall.** `services/rag_service.py:857` prepends
   `_get_kb_synthesis_context` and `:864` appends `_get_analyzer_lessons_context` to the string
   `optimizer.get_optimized_context` already firewalled and returned
   (`advanced_rag_optimizer.py:1050-1055`). Both helpers run their own raw ChromaDB queries —
   `rag_service.py:905` and `:931`, `collection.query(query_texts=[query], n_results=2)` — and
   join `documents` straight in at `:913` / `:938`. **Read and confirmed at
   `rag_service.py:845-866`.** This is the sharpest instance: the defence runs, and then text
   is added behind it.
2. **CAG path, no firewall.** `retrieval_dispatcher.py:154` → `cag_service.get_full_context` →
   `_read_source_file` (`cag_service.py:62`) — reads whole files off disk by a *retrieved*
   `source_path` — → `_assemble_context` (`:77`). Zero firewall symbols in the module.
3. **KAG path, no firewall.** `retrieval_dispatcher.py:80-89`, a plain
   `f"[source: {source}]\n{r.content}"` join.
4. **Agentic RAG, no firewall.** `agentic_search.py:377` `_format_results`, reached from
   `chat_workflow/graph.py:1255`. **Mitigated:** `state["agentic_context"]` is written at
   `graph.py:1302` and has no reader (grep over the repo returns only declarations and writes
   at `graph.py:108,1199,1202,1209,1216,1228,1239,1302,1308`), so the docstring claim at
   `:1199-1201` that it is "injected into the LLM prompt by prepare_llm" is not borne out. The
   path appears unwired today — which makes it a latent bypass, not a live one.

**These are reachable over HTTP, not just internally.** `api/knowledge_rag.py` — registered at
`initialization/router_registry/feature_routers.py:540` — exposes both:

- `:205`, on `return_context: true`, calls `rag_service.get_optimized_context` directly, i.e.
  bypass #1 (the post-firewall prepend/append).
- `:568` imports `get_context` from `services.retrieval_dispatcher` and dispatches across
  `rag | cag | kag` by request parameter — bypasses #1, #2 and #3 selectable by the caller. Its
  own docstring (`:558`) describes the return value as **"Assembled context string for LLM
  injection."**

So the unscreened text is not merely assembled internally; it is handed to an API caller labelled
as prompt material. That makes three of the four bypasses live rather than latent. (The fourth,
agentic, stays latent — `agentic_context` still has no reader.)

This is **one defect class with four instances**, structurally identical to the one #16771
closed on the chat path. It belongs in one issue listing the four, not four issues — and the
fix the source points at is the chokepoint form: inspect at the retrieval boundary, so an
assembler cannot skip a defence it does not know about.

### B3. The no-truncation rule — AutoBot passes, with one hole

The source's specific insight: never truncate an oversized chunk, because truncation lets an
attacker pad a payload past the scanner's window.

**AutoBot never truncates.** Budget enforcement *drops whole entries*:
`advanced_rag_optimizer.py:1007-1008`, `services/memory/compression.py:213-214`,
`services/cag_service.py:150-159` — all `break`, none slice. The only `content[:N]` slices on
these paths are a dedup hash key (`advanced_rag_optimizer.py:530,535,882,892`) and log lines
(`:1178`, `services/knowledge/service.py:362`).

**But there is no per-chunk cap at all, and the first chunk is uncapped.** Read at
`advanced_rag_optimizer.py:1000-1011`:

```python
if current_length + entry_length > max_context_length and context_parts:
    break
context_parts.append(context_entry)
```

The `and context_parts` conjunct means the guard cannot fire on the first iteration, so
**result #1 is appended whole however large it is**. The source caps every chunk at a
configurable byte ceiling and flags the oversize; AutoBot caps the *total* and exempts the
first. A single oversized poisoned chunk is therefore both un-dropped and — on the four paths
in B2 — un-inspected.

**Verdict: adopt the per-chunk ceiling. Effort: trivial.** The visible benefit is a bounded
scan window; the hidden cost is one more tunable, which is small because the total-budget
constant already exists next to it.

### B4. Ingest provenance is written for retrieval and never read

`knowledge/ingest_sanitize.py:21-22` states the purpose outright: *"Provenance is recorded on
the fact itself so retrieval can weigh trust — which route wrote it, whether sanitizing changed
the text, and which rules matched."* Four fields are defined at `:35-49`: `ingest_route`,
`injection_sanitized`, `injection_rules_hit`, `credential_redacted`.

**Six production writers, zero readers.** Writers verified at
`knowledge_sync_incremental.py:516`, `knowledge/bulk.py:757`,
`knowledge/adapters/okf_adapter.py:686`, `tasks/knowledge_tasks.py:209` and `:237`,
`tools/tool_registry.py:497`. No retrieval path reads any of the four.

This is the supply side of open issue **#16776** (`priority: critical`, "no taint propagation —
approval gates never learn that untrusted content entered the context"). #16776 traces the
*consumer* end — three approval gates that take no provenance input. The producer end is
already writing the signal; the wire between them is what is missing. **Records as a witness on
#16776, not a new issue.**

### B5. No redactor runs on the way out

`docs/developer/REDACTION_BOUNDARY.md` censuses eight redactor modules and its own routing
table assigns `a2a.pii_pipeline.scrub_outbound` to *"text leaving the process to a peer **or an
LLM**, needing a policy"*. The retrieval path calls none of the eight. Redaction happens only
at write time — `knowledge/ingest_sanitize.py:122` `redact_content`.

The consequence is narrow but real: **content stored before the ingest chokepoint landed
(#16770, closed 2026-09-16), or by any of the 26 writers #17649 counts, is never re-scanned on
the way out.** The doctrine says outbound-to-an-LLM needs a policy; the RAG path is
outbound-to-an-LLM and has none. Whether that is a doc defect or a code defect is a question
for the owner, not a thing to guess — it is stated here and left open deliberately.

### B6. No adversarial forensics over the vector store

The source runs a memory-poison forensics worker. AutoBot's nearest module,
`knowledge/vector_repair.py:168` `scan_poisoned_rows`, is a read-only full-collection walk that
skips everything except empty documents (`:162 if not is_empty_document(document): continue`) —
"poisoned" there means a bytes-vs-str key bug (#13277), not injected content. `forensic` returns
zero hits across `autobot-backend/**/*.py`.

**Verdict: adopt-with-conditions, low priority.** The visible benefit is detecting a payload
that landed before a defence existed — directly relevant given #17649's 26 writers. The hidden
cost is an LLM-scored scan over the whole collection, which is a recurring spend, and a new
finding queue nobody owns. Worth it only *after* the B2 chokepoint lands, since a read-side
screen makes stored poison inert without having to find it.

## Part C — coordination: AutoBot's unhappy-path machinery is better designed and less wired

**The source's design:** one claims package, an explicit status lattice on the claim itself
(`active / paused / handoff-pending / review-requested / blocked / stealable / completed`),
enumerated steal and handoff reasons, a **contest window** on a steal, and load rebalancing.

### C1. AutoBot has the primitives, a doctrine, and a CI guard the source lacks

| Primitive | file:line |
|---|---|
| Scope claims (TTL, Lua acquire, reentrancy, named refusal) | `autobot_shared/coordination/work_claims.py:315-351` `_ACQUIRE_LUA`, `:466` `try_acquire`, `:558` `work_claim` ctx mgr |
| Task claims (`SET NX EX`, audit outcomes) | `autobot-backend/services/task_claim.py:88/119/149/178` |
| Leader lease (compare-and-extend) | `autobot_shared/leader_lease.py:41-48` |
| LLC work-item checkout | `autobot-backend/llc/services/work_item_service.py:467`, `:490`, `:504` |
| Enforcement wrapper wired into agents | `autobot-backend/agents/scope_enforcement.py:315` `hold_scopes`, used by `agents/base_agent.py:52`, `a2a/task_executor.py:19` |

Ahead of the source on two counts the source has no analogue for:

- **A doctrine with a CI guard.** `docs/developer/AGENT_COORDINATION.md` mandates one registry,
  and `repo_tests/one_claim_registry_16653_test.py:290`
  `test_no_new_claim_or_lock_primitive_outside_the_registry` **fails the build** when a new
  claim primitive appears outside it, with a frozen shrink-only exemption list (`:305`, `:340`).
  The source has 35 plugins and no equivalent structural guard.
- **Structural ownership.** `work_claims.py:353-362` — the Redis key contains the holder
  identity, so "releasing another holder's claim … is unaddressable". The source *checks*
  ownership; AutoBot makes it unrepresentable.

### C2. The contested-takeover design already exists, and is better than the source's

The source's steal has a contest window: a stolen claim can be disputed. AutoBot's equivalent
is `autobot-backend/services/claim_yield.py` — ask the holder to release (`:83-117`), holder
answers `YIELD` / `HOLD` (`:60-61`, `:120-129`) — and its tie-break rule is stricter:
`:132-165` `await_decision` **resolves silence to HOLD**, with the reasoning at `:24-27`:
*"Silence means hold … would turn 'ask nicely' into 'take it after N seconds'."* Contention
between two waiters is arbitrated deterministically at
`autobot_shared/coordination/claim_waitlist.py:92-109` (priority → join time → agent id).

**Neither has a production caller.** A grep for `request_yield|answer_yield|await_decision|
invite_next_waiter|next_waiter|claim_waitlist import` across `*.py,*.ts,*.vue` returns only
`autobot-backend/tests/coordination/test_claim_yield.py` and `test_claim_waitlist.py`.

Meanwhile the takeover that **does** run is unilateral:
`agents/agent_orchestration/distributed_management.py:593` `_detect_and_steal_stale_tasks`
→ `:526-591` `_reassign_task` — the source agent's `active_tasks.discard(task_id)` at `:547`,
health forced to `degraded` at `:562-566`, and a fire-and-forget event on the `"global"` channel
at `:576-589` that is never addressed to the dispossessed agent. The only brake is
`max_reassignments` (`:487-488`). The ex-holder learns of the loss only by calling `renew_claim`
and getting `False` (`services/task_claim.py:135-142`, audit outcome `"lost"`).

**Verdict: no adoption — wire what we have.** The source's contest window is the *weaker* of
the two designs (it resolves toward the thief; ours resolves toward the holder). This is a
"never delete — wire it in" item, not a borrow. Effort: moderate.

### C3. A claim has no state of its own — this is the one design worth borrowing

`work_claims.py:237-247`: a `Claim` is `scope, agent_id, task_id, mode, intent, acquired_at,
expires_at`. **No status field.** A claim's only state is present-in-Redis or absent, plus
`ClaimMode ∈ {exclusive, shared}` (`:158-162`).

The states exist, but scattered across adjacent objects: run standing
`Literal["held","lapsed","degraded"]` (`autobot_shared/coordination/run_progress.py:52`), work
item `{backlog, ready, in_progress, in_review, done, cancelled, blocked}`
(`llc/models/enums.py:51-59`), A2A task `{submitted, working, input-required, completed, failed,
cancelled}` (`a2a/types.py:20-27`), agent `LLCAgentStatus.PAUSED` (`llc/models/enums.py:100-110`),
and a generic 18-member `TaskStatus` (`autobot_shared/status_enums.py:40-64`).

Grepped and **absent as states anywhere**: `handoff-pending` (0 hits), `stealable` (0 hits),
`abandoned` (0 hits as an enum member — the word occurs only in prose and env-var descriptions),
`ClaimState`/`claim_state` (0 hits).

The practical consequence, in the audit's own words, is that **abandonment is modelled three
different ways at three layers with no shared vocabulary**: silent TTL evaporation
(`work_claims`), silent steal-and-requeue (`distributed_management.py:526-591`), and loud
block-plus-recovery-ticket (`llc/scheduler/liveness_monitor.py:132`, `:173-179`, `:181-210`).

**Verdict: adopt-with-conditions.** Visible benefit: one vocabulary for "what happened to this
claim", which is what makes `GET /api/coordination/claims` answerable without reading three
subsystems. Hidden cost: a status field on a Redis-only record invites treating it as durable,
which contradicts `store_authority.py:257-268` (`agent_work_claims`, Redis-only,
`rebuilt_by="The holding agent re-acquires the scope on its next work step."`). Condition: the
enum lives on the *projection*, not on the claim record. Effort: moderate.

### C4. `work_claims` has no reaper — and that is a recorded decision, not a gap

No background task scans `work_claims:*`. Expiry is Redis `EX` (`work_claims.py:347`) plus a
lazy index prune on read (`:550-553`, Lua `SREM` at `:324-326`).

This is **deliberate and written down**: `work_claims.py:20-24` says "THE TTL IS THE POINT", and
`autobot_shared/store_authority.py:257-268` declares the rebuild path. The source's reaper is
therefore **not** a gap to fill — filing it would reverse a recorded ruling. Stated here so the
next reader does not re-derive it as a finding.

### C5. Two fail-open paths — also recorded rulings, with the residual risk named

The audit flagged these as holes. Reading them, both are documented decisions:

- `agents/scope_enforcement.py:279-290` `_acquire_or_degrade` — on `ClaimUnavailable` the run
  proceeds unclaimed, because "refusing every run would make the coordination layer a single
  point of failure for work it only advises on".
- `agents/scope_enforcement.py:348-361` `require_held` — the docstring enumerates the owner's
  ruling per standing: `held` allow, `lapsed` **refuse**, `degraded` allow-and-log, no claimed
  run allow-with-warning. The last is explicitly temporary, tied to open issue **#16269**:
  "refusing now would break live writes on those paths".
- `services/task_claim.py:96-100/129-131/158-160/185-187` returns granted/renewed/alive when
  Redis is unreachable, distinguishable only via the `redis_unavailable` audit outcome.

**Verdict: no filing.** The residual risk — a Redis blip permits double-pickup — is real and is
the accepted cost of not making coordination a SPOF. Recorded, not raised.

### C6. The claim event never fires in production — corrected, and narrower than it looked

**First reading, and why it was wrong.** `services/claim_projection.py:67-69` defines
`work_claim_acquired` / `released` / `conflict`, publishers at `:78`, `:83`, `:93`;
`live_event_manager.py:46-48` allow-lists all three citing #15949; and a grep for
`claim_projection|acquire_and_publish` across `autobot-backend/` and `autobot_shared/`,
excluding tests, returns four hits — the three allow-list *comments* and one import of
`claim_table` at `api/coordination.py:28`. **Zero production callers of the publishers**, because
the acquire path calls `work_claims.try_acquire` directly (`agents/scope_enforcement.py:211-215`).

That much holds. The conclusion drawn from it — that #15949 was prematurely closed and operators
still cannot see claims — does not. Two things corrected on a closer read:

**1. The state half is fully wired and answers the operator's question.**
`claim_projection.py:152` `claim_table` reads live from `list_claims(kind)` (`:161`) — the Redis
registry itself, not a materialised projection — and is served by `api/coordination.py:38`. An
operator asking "who holds what" gets a correct live answer today. The problem statement #15949
opened with (*"Claims are invisible… a client that reconnects has no way to learn the current
holdings"*) **is solved.** The module docstring names both halves the doctrine requires:
*"an event when it changes, and state that can be read back when the event was missed"*
(`claim_projection.py:11-13`). The second is live; the first is not.

**2. The closure was evidence-backed against every criterion it stated.** #15949's ACs are about
*how* the events publish, not *that anything invokes them* — AC1 reads "The three event types
publish via `events/bus.py` — no direct `live_event_manager` call"; AC2 pins the channel. The
closing comment verifies each against merged base with file:line. No tick was false.

**So the accurate finding is an AC-completeness one, not a closure one.** The criteria tested the
mechanism and never required a caller, so an issue could close correctly with its push half
inert. There is also a structural reason the wiring is awkward, stated in the same docstring
(`:15-20`): `autobot_shared` imports nothing from `autobot-backend`, so the primitive **cannot**
publish its own events — deliberately, since "a claim registry that fails when the event bus is
down would be a coordination outage caused by a dashboard". The only backend-side acquire site,
`scope_enforcement._acquire_all`, *could* publish and does not.

**Actual consequence:** a claims dashboard must poll `GET /api/coordination/claims`; it never
receives a push, so a UI built on the allow-listed event names would silently show nothing.
**Verdict: already filed as #16646** (`not-wired`, `v0.11.0`, wave 1, parent #15946), which
states this exactly and carries stronger ACs than this doc would have written. The only thing to
contribute is a line-number refinement — see Part E1. Not a reopen of #15949, and not a new
issue. Effort: trivial. Priority: moderate, not the critical item the first draft implied.

### C7. Load rebalancing — absent, and not worth adopting

`rebalanc|redistribut` returns **0 hits** across `autobot_shared`, `autobot-backend`,
`autobot-slm-backend`, `scripts`, `pipeline-scripts`, `autobot-frontend/src`. The only load
balancer is for NPU hardware workers, not agents — `services/load_balancer.py:230-324`, whose
API is `select_worker` at dispatch time (`:442`) with no rebalance, redistribute or drain
method. Agent selection is a circuit-breaker filter at routing time
(`distributed_management.py:359-398` `get_healthy_agents`).

Stale-task reassignment is failure-triggered, not load-triggered, and deliberately does not pick
a new owner: `distributed_management.py:533-537` — "The task is disassociated from the source
agent so that the TaskQueue's own retry / scheduling logic can pick it up … We intentionally do
not push directly into the queue here."

**Verdict: rejected by hidden metrics.** Visible benefit: smoother utilisation. Hidden cost:
rebalancing requires a live per-agent load model, and moving in-flight work between agents
re-opens every ownership question C2–C3 is still working through. The existing
disassociate-and-requeue is the cheaper correct answer while the claim vocabulary is unsettled.

### C8. Unrelated leftovers confirmed in passing

`LLCWorkspaceLease` (`llc/models/workspace_lease.py:32-75`) has a model, a re-export, a unit
test and a migration (`migrations/versions/20260916_093_llc_workspace_leases.py:51`) — and no
service: no `acquire`, `renew`, `reclaim` or sweep touches the table, while
`llc/scheduler/stalled_run_sweep.py:30-33` states it "deliberately does NOT … release what the
run held". Already filed as **#16963**; confirmed still true, recorded as a witness there.

## Part D — the run ledger: every piece exists, none of them join

**The source's design:** one run event per execution, scored immediately by objective
evaluators (tests, lint, forbidden dependency, forbidden command, required plan sections) and
subjective ones (reviewer rating, architecture compliance), with ranked violations.

**AutoBot has more run-record machinery than the source and no verdict attached to any of it.**

### D1. Run records — ahead of the source, and plural

| Record | file:line |
|---|---|
| `LLCRunReplayLog` — per-run tool calls, input + agent snapshots, final status | `autobot-backend/llc/models/replay_log.py:29` |
| `LLCHeartbeatRun` | `autobot-backend/llc/models/heartbeat_run.py:24` |
| `heartbeat_runs` / `heartbeat_run_events` | `autobot-backend/models/heartbeat.py:134`, `:176` |
| Activity log, append-only by construction (no update/delete methods) | `llc/models/activity.py:37`, `llc/services/activity_log.py:74-75` |
| `Trajectory` | `autobot-backend/memory/trajectory_store.py:93`, written at `orchestration/workflow_runner.py:375-408` |
| `TaskExecutionRecord` | `autobot-backend/memory/models.py:18` via `task_execution_tracker.py:44` |

And a **replay API the source has no equivalent of**: trigger a replay
(`llc/api/replay.py:179`), fetch the log (`:253`), **diff two runs** (`:291`), export a fixture
(`:318`). Being able to diff run A against run B is strictly more than a scored event.

**A vocabulary warning for the next reader:** "LEDGER" in this repo is a *prompt string* —
`autobot_shared/prompt_rules.py` `LEDGER_VS_EXECUTOR_RULE`, pinned by
`autobot-backend/tests/agents/test_ledger_vs_executor.py:32`. Grepping `ledger` finds it and
not a data structure.

### D2. The one evaluator that runs, discards its own detail

`orchestration/success_criteria.py:95` `SuccessCriteriaEvaluator` produces
`EvaluationResult(overall, score, results)` (`:63`) from `CriteriaResult.passed` per criterion
(`:54`). It is wired into three executors (`workflow_runner.py:339`, `dag_executor.py:535`,
`workflow_executor.py:761`).

Then, read at `memory/trajectory_store.py:179-195`, `reward_from_execution` collapses the whole
thing to a scalar — `1.0 / 0.8 / 0.5 / 0.0` — and reads only `criteria_evaluation["overall"]`.
**The per-criterion `results[]` list is never persisted.** Only `outcome` and `reward` reach the
`Trajectory` (`:93-160`).

Its four check types (`success_criteria.py:23-31`) are `EXIT_CODE`, `OUTPUT_PATTERN`,
`RESOURCE_EXISTS`, `CUSTOM` — no test, lint, dependency or command check among them. And
`LLCHeartbeatRun` (`llc/models/heartbeat_run.py:24-79`) has no score, verdict or compliance
column at all: `status`, `error`, `retry_count`, `context_snapshot`.

**Verdict: adopt — persist the per-criterion results, don't just the scalar.** Visible benefit:
"why did this run score 0.5" becomes answerable. Hidden cost: near zero — the data is already
computed and thrown away one function later; this is a schema column and a write, not a new
subsystem. **Effort: trivial. This is the single best-value item in the whole comparison.**

### D3. The judge's score cannot be joined to the run that earned it

`judges/task_outcome_judge.py:52` `TaskOutcomeRecord` — read and confirmed — carries
`task_type, goal, output_summary, strategy_used, score, rationale, timestamp`. It is written per
completed workflow from `orchestration/workflow_runner.py:416` `_record_outcome_for_learning`
(#10602), to Redis key `task:outcomes:{tenant_id}:{task_type}` (`task_outcome_judge.py:25`).

**There is no `run_id` or `plan_id` field.** A subjective score exists for every completed
workflow and there is no way to ask which run produced it. `task_pattern_learner.py:172,200`
consumes those scores to pick a strategy, so the learning loop is running on records it cannot
trace back.

**Verdict: adopt — add the run identifier.** Visible benefit: the judge's score joins the run
record, which is the entire premise of D2. Hidden cost: one field; the risk is that a
`run_id`-keyed Redis record needs the same key-cap treatment already applied at `:142`.
**Effort: trivial.** Pairs with D2 — same PR.

### D4. CI is attached to commits, never to runs

65 workflows in `.github/workflows/` (23 `pull_request`, 19 `push`, 12 `schedule`), including
real blocking objective gates — `llc-contract.yml:62-77` (API-wiring audit `--fail-on-unwired`
plus LLC e2e), `pr-template-check.yml` with `scripts/check_pr_template_sections.py` (required PR
sections), `ratchet-base-guard.yml`, `duplication-guard.yml`, `canonical-audit.yml:31-58`.

A grep for `llc_heartbeat_run|heartbeat_run|llc_run_replay|trajectory_store|agent_run_id` across
`.github/workflows/` returns **0**. Every gate scores a commit or a PR; none scores a run.

That is the structural difference from the source, and it is defensible — CI gates *code*, and
AutoBot's agent runs mostly produce code that CI then gates. The gap only bites for runs that
produce something other than a diff.

### D5. A correction to record — the eval harness is not a gap, it is the doctrine working

`autobot-backend/eval/run.py:155-162` was flagged in the audit as an unmeasured harness. Reading
it, that is the wrong reading. The code **deliberately declares its own blindness**:

```
# The baseline candidate replays each golden's own recorded outcome, so
# every comparison is a file against itself and no input can make it
# red. Saying so is the point: a green here otherwise reads as drift
# detection to anyone who did not open candidates.py (#16157).
logger.warning("UNMEASURED: no recorded runs in %s, so this replay compared each golden "
               "with itself. It cannot detect drift and its result asserts nothing.", ...)
```

This is `MEASUREMENT_DISCIPLINE.md`'s central rule — *distinguish "nothing found" from "did not
look"* — implemented in code, not asserted in prose. The real limitation is narrow: the recorded
runs corpus is empty and the golden corpus is three files
(`autobot-backend/eval/golden/`: `code_fix_null_guard.json`, `qa_deploy_role.json`,
`triage_502_websocket.json`). **That is a corpus gap, not a harness defect**, and the harness is
already refusing to report a false green. Recorded here so this does not get re-filed as a bug.

### D6. The discipline docs are not themselves enforced

`MEASUREMENT_DISCIPLINE.md` states its own remedy at `:213-217`: **"prose is not a guard. Where
a file carries a constraint that a future edit can violate, the constraint needs a mechanical
check, not a comment."**

Grepping `MEASUREMENT_DISCIPLINE|RATCHET_BASELINES` across `scripts/` and `.github/` returns
**three hits, all prose references** — `scripts/benchmark_decision_backends_test.py:9`,
`scripts/check_shell_file_size.py:82`, `.github/commit-trailer-baseline.txt:30`. No script,
hook or workflow enforces the discipline itself.

That is not hypocrisy — several *individual* ratchets are mechanically enforced
(`scripts/check_python_file_size.py` with `MAX_LINES=600` at `:79` and its frozen baseline
`repo_tests/python_file_size_ratchet_baseline.py`; `no-commit-trailers.yml`;
`duplication-guard.yml`; `ssot-coverage.yml`; `frontend_api_contract_ratchet_test.py`). And
`RATCHET_BASELINES.md:82-86` *forbids* a shared harness for the second-derivation rule on
purpose. But two gaps are stated in the docs themselves and remain open: the hardcoded-values
re-derivation is "outstanding" (`RATCHET_BASELINES.md:291-307`) and the commit-trailer boundary
is "Not guarded" (`:282-290`). And `ratchet-base-guard.yml:28-36` says in its own header that it
is **not a required status check and cannot block a merge**.

**Verdict: no adoption from the source here.** Its guidance package compiles rules into gates,
which sounds like the answer — but AutoBot's per-ratchet approach with a frozen baseline and a
known-positive test is more rigorous than a generic gate engine, and the source's own gates ship
with `toolAllowlist: false` by default. The finding is ours to act on, not theirs to lend.

### D7. Violations with severity exist — for code findings, not for runs

`llc/models/finding_proposal.py:19` `LLCFindingProposal` carries `severity` (`:43`),
`finding_type` (`:42`), `verdict_is_real` (`:47`), `verdict_confidence` (`:48`),
`verdict_rationale` (`:49`), `status` (`:50`), with a unique `(project_id, finding_key)`
(`:70`) — i.e. **one finding, one row, rediscoveries deduplicated**, which is the standing
"one defect, one fix" rule enforced in a schema. Queryable with a severity floor at
`llc/api/findings.py:52,100,119`. The verifier producing the verdict is
`llc/services/findings_verify.py:248` `verify_finding`, with cross-vendor combination at `:187`.

This is **materially ahead of the source's** violation ranking, which has no dedup key and no
verification step.

**No violation row carries a run id** — same join failure as D2/D3. Two near-misses are not
persisted at all: `security/enterprise/security_policy_manager.py:89` `PolicyViolation` lives in
an in-process list at `:127` with no table, and `secure_command_executor.py:931-932` appends
forbidden-command history to a Python list, not a store.

### D8. Nothing measures whether agent work gets better

`llc/services/agent_scorecard.py:58` `AgentScore(success_rate, reliability_score, throughput,
spend)` exists, exposed at `GET /sprints/{id}/agent-scorecard` (`llc/api/sprints.py:1200`) — but
it is **scoped to one sprint**, and cross-sprint trends are an explicit **Non-Goal** in its own
design doc (`docs/design/2026-07-26-agent-scored-retrospectives.md:38-39`). Its run→sprint
attribution is a time-window approximation because `work_item_id` is never populated by any
writer (`agent_scorecard.py:16-20`), and spend is labelled `spend_window="lifetime"` (`:74`).

`api/analytics_quality.py:618` `_build_quality_trends` is **codebase** health history, not agent
quality. `agents/task_pattern_learner.py:172,200` picks a strategy from judge scores and records
no before/after of whether the learned strategy helped.

**This is the same hidden metric Phase 1 charged the source with** — its learning loop
benchmarks retrieval latency and never measures outcome improvement. AutoBot has the same hole,
and unlike the source it has the records to close it (D1) once they carry verdicts (D2) and
identifiers (D3).

**Verdict: adopt-with-conditions, gated on D2+D3.** Visible benefit: "is the learning loop
working" becomes answerable instead of assumed. Hidden cost: a trend metric invites tuning
against it, and the design doc's Non-Goal was a deliberate scope decision — reversing it is an
owner call, not a drive-by.

---

## Summary

### What we can adopt

Ranked by value ÷ effort. Every row passed the audit-first gate (the AutoBot code was read, not
inferred) and carries both a visible benefit and a hidden cost.

| # | Adoption | AutoBot target | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|
| 1 | **Persist per-criterion evaluator results, not just the collapsed reward** | `memory/trajectory_store.py:179-195`, `orchestration/success_criteria.py:63` | "Why did this run score 0.5" becomes answerable | ~none — the data is computed and discarded one function later | **adopt** | trivial |
| 2 | **Put a run identifier on the judge's outcome record** | `judges/task_outcome_judge.py:52`, key at `:25` | Subjective score joins the run record; the learning loop becomes traceable | One field; needs the same key-cap treatment as `:142` | **adopt** (same PR as #1) | trivial |
| 3 | **A per-chunk byte ceiling on retrieved content** | `advanced_rag_optimizer.py:1000-1011` | Bounded scan window; closes the uncapped-first-chunk hole | One more tunable, next to the constant that already exists | **adopt** | trivial |
| 4 | **Screen at the retrieval boundary, not at each assembly site** | `services/retrieval_dispatcher.py:115`, the 5 assemblers | Four bypass paths close structurally; new assemblers inherit the defence | Needs an answer for internally-generated text that must not be mangled — the same question #17649 poses for writes | **adopt-with-conditions** | significant |
| 5 | **A state vocabulary for a claim** (`handoff-pending`, `stealable`, `abandoned`) | `autobot_shared/coordination/work_claims.py:237-247`, projected via `services/claim_projection.py` | One vocabulary for "what happened to this claim" across three layers that currently disagree | A status field on a Redis-only record invites treating it as durable, against `store_authority.py:257-268`. Condition: the enum lives on the projection, not the claim | **adopt-with-conditions** | moderate |
| 6 | **Contradiction check at write time, not only as a sweep** | `services/knowledge/contradiction_detector.py`, `knowledge/facts.py:1570` | Catches the conflict while the writer is still there to be told | A second contradiction path unless folded into the existing detector | **adopt-with-conditions**, low priority | moderate |
| 7 | **Adversarial forensics over the vector store** | new; nearest is `knowledge/vector_repair.py:168` | Finds payloads that landed before a defence existed — relevant to #17649's 26 writers | Recurring LLM spend over the whole collection; a finding queue nobody owns | **adopt-with-conditions**, *after* #4 | significant |
| 8 | Reaper for expired claims | — | — | — | **rejected** — reverses a recorded ruling (`work_claims.py:20-24`, `store_authority.py:257-268`) | — |
| 9 | Contest window on a steal | — | — | — | **rejected** — ours (`claim_yield.py:24-27`, silence = HOLD) is the stronger design; wire it, don't replace it | — |
| 10 | Load rebalancing across agents | — | — | Needs a live per-agent load model and re-opens every ownership question in C2–C3 | **rejected by hidden metrics** | — |
| 11 | The harness itself (install, plugins, MCP surface) | — | Coordination + memory + learning prebuilt | Repo-writing install onto our own agent-policy surface; 71 KB instruction-file context tax; release every 1–3 days; duplicate governance plane | **rejected by hidden metrics** | — |

### What we already do better

| Area | AutoBot | Evidence |
|---|---|---|
| Federation trust | Same formula and lattice, plus a capability matrix, PII-block→trust feedback, an audit DB with actor-recorded grant/revoke | `a2a/trust_score.py:106,189,285-309,349`, `a2a/task_executor.py:202,243-249` |
| Outbound PII policy | Same 14 types and 4 actions, but the policy table is SSOT-loaded and governed by a single-owner boundary doc | `a2a/pii_pipeline.py:15,31-33,79-92` |
| RAG screening strength | On by default, fail-closed, and the untrusted marking reaches the prompt the model reads | `services/knowledge/service.py:96`, `security/content_firewall.py:64-70,298-301` |
| Coordination doctrine | A CI guard that fails the build on a new claim primitive, plus structurally unforgeable ownership | `repo_tests/one_claim_registry_16653_test.py:290`, `work_claims.py:353-362` |
| Yield semantics | Silence resolves to **HOLD**, not to takeover | `services/claim_yield.py:24-27,132-165` |
| Run records | Replay, and **diff two runs** — no source equivalent | `llc/api/replay.py:179,253,291,318` |
| Findings | One finding one row, with a verification verdict and confidence | `llc/models/finding_proposal.py:19,43-50,70`, `llc/services/findings_verify.py:187,248` |
| Data safety on consolidation | Epoch-gated, circuit-broken, dry-run-default, never touches curated facts | `knowledge/facts.py:1570-1594` |
| Honesty of instruments | A harness that logs `UNMEASURED` rather than report a false green | `autobot-backend/eval/run.py:155-162` |

### Gaps and opportunities, prioritised

1. **Four RAG assembly paths reach a prompt without the firewall** (B2) — **three live, one
   latent.** One defect class, four instances, the sharpest being content appended *after* the
   firewall at `services/rag_service.py:857,864`. The latent one is agentic RAG: `agentic_context`
   is written at `chat_workflow/graph.py:1302` and read nowhere in the repository, tests included,
   so the bypass exists and nothing currently traverses it. That makes it a weaker instance and a
   stronger warning — it becomes live the moment anything reads that state, with no further defect
   required. Belongs in one issue listing all four, not four issues, and not three.
2. **The claim event never fires in production** (C6). The projection is built, allow-listed by
   name, and has zero production callers, so a claims UI gets no push and must poll. The state
   half works and #15949 closed correctly — its ACs tested the publisher, never a caller.
3. **The evaluator's detail is discarded and the judge's score cannot be joined to a run**
   (D2, D3). Two trivial fixes that together unlock D8.
4. **Ingest provenance is written "so retrieval can weigh trust" and never read** (B4) — six
   writers, zero readers. The producer half of `priority: critical` **#16776**.
5. **The uncapped first chunk** (B3) — `advanced_rag_optimizer.py:1007`, `and context_parts`.
6. **No redactor runs on the retrieval path** (B5), though `REDACTION_BOUNDARY.md`'s own routing
   table assigns outbound-to-an-LLM a policy. Doc defect or code defect — an owner question.
7. **Nothing measures whether agent work improves** (D8), gated on 3.
8. **The contested-yield machinery has no production caller** (C2) — "wire it in", not "build it".

### Specific files affected

```
autobot-backend/memory/trajectory_store.py          D2 — persist results[], not just reward
autobot-backend/judges/task_outcome_judge.py        D3 — add run_id to TaskOutcomeRecord
autobot-backend/advanced_rag_optimizer.py           B3 — per-chunk ceiling; B2 — first-chunk gap
autobot-backend/services/rag_service.py             B2 — firewall the post-hoc prepend/append
autobot-backend/services/cag_service.py             B2 — CAG path has no firewall
autobot-backend/services/retrieval_dispatcher.py    B2 — KAG path; the chokepoint's natural home
autobot-backend/knowledge/search_components/agentic_search.py   B2 — latent (unwired today)
autobot-backend/agents/scope_enforcement.py         C6 — acquire path bypasses the projection
autobot-backend/services/claim_projection.py        C6 — publishers with no callers
autobot-backend/services/claim_yield.py             C2 — better than the source's, unwired
autobot_shared/coordination/work_claims.py          C3 — no state vocabulary
autobot-backend/knowledge/ingest_sanitize.py        B4 — provenance written, never read
```

### Closing verdict

**The source is not adoptable and was never likely to be** — a Node meta-harness that writes
into the repository it manages, against a Python/Vue platform with its own coordination doctrine,
redaction boundary and rule set. Phase 1 called that on hidden metrics and Phase 2 confirms it:
its headline capability (federated zero-trust agents with a PII pipeline) is **already built here
and ahead**, down to an identical trust formula arrived at independently sixteen months ago.

What the comparison was actually worth is different from what it was aimed at. Of eleven
candidates, three are trivial adoptions, one is a real architectural borrow, and four of the
prioritised gaps are defects in AutoBot that the source had nothing to do with — surfaced because
reading someone else's answer to a problem forces you to locate your own. The single most useful
sentence in the whole exercise is one AutoBot already wrote about its own write path, in #17649:
*"a writer cannot skip a defence it does not know about."* The source's retrieval guard is that
sentence applied to readers, and it is the one place where AutoBot argued a principle on one side
of the store and not the other.

**Filing:** nothing filed yet — this is a research session, and the gap list above is for the
owner to convert. Items 1–3 and 5 are self-contained enough to batch; item 4 is a witness on
#16776 rather than a new issue; item 2 is already filed as #16646 — see Part E.

---

## Part E — dedup against the existing backlog

Run before anything is filed, per *search open **and** closed issues first* and *one defect, one
fix*. **Two findings this doc first called "new" were already filed** — corrected below, with the
issue that owns each.

### E1. Already filed — my contribution is a witness, or a line-number refinement

| Finding | Existing home | Correction |
|---|---|---|
| **C6** — claim events never fire; the acquire path calls `try_acquire` directly | **#16646** OPEN, `not-wired`, `v0.11.0`, wave 1, parent #15946 — *"claim events never fire — hold_scopes calls try_acquire directly instead of the publishing wrapper"* | **This doc first called it new. It is not.** #16646 states it exactly, and its ACs are stronger than what I would have written — including *"a guard test asserts that no production module calls `work_claims.try_acquire`/`release` directly, except the wrapper itself"*. One refinement to contribute: #16646 cites `scope_enforcement.py:134-139` (`hold_scopes`); the direct call is actually one level down in `_acquire_all` at **`:211-215`**, which is where the guard must point. |
| **C3** — a claim has no state vocabulary | **#16649** OPEN — *"one queryable view of who is doing what, **in which state**"* | Its AC joins each claim with its task state, naming the same three stores. Witness. |
| **B4** — ingest provenance, 6 writers / 0 readers | **#16776** OPEN `priority: critical` — no taint propagation | #16776 traces the consumer end; B4 is the producer end already emitting. Witness, one wire. |
| **D5** — the trajectory gate compares each golden against itself | **#16157** OPEN (with #16115, #16159), parent #16108 | Already filed, and correctly framed there. Nothing to add. |

### E2. Partially covered — same file, different function

**B2 bypass #1** (`services/rag_service.py:857,864` — synthesis and lessons text appended *after*
the firewall) is **not** covered by an existing issue, but **#16780** (OPEN, `priority: high`)
covers a *sibling gap in the same file*: `RAGService.advanced_search()` at `:786-801` merges
`doc_indexer_service` results into the returned list without inspection.

Same file, same defect class, same fix pattern — #16780's AC even specifies reusing the shared
firewall call rather than "a fourth independent copy". Under *issues touching the same file go in
ONE PR, solved by ONE agent*, bypass #1 **appends to #16780**; it does not get its own issue.

### E3. Genuinely new — zero search results

| Finding | Searches returning zero |
|---|---|
| **B2 bypasses #2–#4** — CAG (`services/cag_service.py`), KAG (`retrieval_dispatcher.py:80`), agentic (`agentic_search.py:377`) have no firewall | `CAG KAG firewall`, `kb synthesis prepend`, `assembled context inspect`, `agentic_search firewall` |
| **B3** — the first retrieved chunk is uncapped (`advanced_rag_optimizer.py:1007`, `and context_parts`) | `context length first chunk`, `chunk size cap retrieval`, `oversized chunk` |
| **B5** — no redactor runs on the retrieval path | write-side twins are #17025 and #17649; read side uncovered |
| **B6** — no adversarial forensics over the vector store | `KB audit injected content`, `retro scan knowledge base`, `vector_repair` (the one hit, #13277, is the empty-document bug) |
| **C2** — `claim_yield` and `claim_waitlist` have zero production callers | `claim_yield`, `claim waitlist`, `yield scope holder`, `arbitrate claim` — all four zero |
| **D2 / D3** — evaluator detail discarded; judge record has no run id | no home; #10603 is the umbrella for built-but-disconnected |
| **F13** — `chat_workflow/graph.py:1302` writes `agentic_context`, nothing reads it | `agentic_context`, `agentic RAG unwired`, `graph.py agentic` — all zero |

### E4. The umbrellas that already own this work

- **#16777** — *"Umbrella: indirect prompt injection — close the document to action chain"*. Its
  Goal states the structural finding this doc arrived at independently: **"The defenses exist;
  they are applied at the wrong granularity."** Tasks 1–3 are #16770 (write chokepoint), #16771
  (chat RAG path), #16776 (taint). **B2–B6 are more instances of its own thesis**, and the
  retrieval-boundary chokepoint is the missing Task 4.
- **#17217** — *"Umbrella: declared controls that do not execute — the regulated-readiness gap"*.
  Its table catalogues controls that exist, are documented, and never run (`ComplianceManager`
  never instantiated, three rate-limiter singletons never called, `emergency_system_stop` stopping
  nothing). **C2 and C6 are the same shape**, and so is the root cause in E5.
- **#10603** — built-but-disconnected machinery; home for D2/D3 and A4's grounding path.

### E5. The root cause behind #17217's pattern

Both children of umbrella #15946 closed COMPLETED with careful, criterion-by-criterion evidence
verified against merged base — and both left their primitive with no caller:

| Issue | Closed | Closure evidence | Callers today |
|---|---|---|---|
| **#15948** — waitlist, yield, arbitration | 2026-09-08 | per-criterion table citing `claim_waitlist.py:212,268,291,305,318`, `claim_yield.py:39,51,106` | **test-only** |
| **#15949** — claim events + claims API | 2026-09-09 | per-criterion table citing `claim_projection.py:58,70,98,108,125` | API half live; **publishers test-only** |

Neither closure was wrong. Every criterion each issue *stated* was met and verified the way the
rules require. **The criteria never asked whether anything calls the thing.** #15949's AC1 —
"the three event types publish via `events/bus.py`" — is satisfied by a correct publisher nobody
invokes.

That is why #17217 keeps finding the same shape from unrelated corners: it catalogues the
instances, and the mechanism producing them is upstream, in how acceptance criteria are written.
Two witnesses, one finding. **The fix is a criterion of the form "a named production call site
exists"** on any issue whose deliverable is a module rather than a behaviour — the
`--fail-on-unwired` idea (`llc-contract.yml:62-77`) applied to ACs instead of routes. Worth
proposing on #17217 as its root cause rather than filing as a sixteenth instance.

### E6. Consolidated filing shape

Nothing is filed by this session. If the owner converts it — **4 new issues, 5 witness comments**,
not 13 issues:

| # | Action | Target |
|---|---|---|
| 1 | **Append** bypass #1 (`rag_service.py:857,864`) | comment on **#16780** — same file, one PR, one agent |
| 2 | **New** — CAG + KAG + agentic bypasses, the uncapped first chunk, and the read-side chokepoint proposal | child of **#16777** (its missing Task 4) |
| 3 | **New** — no redactor on the retrieval path | child of **#16777**, sibling to #17025/#17649 |
| 4 | **New** — persist per-criterion results + run id on the judge record (D2+D3, one PR) | child of **#10603** |
| 5 | **New** — wire `claim_yield`/`claim_waitlist` (C2) | child of **#17217**, referencing #15948 |
| 6 | **Witness** — `_acquire_all:211-215` is the real direct-call site, not `:134-139` | comment on **#16646** |
| 7 | **Witness** — provenance producer end | comment on **#16776** |
| 8 | **Witness** — claim state vocabulary evidence | comment on **#16649** |
| 9 | **Witness** — the AC-design root cause (E5) | comment on **#17217** |
| 10 | **Witness** — grounding built, registered, uncalled (A4) | comment on **#16533** |

B6 (vector-store forensics) is deliberately **not** filed: it is only worth doing after item 2
lands, since a read-side screen makes stored poison inert without having to find it.
