# Handoff: issue-10035
status: complete
pr: #10112
base_at_push: 8ae42e2bd96c7d80739204384d2b5bc12b3b8844
gates: tests=PASS (branch-guards_test.sh 15/15) · shell-syntax=PASS · workflow-yaml=PASS · shellcheck/actionlint=deferred-to-CI
needs_rebase_before_merge: no
remaining:
blocked_on:
worktree: .worktrees/issue-10035  (safe to remove after merge)

## What this is
PR-A of umbrella #9927 governance: hardened automated branch pruning (#10035 + code half of #9917).
New shared lib scripts/lib/branch-guards.sh (extract_issue_number / branch_recently_pushed /
branch_has_open_pr), wired into branch-cleanup.yml and cleanup-worktrees.sh; policy documented in
docs/developer/CLAUDE_GIT.md.

## Umbrella #9927 — remaining members (for next session)
- #9917 owner toggle: Settings → Pull Requests → Automatically delete head branches.
- #9464 PR→issue linking Action — NOTE: a worktree .worktrees/issue-9464 already exists; check it before starting.
- #10024 blocks-merge label gate + required_conversation_resolution decision.
- #9918 .session/README.md + CLAUDE_WORKFLOW.md protocol docs.
- #9911 one-time stale-branch backfill — run AFTER this PR merges, via the now-hardened
  scripts/cleanup-worktrees.sh --dry-run first. Owner-gated (destructive).
- #9857 / #9284 — already resolved in tree; verify-and-close with lock-file evidence.
