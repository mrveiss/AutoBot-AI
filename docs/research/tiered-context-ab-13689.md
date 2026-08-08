# Tiered L0–L4 context stack — A/B result and flag decision (#13689)

**Date:** 2026-08-08
**Issue:** #13689 · umbrella #13685 · original experiment #5066
**Harness:** `autobot-backend/scripts/tiered_context_ab.py` (committed; re-run to reproduce)
**Decision:** **Leave `tiered_context_enabled` OFF.** Reason below — it is a specific,
fixable blocker, not a null result.

---

## Why this record exists

#5066 shipped the stack behind an A/B flag and left no recorded outcome. The absence was read as
"the tiered stack isn't worth enabling", when in fact the experiment could never have won: two of
the five layers were structurally unable to render (#13686, #13687), so the flag compared the
legacy path against the legacy path plus a static identity block.

Both are now fixed and merged. This is the first run where all five layers can render, and this
file exists so the next person does not have to re-derive the outcome from an unexplained default.

## Result — all five layers render

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
**AC 1 satisfied** — the first time it could be.

Cost: **+14 to +45 tokens** and **+6 to +8 ms** of assembly per turn.

## The blocker: L3 duplicates the retrieval the chat path already does

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

**Filed as #13742.** The flag should flip once it is resolved; the rest of the evidence supports
enabling.

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

## Decision

**Off, pending #13742.**

- All five layers work; the stack does what #5066 intended.
- Token and latency costs are modest and acceptable.
- The single blocker is L3's duplicate retrieval, which wastes both context and money on exactly
  the turns L3 is meant to help.

`autobot_shared/ssot_config.py` links this file from the `tiered_context_enabled` field so the
default is explained where it is defined, not only here.

## Reproducing

```bash
PYTHONPATH=".:autobot-backend" python3 autobot-backend/scripts/tiered_context_ab.py
PYTHONPATH=".:autobot-backend" python3 autobot-backend/scripts/tiered_context_ab.py --json
```
