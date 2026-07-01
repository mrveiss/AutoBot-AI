# AutoBot Core Rules (Detail Reference)

> This file contains the full text of the 6 core rules. CLAUDE.md summarizes them;
> agents and sessions should read this file only when they need the complete policy.

---

## Rule 1: Check Before Writing

**Before writing a single line of code or documentation:**

- Search for existing implementations: `grep`/`glob` or `git log --oneline --grep="<topic>"`
- Check existing docs: `ls docs/`, `gh issue list`, recent commits
- Review related files in the same module/directory
- Search Memory MCP: `mcp__memory__search_nodes` for prior decisions
- Only after confirming nothing exists should you write new code or docs

**Before implementing anything, verify:**
1. Is the issue still open? `gh issue view <number>`
2. Are there any existing PRs or branches? `gh pr list | grep <issue>`
3. Any recent commits? `git log --oneline -20 --grep="<keywords>"`
4. Is there already code that partially implements this? Quick grep/glob search

If you find existing work, USE IT — don't reimplement from scratch.

> Violation: Writing a utility that already exists in `autobot_shared/`, or starting implementation without checking for an existing PR.

---

## Rule 2: Reuse Existing Code

**Always prefer existing code over new code:**

- Import and call existing utilities, helpers, and services
- Extend existing classes/functions rather than duplicating logic
- Use `autobot_shared/` utilities before writing custom implementations
- If similar code exists elsewhere, refactor to share it — never copy-paste

**Redis Client — always use canonical utility:**

```python
from autobot_shared.redis_client import get_redis_client
redis_client = get_redis_client(async_client=False, database="main")
# NEVER: redis.Redis(host="<database-ip>", ...)
```

Databases: `main`, `knowledge`, `prompts`, `analytics`

**Hardcoding Prevention — always use SSOT config:**

```python
from autobot_shared.ssot_config import config
redis_host = config.redis.host
```

```typescript
import { getBackendUrl } from '@/config/ssot-config'
```

Pre-commit hook enforces this. Guide: [`HARDCODING_PREVENTION.md`](HARDCODING_PREVENTION.md)

**Network Configuration — never hardcode IPs:**

Always check existing config files for correct network ranges. Use environment variables or SSOT config.

> Violation: Writing a new Redis helper when `autobot_shared.redis_client.get_redis_client` already exists, or hardcoding `<database-ip>`.

---

## Rule 3: Standardize for Reuse

**Write code that others can reuse:**

- Place shared logic in `autobot_shared/` or the appropriate shared module
- Match existing naming, signatures, and patterns in the codebase
- Generalize implementations when the cost is low (no over-engineering)

**Function Length:**

| Lines | Action |
|-------|--------|
| ≤30 | Ideal |
| 31–50 | Consider refactoring |
| 51–65 | Must refactor before merge |
| >65 | Immediate refactoring required |

Use **Extract Method** pattern: create `_helper_function()` with docstring referencing parent issue.

**File Naming — FORBIDDEN suffixes:** `_fix`, `_v2`, `_optimized`, `_new`, `_temp`, `_backup`, `_old`, date suffixes.

**Code Ownership:** `mrveiss` is the SOLE OWNER and AUTHOR of ALL AutoBot code.

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
```

**UTF-8 Encoding:** Always use `encoding='utf-8'` explicitly.

**Cache TTL Overrides — never hard-code Redis TTLs (#6743):**

Hard-coded Redis TTLs are bugs. For any surface where operators may need to tune
memory pressure, declare a module-level constant resolved from an env var with a
logged-fallback default.

Known tunable TTL env vars:

| Env var | Default | Controls | Code location |
|---------|---------|----------|---------------|
| `AUTOBOT_CHAT_SESSION_CACHE_TTL` | `86400` (24 h) | TTL (seconds) for `chat:session:*` Redis keys | `autobot-backend/chat_history/cache.py` — `_resolve_chat_session_cache_ttl()` |

Canonical resolver pattern (copy for every new tunable TTL surface):

```python
# module-level constant — resolved once at import time
_CHAT_SESSION_CACHE_TTL = _resolve_chat_session_cache_ttl()

def _resolve_chat_session_cache_ttl() -> int:
    """Return TTL seconds for chat:session:* Redis keys."""
    raw = config.chat_session_cache_ttl  # reads AUTOBOT_CHAT_SESSION_CACHE_TTL
    if raw is None:
        return TTL_24_HOURS  # from constants/ttl_constants.py
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "AUTOBOT_CHAT_SESSION_CACHE_TTL=%r is not an integer; falling back to %ds (24h)",
            raw, TTL_24_HOURS,
        )
        return TTL_24_HOURS
    if value <= 0:
        logger.warning(
            "AUTOBOT_CHAT_SESSION_CACHE_TTL=%d must be positive; falling back to %ds (24h)",
            value, TTL_24_HOURS,
        )
        return TTL_24_HOURS
    return value
```

Rules:
- Env var name: `AUTOBOT_<AREA>_<RESOURCE>_TTL` (screaming-snake, `AUTOBOT_` prefix)
- Always log a warning with the invalid value and the fallback when env var is absent or invalid
- Constant must be positive; reject zero or negative with warning + fallback to default
- Never call `int(os.getenv(...))` inline at call sites — use a named `_resolve_*` function

> Violation: Hard-coding `expire(key, 3600)` or reading the env var inline at call sites.

**Logging:**

```python
# Backend
import logging
logger = logging.getLogger(__name__)
logger.info("Message: %s", data)
```

```typescript
// Frontend
import { createLogger } from '@/utils/debugUtils'
const logger = createLogger('ComponentName')
```

No `console.*` or `print()` — pre-commit blocks these.

> Violation: Hardcoding a value that belongs in SSOT config, or writing a private helper that duplicates a public one.

---

## Rule 4: Clarify Requirements Before Starting

**Before touching any code, ensure requirements are complete:**

- Read the full issue/PRD and identify every gap, ambiguity, or missing edge case
- Ask all clarifying questions UP FRONT in a single pass — not mid-implementation
- Do not start until you can describe the complete expected end result in concrete terms

**Simplicity First — always prefer the simplest approach:**

- When the user asks to remove/fix something, do NOT add extra validation or defensive code unless requested
- If the scope is unclear, ASK rather than assuming a more complex approach
- Solve the stated problem — don't over-engineer for hypothetical edge cases

**Architecture Confirmation — before implementing any ambiguous task, state:**
1. **Approach:** What method/pattern you'll use
2. **Assumptions:** What you're assuming about architecture, startup, deployment
3. **Scope:** What will change and what will stay the same

Wait for user confirmation before writing code.

**Architecture exceptions:** When deviating from a standard pattern intentionally, document it in [`docs/developer/ARCHITECTURE_EXCEPTIONS.md`](ARCHITECTURE_EXCEPTIONS.md) with rationale and a grep check.

**No Temporary Fixes (ZERO TOLERANCE):**
- No quick fixes, workarounds, or disabling functionality
- No hardcoding to bypass issues, try/catch hiding errors
- No "TODO: fix later" comments
- Identify root problem → fix underlying issue → verify → remove workarounds

> Violation: Starting implementation from a vague issue, or creating a "partition mode" when the existing mode just needs extension.

---

## Rule 5: Verify Before Reporting Complete

**Before claiming any work is done, show evidence it works:**

- Run the relevant test, lint check, curl, or build command and include the output
- Never say "done", "fixed", or "complete" without proof
- If the change touches multiple layers (backend + frontend, multiple nodes), verify each one

**Issue is complete ONLY when:**

1. All code committed with issue refs
2. All acceptance criteria verified
3. Tests passing
4. Code reviewed
5. Closing summary added to issue
6. Issue status = closed
7. Worktree removed (if one was created)
8. Feature branch deleted (local + remote)

**Pre-commit & Linting:**

- Maximum line length: 120 characters (enforced by flake8/ruff)
- After ANY commit attempt, verify changes were actually committed
- Never mix unrelated staged files — stage and commit in focused batches
- Bulk operations: commit in batches of 10–15 files max
- **NEVER** use `git commit --no-verify`

**Bulk File Changes:**

- Apply changes in batches of **10–20 files at a time**
- Test on **2–3 representative files first** before bulk operations across 50+ files
- If a bulk fix script produces syntax errors: stop, fix the script, re-test

**Pre-commit Stash Bypass (Issue #2512, #1503):**

The pre-commit wrapper (`scripts/hooks/pre-commit-branch-guard-wrapper`) runs `pre-commit run --files <staged>` instead of calling the framework hook directly, eliminating stash push/pop issues.

**Deployment Verification Checklist — after deploying to ANY remote server:**

1. No .env override conflicts
2. Correct Python interpreter (Python 3.14 deadsnakes PPA venv)
3. Database migrations current
4. Service actually restarted
5. Endpoints responding
6. No errors in recent logs

> Violation: Saying "the bug is fixed" after editing a file without running the code.

---

## Rule 6: Report Every Discovered Problem

**"It was already there" is never a reason to ignore a problem.**

Every bug, inconsistency, security issue, hardcoded value, or tech debt found must be reported **AND, by default, FIXED**. "It was already there" is never a reason to leave it. File a tracking issue for visibility, then fix it — in the **same PR when it's in-scope**, or a **fast-follow PR** when larger. Do not merely file-and-move-on.

**Classification:**

Fix along the way WITHOUT asking (file a tracking issue, then fix — same PR when in-scope):
- Any pre-existing bug in a file/module you are already modifying
- A pre-existing defect that nullifies or undermines the change you're making (e.g. a missing `await` that makes the code you just optimized a silent no-op; a mangled list entry that disables a security check)
- Security vulnerability, data-corruption risk, syntax/import error, swallowed exception, or other correctness bug
- Low-risk correctness fixes with a clear root cause — always add a regression test

Create issue + ASK before fixing:
- Large refactors, architecture/product decisions, or feature builds (PRD-gated) — surface with a recommendation, don't build unilaterally
- Fixes with a wide/risky blast radius or genuinely ambiguous intended behavior

Create issue + DEFER (don't ask):
- Genuinely unrelated bugs far from the current change
- Speculative optimizations with no measured impact (e.g. bounded analyzer loops)

**One Issue Per Session Rule:**
When an issue is complete, wait for explicit user instruction before starting new work.

> Violation: Noticing a broken error handler and not creating a GitHub issue because "it's not my task."

---

## Rule 7: Behavioral Grep for Extraction PRs (#5372)

**Extraction PRs (pulling a duplicated pattern into a shared composable/utility + migrating N sites) MUST grep for the *behavior*, not just the *symbol*, and document before/after hit counts in the PR description.**

**Why:** The issue body enumerates sites by symbol name at filing time. Symbol names drift (rename, different convention per consumer); behavior does not. Symbol-only greps underreport consistently — **~50% of extraction PRs this session shipped incomplete migrations** and required follow-up PRs.

**Required PR section:**

```markdown
## Behavioral grep audit

Before:
\`\`\`bash
$ grep -rnE "<behavior regex>" <tree>
# N hits
\`\`\`

After:
\`\`\`bash
$ <same grep>
# 0 hits (or explicit follow-up with #N filed)
\`\`\`
```

**Rule of thumb:** Match the pattern body (e.g. `key === 'Tab'` and `shiftKey &&` for focus-trap code), cast wider than the issue's enumeration, and run **twice** — once loose, once tight — to catch the delta.

Full Phase 0d specification and concrete examples: [`skills/batch-implement.md` §Phase 0d](skills/batch-implement.md).

> Violation: Filing a follow-up issue #5410 for 2 dialogs that the original #5371 grep should have surfaced, because #5371 grepped for `handleKeydown` (symbol) instead of `key === 'Tab'` (behavior).

---

## Latency Budgets

**Hot paths have explicit p95 targets. PRs touching these paths must include a perf measurement or justify any regression.**

| Hot path | p95 target |
|---|---|
| Memory wake-up (L0+L1 injection) | ≤ 100 ms |
| KB hybrid search (no rerank) | ≤ 200 ms |
| KB hybrid search (with rerank) | ≤ 500 ms |
| Memory-graph entity lookup | ≤ 50 ms |
| Agent-tool dispatch overhead | ≤ 30 ms |
| Pre-compact hook (background) | ≤ 500 ms |
| Stop hook (background) | ≤ 500 ms |
| Chat turn p95 (agent response start) | ≤ 1500 ms |

**PR template line for hot-path changes:**

```
Perf impact on [memory wake-up / KB search / entity lookup / tool dispatch / hooks / chat turn]: [measurement or N/A]
```

**Enforcement:** Any PR that degrades a hot path beyond its p95 target must include either a Prometheus histogram measurement confirming the regression is within budget, or an explicit justification approved by the reviewer.

**Prometheus histogram verification** — ensuring each target above has a corresponding histogram — is tracked as a separate follow-up. Do not block PRs on missing histograms; file a discovery issue if a histogram is absent.

> Violation: Merging a change to KB hybrid search without reporting measured p95 latency when the code path is on the hot-path list above.

---

## Decorator Order Fix Tool

`tools/lint/check_decorator_order.py` enforces the `@router.*` / `@with_error_handling` decorator order (see #6558, #6633, #6638).

**Check-only (default, used by pre-commit):**

```bash
python3 tools/lint/check_decorator_order.py <file-or-dir> ...
```

**Auto-fix mode (opt-in):**

```bash
pip install libcst   # one-time
python3 tools/lint/check_decorator_order.py --fix <file-or-dir> ...
```

`--fix` uses libcst to correct violations in place while preserving formatting, comments, and docstrings.
It fixes both patterns in a single pass:

- **Pattern A** — `@with_error_handling` above `@router.*`: swapped so `@router.*` is outermost.
- **Pattern B** — two adjacent `@with_error_handling` decorators: outer duplicate removed.

The pre-commit hook entry in `.pre-commit-config.yaml` does **not** include `--fix` — CI always runs check-only so it never silently mutates files.  `--fix` is a developer convenience for bulk remediation.

`libcst` is a soft dependency: if not installed, `--fix` prints an error and exits 1.

---

## AUTOBOT_* Environment Variables

All `AUTOBOT_*` environment variables must be registered in
`autobot_shared/env_registry.py` before use. The pre-commit hook
`env-vars-documented` enforces this and keeps this table up to date.

To add a new variable:
1. Add a `register_env_var(EnvVarSpec(...))` call to `autobot_shared/env_registry.py`.
2. Run `python3 pipeline-scripts/generate_env_docs.py` to regenerate this table.
3. Stage both files.

<!-- BEGIN_AUTOGEN_ENV_DOCS -->
| Name | Component | Type | Default | Description |
|---|---|---|---|---|
| `AUTOBOT_BACKEND_HOST` | backend | str | `'10.0.0.1'` | Hostname or IP address of the AutoBot backend service. |
| `AUTOBOT_BACKEND_PORT` | backend | str | `'8001'` | TCP port of the AutoBot backend service. |
| `AUTOBOT_BACKEND_URL` | backend | str | `'http://10.255.255.254:8001'` | Full base URL of the AutoBot backend service (overrides HOST+PORT). |
| `AUTOBOT_CHATS_DIRECTORY` | chat | str | `'data/chats'` | Filesystem path where chat session files are stored. |
| `AUTOBOT_CLASSIFICATION_MODEL` | ai | str | `'gemma2:2b'` | Ollama model name used for intent classification. |
| `AUTOBOT_DEPLOYMENT_MODE` | system | str | `'distributed'` | Deployment topology: 'distributed' or 'standalone'. |
| `AUTOBOT_ENV` | system | str | `'production'` | Short environment label used in logs and traces (e.g. 'development', 'production'). |
| `AUTOBOT_ENVIRONMENT` | system | str | `'development'` | Full environment name for OTel deployment.environment attribute. Prefer AUTOBOT_ENV for new code. |
| `AUTOBOT_GIT_BRANCH` | system | str | `'Dev_new_gui'` | Git branch that the running instance was built from. |
| `AUTOBOT_INTERNAL_API_KEY` | auth | str | `""` | Shared secret used to authenticate internal service-to-service calls. |
| `AUTOBOT_KB_TIMEOUT` | kb | int | `30` | Timeout in seconds for knowledge-base HTTP requests. Range: 1–300. |
| `AUTOBOT_LOGS_BACKUP_DIR` | logging | str | `'backup'` | Directory where rotated log archives are written. |
| `AUTOBOT_LOGS_DIR` | logging | str | `'logs'` | Primary directory for application log files. |
| `AUTOBOT_LOG_VIEWER_URL` | logging | str | `'http://localhost:5341'` | Base URL of the Seq (or compatible) structured-log viewer. |
| `AUTOBOT_OLLAMA_BASE_URL` | ai | str | *(none)* | Base URL of the local Ollama API (e.g. http://localhost:11434). |
| `AUTOBOT_ORCHESTRATOR_MODEL` | ai | str | `'llama3.2:1b'` | Ollama model name used for the main orchestrator/routing loop. |
| `AUTOBOT_OTEL_ENABLED` | otel | bool | false | Enable OpenTelemetry tracing when truthy. |
| `AUTOBOT_OTEL_ENDPOINT` | otel | str | *(none)* | OTLP collector endpoint URL (e.g. http://otel-collector:4317). |
| `AUTOBOT_OTEL_PROTOCOL` | otel | str | `'grpc'` | OTLP export protocol: 'grpc' or 'http/protobuf'. |
| `AUTOBOT_OTEL_SAMPLE_RATE` | otel | float | `0.1` | Fraction of traces to sample (0.0–1.0). Range: 0.0–1.0. |
| `AUTOBOT_OTEL_SERVICE_VERSION` | otel | str | `'1.5.0'` | Service version tag attached to all OTel spans. |
| `AUTOBOT_POSTGRES_DB` | postgres | str | `'autobot_users'` | PostgreSQL database name. |
| `AUTOBOT_POSTGRES_HOST` | postgres | str | `'127.0.0.1'` | PostgreSQL server hostname or IP. |
| `AUTOBOT_POSTGRES_PASSWORD` | postgres | str | `""` | PostgreSQL user password. |
| `AUTOBOT_POSTGRES_PORT` | postgres | str | `'5432'` | PostgreSQL server port. |
| `AUTOBOT_POSTGRES_USER` | postgres | str | `'slm_app'` | PostgreSQL login role. |
| `AUTOBOT_PROMETHEUS_URL` | monitoring | str | `'http://10.0.0.4:9090'` | Base URL of the Prometheus metrics server. |
| `AUTOBOT_REDIS_DB_ANALYTICS` | redis | int | `11` | Redis logical database number for analytics data. Range: 0–15. |
| `AUTOBOT_REDIS_DB_KNOWLEDGE` | redis | int | `1` | Redis logical database number for knowledge-base vectors. Range: 0–15. |
| `AUTOBOT_REDIS_DB_MAIN` | redis | int | `0` | Redis logical database number for primary application data. Range: 0–15. |
| `AUTOBOT_REDIS_HOST` | redis | str | `'localhost'` | Redis server hostname or IP address. |
| `AUTOBOT_REDIS_PASSWORD` | redis | str | *(none)* | Redis AUTH password (omit or leave blank for unauthenticated servers). |
| `AUTOBOT_REDIS_PORT` | redis | int | `6379` | Redis server TCP port (plain connection). Range: 1–65535. |
| `AUTOBOT_REDIS_TLS_ENABLED` | redis | bool | false | Enable TLS for Redis connections when truthy. |
| `AUTOBOT_REDIS_TLS_PORT` | redis | int | `6380` | Redis server TCP port for TLS connections. Range: 1–65535. |
| `AUTOBOT_SHOW_DEPRECATION_WARNINGS` | system | bool | false | Emit Python DeprecationWarnings for deprecated AutoBot APIs when truthy. |
| `AUTOBOT_TLS_CA_PATH` | tls | str | *(none)* | Path to the CA certificate file for TLS verification. |
| `AUTOBOT_TLS_CERT_DIR` | tls | str | `'/etc/autobot/certs'` | Directory containing TLS certificate and key files. |
| `AUTOBOT_TLS_CERT_PATH` | tls | str | *(none)* | Path to the TLS client/server certificate file. |
| `AUTOBOT_TLS_KEY_PATH` | tls | str | *(none)* | Path to the TLS private key file. |
| `AUTOBOT_TRUSTED_PROXIES` | network | str | `""` | Comma-separated list of trusted reverse-proxy IP addresses or CIDR ranges for X-Forwarded-For header trust. |
| `AUTOBOT_USERS_DATABASE_URL` | postgres | str | *(none)* | Full SQLAlchemy connection URL for the users database. Overrides AUTOBOT_POSTGRES_* individual vars when set. |

*42 variables registered as of last generation.*
<!-- END_AUTOGEN_ENV_DOCS -->
