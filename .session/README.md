# `.session/` — Session Handoffs

Sessions are mortal: they terminate before their PRs merge, so a session can
never clean up after its own merge. The session-lifecycle protocol inverts
responsibility — **every session cleans up after its predecessors at start, and
leaves a machine-readable handoff at end.** This directory holds those handoffs.

See the full protocol in
[`docs/developer/CLAUDE_WORKFLOW.md`](../docs/developer/CLAUDE_WORKFLOW.md#session-lifecycle)
and the `session-lifecycle` skill.

## When to write one

At the **end of every session** that touched a branch (also when blocked),
write `HANDOFF-<branch-name>.md` here and commit it on your branch. Slashes in
the branch name become dashes (`issue-1234`, `chore-triage-delta`).

## Schema

```markdown
# Handoff: <branch-name>
status: complete | blocked | partial
pr: #NNNN
base_at_push: <sha of origin/Dev_new_gui you rebased onto>
gates: wiring=PASS duplication=PASS tests=PASS|details   # or "n/a — <why>"
needs_rebase_before_merge: yes | no
remaining: <bullets, or "(none)">
blocked_on: <only when status=blocked — be precise>
worktree: .worktrees/<name>  (safe to remove after merge)
```

Optional blocks: `done:` (what landed) and `notes:` (gotchas for the next
session — base drift, untouched parallel worktrees, follow-up issue numbers).

| Field | Meaning |
|-------|---------|
| `status` | `complete` = mission done; `partial` = WIP committed with a `wip:` prefix; `blocked` = cannot proceed |
| `pr` | The PR this branch opened (`#NNNN`), or how to find it |
| `base_at_push` | The `origin/Dev_new_gui` SHA you rebased onto — lets the next session tell if a rebase is due |
| `gates` | Which gates ran and their result; `n/a` with a reason for docs/triage-only work |
| `needs_rebase_before_merge` | `yes` if base advanced past `base_at_push` with overlapping files |
| `remaining` | Outstanding work; empty when `complete` |
| `blocked_on` | Required only when `status: blocked` |
| `worktree` | The worktree path; the next session removes it once the branch merges |

## Lifecycle

A handoff is consumed by the **next** session's start protocol: it removes
worktrees/branches already merged into base and reads remaining handoffs to
decide whether to continue an unmerged branch (rebase first) or start fresh.
Handoffs for merged branches are safe to delete during that cleanup.
