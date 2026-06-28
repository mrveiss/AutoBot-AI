# Handoff: issue-10126-u7disc
status: complete
pr: #10433
base_at_push: beb3a9f7f0d791efc6e8a451981bc83e751aa238
gates: hook-test=27/27 git-cliff=catch-all-renders code-review=APPROVE(no HIGH/MED)
needs_rebase_before_merge: no
remaining: (none for this PR)
notes:
  - Scope was 4 U7 #9926 discovery issues; #10119 + #10059 were fixed by other
    sessions mid-work (closed via #10402 / #10393). Dropped those 2 commits;
    PR carries only #10126 + #10118.
  - Filed discovery #10434 (pre-existing `git -c ... checkout` hook bypass, low).
  - #10117 (GPL-3.0 vs ISC vendored dep) intentionally NOT touched — owner-gated
    licensing under relicense epic #9826.
worktree: .worktrees/issue-10126-u7disc  (safe to remove after #10433 merges)
