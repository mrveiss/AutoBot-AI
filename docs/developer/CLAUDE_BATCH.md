# Batch Execution & Parallel Agent Rules

## Batch Execution Default

When the user says "implement all X-labeled issues", "fix all Y bugs", or "run `/batch-implement` on Z" — **launch immediately without asking for scope clarification.**

Default behavior:
- Batch size: 3 agents max per round (API rate limit)
- All issues get their own worktree: `.worktrees/issue-XXXX/`
- Main session stays on `Dev_new_gui` — never switches
- Agents commit locally; main session pushes and creates PRs
- After each batch: review, merge, file discovery issues, then next batch

**Do NOT ask:** "Which issues?", "Parallel?", "How many?" — just run the pre-flight checklist and start.

**Only stop** if: specific issue has unresolved dependencies, architectural decision needed, or pre-flight finds a problem.

**Domain schema files (resolved #5799):** Parallel batches targeting different domain files can run concurrently without conflicts — see `schemas_terminal.py`, `schemas_analytics.py`, `schemas_agent.py`, `schemas_system.py`, `schemas_workflows.py`, `schemas_code.py`.

---

## Pre-Implementation Validation

**Before spawning agents, verify:**

1. `git branch --show-current` — must be `Dev_new_gui`
2. `git status --porcelain` — if dirty, commit or stash before spawning
3. Issue not already resolved: check `git log origin/Dev_new_gui --grep="#<issue>"`
4. No stale worktrees: clean up existing `.worktrees/issue-<number>/` directories
5. Issue preconditions resolved

---

## Parallel Agents Strategy

1. **Main session stays on `Dev_new_gui`** throughout — never switches
2. **Agents work in isolated worktrees** — no cross-contamination
3. **Batch size: 3 agents max** — avoid API rate limiting (529 errors), wait between batches
4. **Agents commit locally only** — do NOT push; main session handles all pushes
5. **After each batch:** `/batch-implement` auto-detects failures:
   - API 529 → wait 60s, retry
   - Merge conflicts → auto-rebase, retry
   - Already resolved → skip
   - Agent crash → retry up to 3 times
   - Only escalate unresolvable issues

---

## Sub-Agent Permission Enforcement (CRITICAL)

Sub-agents without Bash permissions cannot complete git operations and stall mid-batch.

**Required tools for every implementation agent:** `Bash, Read, Edit, Write, Grep, Glob`

**Every agent prompt MUST include:**
> "You have Bash, Read, Edit, Write, Grep, and Glob permissions. If you lose Bash permissions at any point, STOP immediately and report — do not retry or work around it."

**Pre-launch check:** Confirm main session has Bash approved — sub-agents inherit from parent.

**On permission failure:** Do not retry the same agent. Report: which agent failed, at which step, what was left incomplete. Main session completes the git operation manually.

---

## Headless / Automated Audit

```bash
# Validate all open PRs before merge window
for pr in $(gh pr list --state open --limit 20 --json number -q '.[].number'); do
  /pre-merge-validate $pr || gh pr comment $pr -b "❌ Validation failed"
done

# Nightly codebase audit (cron: 0 23 * * *)
/dead-code-audit >> /var/log/codebase-audit.log
```
