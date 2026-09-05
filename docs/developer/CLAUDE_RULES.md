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
| `AUTOBOT_A2A_CAPABILITY_TTL` | a2a | int | `300` | How long a fetched remote A2A capability descriptor is cached before the next check re-fetches it. Raising it reduces repeated cross-agent capability lookups; lowering it makes a capability change on the remote side (e.g. a tool removed) visible sooner (a2a/capability_verifier.py). |
| `AUTOBOT_ALLOW_CONFIG_EDITS` | system | bool | false | Permit writes to the repository's tracked config files. Off by default: the codebase is the source of truth and an edit made here is invisible to deployment (#11220). |
| `AUTOBOT_APPROVAL_PENDING_SESSION_TTL_SECONDS` | execution | int | `604800` | Seconds a session holding a pending approval survives in Redis. Deliberately long — what it waits for is a person, and expiring sooner discards the approval rather than the wait (#13478). |
| `AUTOBOT_ASK_HUMAN_TIMEOUT_SECONDS` | agent_loop | int | `300` | Seconds the agent loop suspends waiting for a human to answer an ask-human question before escalating past it (#10553). Raising it gives a human longer to respond; lowering it escalates sooner, risking a question no one had time to see (agent_loop/types.py). |
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
| `AUTOBOT_CODE_INDEX_GIT_TIMEOUT_SECONDS` | knowledge | int | `10` | Ceiling on each read-only git call the code indexer's provenance lookups make. Raising it tolerates a slower git history walk on a large repo; lowering it fails a stalled git call faster, at the risk of a false timeout on a legitimately slow repo (services/knowledge/code_indexer.py). |
| `AUTOBOT_COGNIFIER_BATCH_MAX_TOKENS_CAP` | knowledge | int | `8192` | Absolute ceiling on the max_tokens sent for a batched cognifier extraction call, regardless of batch size (#11012). Raising it allows a larger batched response before truncation; lowering it protects against an oversized request to the LLM provider (knowledge/pipeline/cognifiers/llm_utils.py). |
| `AUTOBOT_COGNIFIER_BATCH_MAX_TOKENS_PER_CHUNK` | knowledge | int | `1024` | Per-chunk token budget used to scale max_tokens with the number of chunks packed into one batched cognifier extraction call (#11012). Raising it reduces truncation risk for large chunks; lowering it caps per-chunk cost, at the risk of truncating longer chunks (knowledge/pipeline/cognifiers/llm_utils.py). |
| `AUTOBOT_COMPACTION_BOUNDARY_WINDOW` | chat | int | `10` | How far back the compaction boundary looks for a user turn before settling for any turn start, so the cut cannot be dragged far from the midpoint. |
| `AUTOBOT_COMPACTION_STATE_COMMAND_CAP` | chat | int | `10` | Most recent shell commands named in a compaction's extracted state block. |
| `AUTOBOT_COMPACTION_TOOL_RESULT_CLIP_CHARS` | chat | int | `400` | Maximum characters of a tool result in the summarised region before it is clipped for the summariser; a file read many turns ago is cheaper to re-read than to carry. |
| `AUTOBOT_COMPACTION_USER_MESSAGE_CAP` | chat | int | `40` | How many of the most recent user messages cross a context compaction verbatim instead of being summarised. Bounded so repeated compaction cannot grow the preserved set without limit. |
| `AUTOBOT_CONFIG_REGISTRY_REDIS_RETRY_SECONDS` | redis | float | `30.0` | Interval between config-registry attempts to reconnect to Redis after a failure, so a Redis outage does not become a reconnect storm. |
| `AUTOBOT_DB_BACKUP_KEEP` | slm | int | `5` | Number of pg_dump backups retained per component before the oldest are pruned. Raising it keeps a longer rollback history at the cost of more disk in the backup directory; lowering it frees disk sooner but shortens how far back a restore can reach (autobot-slm-backend/api/code_sync.py, #11376). |
| `AUTOBOT_DELEGATION_ENABLED` | ai | bool | false | Master switch for the delegate tool. Off, it records the delegation request and does not dispatch it. |
| `AUTOBOT_DEPLOYMENT_MODE` | system | str | `'distributed'` | Deployment topology: 'distributed' or 'standalone'. |
| `AUTOBOT_DESKTOP_CONTROL_LOCK_TTL_SECONDS` | desktop | int | `120` | Idle-TTL for a desktop-control lock: if not refreshed within this window, it auto-expires and control returns to the agent. Raising it tolerates a longer human takeover before auto-release; lowering it returns control to the agent sooner after the human goes idle (api/desktop_control_lock.py). |
| `AUTOBOT_DEVICE_POLL_BACKOFF_SECONDS` | auth | int | `5` | Extra delay added to the device-code poll interval after the provider answers `slow_down`. |
| `AUTOBOT_DEVICE_POLL_MAX_ATTEMPTS` | auth | int | `360` | Maximum device-code poll attempts before the flow is abandoned. Bounds the poll loop independently of the time window below. |
| `AUTOBOT_DEVICE_POLL_MIN_INTERVAL_SECONDS` | auth | int | `5` | Floor on how often the device-code flow polls the provider for completion, regardless of the interval the provider advertises. |
| `AUTOBOT_DEVICE_POLL_WINDOW_SECONDS` | auth | int | `1800` | Wall-clock ceiling on a device-code flow. Reached first when the provider advertises a long interval, whereas the attempt cap above binds first when it advertises a short one. |
| `AUTOBOT_DOCKER_POOL_SIZE` | execution | int | `3` | Number of warm containers kept when AUTOBOT_DOCKER_USE_POOL is on. Ignored entirely when pooling is off. |
| `AUTOBOT_DOCKER_USE_POOL` | execution | bool | false | Reuse a pool of warm containers for tool execution instead of starting one per call. Off by default — the pool trades isolation between calls for start-up latency. |
| `AUTOBOT_ENV` | system | str | `'production'` | Short environment label used in logs and traces (e.g. 'development', 'production'). |
| `AUTOBOT_ENVIRONMENT` | system | str | `'development'` | Full environment name for OTel deployment.environment attribute. Prefer AUTOBOT_ENV for new code. |
| `AUTOBOT_EXTRACT_CHUNK_THRESHOLD` | llm | int | `8000` | Character-count threshold above which structured-extraction input is auto-chunked before an LLM call. Raising it sends larger inputs in a single call; lowering it chunks sooner, trading more calls for a smaller per-call context (llm_shared/structured_ops.py). |
| `AUTOBOT_EXTRACT_MAX_RETRIES` | llm | int | `3` | Maximum LLM call attempts a structured-extraction request makes before raising ExtractionError. Raising it tolerates more transient failures before giving up; lowering it fails faster but is less tolerant of a flaky provider (llm_shared/structured_ops.py). |
| `AUTOBOT_FACT_FORCING` | ai | bool | false | Enable the fact-forcing gate, which requires an answer to cite retrieved facts. |
| `AUTOBOT_GATEWAY_REQUIRE_OUTBOUND_APPROVAL` | gateway | bool | false | Require approval before the Gateway hands an agent-authored message to a channel adapter. Off means audit-only: every governed send is recorded, none is blocked. On fails closed — no registered approver, a denial, or an approver error all deny the send. |
| `AUTOBOT_GIT_BRANCH` | system | str | `'Dev_new_gui'` | Git branch that the running instance was built from. |
| `AUTOBOT_GRAFANA_PORT` | monitoring | str | `'3000'` | TCP port of the Grafana instance. Also declared in ssot_config.py; 3000 is Grafana's own default and is NOT the browser service, which is 9001 (#4052, #14198). |
| `AUTOBOT_GRAPH_PATH_TIMEOUT_SECONDS` | kb | float | `10.0` | Ceiling on a knowledge-graph path search. Path queries are unbounded in the worst case, so this is what stops one request occupying a worker indefinitely. |
| `AUTOBOT_HEALTH_POLL_CONNECT_TIMEOUT` | slm | float | `3.0` | Per-attempt connect timeout, in seconds, when probing a just-restarted component's health endpoint. Raising it tolerates a service that is slower to accept connections; lowering it fails an unreachable endpoint faster (autobot-slm-backend/api/code_sync.py, #11378). |
| `AUTOBOT_HEALTH_POLL_INTERVAL` | slm | float | `2.0` | Delay, in seconds, between health-probe attempts after a component restart. Raising it polls less often (lower overhead, slower detection); lowering it detects a healthy service sooner at the cost of more probe traffic (autobot-slm-backend/api/code_sync.py, #11378). |
| `AUTOBOT_HEALTH_POLL_TIMEOUT` | slm | float | `180.0` | Total seconds to wait for a component to report healthy after a restart that recreated its venv, covering first-run py3.14 bytecode compilation of the whole dependency tree (#11413). Lowering it risks a false #11377 rollback of a slow-but-healthy cold start; raising it waits longer before giving up on a genuinely stuck restart (autobot-slm-backend/api/code_sync.py, #11378). |
| `AUTOBOT_HEALTH_POLL_TIMEOUT_FAST` | slm | float | `60.0` | Total seconds to wait for a component to report healthy after a restart that reused its existing venv (warm interpreter, no cold-start compilation). Lowering it detects a stuck restart sooner; raising it tolerates a slower warm restart before the wait ends (autobot-slm-backend/api/code_sync.py, #11458). |
| `AUTOBOT_IMESSAGE_ENABLED` | gateway | bool | false | Opt in to the iMessage gateway adapter. Off by default: it is macOS-only and needs Full Disk Access to the Messages database. |
| `AUTOBOT_INJECTION_HARDBLOCK_ENABLED` | auth | bool | false | Hard-block prompt injection rather than only flagging it. When on and confidence clears the threshold, the request is refused instead of annotated. |
| `AUTOBOT_INJECTION_HARDBLOCK_THRESHOLD` | auth | float | `0.75` | Confidence in [0.0, 1.0] at or above which a detected injection is hard-blocked. 0.75 maps to HIGH; 1.0 would block only CRITICAL. |
| `AUTOBOT_INTERNAL_API_KEY` | auth | str | `""` | Shared secret used to authenticate internal service-to-service calls. |
| `AUTOBOT_KB_TIMEOUT` | kb | int | `30` | Timeout in seconds for knowledge-base HTTP requests. Range: 1–300. |
| `AUTOBOT_KNOWLEDGE_EXPORT_MIN_CONFIDENCE` | self_improvement | float | `0.8` | Minimum confidence score a learned failure pattern must have to be included in a governance knowledge export. Raising it exports only higher-confidence patterns; lowering it includes more, less-certain ones (api/agents_self_improvement.py). |
| `AUTOBOT_KNOWLEDGE_EXPORT_PATTERN_LIMIT` | self_improvement | int | `500` | Maximum number of failure patterns scanned when building a governance knowledge export (GH#11179). Raising it scans more patterns before truncating; lowering it risks silently omitting patterns beyond the limit (api/agents_self_improvement.py). |
| `AUTOBOT_LEARNED_TEMPLATE_MAX` | self_improvement | int | `500` | Maximum characters kept from untrusted imported free-text when importing a reviewer-curated learned strategy (#11060). Raising it preserves more of a long imported template; lowering it truncates more aggressively, reducing how much unsanitized text is retained (api/agents_self_improvement.py). |
| `AUTOBOT_LIVE_PROBE_TIMEOUT_SECONDS` | testing | float | `1.0` | Seconds a test's live-service precondition probe waits for a TCP connect before reporting the service as absent and skipping (autobot_shared/live_service_probe.py, #14930). Short by default: a refused loopback connect returns immediately, and this runs once per endpoint per process. Raise it when probing a fleet host across a link slow enough that a live service could be mistaken for a missing one. Range: 0.1–60.0. |
| `AUTOBOT_LLC_H2A_BRIEF_CACHE_TTL` | orchestrator | int | `86400` | Cache lifetime in seconds for a human-to-agent handoff brief (llc/services/handoff.py). One day. |
| `AUTOBOT_LLM_MAX_RETRY_AFTER_SECONDS` | ai | float | `30.0` | Cap applied to a provider's `Retry-After`. Without it a provider advertising a long back-off would stall a request for that whole period (services/llm_service.py). |
| `AUTOBOT_LLM_TOKEN_BUDGET_PER_RUN` | ai | int | `0` | Cumulative token ceiling (input plus output) for one run. Zero disables the gate, which is the shipped default (#11541). |
| `AUTOBOT_LLM_TOKEN_BUDGET_TTL_SECONDS` | ai | int | `86400` | Seconds a run's cumulative token counter survives in Redis, bounding memory for abandoned sessions. Refreshed on every increment. |
| `AUTOBOT_LOGS_BACKUP_DIR` | logging | str | `'backup'` | Directory where rotated log archives are written. |
| `AUTOBOT_LOGS_DIR` | logging | str | `'logs'` | Primary directory for application log files. |
| `AUTOBOT_LOG_FLOOD_ENABLED` | logging | bool | true | Bound how many identical WARNING/ERROR records one call site may emit per window (#15774). |
| `AUTOBOT_LOG_FLOOD_MAX_KEYS` | logging | int | `2048` | Maximum distinct call sites tracked by the log-flood guard before least-recent eviction. |
| `AUTOBOT_LOG_FLOOD_THRESHOLD` | logging | int | `5` | Records one log call site may emit per flood window before the rest are suppressed. |
| `AUTOBOT_LOG_FLOOD_WINDOW_SECONDS` | logging | int | `60` | Length of the log-flood suppression window, in seconds. |
| `AUTOBOT_LOG_VIEWER_URL` | logging | str | `'http://localhost:5341'` | Base URL of the Seq (or compatible) structured-log viewer. |
| `AUTOBOT_MATRIX_E2EE` | gateway | bool | false | Opt in to end-to-end encryption for the Matrix adapter. Off by default because E2EE needs the optional olm dependency and a persisted device store. |
| `AUTOBOT_MAX_ATTEMPTS_REFUSAL_BROADCAST_INTERVAL_S` | backend | int | `3600` | How often to re-broadcast that a node is still at MAX_REMEDIATION_ATTEMPTS. Once exhausted, last_attempt freezes and this refusal is refused again on every reconcile pass forever — unthrottled, that is once per reconcile_interval (services/reconciler.py, #14465). |
| `AUTOBOT_MAX_DELEGATIONS_PER_TURN` | ai | int | `5` | Delegate calls allowed in a single LLM turn — a fan-out bound, not a quality setting. |
| `AUTOBOT_MAX_DELEGATION_DEPTH` | ai | int | `2` | How deep delegation may nest before it is refused, bounding runaway recursive delegation. |
| `AUTOBOT_MAX_FALLBACK_ATTEMPTS` | llm | int | `3` | Maximum model-level fallback attempts the coordinator makes after a quota/rate-limit exhaustion before giving up. Raising it tries more fallback models before failing; lowering it gives up sooner, failing faster but with less fallback coverage (llm_shared/model_fallback_coordinator.py). |
| `AUTOBOT_MAX_TASK_TYPE_KEYS_PER_TENANT` | agents | int | `64` | Per-tenant cap on distinct task_type keys the pattern learner tracks in Redis, beyond the known-vocabulary allowlist (GH#11534). Raising it tolerates more distinct task types per tenant before capping; lowering it bounds Redis key growth more tightly against a runaway integration (agents/task_pattern_learner.py). |
| `AUTOBOT_MAX_UNMATCHED_OUTPUT_CHARS` | tools | int | `20000` | Cap on unmatched tool-output characters retained before the filter truncates. Raising it keeps more raw output for unmatched patterns; lowering it truncates sooner, reducing memory/storage per tool call (services/tool_output_filter.py). |
| `AUTOBOT_MULTIMODAL_VOICE_CONFIDENCE_THRESHOLD` | voice | float | `0.7` | Fallback confidence threshold for VoiceProcessor when the multimodal.voice config section omits it (#13207). Range: 0.0–1.0. |
| `AUTOBOT_MULTIMODAL_VOICE_PROCESSING_TIMEOUT` | voice | int | `30` | Fallback processing timeout in seconds for VoiceProcessor when the multimodal.voice config section omits it (#13207). |
| `AUTOBOT_NODE_PROXY_TIMEOUT_SECONDS` | slm | float | `15.0` | Ceiling on a proxied request from the SLM to a node's backend. The aggregator fans out across the fleet, so without a bound one unresponsive node would hold the whole lifecycle view open. |
| `AUTOBOT_NPM_BUILD_TIMEOUT` | slm | float | `300.0` | Timeout, in seconds, for `npm run <build>` (the vite build step) during a frontend component sync. Raising it tolerates a slower build; lowering it fails a stuck build sooner (autobot-slm-backend/api/code_sync.py, #11351). |
| `AUTOBOT_NPM_INSTALL_TIMEOUT` | slm | float | `300.0` | Timeout, in seconds, for `npm ci` (dependency install) during a frontend component sync. A Windows-generated package-lock.json read over WSL can be slow, which is why the default matches pip's. Raising it tolerates a slower install; lowering it fails a stuck install sooner (autobot-slm-backend/api/code_sync.py, #11351). |
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
| `AUTOBOT_PAPERCLIP_COMMENT_DEDUP_TTL` | paperclip | int | `3600` | TTL, in seconds, for the idempotency key that deduplicates a Paperclip issue comment. Raising it widens the window in which a retried comment is treated as a duplicate; lowering it narrows that window, risking a duplicate comment on a slow retry (autobot_shared/paperclip_client.py). |
| `AUTOBOT_PIP_INSTALL_TIMEOUT` | slm | float | `300.0` | Timeout, in seconds, for a `pip install` during venv reconciliation. Raising it tolerates a slower package install; lowering it fails a stuck install sooner (autobot-slm-backend/api/venv_reconcile.py). |
| `AUTOBOT_PIP_UNINSTALL_TIMEOUT` | slm | float | `120.0` | Timeout, in seconds, for a `pip uninstall` during venv reconciliation. Raising it tolerates a slower removal; lowering it fails a stuck uninstall sooner (autobot-slm-backend/api/venv_reconcile.py). |
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
| `AUTOBOT_PUSH_NOTIFICATION_TTL` | notifications | int | `86400` | TTL, in seconds, applied to a web-push notification payload (#6743). Raising it lets a push provider retry delivery over a longer window; lowering it drops a stale, undelivered notification sooner (services/push_notification_service.py). |
| `AUTOBOT_RANKING_ALPHA` | code_analysis | float | `1.0` | Multiplicative weight applied to the runtime_risk boost when ranking anti-pattern findings (0 disables the boost; 1.0 lets a fully-risky file double its effective score). Raising it weights runtime risk more heavily in the ranking; lowering it toward 0 weights it less (code_analysis/src/anti_pattern_detector.py). |
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
| `AUTOBOT_RISK_K` | code_analysis | float | `5.0` | Decay constant controlling how steeply a file's runtime_risk score saturates toward 1 as its raw risk grows (a file at raw_risk == K scores about 0.63). Raising it makes the score saturate more slowly; lowering it saturates faster (code_analysis/src/runtime_risk.py). |
| `AUTOBOT_RUN_CHECKPOINT_TTL_SECONDS` | agent_loop | int | `86400` | TTL, in seconds, for a run's durable progress checkpoint in Redis (GH#11175). Raising it lets a crashed/restarted run resume from a checkpoint over a longer window; lowering it expires stale checkpoints sooner (agent_loop/loop.py). |
| `AUTOBOT_RUN_JWT_DENYLIST_TIMEOUT_S` | auth | float | `2.0` | Redis lookup budget, in seconds, for the run-JWT denylist check on the auth path (#12751). Raising it tolerates a slower Redis before treating it as unavailable (fail-closed); lowering it falls over to fail-closed sooner on a slow Redis (services/run_jwt.py). |
| `AUTOBOT_SANDBOX_GIT_STATUS_TIMEOUT_SECONDS` | backend | int | `10` | Seconds the sandbox delete guard waits for `git status --porcelain` before treating the work tree as unverifiable and refusing the recursive delete (api/sandbox_files.py, #15777). |
| `AUTOBOT_SELF_IMPROVEMENT_MAX_CONCURRENCY` | orchestration | int | `2` | Maximum concurrent background self-improvement (judge-LLM) tasks the workflow runner allows (#11014). Raising it lets more workflow completions trigger learning concurrently; lowering it bounds concurrent judge-LLM load more tightly (orchestration/workflow_runner.py). |
| `AUTOBOT_SERVICE_RESTART_PLAYBOOK_TIMEOUT_S` | backend | int | `2100` | Wall-clock ceiling on _restart_service_via_ansible when it restarts an arbitrary ServiceCategory.AUTOBOT unit (_remediate_failed_service), as opposed to the lightweight slm-agent restart (AUTOBOT_REMEDIATION_PLAYBOOK_TIMEOUT_S). That category is populated by unit-name pattern match (postgresql*, redis*, docker*, ...), an open-ended set that includes Type=oneshot units with a multi-minute TimeoutStartSec (autobot-pg-backup.service.j2 declares 1800s) -- reusing the slm-agent budget here would SIGKILL a legitimate long-running restart (services/reconciler.py, #14524). |
| `AUTOBOT_SESSION_ROLE_TTL_SECONDS` | chat_workflow | int | `86400` | TTL, in seconds, for a chat session's role binding in Redis. Raising it keeps a session's assigned role valid longer between activity; lowering it expires it sooner, requiring the role to be re-resolved (chat_workflow/session_role.py). |
| `AUTOBOT_SESSION_WORK_ITEM_TTL_SECONDS` | chat_workflow | int | `86400` | TTL, in seconds, for a chat session's work-item binding in Redis. Raising it keeps the session-to-work-item link valid longer between activity; lowering it expires it sooner (chat_workflow/session_work_item.py). |
| `AUTOBOT_SHARED_LINK_ACCESS_RPH` | chat | int | `100` | Per-client-IP requests-per-hour ceiling on the unauthenticated shared-link /access endpoint (GH#9127). Raising it tolerates more password attempts per hour before rate-limiting; lowering it hardens against brute force sooner, at the risk of blocking a legitimate slow guesser (api/chat_shared_links.py). |
| `AUTOBOT_SHARED_LINK_ACCESS_RPM` | chat | int | `10` | Per-client-IP requests-per-minute ceiling on the unauthenticated shared-link /access endpoint (GH#9127). Raising it tolerates a faster burst of password attempts before rate-limiting; lowering it rate-limits sooner (api/chat_shared_links.py). |
| `AUTOBOT_SHARED_LINK_DEFAULT_TTL` | chat | int | `0` | Default TTL, in seconds, applied to a newly created chat shared link when the caller does not specify one (0 means the link never expires unless a TTL is explicitly requested). Raising it shortens how long a share defaults to being valid before expiring (api/chat_shared_links.py). |
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
| `AUTOBOT_SLM_RESTART_FLUSH_DELAY_SECONDS` | slm | float | `1.0` | Seconds the deferred SLM service restart waits for the HTTP response to flush before it starts killing the services that carried it. Too short and the caller sees a dropped connection instead of its 202; too long and the restart is needlessly delayed, so the right value follows the deployment's network rather than anything fixed (services/service_restart.py, #15611). Range: 0.0–60.0. |
| `AUTOBOT_SLM_RESTART_SSH_TIMEOUT_SECONDS` | slm | float | `30.0` | Seconds a single `systemctl restart` over SSH may take before it is abandoned and reported as failed. A slow node restarting a heavy unit legitimately exceeds a value that is generous on a fast one, so this belongs to the deployment (services/service_restart.py, #15611). Range: 1.0–600.0. |
| `AUTOBOT_SNAPSHOT_KEEP` | slm | int | `3` | Number of component snapshots retained for rollback before the oldest are pruned. Raising it keeps a longer rollback history at the cost of more snapshot-directory disk usage; lowering it frees disk sooner but shortens how far back a rollback can reach (autobot-slm-backend/api/code_sync.py, #11377). |
| `AUTOBOT_SNAPSHOT_STORAGE_PATH` | execution | str | `""` | Directory holding execution snapshots. Empty means 'derive it' — the default is `<project root>/snapshots`, so it follows the install location rather than being pinned to one path. |
| `AUTOBOT_SNAPSHOT_TTL_DAYS` | execution | int | `7` | Age at which the cleanup task removes an execution snapshot. Snapshots are a debugging aid, so the default is deliberately short. |
| `AUTOBOT_STRATEGY_HISTORY_MAX` | agents | int | `10` | Bounded per-key revision history the pattern learner keeps for a learned strategy, so a bad synthesized/imported one can be rolled back (GH#11534). Raising it keeps more prior revisions available to roll back to; lowering it keeps fewer, saving Redis space (agents/task_pattern_learner.py). |
| `AUTOBOT_STT_NO_SPEECH_PROB_THRESHOLD` | voice | float | `0.8` | Decoder no-speech probability at or above which an STT transcript is discarded as a silence hallucination (#13104). Range: 0.0–1.0. |
| `AUTOBOT_STT_PEAK_WINDOW_MS` | voice | int | `100` | Window in milliseconds over which speech energy is measured. Measuring across the whole buffer averages a short reply into silence (#13104). |
| `AUTOBOT_STT_SILENCE_RMS_THRESHOLD` | voice | float | `0.005` | Audio RMS below which the waveform is treated as silence, so any STT transcript over it is a hallucination rather than a user turn (#13104). Range: 0.0–1.0. |
| `AUTOBOT_SUMMARY_FAILURE_BACKOFF_SECONDS` | chat | int | `300` | Quiet period after a context-overflow summarisation failure before another is attempted, so a persistently failing summary does not retry on every turn. |
| `AUTOBOT_SYNC_POST_CMD_TIMEOUT_S` | backend | int | `300` | Seconds a code-sync post-sync command may run before it is abandoned. It covers a dependency install, so the ceiling depends on link speed and wheel availability rather than on anything fixed (services/sync_orchestrator.py, #14275). |
| `AUTOBOT_TEE_RETENTION_HOURS` | tools | int | `168` | Hours an oversized tool-output tee file is kept on disk before being pruned (#14142). Raising it keeps oversized captured output available longer for later inspection; lowering it prunes it sooner, saving disk (services/tool_output_filter.py). |
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
| `AUTOBOT_VENV_INSPECT_TIMEOUT` | slm | float | `60.0` | Timeout, in seconds, for inspecting an existing venv's installed packages during reconciliation. Raising it tolerates a slower inspection; lowering it fails a stuck inspection sooner (autobot-slm-backend/api/venv_reconcile.py). |
| `AUTOBOT_VERBATIM_RECENCY_HALFLIFE_SECONDS` | memory | float | `604800` | Half-life, in seconds, of the exponential recency decay applied when re-ranking verbatim recall results (GH#11163). Raising it makes recency matter over a longer window (older turns stay competitive longer); lowering it decays older turns faster, favoring very recent ones more strongly (memory/verbatim_store.py). |
| `AUTOBOT_VERBATIM_RECENCY_WEIGHT` | memory | float | `0.2` | Weight blending recency decay into verbatim recall's similarity ranking (GH#11163); 0.0 disables the blend (pure semantic order). Raising it favors recent turns more over equally-similar older ones; lowering it toward 0 reverts closer to pure semantic ranking (memory/verbatim_store.py). |
| `AUTOBOT_VOICE_TOOLSETS` | voice | str | `'voice_safe'` | Comma-separated toolset bundles a voice session may call. Defaults to the restricted `voice_safe` bundle — voice input is harder to confirm than typed input, so the surface is narrowed by default. |
| `AUTOBOT_WORKSPACE_CPU_QUOTA` | workspace | int | `100000` | CPU quota (Docker cpu-quota microseconds per 100ms period) applied to a task workspace container (GH#10544). Raising it allows a workspace container more CPU time per period; lowering it throttles it more tightly (services/docker_task_workspace.py). |
| `AUTOBOT_WORKSPACE_DISK_MB` | workspace | int | `2048` | Disk quota, in MB, applied to a task workspace's storage_opt size where the storage driver honours it (GH#10544, GH#11694). Raising it allows a workspace to use more disk; lowering it caps it more tightly (services/docker_task_workspace.py). |
| `AUTOBOT_WORKSPACE_IDLE_SECONDS` | workspace | int | `14400` | Idle-expiry window, in seconds, after which an unused task workspace container is torn down (GH#10544). Raising it keeps an idle workspace around longer for reuse; lowering it reclaims idle workspace resources sooner (services/docker_task_workspace.py). |
| `AUTOBOT_WORKSPACE_MAX_COUNT` | workspace | int | `20` | Maximum number of concurrent task workspace containers allowed (GH#10544). Raising it allows more concurrent workspaces at the cost of more host resource usage; lowering it caps concurrent workspace count more tightly (services/docker_task_workspace.py). |
| `AUTOBOT_WORKSPACE_PIDS_LIMIT` | workspace | int | `512` | PID-count limit (Linux pids cgroup) applied to a task workspace container, capping process count so a fork-bomb inside it cannot exhaust host PIDs (GH#11059). Raising it allows more processes inside a workspace; lowering it hardens against a fork-bomb more tightly, at the risk of limiting legitimate parallelism (services/docker_task_workspace.py). |

*204 variables registered as of last generation.*
<!-- END_AUTOGEN_ENV_DOCS -->
