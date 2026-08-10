# Tiered L0–L4 context stack — A/B result and flag decision (#13689)

**Date:** 2026-08-08
**Issue:** #13689 · umbrella #13685 · original experiment #5066
**Harness:** `autobot-backend/scripts/tiered_context_ab.py` (committed; re-run to reproduce)
**Decision:** ~~**`tiered_context_enabled` is now ON.**~~ **CORRECTED 2026-08-10 — reverted to OFF (#13866).**

It was measured OFF and stayed off until the one blocker below was fixed. That sequence is kept
rather than rewritten — a decision record that only shows its final state teaches nothing about
how it was reached. The correction below is appended for the same reason.

---

## CORRECTION (2026-08-10, #13866) — this result was measured against test doubles

**The headline below ("all five layers render") is false against production code.** The flag has
been reverted to OFF. Read the correction before the result.

The harness mocks the memory graph and the knowledge service. Both mocks diverge from production
in exactly the way that hides a defect, and the two layers whose fixtures diverge most are the two
that do not work:

| Layer | Result below | Against production code |
|---|---|---|
| L0 | renders | renders a **compile-time constant** — `AutoBotConfig` has no `owner`/`agent` attribute, so both getattr chains always fall through to literals (#13867) |
| L1 | renders | already rendered before the flip, via the legacy path — **no new content**, and a small net cost: the tiered path additionally routes it through `_fit_l0_l1`, which can only shrink it |
| L2 | renders | **cannot render** — entities carry `observations`; the layer reads `description`/`content`, which no write path produces (#13686, reopened) |
| L3 | renders | **cannot render** — `knowledge_service=None` since #13742 (`29eeb904b`), merged in a *sibling* PR earlier the same day, **before** this measurement ran |
| L4 | renders | renders for work-item-bound sessions, and since #13729 only when the binding also passes a membership re-check — narrower still |

Specifically, before this correction the harness supplied `ENTITY_FACTS = [{"name": "Redis",
"description": "..."}]`. No production code produces an entity document with a `description` key.
The harness also mocked the knowledge service — while `29eeb904b`, already merged on this branch,
had removed it from the production call site. The mock contradicted merged code at the moment the
A/B ran.

So "+14 to +45 tokens" describes the mocks. Only **L4** contributes anything that varies with the
turn; L0 adds a fixed block, L1 was already there, and L2 pays up to 20 Redis round-trips per turn
to return an empty string.

The latency figure is stale for a second reason: #13729 added two indexed DB queries on *bound*
sessions after this measurement was taken, and the number here was never revised. (The per-turn
Redis GET for the binding is **not** new — it predates #13729, from #13704.)

**What this record got wrong methodologically:** it correctly noted "real retrieval latency is not
measured here" as an open caveat, then drew a default-changing conclusion as if the caveat were
closed. A layer that has never rendered in production cannot be certified by a fixture written
alongside it — the fixture and the layer share the same wrong assumption, so they agree.

**Re-enabling requires:** #13686 and #13867 fixed, and this A/B re-run against a live backend with
entity documents built by `_build_entity_document`. Not another mock-based pass.

---

## Why this record exists

#5066 shipped the stack behind an A/B flag and left no recorded outcome. The absence was read as
"the tiered stack isn't worth enabling", when in fact the experiment could never have won: two of
the five layers were structurally unable to render (#13686, #13687), so the flag compared the
legacy path against the legacy path plus a static identity block.

Both are now fixed and merged. ~~This is the first run where all five layers can render~~ (**false — three of five cannot; #13866**), and this
file exists so the next person does not have to re-derive the outcome from an unexplained default.

## Result — all five layers render (SUPERSEDED)

> **SUPERSEDED (2026-08-10, #13866)** — see the correction at the top of this file.


| Case | Path | Tokens | ms | Layers rendered |
|---|---|---|---|---|
| plain | tiered | 30 | 8.4 | identity, essential_story |
| | legacy | 16 | 1.4 | essential_story |
| entity mention | tiered | 61 | 9.5 | identity, essential_story, **related_context (L2)** |
| | legacy | 16 | 1.0 | essential_story |
| retrieval keyword | tiered | 49 | 7.2 | identity, essential_story, **deep_search (L3)** |
| | legacy | 16 | 1.0 | essential_story |
| goal-linked session | tiered | 50 | 6.8 | identity, essential_story, **goal_ancestry (L4)** |
| | legacy | 16 | 1.1 | essential_story |

L0 and L1 always; L2 on an entity mention; L3 on a retrieval keyword; L4 on a bound session.
~~**AC 1 satisfied** — the first time it could be.~~ **Not satisfied: L2 and L3 cannot render (#13866).**

~~Cost: **+14 to +45 tokens** and **+6 to +8 ms** of assembly per turn.~~ **Retracted — measured against mocks (#13866).**

## The blocker that held it off — now fixed (#13742, merged `29eeb904b`)

`chat_workflow/llm_handler.py:914` calls `_retrieve_knowledge_context` on every turn where
`use_knowledge` is set, which calls `knowledge_service.conversation_aware_retrieve` (`:692`).

`Layer3DeepSearch.render` calls **the same method on the same service** with the same query.

So enabling the flag today means, on any turn whose message contains a retrieval keyword
(`find`, `search`, `tell me about`, …):

- **two** KB retrievals instead of one — double the vector search, double the latency, double
  the cost of whatever the retrieval backend charges;
- **the same chunks twice in the prompt** — once inside the tiered context block, once in the
  grounded-context section — spending the context window to tell the model the same thing twice.

That is not a tuning question. It is a wiring defect that the A/B surfaced precisely because it
is the first run where L3 could fire at all.

**Fixed in #13742.** The main RAG path keeps ownership of retrieval — it is the copy that passes
through `budget_grounded_context` for trimming and citation rebinding — and the tiered builder is
no longer handed a `knowledge_service`. Verified by call count: one retrieval per turn.

~~With that resolved, every criterion this issue set is met, and the flag is on.~~ **False — see the correction (#13866).**

## What was NOT measured, stated plainly

- **Answer quality.** Recall quality is unmeasurable until #13251/#13243 — `rag_benchmarks.py`
  scores a fake embedding over 20 synthetic documents. #13689 deliberately excludes this: the
  decision rests on what the stack demonstrably puts in the prompt, its token cost, and its
  latency. Do not read "leave it off" as a quality judgement; none was made.
- **Real retrieval latency.** The harness mocks the knowledge service and the memory graph, so
  the numbers above are *assembly* cost. In production L2 and L3 make real calls. The duplicate
  retrieval above makes that worse in a way the mocked figure understates.
- **Live deployment.** No numbers here come from a running backend.

## A regression the A/B caught on its way

The first run showed the tiered path at **50–65 ms** per turn versus under 1 ms for legacy.
Profiling put essentially all of it in one place:

```
L1.token_estimate     49.036 ms/call      →  0.329 ms/call after fix
_fit_l0_l1            41.503 ms/call      →  0.665 ms/call after fix
```

`Layer1EssentialStory.token_estimate` re-read and re-parsed `config/context_windows.yaml` on
every call. That method had no production caller until **#13691** wired it into `_fit_l0_l1` to
derive the per-model budget — so the cost was introduced by that change and had never shown up.

Worth recording as a pattern: #13706 added a cached `ContextWindowManager` factory *specifically*
to stop per-turn parsing of this exact file, and #13691 then reintroduced a per-turn parse of it
through a different entry point. The fix reuses the cached manager rather than adding a second
cache, so there is now one parser of that file. Tracked as **#13741**.

The table above is measured **after** that fix. Reporting the pre-fix numbers as the tiered
path's cost would have made the flag look far worse than it is.

## Decision (SUPERSEDED)

> **SUPERSEDED (2026-08-10, #13866)** — see the correction at the top of this file.


~~**On.**~~ **Reverted to OFF on 2026-08-10 (#13866).**

- All five layers work; the stack does what #5066 intended.
- Token and latency costs are modest and acceptable: +14–45 tokens, +6–8 ms assembly.
- The single blocker — L3's duplicate retrieval — is fixed (#13742), so enabling no longer
  doubles retrieval cost.

~~**What would reverse this:** evidence that the added context hurts answer quality.~~
**This got it wrong.** The decision was reversed on entirely different grounds: the layers it
credited were never rendering, so there was no added context to evaluate (#13866).

`autobot_shared/ssot_config.py` links this file from the `tiered_context_enabled` field so the
default is explained where it is defined, not only here.

## Reproducing

```bash
PYTHONPATH=".:autobot-backend" python3 autobot-backend/scripts/tiered_context_ab.py
PYTHONPATH=".:autobot-backend" python3 autobot-backend/scripts/tiered_context_ab.py --json
```
