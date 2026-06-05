# AutoBot Development Instructions

> **Rules:** [`docs/developer/CLAUDE_RULES.md`](docs/developer/CLAUDE_RULES.md) — read when starting a new task
> **Workflow:** [`docs/developer/CLAUDE_WORKFLOW.md`](docs/developer/CLAUDE_WORKFLOW.md) — read when needed
> **Git & Worktrees:** [`docs/developer/CLAUDE_GIT.md`](docs/developer/CLAUDE_GIT.md) — branching, safety, push recovery
> **Batch & Agents:** [`docs/developer/CLAUDE_BATCH.md`](docs/developer/CLAUDE_BATCH.md) — parallel work, sub-agent rules
> **Code Review:** [`docs/developer/CLAUDE_REVIEW.md`](docs/developer/CLAUDE_REVIEW.md) — review methodology, merge checklist
> **Issue Closure:** [`docs/developer/CLAUDE_CLOSURE.md`](docs/developer/CLAUDE_CLOSURE.md) — closure gate, discovery issues
> **Reference:** [`docs/developer/AUTOBOT_REFERENCE.md`](docs/developer/AUTOBOT_REFERENCE.md)
> **Architecture exceptions:** [`docs/developer/ARCHITECTURE_EXCEPTIONS.md`](docs/developer/ARCHITECTURE_EXCEPTIONS.md)

---

## Engineering Standard

Correctness → Speed → Maintainability. No wasted motion. No speculative work.

- **Parallelize** independent tool calls, file reads, agent tasks
- **Minimal surface area** — least code that fully solves the problem
- **Async-first** — never add sync calls to async paths
- **Decision speed:** ≤3 exploration commands then act; if stuck, escalate with findings

---

## Quick Reference

**Every task must:** link to GitHub issue · search Memory MCP first · break into subtasks · use code-reviewer · update issue throughout · verify before closing.

**Stop if any fails:** work tied to issue? subtasks added? root cause (not workaround)?

---

## Core Rules

1. **Check Before Writing** — search existing code/docs/PRs before creating anything
2. **Reuse** — import from `autobot_shared/`; never duplicate or hardcode
3. **Standardize** — ≤30-line functions; no `_v2`/`_fix` suffixes
4. **Clarify** — confirm architecture before coding
5. **Verify** — show evidence (test output, curl, build) before claiming done
6. **Report** — file GitHub issues for every discovered bug, even off-task

---

## Essential Patterns

| What | How |
|---|---|
| Redis | `from autobot_shared.redis_client import get_redis_client` |
| Config | `from autobot_shared.ssot_config import config` / `import { getBackendUrl } from '@/config/ssot-config'` |
| Logging | `logging.getLogger(__name__)` / `createLogger('Name')` — no `print()` or `console.*` |
| Encoding | Always `encoding='utf-8'` explicitly |
| Cache TTL | Never hard-code — use module-level constant from env var (see `chat_history/cache.py`) |
| LEDGER/EXECUTOR | Coordination tools complete instantly — do NOT wait; continue immediately with execution tools |
| Copyright | `mrveiss` is sole owner/author |

---

## Workflow Quick Rules

- **Branch target:** `Dev_new_gui` for all PRs
- **Commit format:** `<type>(scope): <description> (#issue-number)`
- **Never `--no-verify`** — PostToolUse hook auto-formats `.py`
- **Protected branches:** `main`/`master` blocked by pre-commit hook → use `issue-*` or `hotfix-*`
- **PR template headings:** `Thinking Path` · `What Changed` · `Verification` · `Model Used`
- **PR queue limit:** check open PR count before starting implementation; if ≥5, defer and notify
- **CI diagnosis:** queued checks on self-hosted runners are NOT stuck — confirm failure before acting
- **Posting comments:** write literal markdown — never raw JSON or a file path
- **Worktrees:** `.worktrees/issue-XXXX/` for all parallel work → read [`CLAUDE_GIT.md`](docs/developer/CLAUDE_GIT.md)
- **Codebase is source of truth:** never edit `/opt/autobot/` or `/var/log/autobot/`
- **One issue per session** — don't auto-start others after completing one
- **No temp fixes:** zero tolerance for workarounds, TODO comments, swallowed errors

---

## Model Tier Routing

- **Haiku** (`claude-haiku-4-5-20251001`): heartbeat status checks, label updates, simple transitions
- **Sonnet**: deep reviews, multi-file fixes, feature implementation, extended reasoning
