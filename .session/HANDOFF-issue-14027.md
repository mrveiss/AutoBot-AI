# Handoff: issue-14027

status: complete
pr: #14032
base_at_push: d018373e11862d5503cffaed9e8cbf307fda7010
gates: wiring=N/A duplication=N/A tests=N/A (documentation-only change, no code paths touched)
needs_rebase_before_merge: no
remaining:
worktree: .worktrees/issue-14027  (locked; safe to remove after #14032 merges)

## What this branch is

Documentation only: `docs/research/agent-harness-guard-and-context-audit.md`
plus its `_index.md` row. It is the research artifact behind issues
#14027-#14031, moved out of scratch per the "filing an umbrella or design doc is
the trigger" rule.

**The branch name is misleading — this branch does NOT implement #14027.** It is
named `issue-14027` after the first issue the audit produced. The actual code
fix for #14027 is a different session's work; see below.

## Do not duplicate — #14027 is already being implemented elsewhere

A concurrent session owns the code fix:

- worktree `.worktrees/issue-14027-fix` (locked, reason "in use: #14027") — **not
  mine, not swept, left untouched**
- branch `issue-14027-fix`, commits `76e9be082` (normalize input before
  dangerous-pattern matching) and `5afdb3d1b` (require the OSC terminator so it
  cannot swallow the command)
- **PR #14038**, open

That second commit is worth reading before touching this area: an OSC-strip
without a required terminator will consume the rest of the command, which turns
a hardening fix into a bypass. Whoever reviews #14038 should verify the
both-directions assertion demanded by #14027's acceptance criteria — the bypass
case must now fail **and** a legitimate fullwidth-character filename must still
execute.

## Issues filed from this audit

| Issue | Gap | Wave | State |
|---|---|---|---|
| #14027 | `security/command_patterns.py` matches un-normalized input | 1 | in progress (PR #14038, other session) |
| #14028 | Gateway ingest has no bot-self filter, dedup, or recursion guard | 1 | open, unstarted |
| #14029 | Context windows static with a 4096 fallback; no probe, no learn-from-rejection | 1 | open, unstarted |
| #14030 | Distillation is per-conversation; recurrence invisible | 2 | open, **gated** on `AUTOBOT_SKILL_DISTILLATION_ENABLED` being true and producing accepted proposals |
| #14031 | Pre-action verifier + belief state run nowhere | Wave B of #13587 | open, unstarted |

Cross-cutting notes posted, not filed as issues:

- **#13587** — premise correction: its "Already covered" list cites
  `agent_loop/loop.py` for the pre-action verifier and durable checkpointing, but
  `AgentLoop` has no production caller.
- **#13250** — two-tier safety floor design input, deliberately a comment so it
  does not become a fifth approval mechanism. #14027 is its prerequisite.
- **#13919 / #13997** — cross-linked; same root cause as #14031. One extraction
  pass over `agent_loop/` beats three separate wirings.

## Next session — suggested order

1. Review and land **PR #14038** (#14027), applying the both-directions check above.
2. **#14031** together with #13919 and #13997 — one extraction pass over
   `agent_loop/`, following the #13590 pattern: pure decision function in
   `autobot_shared/`, called from the live seam, plus a wiring assertion.
3. **#14028**, then **#14029** — both wave 1, independent of each other.
4. Leave **#14030** parked until its gate opens.

## Pre-existing condition, not introduced here

`grep -rn "^<<<<<<< "` across the tree hits
`docs/external_apps/system-prompts-and-models-of-ai-tools-main/.../Cline/Prompt.txt`.
Those are example diff markers inside vendored prompt text, committed in #645 —
not conflict residue, and not in this branch's diff (`git diff origin/Dev_new_gui
--name-only` returns exactly the two docs files).
