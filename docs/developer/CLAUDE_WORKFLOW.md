# AutoBot Operational Workflow (Detail Reference)

> This file contains operational standards, git workflow, deployment, and agent delegation details.
> CLAUDE.md summarizes the key points; read this file when you need the full policy.

---

## General Workflow

- **No browsers for CLI tasks:** Use `gh`, `curl`, or API calls instead of Playwright/Puppeteer
- **3-command exploration limit:** If 3 commands haven't converged, write a hypothesis first
- **Implementation first — clarify only on genuine ambiguity.** Default to a brief plan (max 10 lines) then implement. When the task *is* ambiguous, state the approach in 3 bullets and wait for confirmation (Rule 4 in [`CLAUDE_RULES.md`](CLAUDE_RULES.md)); inside a `/loop`, post the question with a recommendation and continue instead of blocking
- For large features (backend + frontend), complete and commit backend fully first
- Commit completed work incrementally
- If approaching context limit: stop at phase boundary, commit, add GitHub comment with next steps
- **Long analyses go to a file, not the response.** Start every one in a scratch path *outside*
  the repo, written incrementally as produced; the reply is the path plus a short summary.
  Filing an umbrella issue or a design doc is the trigger to move it into
  `docs/research/<topic>.md` (or `docs/audit/`, `docs/design/`) and cross-link it both ways.
  An interrupted or token-capped response must never lose the work

---

## Deployment Architecture

**Deployments are triggered through the builtin updater only** — the code-sync API /
self-update path a user reaches in the maintenance UI. It is the updater that runs the
playbooks below. Invoking ansible or ssh by hand is the banned side-channel: if the builtin
cannot do something, fix that gap (issue + PR) rather than routing around it. The playbook
paths here are for *reading and changing* the deployment, not for running it.

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

**Worktree & Branch Cleanup (MANDATORY once the branch's work is merged):**

```bash
git worktree remove .worktrees/issue-XXXX   # NO --force: a dirty tree is unfinished work
git branch -D <branch-name>                 # -D, never -d — see below
git push origin --delete <branch-name> 2>/dev/null || true   # usually already gone
git worktree prune
```

**Use `-D`, never `-d`.** A squash merge rewrites the commits, so the branch is never an
ancestor of the base and `git branch -d` refuses with "not fully merged" — silently aborting
the cleanup. Confirm the merge from the PR (`gh pr view N --json state,mergedAt`), never from
`git branch --merged`, then delete with `-D`. Remove the worktree *before* the branch; a
branch cannot be deleted while a worktree has it checked out.

Bulk: `scripts/cleanup-worktrees.sh --dry-run` then `scripts/cleanup-worktrees.sh`

**Pre-flight checks:** [`CLAUDE_GIT.md`](CLAUDE_GIT.md) "Pre-Flight Checklist" is the
canonical list. Steps 1-4 are universal and apply inside your own worktree; steps 5-8 apply
only when dispatching agents or starting batch work.

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
5. Remove scratch only — **not** your own unmerged worktree.

**Who disposes of a worktree:** whoever observes the merge. If your PR merges while you are
still running, clean up in the same breath as the merge (worktree, local branch, remote
branch) — a merged PR whose worktree still exists is an unfinished merge. If the session ends
first, the next session's start protocol is the backstop. Neither ever removes a worktree
whose work has not landed, and neither touches another session's tree.

LICENSE/NOTICE/SPDX headers are read-only during a session — flag concerns,
never edit.

---

## Multi-Agent Safety

- **Never** `git stash` — the stack is shared repo-wide, see [`CLAUDE_GIT.md`](CLAUDE_GIT.md#never-stash-14078)
- Do NOT switch branches unless explicitly requested
- When pushing, use `git pull --rebase`
- "commit" = YOUR changes only; "commit all" = everything in grouped chunks
- Prefer incremental `Edit` over full file `Write` for files >50 lines

**Schema files — the append-only conflict is resolved (#5799).** Schemas now live in
per-domain modules (`schemas_agent.py`, `schemas_analytics.py`, `schemas_terminal.py`,
`schemas_workflows.py`, `schemas_code.py`, `schemas_system.py`, and siblings), so parallel
`response_model=` batches targeting *different* domain files no longer collide and may run
concurrently.

Two batches appending to the **same** domain module still conflict — that is a git limitation
with concurrent appends, not a code conflict. Serialize those, or resolve deterministically:

```bash
# Step 1: take origin/Dev_new_gui as the authoritative base
git show origin/Dev_new_gui:autobot-backend/api/<schema-module>.py > autobot-backend/api/<schema-module>.py

# Step 2: append the new schema classes from our branch at the end
# (extract them from git diff or the conflicting branch's version)
```

---

## Agent Delegation

**Split by output type, not by convenience.**

- **Deliverables — implement directly.** Code, fixes, reviews, acceptance criteria: do them in
  the main session. Round-tripping a deliverable through a subagent adds a translation layer
  and loses the context that makes it correct.
- **Mechanical work — delegate to a Haiku agent.** Sweeps, inventories, per-PR status checks,
  log triage, caller traces, "which of these N files does X". Mechanical means deterministic,
  verifiable from its output, and requiring no judgement that ships.

**Delegation is not free** — a subagent costs a spawn, a prompt and its own context. For a
single deterministic command, run it inline. Delegate mechanical work only when it is also
**high-volume** (output would flood this context), **repeated** (N independent checks that can
fan out in parallel), or **high-discard** (most of what is read is thrown away).

**Tiers — pick by output type, not task difficulty.** This is the in-repo copy; the extended
routing table and the never-hand-to-Haiku list live in the global model-tiers doc.

| Tier | Model | Use for |
|---|---|---|
| Haiku | `claude-haiku-4-5-20251001` | mechanical work — sweeps, status checks, inventories, capture |
| Fable | `claude-fable-5` | plans and design documents — PRDs, architecture proposals |
| Sonnet | `claude-sonnet-5` | deliverables — code, reviews, acceptance criteria, approvals |

Never hand Haiku a deliverable or a judgement that ships. Each agent declares its own tier in
its `.claude/agents/` definition; an agent with no `model:` inherits the caller's model, which
is a bug rather than a default.

**Verify what comes back.** A subagent's report is an assertion, not evidence — more so the
cheaper the model. Confirm the artifacts (`git log`, `gh pr list`, read the file) before
acting on it. No artifacts ⇒ the work did not happen; resume it yourself.

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

**Update the issue as work progresses — not only at closure.** Post the pickup (what is being
attempted, and the base SHA), any decision taken under a `Decision` heading, and the state you
stopped in if the session dies. The issue is the only record that survives a lost worktree or
a different machine.

**Always close the issue after implementation.** PRs targeting `Dev_new_gui` will NOT auto-close issues — verify with `gh issue view`.

**CI diagnosis** and **posting comments correctly**: see [`CLAUDE_REVIEW.md`](CLAUDE_REVIEW.md)
— it owns both. In short: queued checks on the self-hosted runner are not failures, and a
comment body is literal markdown, never raw JSON or a file path.

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

**Shortcut — run the CI-facing gates in one command:**

```bash
scripts/pr-preflight.sh --issue N [--body pr.md] [--message msg.txt]
```

It reuses the *same* logic CI does rather than approximating it: the same `awk` extraction as `pr-template-check.yml` (so a heading that is present but placeholder-only fails locally exactly as it does in CI), the same keyword regex as `pr-issue-validation.yml`, and black/isort/flake8/bandit with the same flags as `code-quality.yml` — including bandit's absent severity floor, which is stricter than the medium-and-up filter used elsewhere. It also catches backticks in a commit message (the shell executes them when the message is passed via `-m`), authorship trailers, conflict markers, and fleet IPs. The gates below remain the reference; this runs the mechanical ones early.

**Match CI's interpreter first (#13573).** CI runs Python **3.14**. A box's default `python3` is often older, and every local gate silently uses it:

```bash
scripts/setup-ci-parity-env.sh     # build once; idempotent, no sudo
```

This builds the same environment `.github/actions/setup-python-suite/action.yml` builds — same interpreter, same `requirements-ci.txt` + `requirements-ci-test.txt`, same PyTorch CPU index, same venv path. `pr-preflight.sh` then picks it up automatically and reports which interpreter it used.

Running the gates on an older interpreter is not merely a version difference. **`black` skips its AST safety check** — the pass that verifies a reformat did not change the code — for any file using syntax newer than the running interpreter. It warns and passes anyway, so the weaker check is the silent one. Version-dependent tests are also unreproducible: `\z` in a regex is a `re.error` on 3.10 and valid from 3.12, so a red CI test can be green locally and diagnosable only from shard logs.

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
