# Handoff: issue-17024-tool-args-hooks
status: complete
pr: #17044
base_at_push: 0e9b3a82bc505cb769bfb1b7cd6d0560074d8272
gates: wiring=n/a — .claude/settings.json only, no product code touched
needs_rebase_before_merge: no
remaining: (none)
worktree: .worktrees/issue-17024-tool-args-hooks (safe to remove after #17044 merges)

## done
Fixed the two `$TOOL_ARGS`-based hooks in `.claude/settings.json` to read
stdin JSON instead, matching the one proven-working hook in this file
(`block-dangerous-commands.sh`). Pipe-tested against synthesized stdin JSON.

## notes
- Originally attempted alongside #17029 in one PR per the user's request, but
  #17029 turned out to already be solved by another session in parallel
  (branch `issue-17029-commit-msg-hook`, PR #17032) — discovered via a
  push rejection (non-fast-forward) against a branch I hadn't fetched first.
  Dropped my duplicate commit entirely rather than touch that branch; only
  the genuinely-unclaimed #17024 fix is in this PR.
- #16938 (also requested) was already in flight in another active worktree
  (issue-16923-git-hook-formatters) before I started — not touched.
- #17021 (the umbrella) should close once #17032 and #16938's PR both land;
  not evaluated further here since neither is this branch's work.
