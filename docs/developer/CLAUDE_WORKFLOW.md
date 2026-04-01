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

**All fleet deployments go through the SLM Manager (.19) via Ansible playbooks.**

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
- CI runs Python 3.12 (deadsnakes PPA) — never use 3.13-only packages
- All nodes: deadsnakes PPA python3.12 venv at `/opt/autobot/<component>/venv`

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
2. `git status`
3. `git stash list` — if present, ask user
4. `git fetch origin Dev_new_gui && git log --oneline origin/Dev_new_gui -3`

---

## Multi-Agent Safety

- Do NOT create/apply/drop `git stash` unless explicitly requested
- Do NOT switch branches unless explicitly requested
- When pushing, use `git pull --rebase`
- "commit" = YOUR changes only; "commit all" = everything in grouped chunks
- Prefer incremental `Edit` over full file `Write` for files >50 lines

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

---

## Debugging, Errors, Self-Improvement

**Debugging:** Form a hypothesis first, then 3-4 commands to confirm/reject.

**Error Handling:** Auto-retry transient errors up to 2 times.

**Self-Improvement:** After corrections, update `tasks/lessons.md`.

**Elegance Gate:** For non-trivial changes, pause and ask "Is there a more elegant way?" — but elegance means the simplest correct solution.
