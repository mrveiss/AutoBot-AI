# Handoff: issue-13685
status: complete
pr: #13693
base_at_push: cc6760931
gates: n/a — docs-only; no code paths touched. Vendor-token grep PASS (see notes)
needs_rebase_before_merge: no
remaining: (none for this branch — the nine filed issues are all unbuilt, see below)
worktree: .worktrees/issue-13685-docs  (safe to remove after #13693 merges)

## What this branch is

The research artifact behind umbrella #13685 — a comparison audit of an external layered-memory
implementation against our own memory and context-assembly stack. Two files:
`docs/research/layered-agent-memory-and-context-offload.md` (474 lines) and one `_index.md` row.

The branch is *only* the doc. No code fix in this PR.

## Issues filed from this session (all UNBUILT)

Umbrella **#13685** — the tiered L0–L4 context stack was built, merged, and never ran.

| Wave | Issue | What |
|---|---|---|
| 1 | #13686 | L2 OnDemand can never render — `memory_graph` read off an object outside its MRO |
| 1 | #13687 | L4 GoalAncestry can never render — ancestry chain never passed at the only call site |
| 1 | #13688 | memory data plane takes no owner (security) |
| 2 | #13689 | run the #5066 A/B with all five layers live; record the result; flip or park the flag |
| 2 | #13690 | `memory/compat.py` — no production callers, sole user of the untenanted plane |
| 2 | #13691 | L0+L1 budget guard warns instead of trimming (depends on #13640) |
| 2 | #13694 | context-fit decisions run on `words × 1.3`; breaks on code, JSON, CJK |
| 3 | #13692 | no context offload of tool output (the only real capability gap) |
| — | #13695 | spun out: distillation is clock-bound; idle-flush only, knobs deferred behind #13251 |

Cross-links posted on #13640 and #13251.

## Recommended next action

**#13686.** Smallest fix on the list, and #13689 cannot produce a meaningful result until it and
#13687 land — with those two outstanding, two of the five layers return `""` unconditionally, so
the A/B compares the legacy path against the legacy path plus a static identity block.

Do **not** start #13689 first. That is the trap this whole umbrella documents.

## Notes for the next session

- **Do not widen #13686 into a `getattr` cleanup.** A sweep found 14 non-test
  `getattr(self, "...")` sites in `autobot-backend/`; 13 are correct.
  `services/llm_api_key_service.py:116` in particular is a deliberate, documented
  test-injection seam and must not be "fixed". Evidence table is a comment on #13686.
- **The umbrella carries a do-not-re-propose list** (four-service memory topology, per-user LLM
  persona regeneration on a timer, bespoke adapter contract) and a not-in-scope list of things we
  already do better. Read it before proposing memory work.
- **Anonymization:** one vendor env-var identifier survived the first commit because the
  verification grep used word boundaries (`\bNAME\b`) and `_` is a word character — the trailing
  `\b` cannot match inside a `SCREAMING_SNAKE_CASE` token. Fixed in `dbb59ad8`; the false CLEAN
  claim in the PR body was corrected rather than left standing. Screen for the vendor's product,
  company and env-var prefixes **without** word boundaries, case-insensitively. Do not write the
  screened tokens into any artifact — a note explaining the leak must not re-leak it, which is
  the mistake this line replaces.
- **This doc was nearly lost.** It was first written into `docs/research/` in the *main* tree,
  which fast-forwarded twice mid-session (`git reflog`: `pull --tags origin Dev_new_gui`), taking
  the untracked file with it. It survived only because it had already been moved here. Write
  research into a worktree from the start — the main tree is shared and moves under you.
- Pre-existing `<<<<<<< SEARCH` strings under `docs/external_apps/.../Open Source prompts/` are
  literal content of vendored diff-format prompt templates, not conflict markers. They will trip
  a naive `grep '^<<<<<<< '` tree sweep. This branch's own diff is clean (0 hits).
