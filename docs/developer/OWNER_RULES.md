# Owner Rules Register

Where a doc restates one of these, this file wins; add new owner rules here first, then link from the doc.

Each entry: **rule** · date · replaces · detail.

| # | Rule | Date | Replaces | Detail |
|---|---|---|---|---|
| 1 | No open-PR cap; push finished work, never hold it local-only | 2026-10-23 | the cap-40 rule (#17006) | [#19397](https://github.com/mrveiss/AutoBot-AI/issues/19397) |
| 2 | The trainmaster (the PR-coordinator session) builds and lands merge trains, sets CI priority and fixes small findings in-train; authors send PR number and head and do not push to a queued head unless asked | 2026-10-22/23/24 | author-merges-own-PR flow | [CLAUDE_REVIEW.md](CLAUDE_REVIEW.md#merge-trains) |
| 3 | Two CI slots; exactly one train worked at a time | 2026-10-24 | "one PR's CI at a time" (2026-10-02) | [CLAUDE.md](../../CLAUDE.md#when-rules-conflict) |
| 4 | Merge trains use merge commits, never squash | 2026-10-11 | squash-only merging | [CLAUDE_WORKFLOW.md](CLAUDE_WORKFLOW.md) |
| 5 | Never cancel a train branch's CI; check `ledger holds` for `ci-slot` first | 2026-10-23 | "cancel freely" (2026-09-24) | [CLAUDE_REVIEW.md](CLAUDE_REVIEW.md#ci-diagnosis) |
| 6 | Targeted local tests plus whole-tree guards only, never the full local suite; CI is the full gate; the `machine:heavy-run` hold is at most 20m per chunk, trains first | 2026-10-23 | full local `repo_tests/` before review (2026-10-18) | [CLAUDE_CLOSURE.md](CLAUDE_CLOSURE.md) |
| 7 | Reuse your own clean, fully pushed worktree before adding one; take over orphans | 2026-10-21/24 | "never reuse a worktree" | [CLAUDE_GIT.md](CLAUDE_GIT.md) |
| 8 | Claim worktrees in the ledger on create/reuse (`ledger claim worktree`) and release on removal | 2026-10-24 | empty "claim" commits | [CLAUDE_GIT.md](CLAUDE_GIT.md) |
| 9 | At session end: push everything, release claims, remove worktrees with plain `git worktree remove`, never `--force` | 2026-10-24 | forced sweeps | [CLAUDE_GIT.md](CLAUDE_GIT.md) |
| 10 | `Closes #N` auto-closes on merge: write `Closes` only when every AC is delivered, otherwise `Refs` | 2026-09-12 | "Closes never auto-closes" | [CLAUDE_CLOSURE.md](CLAUDE_CLOSURE.md) |
| 11 | No commit trailers; `mrveiss` is sole author | standing | tool-default trailers | [CLAUDE.md](../../CLAUDE.md) |
| 12 | CodeRabbit is advisory, but every comment is answered (fixed, or replied to with the reason): it never blocks a PR opening or its first CI run, while answers are due before any relaunch and before merge | 2026-10-02/10-11/10-24 | "resolve every thread before any CI" read as blocking | [CLAUDE_REVIEW.md](CLAUDE_REVIEW.md#merge-trains) |
| 13 | A hook or guard that blocks your branch is fixed in its own PR first, because the installed hook runs from the main checkout | standing | "fix it in the same PR" for hooks | [CLAUDE_REVIEW.md](CLAUDE_REVIEW.md#pr-granularity) |
| 14 | Goal milestones M1-M4 hold all their issues; phases are `phase:Mx.y` labels, listed in order in each milestone's description | 2026-10-23 | phase sub-milestones Mx.y | GitHub milestones M1-M4 |
| 15 | **Company OS** is the AutoBot feature (code name `llc`); docs, UI strings and issue titles name the feature "Company OS". **AutoBot LLC** is the virtual example company used when documenting Company OS features: keep it as the example, never as the feature's name | 2026-10-22/24 | "AutoBot LLC" used as the feature name | [#19184](https://github.com/mrveiss/AutoBot-AI/issues/19184) |
| 16 | Compliance wording is "aims towards", never "is compliant"; register: [`docs/compliance/COMPLIANCE_TARGETS.md`](../compliance/COMPLIANCE_TARGETS.md) | 2026-10-22 | n/a | [COMPLIANCE_TARGETS.md](../compliance/COMPLIANCE_TARGETS.md) |
