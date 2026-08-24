---
name: implement
description: End-to-end GitHub issue implementation — umbrella gate, worktree, design, code, verify, PR, CI, and the three-gate closure check. Use when told to implement, fix, or solve a specific issue number, or when picking the next issue off the backlog. Supersedes the former `issue` skill.
---

# /implement — End-to-End Issue Implementation

Read your assigned step from the umbrella issue before proceeding.

## Step 0 — Umbrella gate (MANDATORY)
- The task must hang off a GitHub umbrella issue with a task/subtask breakdown. Missing → create it first.
- Add this issue as a subtask checklist item on the umbrella before coding.

## Step 1 — Verify the issue is real and unclaimed
- `gh issue view <n> --json state` — closed or missing → STOP.
- `gh pr list --search "<n>"` and `git branch -a | grep -i "<n>"` — no existing PR or branch.
- **No PR-count gate.** There is no open-PR limit; dispatch gates on review capacity. PRs piling up means review is the bottleneck — review, don't defer.

## Step 2 — Investigate, then design (do NOT code yet)
- Grep/Glob for the affected files; confirm each exists.
- Post the plan in ≤10 lines: files, changes, edge cases, risks.
- Seek approval only if >10 files are touched; otherwise proceed.
- Write a TodoWrite checklist of discrete, testable tasks.

## Step 3 — Worktree (MANDATORY, never edit the main tree)
```bash
git worktree add ../worktrees/issue-<n> -b issue-<n> origin/Dev_new_gui
```
- Branch off the PR base branch, never the GitHub default. Never touch another session's worktree.
- Commit incrementally inside the worktree — never `git stash` (it is shared repo-wide).

## Step 4 — Implement
- <8 files: Read → Edit → verify syntax → next file. No subagents.
- ≥8 files or genuinely parallel work: subagents.
- Run the relevant tests after each task; fix failures before continuing.

## Step 5 — Verify
```bash
pytest <test_dir>
git diff --name-only | grep '\.py$' | xargs flake8 --max-line-length=100
mypy <files>
```

## Step 6 — Commit
```bash
git add <files>
git commit -m "<type>(scope): <description> (#<n>)"
```
- Format is `<type>(scope): <description> (#issue)`. `tech-debt` is NOT a valid type.
- **No commit trailers.** mrveiss is sole author — never add `Co-Authored-By`.
- Never `--no-verify`.

## Step 7 — Pre-push quality checks (MANDATORY)
```bash
# print() outside tests → use get_logger(__name__)
grep -r 'print(' autobot-backend/ autobot_shared/ --include='*.py' | grep -v '#' | grep -v 'test_'
# console.* in TS/Vue → use createLogger()
grep -r 'console\.' autobot-frontend/src/ --include='*.ts' --include='*.vue'
black autobot-backend/ autobot_shared/ autobot-slm-backend/
isort autobot-backend/ autobot_shared/ autobot-slm-backend/
ruff check --fix autobot-backend/ autobot_shared/
git add -u && git diff --cached --quiet || git commit -m "style(format): auto-format (#<n>)"
```
- Frontend lint is oxlint AND eslint — `npx eslint` alone passes while CI fails.

## Step 8 — Push and open the PR
```bash
git push -u origin issue-<n>
gh pr create --base Dev_new_gui --title "<type>(scope): <title> (#<n>)" --body-file <file>
```
- Target `Dev_new_gui`. `main`/`master` are blocked by the pre-commit hook.
- PR body uses these exact headings — never Summary/Test Plan:
  `## Thinking Path` · `## What Changed` · `## Verification` · `## Model Used`
- Use `--body-file`, never an inline `--body`: backticks inside it execute as shell commands.

## Step 9 — CI (do not exit until green)
- `gh pr checks <PR>` — repeat until nothing is PENDING; `smoke-test` must be SUCCESS.
- Dedupe check-runs to the latest push; sort by `startedAt` — rollup order is not chronological.
- **Red CI never merges.** Root-cause it; a tracking issue is not a substitute. Never `--admin`.
- Never merge a branch behind base — a green run describes a merge base that may have moved.

## Step 10 — Merge or hand off
- Merge: `gh pr merge <n> --squash --delete-branch` (verify the remote tip first).
- Must wait: post ONE comment, set status `in_review`, STOP. Never busy-poll.
- `Closes #N` NEVER auto-closes on this repo — always close by hand.

## Step 11 — Three-gate closure check (MANDATORY)
```bash
pipeline-scripts/check-new-module-callers.sh
pipeline-scripts/check-issue-close-refs.sh <n>   # exit 1 = forward refs dangle → do NOT close
```
- **Gate 1 — verbatim ACs:** quote each issue-body AC word-for-word with evidence, or `❌ NOT met → follow-up #X`. Never restate what shipped instead.
- **Gate 2 — dangling refs:** the script above; also eyeball the credited PR diff for `#<n>`.
- **Gate 3 — no partial close:** a bundled PR's `Closes #A, #B` requires each issue's FULL AC set. Subset delivery → check off the subtask, leave the issue open or name the follow-up in the same comment.
- New module with 0 production callers → wire it in, or file a `wire-in:` issue first and reference it.
- Host-behaviour ACs need HOST evidence, never merge evidence.

```bash
gh issue comment <n> --body-file <file>   # implementation ACs + integration ACs, with evidence
gh issue close <n>
gh issue view <n> --json state            # confirm
```

## Step 12 — Dispose
- Remove the worktree only after the PR is merged and the content is verified in base.

## Success checklist
- [ ] Umbrella issue with step breakdown exists; issue verified open, no duplicate PR/branch
- [ ] Work done in a worktree off `origin/Dev_new_gui`, committed incrementally
- [ ] Tests + lint + mypy pass; no `print(`/`console.` violations; formatted
- [ ] Commit format correct, no trailers, no `--no-verify`
- [ ] PR targets `Dev_new_gui` with the four required headings; smoke-test green; not behind base
- [ ] Every new module has ≥1 caller, or a wire-in issue is filed and referenced
- [ ] All three closure gates run; issue closed by hand and confirmed
