---
name: adopt
description: End-to-end external-feature adoption pipeline — audit AutoBot first, research the source, file umbrella + child issues for confirmed gaps, implement each through merged PRs, report with evidence. Use when the user asks to adopt, port, or bring in features from an external repo/article, or to drive research through to merged code.
---

# Adopt External Features

Pipeline: pre-flight → research → confirm → file → implement → evidence report. Each step gates the next. This skill orchestrates existing skills — it duplicates none of their content.

## Input

`/adopt <source> [focus areas]` — source is a URL, GitHub repo, or local file (same auto-detection as `/research`).

## Steps

1. **Pre-flight**
   - Open PR count ≥5 → defer, report, stop
   - Remove stale worktrees (`git worktree list` — merged branch but directory present)
   - Confirm self-hosted runner is online before planning CI-dependent work
2. **Research** — invoke the `research` skill on the source (Phase 1 → user gate → Phase 2). Its audit-first gate applies: nothing is adoptable without cited proof it doesn't already exist in AutoBot.
3. **STOP — user confirms the adoption list.** No issues are filed and no code is written without explicit go-ahead on which gaps to adopt.
4. **File issues** — one umbrella issue owning the adoption goal + one child issue per confirmed gap (use the `issue` skill; umbrella task-list format from global CLAUDE.md). Link each child to its Phase 2 evidence.
5. **Implement each child** — use the `implement` skill per child: own worktree `.worktrees/issue-XXXX/`, tests, PR to `Dev_new_gui`, CI green, merge, close, worktree cleanup. Max 3 children in flight.
6. **Evidence report** — final table, one row per child:

   | Child issue | PR | Commit SHA | CI | Merged | Gaps |
   |---|---|---|---|---|---|

   A row may only read "done" with every artifact present. Missing artifact → flag it and resume the work; never report it complete.

## Rules

- Never skip step 3 — filing issues and writing code require explicit user approval
- Subagent completion claims count only after artifact verification (`git log`, `gh pr view`) — no commits/PR means not done
- Checkpoint Phase 1/2 output and the evidence table to a file incrementally (scratchpad or umbrella issue comment) so an interruption never loses the audit
- Update the umbrella checklist after every child merges
- Discovered off-task bugs → file discovery issues, per Core Rule 6
