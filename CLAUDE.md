# AutoBot Development Instructions

> **Rules:** [`docs/developer/CLAUDE_RULES.md`](docs/developer/CLAUDE_RULES.md) — read when starting a new task
> **Workflow:** [`docs/developer/CLAUDE_WORKFLOW.md`](docs/developer/CLAUDE_WORKFLOW.md) — labels, gh workarounds, CI diagnosis, pre-merge gates
> **Git & Worktrees:** [`docs/developer/CLAUDE_GIT.md`](docs/developer/CLAUDE_GIT.md) — branching, safety, push recovery
> **Batch & Agents:** [`docs/developer/CLAUDE_BATCH.md`](docs/developer/CLAUDE_BATCH.md) — parallel work, sub-agent rules
> **Code Review:** [`docs/developer/CLAUDE_REVIEW.md`](docs/developer/CLAUDE_REVIEW.md) — review methodology, merge checklist
> **Issue Closure:** [`docs/developer/CLAUDE_CLOSURE.md`](docs/developer/CLAUDE_CLOSURE.md) — closure gate, discovery issues
> **Reference:** [`docs/developer/AUTOBOT_REFERENCE.md`](docs/developer/AUTOBOT_REFERENCE.md)
> **Architecture exceptions:** [`docs/developer/ARCHITECTURE_EXCEPTIONS.md`](docs/developer/ARCHITECTURE_EXCEPTIONS.md)

Read a pointed doc only when its topic triggers. Universal rules (worktree mandate, issue decomposition, verification/evidence, CI diagnosis, no temp fixes) live in the global instructions and the docs above — not repeated here.

---

## Engineering Standard

Correctness → Speed → Maintainability. No wasted motion. No speculative work.

- **Parallelize** independent tool calls, file reads, agent tasks
- **Minimal surface area** — least code that fully solves the problem
- **Async-first** — never add sync calls to async paths
- **Decision speed:** ≤3 exploration commands then act; if stuck, escalate with findings

---

## Core Rules

**Every task must:** link to GitHub issue · search memory first · break into subtasks · use code-reviewer · update issue throughout · verify before closing.

1. **Check Before Writing** — search existing code/docs/PRs before creating anything
2. **Reuse** — import from `autobot_shared/`; never duplicate or hardcode
3. **Standardize** — ≤30-line functions; no `_v2`/`_fix` suffixes
4. **Clarify** — confirm architecture before coding
5. **Verify** — show evidence (test output, curl, build) before claiming done
6. **Report & Fix** — file GitHub issues for every discovered bug, even off-task, and **fix pre-existing issues discovered along the way** (same PR when in-scope; fast-follow when larger). ASK only for large refactors / product decisions / risky blast radius. See [`CLAUDE_RULES.md`](docs/developer/CLAUDE_RULES.md) Rule 6.

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
- **Security reviews are findings-first:** read the diff only, emit a severity/`file:line`/issue/fix table within 3 tool calls, verify *after* — never explore before the table lands (skill: `secreview`)
- **Never `--no-verify`** — PostToolUse hook auto-formats `.py`
- **Protected branches:** `main`/`master` blocked by pre-commit hook → use `issue-*` or `hotfix-*`
- **PR template headings:** `Thinking Path` · `What Changed` · `Verification` · `Model Used`
- **No internal info in outward artifacts:** never expose IPs, hostnames, secrets/tokens, or internal filesystem paths in GitHub issues/PRs/comments/logs — redact to generic role/node refs
- **PR queue limit:** ≥5 open PRs → defer implementation and notify
- **Codebase is source of truth:** never edit `/opt/autobot/` or `/var/log/autobot/`
- **System updates (test AND prod):** ONLY via the builtin updater a user reaches at `/slm/maintenance/updates/code-sync` (code-sync API / self-update); if the builtin can't do it, fix that gap (issue + PR) — never side-channel via ad-hoc ansible/shell
- **Batch similar-scope issues per PR:** one PR may close several similar-scope issues (`Closes #A, #B, …`) — each MUST be fully delivered (closure Gate 3: partial delivery never closes); genuinely independent or different-risk changes still get separate PRs
- **Model tiers:** Haiku (`claude-haiku-4-5-20251001`) for status/labels/simple transitions; Sonnet for implementation and reviews
