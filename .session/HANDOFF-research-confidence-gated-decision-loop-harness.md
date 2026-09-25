# Handoff: research/confidence-gated-decision-loop-harness

status: complete
pr: #17472 (opened by a peer session, not by this one — carries the doc plus another session's research docs)
branch: none — research scope, no worktree, branch, commit or PR created by this session
base_at_push: n/a
gates: n/a — no code changed
needs_rebase_before_merge: n/a
worktree: none created

## What this session did

A two-phase `/research` run over an external agent-harness repository: Phase 1 source analysis,
Phase 2 comparison against AutoBot backed by six parallel read-only audits (agent-loop
termination, action permission, context compaction, MCP ingestion, escalation/handoff,
objective & eval). Every load-bearing claim was re-verified directly before publication.

Analysis: `docs/research/confidence-gated-decision-loop-harness.md`

## Filed — all relationship edges created and read back as verified

- #17466 MCP tool annotations never ingested (parent #13227)
- #17467 unparseable MCP tool dropped to a log; every discovery failure labelled "unreachable" (parent #13227)
- #17468 two independent iteration caps — `graph.py:1530` hardcodes 5 beside `MAX_CONTINUATION_ITERATIONS` (parent #17271)
- #17469 three timeout budgets in `AgentLoopConfig` read by nothing (parent #17217)
- #17470 ten free-text tool-status spellings, two synonym pairs (parent #17271, blocked_by #17279)

Correction posted to #14031: `PreActionVerifier` now HAS a production caller at
`chat_workflow/tool_dispatch_guards.py:154`; `AgentLoop` itself still has none. The
belief-state half of #14031 was NOT re-checked — treat it as open and unverified.

Routed as witnesses, deliberately not re-filed: #17279, #17277, #17273, #13414, #13229,
#16755, #17459, #14031.

## Open for whoever comes next

- **#17468 is unclaimed** — a genuine two-line fix, deliberately left unclaimed rather than
  pulled into an unrelated PR. Take it with the file, not beside it.
- **Working tree diverges from PR #17472 on this doc.** The uncommitted copy in the tree is the
  UNSCRUBBED original; the committed copy on `issue-17471-research-docs` has been partly scrubbed
  for source-identifying detail. Do not commit the tree copy over the branch copy.
- **Scrub is incomplete on the branch** — exact repository dates and commit count survive at
  L38, a measurement date at L176, an exact conformance check count at L180, and the commit
  count in the `docs/research/_index.md` row. Exact replacements were sent to the PR's author;
  if they were not applied before merge, apply them in a follow-up.
- `#13227`'s six original tasks (#13228-#13232, #13240) are checklist prose with no native
  sub-issue edges. The two children filed here are currently its only linked ones. Not fixed —
  re-parenting another umbrella's children was out of scope.

## Not this session's work — do not sweep

`docs/research/agentic-desktop-os-distribution.md`,
`docs/research/layer-streamed-low-vram-finetuning-cli.md`,
`.session/HANDOFF-research-agentic-desktop-os-distribution.md`, and the other modified rows in
`docs/research/_index.md` belong to a different session and were already dirty when this one
started.
