# AutoBot Operational Workflow (Detail Reference)

> This file contains operational standards, git workflow, deployment, and agent delegation details.
> CLAUDE.md summarizes the key points; read this file when you need the full policy.

---

## General Workflow

- **No browsers for CLI tasks:** Use `gh`, `curl`, or API calls instead of Playwright/Puppeteer
- **3-command exploration limit:** If 3 commands haven't converged, write a hypothesis first
- **Propose before implementing:** For ambiguous tasks, state approach in 3 bullets and wait for confirmation
- **Implementation first:** Prefer direct implementation over brainstorming — brief plan (max 10 lines) then implement
- For large features (backend + frontend), complete and commit backend fully first
- Commit completed work incrementally
- If approaching context limit: stop at phase boundary, commit, add GitHub comment with next steps

---

## Deployment Architecture

**All fleet deployments go through the SLM Manager via Ansible playbooks.**

- **Code flow:** GitHub repo → SLM Manager pulls latest → Ansible deploys to fleet nodes
- **Primary playbook:** `autobot-slm-backend/ansible/playbooks/update-all-nodes.yml`
- **Node enrollment:** `autobot-slm-backend/ansible/playbooks/enroll-node.yml`
- **NPU worker role:** `autobot-slm-backend/ansible/roles/npu-worker/`
- **Manual sync (dev only):** `autobot-infrastructure/shared/scripts/utilities/sync-to-vm.sh`
- **Ownership:** All deployed files owned by `autobot:autobot`
- Never SSH into nodes for manual changes not captured in Ansible
- Test playbook changes with `--check` (dry run) before applying

---

## Git Workflow

**Pre-commit Self-Healing:**
- PostToolUse hook auto-runs Black + isort + `git add` after `.py` edits
- If pre-commit hook fails: read error, fix, re-stage, retry (max 3) — never `--no-verify`

**CI/Production Parity:**
- CI runs Python 3.14 (deadsnakes PPA) — never use 3.13-only packages
- All nodes: deadsnakes PPA python3.14 venv at `/opt/autobot/<component>/venv`

**Branch Strategy:**
- Always target `Dev_new_gui` for PRs unless told otherwise
- Delete remote feature branches after completing work

**Worktree & Branch Cleanup (MANDATORY after issue closure):**

```bash
git worktree remove .worktrees/issue-XXXX
git branch -d <branch-name>
git push origin --delete <branch-name>
```

Bulk: `scripts/cleanup-worktrees.sh --dry-run` then `scripts/cleanup-worktrees.sh`

**Pre-Flight Checks (before ANY code changes):**
1. `git branch --show-current`
2. `git status` — **if any files are dirty, commit or stash them NOW before spawning subagents or starting batch work.** Uncommitted edits are silently discarded when a subagent commits and upstream is merged. (See #4969.)
3. `git stash list` — if present, ask user
4. `git fetch origin Dev_new_gui && git log --oneline origin/Dev_new_gui -3`

---

## Session Lifecycle

Sessions terminate before their PRs merge, so a session cannot clean up after
its own merge. Responsibility is inverted: **each session cleans up its
predecessors at start and leaves a machine-readable handoff at end.** Full
protocol lives in the `session-lifecycle` skill; the handoff schema is in
[`.session/README.md`](../../.session/README.md).

**Start of session** (before any task work):
1. `git fetch --prune`, then remove worktrees + local branches already merged
   into `origin/Dev_new_gui` (inherited cleanup).
2. Create your **own** isolated worktree — never two sessions in one checkout:
   `git worktree add .worktrees/issue-XXXX -b issue-XXXX origin/Dev_new_gui`.
3. Read predecessor handoffs in [`.session/`](../../.session/): if a branch is
   unmerged, decide to continue it (rebase onto base first) or start fresh —
   never duplicate its work blind.

**End of session** (mandatory — also when blocked):
1. Leave nothing uncommitted; WIP gets a `wip:` commit and a handoff note.
2. Rebase onto latest base, re-run the relevant gates, grep for conflict
   markers (`^<<<<<<< `) before the final push.
3. Push and open/update the PR.
4. Write `.session/HANDOFF-<branch>.md` (see schema) and commit it on your branch.
5. Remove scratch only — **not** your own worktree; the next session's start
   protocol removes it after the branch merges.

LICENSE/NOTICE/SPDX headers are read-only during a session — flag concerns,
never edit.

---

## Multi-Agent Safety

- Do NOT create/apply/drop `git stash` unless explicitly requested
- Do NOT switch branches unless explicitly requested
- When pushing, use `git pull --rebase`
- "commit" = YOUR changes only; "commit all" = everything in grouped chunks
- Prefer incremental `Edit` over full file `Write` for files >50 lines

**schemas_common.py serialization constraint (response_model= batches):**
`autobot-backend/api/schemas_common.py` is an append-only file — every `response_model=` audit batch appends new Pydantic schema classes to its end. When two such batches branch from the same `Dev_new_gui` head and both append to this file, git always produces a `CONFLICT (content)`. This is not a real code conflict; it is a git limitation with concurrent appends to the same file.

Rules:
- **Do not run two `response_model=` audit batches in parallel.** Serialize them — wait for the first batch's PR to merge before starting the next.
- This constraint applies until issue #5799 (per-domain schema split) is resolved.
- If a conflict occurs anyway, the resolution is always deterministic:

```bash
# Step 1: take origin/Dev_new_gui as the authoritative base
git show origin/Dev_new_gui:autobot-backend/api/schemas_common.py > autobot-backend/api/schemas_common.py

# Step 2: append the new schema classes from our branch at the end
# (extract them from git diff or the conflicting branch's version)
```

---

## Agent Delegation

**Prefer direct implementation over subagents** — reserve for exploration/research.

**Worktree Isolation Warning:**
Do NOT use `isolation: "worktree"` for agents that create PRs. Instead, create manual worktrees:
```bash
git worktree add .worktrees/issue-XXXX -b <branch> origin/Dev_new_gui
cd .worktrees/issue-XXXX && git branch --unset-upstream
```

**Worktree Path Enforcement:**
- ALL file operations must target the worktree's absolute path
- Pass absolute path to sub-agents explicitly
- No nested worktrees — all flat under `.worktrees/`

**If subagent fails:** Switch to direct implementation immediately.

**Subagent Bash Permission Constraint:**
Subagents cannot autonomously acquire Bash permission. Run batch file-manipulation and git work in the main session.

**Available Agents:**
- Implementation: `senior-backend-engineer`, `frontend-engineer`, `database-engineer`, `devops-engineer`, `testing-engineer`, `code-reviewer` (MANDATORY), `documentation-engineer`
- Analysis: `code-skeptic`, `systems-architect`, `performance-engineer`, `security-auditor`, `ai-ml-engineer`
- Planning: `project-task-planner`, `project-manager`

---

## GitHub Workflow

**Issue Labels — always apply:**
- **Type:** `bug`, `enhancement`, `technical-debt`, `refactoring`, `security`, `performance`, `testing`, `documentation`
- **Area:** `backend`, `frontend`, `devops`, `database`, `mcp`, `rag`, `deployment`
- **Priority:** `priority: critical`, `priority: high`, `priority: medium`, `priority: low`

**Commit format:** `<type>(scope): <description> (#issue-number)`

**Always close the issue after implementation.** PRs targeting `Dev_new_gui` will NOT auto-close issues — verify with `gh issue view`.

**GitHub CLI Workarounds:**

- **`gh pr edit --body` silently fails** when the repo has classic Projects attached. The command exits non-zero and leaves the body unchanged. Error output:

  ```text
  GraphQL: Projects (classic) is being deprecated in favor of the new Projects experience
  ```

  Affected flags: `--body`, `--title`, `--assignee`, `--label`, `--milestone`, `--reviewer`.
  Use the REST API instead — it succeeds even with classic Projects attached:

  ```bash
  # Single-line body
  gh api repos/mrveiss/AutoBot-AI/pulls/$PR_NUMBER -X PATCH -f body="new body here"

  # Multi-line body (HEREDOC — required for PR descriptions with newlines)
  gh api repos/mrveiss/AutoBot-AI/pulls/$PR_NUMBER -X PATCH -f body="$(cat <<'EOF'
  ## Summary
  - change one
  - change two
  EOF
  )"

  # Update title
  gh api repos/mrveiss/AutoBot-AI/pulls/$PR_NUMBER -X PATCH -f title="new title"
  ```

  A convenience wrapper is available at `scripts/gh-pr-update-body.sh`:

  ```bash
  scripts/gh-pr-update-body.sh $PR_NUMBER "new body text"
  # or pipe a file:
  scripts/gh-pr-update-body.sh $PR_NUMBER "$(cat body.md)"
  ```

---

## Debugging, Errors, Self-Improvement

**Debugging:** Form a hypothesis first, then 3-4 commands to confirm/reject.

**Error Handling:** Auto-retry transient errors up to 2 times.

**Self-Improvement:** After corrections, update `tasks/lessons.md`.

**Elegance Gate:** For non-trivial changes, pause and ask "Is there a more elegant way?" — but elegance means the simplest correct solution.

---

## Pre-Merge Validation

Run these gates before creating a PR or merging any branch. Gates are ordered by cost — cheapest first.

### Gate 0: Squash-Duplicate Detection

Before running any other validation, check whether the branch contains commits that are already squash-merged to `Dev_new_gui`. A squash merge collapses N commits into one, so the individual commit SHAs differ even though the diff is identical. `git log --cherry-pick` detects this by comparing patch IDs rather than SHAs.

```bash
# Gate 0: Squash-Duplicate Detection
DUPES=$(git log --cherry-pick --right-only origin/Dev_new_gui...$BRANCH --oneline 2>/dev/null | wc -l)
TOTAL=$(git log origin/Dev_new_gui...$BRANCH --oneline 2>/dev/null | wc -l)
NEW=$((TOTAL - DUPES))
if [ "$DUPES" -gt 0 ]; then
  echo "WARNING: $DUPES of $TOTAL commit(s) already squash-merged to Dev_new_gui — $NEW truly new"
  git log --cherry-pick --right-only origin/Dev_new_gui...$BRANCH --format="  %H %s"
fi
```

**If DUPES == TOTAL:** The entire branch is already in `Dev_new_gui`. Close the issue without creating a PR — the work is done.

**If DUPES > 0 but < TOTAL:** Some commits are new. Rebase the branch onto `origin/Dev_new_gui` to drop the duplicate patches before opening a PR. This prevents merge conflicts and duplicate hunks in the diff.

**If DUPES == 0:** No duplicates — proceed to Gate 1.

### Gate 1: Syntax and Imports

```bash
# Backend
python -m py_compile <changed_files>
python -c 'import <module>' for each modified file

# Frontend
npx tsc --noEmit -p autobot-vue/tsconfig.app.json
```

### Gate 2: Call-Site Impact

For every function removed or renamed, grep all callers and verify none are broken:

```bash
grep -r "old_function_name" --include="*.py" src/
grep -r "oldFunctionName" --include="*.ts" --include="*.vue" autobot-vue/src/
```

### Gate 3: Targeted Tests

Run tests only for changed files to keep validation fast:

```bash
python -m pytest tests/$(dirname <changed_file>) -x -q
```

### Gate 4: Linting

```bash
# Use the project wrapper — it pins target-version=py312 + line-length=120
# so a host running Python 3.10 doesn't produce spurious diffs (#7249).
make format-check
# Or, equivalently, for the whole tree (note: `bash` prefix because
# scripts/*.sh files in this repo are committed without the exec bit):
bash scripts/format.sh --check
# For a specific file:
bash scripts/format.sh path/to/file.py
npm run lint --prefix autobot-vue 2>&1 | grep "error"
```

Direct invocations like `python -m black <file>` from a Python<3.12 host
will silently downgrade to py3.10 syntax (Black emits a warning, not an
error) and produce 100+-line spurious diffs — always use the wrapper.
