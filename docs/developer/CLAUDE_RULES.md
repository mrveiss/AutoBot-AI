# AutoBot Core Rules (Detail Reference)

> This file contains the full text of the 6 core rules. CLAUDE.md summarizes them;
> agents and sessions should read this file only when they need the complete policy.

---

## Rule 1: Check Before Writing

**Before writing a single line of code or documentation:**

- Search for existing implementations: `grep`/`glob` or `git log --oneline --grep="<topic>"`
- Check existing docs: `ls docs/`, `gh issue list`, recent commits
- Review related files in the same module/directory
- Search session memory for prior decisions — the file-based store lives in the agent's own memory directory, outside this repo
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
# Backend — the canonical logger
from autobot_shared.logging_manager import get_logger
logger = get_logger(__name__)
logger.info("Message: %s", data)
```

```typescript
// Frontend
import { createLogger } from '@/utils/debugUtils'
const logger = createLogger('ComponentName')
```

No `console.*` or `print()` — pre-commit blocks these.

Bare `logging.getLogger(__name__)` is the **exception, not the pattern**: it is permitted
only where a config-mocking test harness cannot tolerate the manager's import-time config
read (see `autobot_shared/user_management/password_epoch.py`). New backend code uses
`get_logger`.

> Violation: Hardcoding a value that belongs in SSOT config, or writing a private helper that duplicates a public one.

---

## Rule 4: Clarify Requirements Before Starting

**This rule is scoped to *ambiguous* work.** When the issue is clear, implement — a brief plan
then code, per `CLAUDE_WORKFLOW.md` "General Workflow". Clarification is the gate for genuine
ambiguity, not a preamble to every task.

**When requirements are incomplete:**

- Read the full issue/PRD and identify every gap, ambiguity, or missing edge case
- Ask all clarifying questions UP FRONT in a single pass — not mid-implementation
- Do not start until you can describe the complete expected end result in concrete terms
- In an autonomous `/loop`, asking means **posting** the question with a recommendation and
  continuing — never blocking the tick

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

**Filing is never blocked.** Not by a rate limit, not by queue depth, not by any governor. A
finding you cannot file is a finding lost. Ratios inform what you *work on*; they never stop
you recording a problem.

**When an issue is complete, start the next one.** Push the PR and pick up the next
non-colliding issue rather than waiting on CI — see the never-idle order in the global
instructions.

> Violation: Noticing a broken error handler and not creating a GitHub issue because "it's not my task."

---

## Rule 7: Behavioral Grep for Extraction PRs (#5372)

**Extraction PRs (pulling a duplicated pattern into a shared composable/utility + migrating N sites) MUST grep for the *behavior*, not just the *symbol*, and document before/after hit counts in the PR description.**

**Why:** The issue body enumerates sites by symbol name at filing time. Symbol names drift (rename, different convention per consumer); behavior does not. Symbol-only greps underreport consistently — **~50% of extraction PRs in one session shipped incomplete migrations** and required follow-up PRs.

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

Full Phase 0d specification and concrete examples: the `batch-implement` skill, Phase 0d.

> Violation: Filing a follow-up issue #5410 for 2 dialogs that the original #5371 grep should have surfaced, because #5371 grepped for `handleKeydown` (symbol) instead of `key === 'Tab'` (behavior).

---

## Rule 8: Outbound HTTP Goes Through the Guarded Fetch (#13625)

**Every outbound connector/integration HTTP request MUST declare an egress policy. Never build a bare `aiohttp.ClientSession`, and never call the shared client without `guard_egress`, against a host that came from stored config or user input.**

Two mechanisms, and which one you need depends on redirects:

| You need | Use |
|---|---|
| A request that must NOT follow redirects | `get_http_client().tracked_request(..., guard_egress=...)` |
| A request that MUST follow redirects | `ssrf_guard.pinned_request_with_redirects` |

`guard_egress` validates the URL and then **refuses redirects** — it raises if you pass `allow_redirects=True`. That is deliberate: validating a URL and then letting aiohttp follow a 302 elsewhere is worse than no guard, because it reads as protected. `pinned_request_with_redirects` is the one that re-resolves and re-pins *every hop*.

**Why:** This rule previously existed only as a docstring inside `ssrf_guard.py`. Six connectors — Confluence, Jira, GitLab, Gitea, Nextcloud and the `integrations/base.py` session builder — were written against bare `aiohttp` with a host string-concatenated from stored config, and a grep for `is_public_url|ssrf_guard|pinned_connector` across all six returned **zero hits**. A rule nobody can find is a rule nobody follows.

**The private-network opt-in:**

A self-hosted Confluence/GitLab/Nextcloud instance legitimately lives on an RFC-1918 address, so a public-only guard would break the feature it protects. `AUTOBOT_CONNECTOR_PRIVATE_NETWORK_EGRESS` (default **off**) permits that range — and *only* that range:

| Target | Flag off | Flag on |
|---|---|---|
| Public address | allowed | allowed |
| RFC-1918 / IPv6 ULA | blocked | **allowed** |
| Loopback | blocked | blocked |
| Link-local, incl. `169.254.169.254` cloud metadata | blocked | blocked |
| Multicast, reserved, unspecified | blocked | blocked |

**Two constraints that are not negotiable:**

1. The opt-in applies to the **operator-configured instance host only**. User-supplied content and download URLs are validated public-only, unconditionally — a connector that fetches an attachment from a URL inside a document must not inherit the instance host's exemption.
2. Config-store-time validation is still the goal (**#13625 item 3, not yet built**). Today the check is per-request, which costs a DNS lookup per call and does not close the rebind race between the check and the connect — `pinned_connector` is what closes that, and it does not yet thread the private-network opt-in. Do not read this rule as claiming the race is handled.

**When adding a connector:** if you are typing `aiohttp.ClientSession(` and the URL contains a value read from config, stop. And if you are calling `tracked_request` without `guard_egress`, that is the same mistake with fewer characters.

**`urljoin` does not pin a host.** `urljoin(base, path)` returns `https://evil.example.com/x` for a path of `//evil.example.com/x`, and the caller's credentials go with it. If a path segment can come from stored data or a server response, assert the result still starts with the base.

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
| `AUTOBOT_ALLOW_CONFIG_EDITS` | system | bool | false | Permit writes to the repository's tracked config files. Off by default: the codebase is the source of truth and an edit made here is invisible to deployment (#11220). |
| `AUTOBOT_APPROVAL_PENDING_SESSION_TTL_SECONDS` | execution | int | `604800` | Seconds a session holding a pending approval survives in Redis. Deliberately long — what it waits for is a person, and expiring sooner discards the approval rather than the wait (#13478). |
| `AUTOBOT_AUDIT_FILING_STATUS_TTL_S` | backend | int | `2592000` | Seconds the audit worker's filing-health record survives in Redis. Refreshed on every run and at worker startup, so this only has to outlive the longest gap between runs (the claims audit is weekly); it exists so a record left by a worker that has since stopped does not keep answering for one that no longer exists (#13570). |
| `AUTOBOT_AUDIT_MAX_DEFERRED` | backend | int | `10000` | Ceiling on audit records held in the deferred queue when the sink is unavailable. Beyond it the oldest are dropped, bounding memory rather than letting an outage grow it without limit. |
| `AUTOBOT_BACKEND_HOST` | backend | str | `'10.0.0.1'` | Hostname or IP address of the AutoBot backend service. |
| `AUTOBOT_BACKEND_PORT` | backend | str | `'8001'` | TCP port of the AutoBot backend service. |
| `AUTOBOT_BACKEND_URL` | backend | str | `'http://10.255.255.254:8001'` | Full base URL of the AutoBot backend service (overrides HOST+PORT). |
| `AUTOBOT_BROWSER_STATE_PROMPT_MAX_ELEMENTS` | backend | int | `30` | How many numbered elements the LLM-visible state block renders per browser tool result. The browser worker caps the raw list separately; this bounds only what reaches the prompt (#11537). |
| `AUTOBOT_CHANNEL_SEQ_KEY_PREFIX` | events | str | `'autobot:events:seq:'` | Redis key prefix for per-channel live-event sequence counters. |
| `AUTOBOT_CHANNEL_STREAM_KEY_PREFIX` | events | str | `'autobot:events:channel:'` | Redis key prefix for per-channel live-event replay streams. |
| `AUTOBOT_CHANNEL_STREAM_MAX_ENTRIES` | events | int | `1000` | Events retained per channel for reconnect replay. A client whose last_event_id has fallen outside this window is told to resync rather than handed a partial history. Range: 1–1000000. |
| `AUTOBOT_CHANNEL_STREAM_TTL_SECONDS` | events | int | `86400` | Idle expiry for a per-channel replay stream, so session and chat channels do not accumulate. Range: 60–2592000. |
| `AUTOBOT_CHATS_DIRECTORY` | chat | str | `'data/chats'` | Filesystem path where chat session files are stored. |
| `AUTOBOT_CHAT_TRAJECTORY_CAPTURE_CONCURRENCY` | ai | int | `2` | Concurrent trajectory judge calls. Bounded so a burst of turns cannot stampede the LLM. |
| `AUTOBOT_CHAT_TRAJECTORY_CONTEXT` | ai | bool | true | Search past trajectories before answering. Defaults on because the search is one vector query; capture is gated separately since it spends a judge call. |
| `AUTOBOT_CHAT_TRAJECTORY_TIMEOUT_S` | ai | float | `0.15` | Seconds the pre-answer trajectory search may take. It rides the response hot path, so a cold or slow collection must never delay first token. |
| `AUTOBOT_CHAT_TRAJECTORY_TOP_K` | ai | int | `3` | How many past trajectories the pre-answer search retrieves. |
| `AUTOBOT_CLASSIFICATION_MODEL` | ai | str | `'gemma2:2b'` | Ollama model name used for intent classification. |
| `AUTOBOT_COCHANGE_GIT_TIMEOUT_SECONDS` | backend | int | `120` | Seconds the co-change history walk may run before it is abandoned. |
| `AUTOBOT_COCHANGE_MAX_FILES_PER_COMMIT` | backend | int | `50` | Commits touching more files than this are ignored as coupling evidence: a bulk rename, a vendored-tree import or a reformat is not a signal (#13639). |
| `AUTOBOT_COCHANGE_MIN_CO_CHANGES` | backend | int | `3` | How many commits two files must share before the pair is reported at all. One shared commit is a coincidence. |
| `AUTOBOT_COCHANGE_STRENGTH_THRESHOLD` | backend | float | `0.3` | Minimum normalised coupling strength to report. Independent of the count threshold: a pair can clear the count and still be weak if either file changes constantly. |
| `AUTOBOT_COCHANGE_WINDOW_DAYS` | backend | int | `180` | Days of history the co-change analysis considers. Coupling decays — a pair that moved together two years ago is history, not structure. |
| `AUTOBOT_CODEEXEC_APPROVAL_POLL_SECONDS` | execution | int | `2` | Seconds between polls while waiting for a code-execution approval decision. |
| `AUTOBOT_CODEEXEC_APPROVAL_WAIT_SECONDS` | execution | int | `1800` | Seconds a code-execution request waits for approval before expiring. Expiry is a decision the caller can act on, not a side effect of how long a coroutine lives (GH#11568). |
| `AUTOBOT_CODEEXEC_AUTOAPPROVE_READONLY` | execution | bool | true | Auto-approve code-execution calls limited to the read-only tool set. The eligible set is fixed in code, not configurable here (GH#11568, GH#11662). |
| `AUTOBOT_CODEEXEC_ENABLED` | execution | bool | false | Master switch for the compose/code-execution tool. Ships off (GH#11568). |
| `AUTOBOT_CODEEXEC_MAX_SCRIPT_RETRIES` | execution | int | `1` | How many times a failed generated script may be retried within one code-execution call. |
| `AUTOBOT_CODEEXEC_MAX_TOOL_CALLS` | execution | int | `50` | Ceiling on tool calls a single code-execution script may make, bounding a runaway loop inside the sandbox. |
| `AUTOBOT_CODEEXEC_TIMEOUT_SECONDS` | execution | int | `120` | Seconds a compose-tool sandbox execution may run (GH#11568). |
| `AUTOBOT_CODE_ANALYSIS_POOL_MAX_TASKS` | backend | int | `8` | Tasks a code-analysis child handles before it is recycled. Recycling bounds memory growth in long-lived children. |
| `AUTOBOT_CODE_ANALYSIS_POOL_WORKERS` | backend | int | `2` | Child processes used to offload code analysis. Deliberately small: each carries a full interpreter, and analysis is bursty rather than sustained. |
| `AUTOBOT_COMPACTION_BOUNDARY_WINDOW` | chat | int | `10` | How far back the compaction boundary looks for a user turn before settling for any turn start, so the cut cannot be dragged far from the midpoint. |
| `AUTOBOT_COMPACTION_STATE_COMMAND_CAP` | chat | int | `10` | Most recent shell commands named in a compaction's extracted state block. |
| `AUTOBOT_COMPACTION_TOOL_RESULT_CLIP_CHARS` | chat | int | `400` | Maximum characters of a tool result in the summarised region before it is clipped for the summariser; a file read many turns ago is cheaper to re-read than to carry. |
| `AUTOBOT_COMPACTION_USER_MESSAGE_CAP` | chat | int | `40` | How many of the most recent user messages cross a context compaction verbatim instead of being summarised. Bounded so repeated compaction cannot grow the preserved set without limit. |
| `AUTOBOT_CONFIG_REGISTRY_REDIS_RETRY_SECONDS` | redis | float | `30.0` | Interval between config-registry attempts to reconnect to Redis after a failure, so a Redis outage does not become a reconnect storm. |
| `AUTOBOT_DELEGATION_ENABLED` | ai | bool | false | Master switch for the delegate tool. Off, it records the delegation request and does not dispatch it. |
| `AUTOBOT_DEPLOYMENT_MODE` | system | str | `'distributed'` | Deployment topology: 'distributed' or 'standalone'. |
| `AUTOBOT_DEVICE_POLL_BACKOFF_SECONDS` | auth | int | `5` | Extra delay added to the device-code poll interval after the provider answers `slow_down`. |
| `AUTOBOT_DEVICE_POLL_MAX_ATTEMPTS` | auth | int | `360` | Maximum device-code poll attempts before the flow is abandoned. Bounds the poll loop independently of the time window below. |
| `AUTOBOT_DEVICE_POLL_MIN_INTERVAL_SECONDS` | auth | int | `5` | Floor on how often the device-code flow polls the provider for completion, regardless of the interval the provider advertises. |
| `AUTOBOT_DEVICE_POLL_WINDOW_SECONDS` | auth | int | `1800` | Wall-clock ceiling on a device-code flow. Reached first when the provider advertises a long interval, whereas the attempt cap above binds first when it advertises a short one. |
| `AUTOBOT_DOCKER_POOL_SIZE` | execution | int | `3` | Number of warm containers kept when AUTOBOT_DOCKER_USE_POOL is on. Ignored entirely when pooling is off. |
| `AUTOBOT_DOCKER_USE_POOL` | execution | bool | false | Reuse a pool of warm containers for tool execution instead of starting one per call. Off by default — the pool trades isolation between calls for start-up latency. |
| `AUTOBOT_ENV` | system | str | `'production'` | Short environment label used in logs and traces (e.g. 'development', 'production'). |
| `AUTOBOT_ENVIRONMENT` | system | str | `'development'` | Full environment name for OTel deployment.environment attribute. Prefer AUTOBOT_ENV for new code. |
| `AUTOBOT_FACT_FORCING` | ai | bool | false | Enable the fact-forcing gate, which requires an answer to cite retrieved facts. |
| `AUTOBOT_GATEWAY_REQUIRE_OUTBOUND_APPROVAL` | gateway | bool | false | Require approval before the Gateway hands an agent-authored message to a channel adapter. Off means audit-only: every governed send is recorded, none is blocked. On fails closed — no registered approver, a denial, or an approver error all deny the send. |
| `AUTOBOT_GIT_BRANCH` | system | str | `'Dev_new_gui'` | Git branch that the running instance was built from. |
| `AUTOBOT_GRAFANA_PORT` | monitoring | str | `'3000'` | TCP port of the Grafana instance. Also declared in ssot_config.py; 3000 is Grafana's own default and is NOT the browser service, which is 9001 (#4052, #14198). |
| `AUTOBOT_GRAPH_PATH_TIMEOUT_SECONDS` | kb | float | `10.0` | Ceiling on a knowledge-graph path search. Path queries are unbounded in the worst case, so this is what stops one request occupying a worker indefinitely. |
| `AUTOBOT_IMESSAGE_ENABLED` | gateway | bool | false | Opt in to the iMessage gateway adapter. Off by default: it is macOS-only and needs Full Disk Access to the Messages database. |
| `AUTOBOT_INJECTION_HARDBLOCK_ENABLED` | auth | bool | false | Hard-block prompt injection rather than only flagging it. When on and confidence clears the threshold, the request is refused instead of annotated. |
| `AUTOBOT_INJECTION_HARDBLOCK_THRESHOLD` | auth | float | `0.75` | Confidence in [0.0, 1.0] at or above which a detected injection is hard-blocked. 0.75 maps to HIGH; 1.0 would block only CRITICAL. |
| `AUTOBOT_INTERNAL_API_KEY` | auth | str | `""` | Shared secret used to authenticate internal service-to-service calls. |
| `AUTOBOT_KB_TIMEOUT` | kb | int | `30` | Timeout in seconds for knowledge-base HTTP requests. Range: 1–300. |
| `AUTOBOT_LIVE_PROBE_TIMEOUT_SECONDS` | testing | float | `1.0` | Seconds a test's live-service precondition probe waits for a TCP connect before reporting the service as absent and skipping (autobot_shared/live_service_probe.py, #14930). Short by default: a refused loopback connect returns immediately, and this runs once per endpoint per process. Raise it when probing a fleet host across a link slow enough that a live service could be mistaken for a missing one. Range: 0.1–60.0. |
| `AUTOBOT_LLC_H2A_BRIEF_CACHE_TTL` | orchestrator | int | `86400` | Cache lifetime in seconds for a human-to-agent handoff brief (llc/services/handoff.py). One day. |
| `AUTOBOT_LLM_MAX_RETRY_AFTER_SECONDS` | ai | float | `30.0` | Cap applied to a provider's `Retry-After`. Without it a provider advertising a long back-off would stall a request for that whole period (services/llm_service.py). |
| `AUTOBOT_LLM_TOKEN_BUDGET_PER_RUN` | ai | int | `0` | Cumulative token ceiling (input plus output) for one run. Zero disables the gate, which is the shipped default (#11541). |
| `AUTOBOT_LLM_TOKEN_BUDGET_TTL_SECONDS` | ai | int | `86400` | Seconds a run's cumulative token counter survives in Redis, bounding memory for abandoned sessions. Refreshed on every increment. |
| `AUTOBOT_LOGS_BACKUP_DIR` | logging | str | `'backup'` | Directory where rotated log archives are written. |
| `AUTOBOT_LOGS_DIR` | logging | str | `'logs'` | Primary directory for application log files. |
| `AUTOBOT_LOG_VIEWER_URL` | logging | str | `'http://localhost:5341'` | Base URL of the Seq (or compatible) structured-log viewer. |
| `AUTOBOT_MATRIX_E2EE` | gateway | bool | false | Opt in to end-to-end encryption for the Matrix adapter. Off by default because E2EE needs the optional olm dependency and a persisted device store. |
| `AUTOBOT_MAX_ATTEMPTS_REFUSAL_BROADCAST_INTERVAL_S` | backend | int | `3600` | How often to re-broadcast that a node is still at MAX_REMEDIATION_ATTEMPTS. Once exhausted, last_attempt freezes and this refusal is refused again on every reconcile pass forever — unthrottled, that is once per reconcile_interval (services/reconciler.py, #14465). |
| `AUTOBOT_MAX_DELEGATIONS_PER_TURN` | ai | int | `5` | Delegate calls allowed in a single LLM turn — a fan-out bound, not a quality setting. |
| `AUTOBOT_MAX_DELEGATION_DEPTH` | ai | int | `2` | How deep delegation may nest before it is refused, bounding runaway recursive delegation. |
| `AUTOBOT_MULTIMODAL_VOICE_CONFIDENCE_THRESHOLD` | voice | float | `0.7` | Fallback confidence threshold for VoiceProcessor when the multimodal.voice config section omits it (#13207). Range: 0.0–1.0. |
| `AUTOBOT_MULTIMODAL_VOICE_PROCESSING_TIMEOUT` | voice | int | `30` | Fallback processing timeout in seconds for VoiceProcessor when the multimodal.voice config section omits it (#13207). |
| `AUTOBOT_NODE_PROXY_TIMEOUT_SECONDS` | slm | float | `15.0` | Ceiling on a proxied request from the SLM to a node's backend. The aggregator fans out across the fleet, so without a bound one unresponsive node would hold the whole lifecycle view open. |
| `AUTOBOT_OAUTH_REFRESH_LOCK_TTL_MS` | auth | int | `90000` | Milliseconds a connector holds the single-flight lock while refreshing an OAuth token. Derived as three times the token request timeout — 90000 with the default 30s timeout — so it tracks that timeout instead of drifting from it (knowledge/connectors/credential_store.py). This variable can only RAISE it: a smaller value is floored back to the derived TTL and a warning is logged, because the lease is held across the store write as well as the HTTP call, and one that expires mid-refresh lets two workers rotate the same token (#14238). |
| `AUTOBOT_OAUTH_REFRESH_POLL_S` | auth | float | `0.2` | Polling interval while waiting on another worker's token refresh. Floored at 0.05s, since zero would busy-loop the executor. |
| `AUTOBOT_OAUTH_REFRESH_WAIT_S` | auth | float | `0.0` | Seconds a caller waits for another worker's in-flight token refresh before refreshing itself. The effective value is floored at the lock TTL plus five seconds — 95 with the defaults — because a caller that gives up before the lease expires abandons a refresh still in progress. Setting it below that floor therefore has no effect. |
| `AUTOBOT_OLLAMA_BASE_URL` | ai | str | *(none)* | Base URL of the local Ollama API (e.g. http://localhost:11434). |
| `AUTOBOT_OPENVINO_CACHE_DIR` | ai | str | `'data/openvino_cache'` | Directory for compiled OpenVINO model artefacts. Relative to the working directory unless given as an absolute path. |
| `AUTOBOT_ORCHESTRATOR_MODEL` | ai | str | `'llama3.2:1b'` | Ollama model name used for the main orchestrator/routing loop. |
| `AUTOBOT_OTEL_ENABLED` | otel | bool | false | Enable OpenTelemetry tracing when truthy. |
| `AUTOBOT_OTEL_ENDPOINT` | otel | str | *(none)* | OTLP collector endpoint URL (e.g. http://otel-collector:4317). |
| `AUTOBOT_OTEL_PROTOCOL` | otel | str | `'grpc'` | OTLP export protocol: 'grpc' or 'http/protobuf'. |
| `AUTOBOT_OTEL_SAMPLE_RATE` | otel | float | `0.1` | Fraction of traces to sample (0.0–1.0). Range: 0.0–1.0. |
| `AUTOBOT_OTEL_SERVICE_VERSION` | otel | str | `'1.5.0'` | Service version tag attached to all OTel spans. |
| `AUTOBOT_OWNERSHIP_BLAME_TIMEOUT_SECONDS` | backend | float | `10.0` | Seconds a single `git blame` may take during ownership analysis. Must stay below the whole-analysis budget, which a previous 30s value exceeded (#13602). |
| `AUTOBOT_OWNERSHIP_BUDGET_SECONDS` | backend | float | `20.0` | Total seconds ownership analysis may spend blaming files before it returns what it has (#13602). |
| `AUTOBOT_OWNERSHIP_MAX_FILES` | backend | int | `2000` | How many files ownership analysis will blame. Paired with the time budget because a file count alone is the wrong bound — file size dominates blame cost (#13602). |
| `AUTOBOT_PLAN_BEST_OF_N_COUNT` | ai | int | `3` | How many candidate plans best-of-N generates before selection. Clamped to a minimum of 2, since best-of-1 is not a selection. |
| `AUTOBOT_PLAYBOOK_FAILURE_TAIL_CHARS` | backend | int | `500` | How many characters of a failed playbook's output to fall back to when no failed task can be parsed out of it. Taken from the END of the run: ansible opens with its banner, so a head slice returns deprecation warnings and hides the failure (services/ansible_utils.py, #14298). |
| `AUTOBOT_PLAYBOOK_KILL_GRACE_S` | backend | float | `5.0` | Grace period between SIGTERM and SIGKILL when killing a timed-out playbook subprocess's whole process group. Long enough for ansible-playbook / a forked ssh child to unwind cleanly; short enough that a wedged process does not itself become an unbounded second wait (services/playbook_executor.py, #14524). |
| `AUTOBOT_POSTGRES_DB` | postgres | str | `'autobot_users'` | PostgreSQL database name. |
| `AUTOBOT_POSTGRES_HOST` | postgres | str | `'127.0.0.1'` | PostgreSQL server hostname or IP. |
| `AUTOBOT_POSTGRES_PASSWORD` | postgres | str | `""` | PostgreSQL user password. |
| `AUTOBOT_POSTGRES_PORT` | postgres | str | `'5432'` | PostgreSQL server port. |
| `AUTOBOT_POSTGRES_USER` | postgres | str | `'slm_app'` | PostgreSQL login role. |
| `AUTOBOT_PROMETHEUS_PORT` | monitoring | str | `'9090'` | TCP port of the Prometheus instance. Also declared in ssot_config.py. |
| `AUTOBOT_PROMETHEUS_URL` | monitoring | str | `'http://10.0.0.4:9090'` | Base URL of the Prometheus metrics server. |
| `AUTOBOT_PROVIDER_DEGRADATION_TTL_SECONDS` | ai | int | `300` | Seconds a provider stays marked degraded after a failure before traffic is offered to it again. |
| `AUTOBOT_PROVIDER_OAUTH_STATE_TTL_SECONDS` | auth | int | `600` | Lifetime of a pending OAuth `state` value. A provider authorisation that is not completed within this window is rejected as expired (api/provider_auth.py). |
| `AUTOBOT_PROVISION_STALE_SECONDS` | provisioning | int | `1800` | How long a provision run may report no progress before the setup wizard treats it as abandoned and lets a new run supersede it (#14856). Keyed on observed progress, not on time since start, so a slow-but-live run is never superseded; the floor keeps a value too small to distinguish the two from wedging the wizard the other way. Range: 60–86400. |
| `AUTOBOT_REDIS_DB_ANALYTICS` | redis | int | `11` | Redis logical database number for analytics data. Range: 0–15. |
| `AUTOBOT_REDIS_DB_KNOWLEDGE` | redis | int | `1` | Redis logical database number for knowledge-base vectors. Range: 0–15. |
| `AUTOBOT_REDIS_DB_MAIN` | redis | int | `0` | Redis logical database number for primary application data. Range: 0–15. |
| `AUTOBOT_REDIS_HOST` | redis | str | `'localhost'` | Redis server hostname or IP address. |
| `AUTOBOT_REDIS_PASSWORD` | redis | str | *(none)* | Redis AUTH password (omit or leave blank for unauthenticated servers). |
| `AUTOBOT_REDIS_PORT` | redis | int | `6379` | Redis server TCP port (plain connection). Range: 1–65535. |
| `AUTOBOT_REDIS_TLS_ENABLED` | redis | bool | false | Enable TLS for Redis connections when truthy. |
| `AUTOBOT_REDIS_TLS_PORT` | redis | int | `6380` | Redis server TCP port for TLS connections. Range: 1–65535. |
| `AUTOBOT_REMEDIATION_HEARTBEAT_POLL_S` | backend | int | `5` | How often to re-read the node row while waiting for a post-restart heartbeat (services/reconciler.py, #14344). |
| `AUTOBOT_REMEDIATION_HEARTBEAT_WAIT_S` | backend | int | `90` | Seconds to wait for a heartbeat after the reconciler restarts a node's agent before recording the remediation as failed. Remediation exists to restore the heartbeat, so the heartbeat is what success means — the restart exiting 0 only says the command ran (services/reconciler.py, #14344). |
| `AUTOBOT_REMEDIATION_PLAYBOOK_TIMEOUT_S` | backend | int | `180` | Wall-clock ceiling on the ansible-playbook subprocess _restart_service_via_ansible launches. Previously unbounded — a hung SSH connection or stuck remote task blocked remediation for a node indefinitely. manage-service.yml (the only playbook this call path runs) is a single-host, single-service restart that normally completes in seconds; 180s stays comfortably below REMEDIATION_COOLDOWN (300s) while giving generous headroom (services/reconciler.py, services/playbook_executor.py, #14524). |
| `AUTOBOT_REMEDIATION_TRACKER_EXPIRY_S` | backend | int | `1800` | Seconds a non-exhausted remediation attempt tracker may sit with no NEW attempt before its count is forgiven. Clamped strictly above REMEDIATION_COOLDOWN plus a reconcile-tick margin — a lower value forgives an attempt in the same instant one becomes due, so count could never exceed 1 (services/reconciler.py, #14465). |
| `AUTOBOT_REMOTE_APPROVAL_FLAG_TTL_SECONDS` | approvals | int | `604800` | How long a session stays flagged for remote approval routing without being refreshed. Expiry returns the session to asking inline; it never widens autonomy. |
| `AUTOBOT_REMOTE_APPROVAL_TTL_SECONDS` | approvals | int | `86400` | How long a remotely delivered approval stays correlatable with its reply. After this the reply can no longer be tied to a request and resolves nothing. |
| `AUTOBOT_REQUIRE_CLASSIFICATION` | orchestrator | bool | false | Fail orchestrator construction when request classification is unavailable. Default (off) degrades gracefully: every request is defaulted to COMPLEX and the reason is reported in the orchestration status. Deployments that depend on classification set this so the failure is loud instead of silent (#13807). |
| `AUTOBOT_RESTART_CHURN_WINDOW_S` | backend | int | `600` | Seconds a managed autobot/slm-agent service is reported as CURRENTLY churning after its last observed n_restarts increase, for node-status degrade purposes. Must clear health_collector's own 300s discovery-cache TTL by a comfortable margin — a shorter window only fires on the beat that happens to land on a cache refresh (services/reconciler.py, #14465). |
| `AUTOBOT_RETRIEVAL_REDIS_TIMEOUT` | redis | float | `1.5` | Seconds the retrieval learner waits for its Redis lock before proceeding without it. Short on purpose — retrieval must answer even when the learner cannot record what it learned. |
| `AUTOBOT_SERVICE_RESTART_PLAYBOOK_TIMEOUT_S` | backend | int | `2100` | Wall-clock ceiling on _restart_service_via_ansible when it restarts an arbitrary ServiceCategory.AUTOBOT unit (_remediate_failed_service), as opposed to the lightweight slm-agent restart (AUTOBOT_REMEDIATION_PLAYBOOK_TIMEOUT_S). That category is populated by unit-name pattern match (postgresql*, redis*, docker*, ...), an open-ended set that includes Type=oneshot units with a multi-minute TimeoutStartSec (autobot-pg-backup.service.j2 declares 1800s) -- reusing the slm-agent budget here would SIGKILL a legitimate long-running restart (services/reconciler.py, #14524). |
| `AUTOBOT_SHOW_DEPRECATION_WARNINGS` | system | bool | false | Emit Python DeprecationWarnings for deprecated AutoBot APIs when truthy. |
| `AUTOBOT_SIGNAL_ENABLED` | gateway | bool | false | Opt in to the Signal gateway adapter. Off by default: it needs a running signal-cli daemon and a registered number. |
| `AUTOBOT_SKILL_DISTILLATION_ENABLED` | backend | bool | false | Master switch for skill distillation. Ships inert — enable once the LLM cost of a recurring pass is accepted. |
| `AUTOBOT_SKILL_DISTILLATION_FAILURE_TTL_S` | backend | int | `86400` | How long a conversation's consecutive-failure count survives, in seconds. Derived as 24 distillation intervals, so failures accumulate across passes rather than expiring between them, while a counter for a conversation nobody retries eventually clears instead of accumulating forever (#14255). |
| `AUTOBOT_SKILL_DISTILLATION_IDLE_FLUSH_S` | backend | int | `900` | Seconds of corpus idleness after which a distillation pass runs early. Without it the pass is purely clock-bound and a conversation ending at 09:00 waits for the small hours (#13695). |
| `AUTOBOT_SKILL_DISTILLATION_INTERVAL_S` | backend | int | `3600` | Seconds between skill distillation passes. |
| `AUTOBOT_SKILL_DISTILLATION_MAX_FAILURES` | backend | int | `3` | Consecutive failures on the SAME conversation before the distillation pass stops waiting for it and moves on. Below this the pass halts and retries next run, so a transient fault costs nothing; at it, the conversation is quarantined with a warning and the cursor advances, so one unreadable conversation cannot starve every newer one behind it in an oldest-first queue (#14255). A success resets the count. |
| `AUTOBOT_SKILL_DISTILLATION_MAX_SESSIONS` | backend | int | `10` | Conversations distilled per pass. Bounds the LLM spend of any one run; the remainder is picked up next time because the cursor only advances over what was handled. |
| `AUTOBOT_SKILL_DISTILLATION_MIN_MESSAGES` | backend | int | `4` | Minimum messages a conversation needs before distillation attempts it. Shorter ones cannot contain a reusable workflow and the extractor rejects them anyway. |
| `AUTOBOT_SLM_JOURNAL_SSH_TIMEOUT_SECONDS` | slm | float | `30.0` | Wall-clock ceiling on the journalctl-over-SSH fetch behind GET /nodes/{node_id}/services/{service_name}/logs (api/services.py, #15620). Fetching journal entries from a node under load is slower than restarting a unit on it, and the request is operator-facing, so the cost runs both ways: raise it and an API worker stays occupied that much longer per unresponsive node, which a fleet-wide log sweep multiplies; lower it and a busy node answers HTTP 504 instead of returning its logs, and the operator has to retry asking for fewer lines. Tune it to the slowest link in the fleet, not to the fastest. Range: 5.0–600.0. |
| `AUTOBOT_SNAPSHOT_STORAGE_PATH` | execution | str | `""` | Directory holding execution snapshots. Empty means 'derive it' — the default is `<project root>/snapshots`, so it follows the install location rather than being pinned to one path. |
| `AUTOBOT_SNAPSHOT_TTL_DAYS` | execution | int | `7` | Age at which the cleanup task removes an execution snapshot. Snapshots are a debugging aid, so the default is deliberately short. |
| `AUTOBOT_STT_NO_SPEECH_PROB_THRESHOLD` | voice | float | `0.8` | Decoder no-speech probability at or above which an STT transcript is discarded as a silence hallucination (#13104). Range: 0.0–1.0. |
| `AUTOBOT_STT_PEAK_WINDOW_MS` | voice | int | `100` | Window in milliseconds over which speech energy is measured. Measuring across the whole buffer averages a short reply into silence (#13104). |
| `AUTOBOT_STT_SILENCE_RMS_THRESHOLD` | voice | float | `0.005` | Audio RMS below which the waveform is treated as silence, so any STT transcript over it is a hallucination rather than a user turn (#13104). Range: 0.0–1.0. |
| `AUTOBOT_SUMMARY_FAILURE_BACKOFF_SECONDS` | chat | int | `300` | Quiet period after a context-overflow summarisation failure before another is attempted, so a persistently failing summary does not retry on every turn. |
| `AUTOBOT_SYNC_POST_CMD_TIMEOUT_S` | backend | int | `300` | Seconds a code-sync post-sync command may run before it is abandoned. It covers a dependency install, so the ceiling depends on link speed and wheel availability rather than on anything fixed (services/sync_orchestrator.py, #14275). |
| `AUTOBOT_TERMINAL_SESSION_TTL_SECONDS` | terminal | int | `86400` | TTL for terminal:session_config:* Redis keys — the cross-worker terminal session registry (services/terminal_session_store.py, #14961). A session config outlives the connection it was created for (the WebSocket may attach on a different uvicorn worker, or reconnect after one), so this is deliberately generous: 24h matches the sibling chat:session:* cache TTL (chat_history/cache.py) rather than the lifetime of any single PTY process. Range: 60–604800. |
| `AUTOBOT_TLS_CA_PATH` | tls | str | *(none)* | Path to the CA certificate file for TLS verification. |
| `AUTOBOT_TLS_CERT_DIR` | tls | str | `'/etc/autobot/certs'` | Directory containing TLS certificate and key files. |
| `AUTOBOT_TLS_CERT_PATH` | tls | str | *(none)* | Path to the TLS client/server certificate file. |
| `AUTOBOT_TLS_KEY_PATH` | tls | str | *(none)* | Path to the TLS private key file. |
| `AUTOBOT_TRAJECTORY_CONSOLIDATE_SCAN_LIMIT` | ai | int | `50000` | Rows a consolidation pass may scan, keeping the pass bounded on a large trajectory store. |
| `AUTOBOT_TRAJECTORY_OUTCOME_PARTIAL_MIN` | ai | float | `0.4` | Reward at or above which a trajectory outcome is 'partial'. Below it the outcome is a failure (#11280). |
| `AUTOBOT_TRAJECTORY_OUTCOME_SUCCESS_MIN` | ai | float | `0.7` | Reward at or above which a trajectory outcome is 'success'. The canonical threshold, so callers stop re-deriving it inline (#11280). |
| `AUTOBOT_TRAJECTORY_PRUNE_MAX_AGE_DAYS` | ai | int | `30` | Age in days beyond which a low-reward trajectory is eligible for pruning (#11263). |
| `AUTOBOT_TRAJECTORY_PRUNE_REWARD_FLOOR` | ai | float | `0.4` | Reward below which an aged trajectory is pruned. Stale low-reward failures are noise that costs retrieval precision (#11263). |
| `AUTOBOT_TRAJECTORY_USER_SCOPED` | ai | bool | true | Scope trajectory retrieval by user as well as tenant. tenant_id alone is insufficient in single-company deployments where org_id is empty or identical for everyone (#11089). |
| `AUTOBOT_TRANSCRIBER_DB_PATH` | voice | str | `'data/transcriber.db'` | SQLite database backing the transcriber. Relative to the working directory unless given as an absolute path. |
| `AUTOBOT_TRUSTED_PROXIES` | network | str | `""` | Comma-separated list of trusted reverse-proxy IP addresses or CIDR ranges for X-Forwarded-For header trust. |
| `AUTOBOT_UPDATE_CODE_SOURCE_GIT_TIMEOUT_S` | backend | int | `30` | Per-command timeout for the git checkout/fetch/reset subcommands PlaybookExecutor._update_code_source runs before every playbook. On expiry the WHOLE process group is killed (not just git's own pid), since git can leave an ssh/credential-helper child holding the output pipes open (services/playbook_executor.py, #14524). |
| `AUTOBOT_UPDATE_CODE_SOURCE_REV_PARSE_TIMEOUT_S` | backend | int | `10` | Timeout for the best-effort 'git rev-parse --short HEAD' traceability log PlaybookExecutor._update_code_source runs after a successful sync (services/playbook_executor.py, #14524). |
| `AUTOBOT_USERS_DATABASE_URL` | postgres | str | *(none)* | Full SQLAlchemy connection URL for the users database. Overrides AUTOBOT_POSTGRES_* individual vars when set. |
| `AUTOBOT_VOICE_TOOLSETS` | voice | str | `'voice_safe'` | Comma-separated toolset bundles a voice session may call. Defaults to the restricted `voice_safe` bundle — voice input is harder to confirm than typed input, so the surface is narrowed by default. |

*151 variables registered as of last generation.*
<!-- END_AUTOGEN_ENV_DOCS -->
