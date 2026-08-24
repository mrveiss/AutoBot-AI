---
name: session-lifecycle
description: Mandatory start-of-session and end-of-session protocol for every Claude Code session in this repository. Use this skill at the BEGINNING of every session (worktree setup, stale-branch inheritance cleanup, rebase onto latest base) and at the END of every session or when the user says wrap up, finish, end session, hand off, or when the mission is complete or cannot proceed. Also use when resuming or taking over a previous session's work, or when the working tree contains another session's leftovers. This skill applies to ALL sessions regardless of task — coding, docs, audits, reviews.
---

# Session Lifecycle Protocol

Sessions are mortal: they terminate before their PRs merge, so a session can
never clean up after its own merge. This protocol inverts responsibility —
**every session cleans up after its predecessors at start, and leaves a
machine-readable handoff at end.**

Base branch: `Dev_new_gui` (adjust if the dispatch says otherwise).

## SESSION START (do this before any task work)

1. **Sync, and REPORT — do not sweep:**
   ```bash
   git fetch --prune
   git worktree prune          # safe: only drops admin refs whose dir is already gone
   git worktree list           # read-only inventory
   ```

   **Never delete a worktree or branch you did not create.** Other sessions run
   concurrently, and a worktree that is clean with zero commits ahead is
   indistinguishable from a finished one — it is usually a session that has just
   started. A prior version of this step force-removed anything that looked
   merged and destroyed an in-progress worktree mid-task.

   Exceptions, and only these two: the user asks, or the leftover belongs to the
   issue you were dispatched to work on. Otherwise list what you found in the
   report and move on.

   When an exception applies, **cleanup means finishing the work, not deleting it**
   — see `~/.claude/docs/worktrees.md`:
   - **Landed** (the branch's own work is solved and merged, verified in base)
     → dispose, even if an umbrella issue is still open. A worktree is cheap to
     recreate; unfinished work is not.
   - **Stale** (untouched for several days, not landed) → rebase onto base →
     link or file its issue → solve it → PR → review → merge → *then* dispose.
   - **Active** (touched recently, or zero commits — a session that just
     started) → leave alone.
   - never `--force` (a dirty tree refusing removal is unfinished work, not an obstacle)
   - never `-d`/`-D` on ancestry alone; squash-merge makes ancestry lie — confirm
     via the branch's PR state
   - skip anything `locked`

2. **Create YOUR isolated worktree**, then claim it so a concurrent sweep cannot
   take it (never work in a shared checkout; never two sessions in one directory):
   ```bash
   git worktree add ../wt-<short-task-name> -b <type>/<task-name> origin/Dev_new_gui
   cd ../wt-<short-task-name>
   git worktree lock . --reason "in use: <task> (session started $(date -u +%FT%TZ))"
   git commit --allow-empty -m "chore: claim worktree for <task>"
   ```
   `lock` makes `git worktree remove --force` fail outright (it demands `-f -f`),
   and the claim commit stops "no unique commits" heuristics from classifying the
   worktree as finished. Unlock at the end: `git worktree unlock <path>`.
3. **Read predecessor handoffs:** check `.session/` directory on the base
   branch for HANDOFF files from unmerged sessions touching your area. If one
   exists and its branch is unmerged, decide: continue their branch (rebase it
   onto base first) or start fresh — never duplicate their work blind.
4. **Confirm gates run locally** before relying on them: the wiring audit,
   duplication guard, and test suite relevant to your task.

## DURING THE SESSION

- One commit per logical change; reference issues (`fixes #NNNN`).
- LICENSE, NOTICE, SPDX headers, and licensing statements are READ-ONLY.
  Flag concerns in the report; never modify.
- Never push directly to the base branch. Never merge — merging is the
  human's action.
- If you discover another session has landed overlapping work: rebase onto
  latest base immediately and reconcile before continuing.

## SESSION END (mandatory before terminating — also run when blocked)

1. **Leave nothing uncommitted:** `git status` must be clean. Work-in-progress
   that can't be completed gets committed to your branch with a `wip:` prefix
   and explained in the handoff — never left dangling in the worktree.
2. **Rebase onto latest base, re-run gates:**
   ```bash
   git fetch origin && git rebase origin/Dev_new_gui
   # re-run: wiring audit, duplication guard, relevant tests
   ```
   If the rebase conflicts and resolution is non-trivial, STOP — resolve only
   what you are confident about; otherwise note the conflict precisely in the
   handoff for the next session. NEVER commit conflict markers (grep
   `^<<<<<<< ` across the tree before the final push).
3. **Push and open/update the PR** with `gh pr create` (or `gh pr edit`):
   title = mission, body = summary + link to the report.
4. **Write the handoff file** `.session/HANDOFF-<branch-name>.md` committed on
   your branch:
   ```markdown
   # Handoff: <branch>
   status: complete | blocked | partial
   pr: #NNNN
   base_at_push: <sha of origin/Dev_new_gui you rebased onto>
   gates: wiring=PASS duplication=PASS tests=PASS|details
   needs_rebase_before_merge: yes|no
   remaining: <bullet list, empty if complete>
   blocked_on: <only if status=blocked — be precise>
   worktree: ../wt-<name>  (safe to remove after merge)
   ```
5. **Write the mission report** (`*_REPORT.md` per the dispatch prompt) — the
   handoff is for machines/next sessions; the report is for the human.
6. **Self-cleanup of scratch only:** remove temp files, caches, and anything
   not belonging on the branch. Do NOT remove your own worktree — it must
   survive until merge; the next session's start-protocol removes it after
   the branch merges.

## FAILURE MODES THIS PREVENTS
- Orphaned branches drifting behind base (start-step 1 + end-step 2)
- Committed conflict markers (end-step 2 grep)
- Two sessions colliding in one checkout (start-step 2)
- Duplicate work on the same problem (start-step 3 handoffs)
- Posthumous cleanup that never happens (inheritance model)
- Silent license/business-model changes (during-session read-only rule)
