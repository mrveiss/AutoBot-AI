# AutoBot Development Instructions

> **Full rules:** [`docs/developer/CLAUDE_RULES.md`](docs/developer/CLAUDE_RULES.md) — read when starting a new task
> **Full workflow:** [`docs/developer/CLAUDE_WORKFLOW.md`](docs/developer/CLAUDE_WORKFLOW.md) — read when needed
> **Reference (IPs, playbooks):** [`docs/developer/AUTOBOT_REFERENCE.md`](docs/developer/AUTOBOT_REFERENCE.md)
> **Worktrees:** Use `.worktrees/` (project-local, gitignored) for all parallel/isolated work

---

## Quick Reference

**Every task must:** link to GitHub issue, search Memory MCP first, break into subtasks, use code-reviewer agent, update issue throughout, verify before closing.

**Before proceeding:** Work tied to issue? Subtasks added? Memory searched? Root cause (not workaround)? If ANY fails: STOP.

---

## Core Rules (Summary)

1. **Check Before Writing** — search for existing code/docs/PRs before creating anything new
2. **Reuse Existing Code** — import from `autobot_shared/`, never duplicate or hardcode
3. **Standardize for Reuse** — shared modules, ≤30-line functions, no `_v2`/`_fix` suffixes
4. **Clarify Requirements** — ask all questions up front, confirm architecture before coding
5. **Verify Before Complete** — show evidence (test output, curl, build) before claiming done
6. **Report Every Problem** — file GitHub issues for all discovered bugs, even if not your task

> Full details with examples and violation cases: [`docs/developer/CLAUDE_RULES.md`](docs/developer/CLAUDE_RULES.md)

---

## Essential Patterns

**Redis:** `from autobot_shared.redis_client import get_redis_client` (databases: main, knowledge, prompts, analytics)

**Config:** `from autobot_shared.ssot_config import config` / `import { getBackendUrl } from '@/config/ssot-config'`

**Logging:** `logging.getLogger(__name__)` (backend) / `createLogger('Name')` (frontend). No `print()` or `console.*`.

**Encoding:** Always `encoding='utf-8'` explicitly.

**Copyright:** `mrveiss` is sole owner/author of all AutoBot code.

---

## Key Workflow Rules

- **Branch target:** `Dev_new_gui` for all PRs unless told otherwise
- **Commit format:** `<type>(scope): <description> (#issue-number)`
- **Pre-commit:** Never `--no-verify`. PostToolUse hook auto-formats `.py` files.
- **Worktrees:** No nesting. Manual creation for PRs (not `isolation: "worktree"`). Clean up after issue closure.
- **Agents:** Prefer direct implementation. Reserve subagents for research/exploration. Subagents can't acquire Bash permission.
- **Deployment:** All via Ansible playbooks on SLM Manager (.19). Never manual SSH changes.
- **No temporary fixes:** Zero tolerance for workarounds, TODO comments, try/catch hiding errors.
- **One issue per session:** Don't auto-start other issues after completing one.
- **Edit strategy:** `Edit` for files >50 lines, `Write` for new/small files.

> Full workflow details: [`docs/developer/CLAUDE_WORKFLOW.md`](docs/developer/CLAUDE_WORKFLOW.md)
