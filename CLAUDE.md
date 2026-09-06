# AutoBot Development Instructions

Index plus the rules that are catastrophic to miss. Everything else is in `docs/developer/` —
read a doc when its trigger fires, not before. Universal rules (worktree mandate, issue
decomposition, evidence, model tiers, never-idle) live in the global instructions and are not
repeated here; where the two disagree, **this file wins**.

## Read when triggered

| Trigger | Doc |
|---|---|
| Starting a task — the 8 core rules in full | [`CLAUDE_RULES.md`](docs/developer/CLAUDE_RULES.md) |
| Branching, worktree collisions, stashing, force-push, push recovery | [`CLAUDE_GIT.md`](docs/developer/CLAUDE_GIT.md) |
| Labels, `gh` workarounds, deployment, pre-merge gates | [`CLAUDE_WORKFLOW.md`](docs/developer/CLAUDE_WORKFLOW.md) |
| Opening, reviewing, or merging a PR (incl. the required body headings) | [`CLAUDE_REVIEW.md`](docs/developer/CLAUDE_REVIEW.md) |
| Closing an issue | [`CLAUDE_CLOSURE.md`](docs/developer/CLAUDE_CLOSURE.md) |
| Running parallel agents or a batch | [`CLAUDE_BATCH.md`](docs/developer/CLAUDE_BATCH.md) |
| Need a service, port, or architecture fact | [`AUTOBOT_REFERENCE.md`](docs/developer/AUTOBOT_REFERENCE.md) |
| Adding an event type, WebSocket route, bus, or session state | [`EVENT_STATE_DOCTRINE.md`](docs/developer/EVENT_STATE_DOCTRINE.md) |
| Reviewing or changing path validation, session ownership, plugin loading, or secrets | [`THREAT_MODEL.md`](docs/developer/THREAT_MODEL.md) |
| Deviating from a standard pattern on purpose | [`ARCHITECTURE_EXCEPTIONS.md`](docs/developer/ARCHITECTURE_EXCEPTIONS.md) |

## Engineering Standard

Correctness → Speed → Maintainability. No wasted motion, no speculative work.
Parallelize independent calls · minimal surface area · async-first · ≤3 exploration commands
then act.

**The 8 core rules** — full text in [`CLAUDE_RULES.md`](docs/developer/CLAUDE_RULES.md):
1 Check before writing · 2 Reuse from `autobot_shared/` · 3 Standardize (≤30-line functions,
no `_v2`/`_fix` suffixes) · 4 Clarify ambiguous architecture before coding · 5 Verify with
evidence · 6 Report **and fix** every discovered problem · 7 Grep the *behavior*, not the
symbol, on extraction PRs · 8 Outbound HTTP goes through the guarded fetch (egress policy).

## Never violate

- **PRs target `Dev_new_gui`.** `main`/`master` are blocked by the pre-commit hook — use `issue-*` or `hotfix-*`.
- **Never work from a stale base** — and the half that bites is the judgement, not the freshness. Answer "is this already done?" against current `origin/Dev_new_gui` and the issue's acceptance criteria, **never against an old branch**: a stale answer points toward doing *more* work, so nothing pushes back on it, and reviving such a branch can regress newer code. `git fetch origin` and branch from (or rebase onto) current base before the first edit — the auto-update bot only refreshes branches that already have a PR, so the window this covers is everything before the first push.
- **Commit format:** `<type>(scope): <description> (#issue-number)`. Never `--no-verify` — a PostToolUse hook auto-formats `.py`.
- **Never hardcode.** Config via SSOT, TTLs via env-var-backed module constants, no IPs or ports in code.
- **The codebase is the source of truth** — never edit `/opt/autobot/` or `/var/log/autobot/`.
- **System updates (test AND prod) go through the builtin updater only** — the code-sync API / self-update path a user reaches in the maintenance UI. If the builtin cannot do it, fix that gap (issue + PR); never side-channel via ad-hoc ansible or shell.
- **Security reviews are findings-first** — one-line verdict, then a severity/`file:line`/issue/fix table, within 3 tool calls. Verify *after*; never explore before the verdict lands. Skill: `secreview`.
- **Nothing internal in outward artifacts** — no IPs, hostnames, secrets, tokens, or internal filesystem paths in issues, PRs, comments or logs. Redact to a generic role or node reference.
- **Dispatch gates on review capacity, not PR count.** There is no open-PR limit; every PR still gets a `code-reviewer` pass before merge. PRs accumulating means review is the bottleneck — do that, don't defer new work.
- **Batch same-scope issues into one PR by default** (`Closes #A, #B`) — one CI suite per batch, not per issue. Each issue must still be *fully* delivered; partial delivery never closes. Independent or different-risk changes get separate PRs, as does anything too large for one honest review pass.
- **A pushed PR ends the tick — never wait on its CI.** Pushing is the sweep point: check every *other* in-flight PR once (approval gate, CI verdict, behind-ness), act on what is green or red, then start the next non-colliding scoped issue immediately. The PR just pushed is re-checked at the next sweep, never polled.

## Essential Patterns

| What | How |
|---|---|
| Redis | `from autobot_shared.redis_client import get_redis_client` |
| Config | `from autobot_shared.ssot_config import config` / `import { getBackendUrl } from '@/config/ssot-config'` |
| Logging | `from autobot_shared.logging_manager import get_logger` → `get_logger(__name__)` / `createLogger('Name')` — no `print()` or `console.*`; stdlib `logging` only where a config-mocking test harness forbids it (see `autobot_shared/user_management/password_epoch.py`) |
| Encoding | Always `encoding='utf-8'` explicitly |
| Cache TTL | Never hard-code — module-level constant from an env var (see `chat_history/cache.py`) |
| Store authority | Persisting a concept? `from autobot_shared.store_authority import system_of_record` — one store is durable, every other copy is a rebuildable projection |
| LEDGER/EXECUTOR | Coordination tools complete instantly — do NOT wait; continue immediately with execution tools |
| Copyright | `mrveiss` is sole owner and author |
