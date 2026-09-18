# Handoff: issue-17028-bug-ledger
status: complete
pr: #17031
base_at_push: ba987556e7323b6aa6dafeffbf1cdc7c7f5be6dc
gates: wiring=n/a — docs-only, no code touched
needs_rebase_before_merge: no
remaining: (none)
worktree: .worktrees/issue-17028-bug-ledger (safe to remove after #17031 merges)

## done
Added "## Known Self-Inflicted Bug Patterns" section to CLAUDE.md — 8 items
clustered from reviewer-caught defects across the last 20 merged PRs
(#16860-#16973), each citing its source PR numbers.

## notes
- Evidence is review-comment-caught, not confirmed CI-failure history — stated
  explicitly in both the CLAUDE.md section and the PR body rather than
  overclaiming a CI-failure narrative the data didn't support.
- Worktree is unlocked (session ending) — safe for whoever observes the
  #17031 merge to dispose of via the normal `git worktree remove` +
  `git branch -D` + `git push origin --delete` sequence.
