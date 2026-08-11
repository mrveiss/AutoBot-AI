# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Background audit daemon tasks (GH#7356).

Three Celery Beat tasks that run on a fixed schedule and file GitHub issues
for newly discovered gaps, deduplicating against existing open issues via Redis.

Beat schedule (registered in celery_app.py):
    audit_testgaps  — every 6h   (audit:testgaps:last_run)
    audit_dead_code — daily      (audit:dead_code:last_inventory)
    audit_claims    — weekly     (audit:claims:last_run)

All tasks are idempotent: re-running with no new changes files zero issues.
Beat pidfile MUST NOT reside on tmpfs (/run/autobot/ is wiped on reboot).
"""

import json
import os
import re
import subprocess  # nosec B404  # internal git/gh CLI calls only
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp
from celery_app import celery_app

logger = get_logger(__name__)

# Redis key constants
_TESTGAPS_LAST_RUN_KEY = "audit:testgaps:last_run"
_DEAD_CODE_INVENTORY_KEY = "audit:dead_code:last_inventory"
_CLAIMS_LAST_RUN_KEY = "audit:claims:last_run"

# Dead-letter queue: findings that could not be filed (e.g. gh unauthenticated)
# are persisted here for retry on the next run instead of being discarded (#12319).
_DEFERRED_FINDINGS_KEY = "audit:deferred_findings"

# Upper bound on the dead-letter queue so it cannot grow without limit while
# filing is broken. Overflow is logged in full (never silently truncated); the
# oldest findings are shed first. Overridable via env for large backlogs.
try:
    _MAX_DEFERRED = max(1, int(os.getenv("AUTOBOT_AUDIT_MAX_DEFERRED", "10000")))
except ValueError:
    _MAX_DEFERRED = 10000

# GitHub repo used for filing issues
_GH_REPO = "mrveiss/AutoBot-AI"
# #13859: canonical name of the issue-filing token in the SYSTEM vault. The
# worker had no owned credential at all — see _resolve_filing_token.
_FILING_TOKEN_SECRET = "github_issue_filing_token"  # nosec B105  # a secret NAME, not a value

# Labels applied to all discovery issues filed by this daemon
_AUDIT_LABELS = "enhancement,observability,priority: medium"

# Max characters of gh output kept in logs on failure
_MAX_LOG_CHARS = 500

# Cap on the full-findings dump written when the dead-letter queue itself cannot
# be persisted (#13570). Generous: at that point the log IS the queue, and a
# truncated finding is still better than none — but an unbounded dump could
# itself take out the log.
_MAX_DEFERRED_LOG_CHARS = 100_000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_redis():
    """Return a synchronous Redis client on the analytics DB, or None."""
    try:
        from autobot_shared.redis_client import get_redis_client

        return get_redis_client(async_client=False, database="analytics")
    except Exception:
        return None


def _redis_get(redis, key: str) -> Any | None:
    """Return decoded JSON value from Redis or None on any error."""
    if redis is None:
        return None
    try:
        raw = redis.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _redis_set(redis, key: str, value: Any, ttl: int | None = 86400 * 14) -> bool:
    """Persist a JSON-serialisable value in Redis. Returns True when it landed.

    #13570: this used to swallow every failure and return None, so a caller had
    no way to tell a successful write from a no-op. The dead-letter queue then
    reported findings as "deferred ... instead of being filed or lost" while
    nothing had been stored — a reassuring message about preservation that did
    not happen, which is worse than an error.

    ``ttl=None`` stores the key without expiry.
    """
    if redis is None:
        return False
    try:
        redis.set(key, json.dumps(value, default=str), ex=ttl)
        return True
    except Exception as exc:  # noqa: BLE001 - a telemetry write must not kill the task
        logger.error("audit: Redis write to %s failed: %s", key, exc)
        return False


def _run(cmd: list[str], cwd: str | None = None, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Run *cmd*, return (returncode, stdout, stderr). Never raises."""
    try:
        result = subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
            timeout=60,
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as exc:
        return 1, "", str(exc)


def _resolve_filing_token() -> str | None:
    """Read the issue-filing token from the SYSTEM vault (#13859).

    The worker used to rely entirely on ambient `gh` CLI auth for whichever
    account Celery happened to run as. Nothing owned that credential, nothing
    rotated it, nothing audited its use, and the only place its absence showed
    up was a log line — which is exactly how it lapsed unnoticed in #13570.

    SYSTEM vault and `PrincipalKind.SERVICE`: this is a background task, not a
    user session, so there is no user vault it could belong to and the audit
    trail should attribute filings to the service rather than to whoever last
    logged into the host. `VaultKind.SYSTEM` is documented as the home for
    "admin-only system secrets (provider keys, internal tokens)".

    Returns None when no token is stored — the caller decides what that means,
    and says so loudly rather than silently continuing on ambient state.
    """
    try:
        return run_or_schedule(_read_filing_token())
    except Exception as exc:  # noqa: BLE001 — a vault outage must not kill the audit run
        logger.warning("audit: vault lookup for the filing token failed: %s", exc)
        return None


async def _read_filing_token() -> str | None:
    from sqlalchemy import select  # noqa: PLC0415

    from api.user_management.dependencies import get_async_session  # noqa: PLC0415
    from autobot_shared.secrets_vault import VaultKind, VaultRef  # noqa: PLC0415
    from models.secret import Secret  # noqa: PLC0415
    from services.envelope_secrets_service import (  # noqa: PLC0415
        EnvelopeSecretsService,
        SecretAccessError,
        SecretNotFoundError,
    )

    owner = VaultRef(kind=VaultKind.SYSTEM)
    owner_str = owner.to_str()
    async for session in get_async_session():
        result = await session.execute(
            select(Secret).where(Secret.name == _FILING_TOKEN_SECRET, Secret.owner_vault == owner_str)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        try:
            raw = await EnvelopeSecretsService().read(session, secret_id=row.id, accessible_vaults=[owner])
        except (SecretNotFoundError, SecretAccessError) as exc:
            logger.warning("audit: filing token present but unreadable: %s", exc)
            return None
        return raw.decode("utf-8").strip() or None
    return None


# (env, came_from_vault) — one fact, cached together. Deriving the second from
# the first is what made the detector lie (#13859 review).
_gh_env_cache: tuple[dict[str, str], bool] | None = None


def reset_gh_env_cache() -> None:
    """Drop the cached credential so the next run re-reads the vault (#13859).

    Called at the start of every audit task. Celery workers are long-lived, so
    without this a rotated or revoked token would keep working for the life of
    the process — which would defeat the revocation this issue is about.
    """
    global _gh_env_cache
    _gh_env_cache = None


def _gh_env() -> tuple[dict[str, str], bool]:
    """Subprocess environment for every `gh` call, and whether the vault
    supplied the token (#13859).

    Mirrors the LLC Copilot adapter: both GH_TOKEN and GITHUB_TOKEN, because
    different gh subcommands read different ones.

    Returns the flag rather than letting callers test `"GH_TOKEN" in env`. That
    test answers "does this process have a token anywhere?", which is a
    different question: the env starts as a copy of os.environ, and an ambient
    GH_TOKEN is exactly what the pre-#13859 CRITICAL log told operators to set
    — docker-compose injects an empty one unconditionally. Deriving the flag
    that way reported ambient state as vault-owned, suppressed the warning this
    change exists to emit, and told the operator the credential came from the
    vault while asking them to put one there.

    Cached per run: a task files one issue per finding, and a vault round-trip
    per finding would be pure waste.
    """
    global _gh_env_cache
    if _gh_env_cache is not None:
        env, from_vault = _gh_env_cache
        return dict(env), from_vault
    env = dict(os.environ)
    token = _resolve_filing_token()
    if token:
        env["GH_TOKEN"] = token
        env["GITHUB_TOKEN"] = token
    _gh_env_cache = (env, bool(token))
    return dict(env), bool(token)


def _repo_root() -> Path:
    """Resolve the AutoBot-AI repo root relative to this file."""
    return Path(__file__).resolve().parent.parent.parent


def _list_open_issues(label: str | None = None) -> list[str]:
    """Return titles of open GitHub issues (optionally filtered by label)."""
    cmd = [
        "gh",
        "issue",
        "list",
        "--repo",
        _GH_REPO,
        "--state",
        "open",
        "--json",
        "title",
        "--limit",
        "500",
    ]
    if label:
        cmd += ["--label", label]
    code, out, _ = _run(cmd, env=_gh_env()[0])
    if code != 0:
        return []
    try:
        return [item["title"] for item in json.loads(out)]
    except Exception:
        return []


def _gh_available() -> bool:
    """Return True if the gh CLI is authenticated and can file issues.

    Checked once per task run so a missing credential produces a single CRITICAL
    log instead of one ERROR per lost finding (#12319).

    #13570: reported unconditionally, not only when there are findings to lose.
    The credential lapsed for the service account and the first symptom was a
    run that happened to produce findings — every clean run in between looked
    identical to a healthy one, so there was no way to tell when filing broke or
    how much had been deferred since.
    """
    env, vault_backed = _gh_env()
    if not vault_backed:
        # #13859: ambient CLI auth is not an owned credential. Nothing rotates
        # it, nothing audits its use, and nothing can revoke it — which is how
        # it lapsed unnoticed in #13570. Say so on every run, even when the
        # ambient session happens to work, or the gap stays invisible until the
        # day it does not.
        logger.warning(
            "audit worker has no vault-owned filing credential: falling back to "
            "ambient `gh` CLI auth for whichever account this worker runs as. "
            "Store a token as '%s' in the system vault to get grant, audit and "
            "revocation. (#13859)",
            _FILING_TOKEN_SECRET,
        )
    code, out, err = _run(["gh", "auth", "status"], env=env)
    if code != 0:
        logger.critical(
            "audit worker cannot file issues: `gh auth status` failed (%s, "
            "credential source: %s). Every finding this run produces will be "
            "queued instead of filed. Fix: store a token as '%s' in the system "
            "vault, or authenticate gh for the service account. gh said: %s",
            _GH_REPO,
            "system vault" if vault_backed else "ambient CLI auth",
            _FILING_TOKEN_SECRET,
            # stdout as well as stderr: gh routes this message to stderr today,
            # but a build that changed that would gut the diagnostic silently.
            ((err or "").strip() or (out or "").strip())[:_MAX_LOG_CHARS] or "no output",
        )
    return code == 0


def _file_issue(title: str, body: str, labels: str = _AUDIT_LABELS) -> bool:
    """Create a GitHub issue. Returns True on success."""
    code, _, err = _run(
        [
            "gh",
            "issue",
            "create",
            "--repo",
            _GH_REPO,
            "--title",
            title,
            "--body",
            body,
            "--label",
            labels,
        ],
        env=_gh_env()[0],
    )
    if code != 0:
        logger.error("gh issue create failed (%s): %s", title, err[:_MAX_LOG_CHARS])
        return False
    return True


def _load_deferred(redis) -> tuple[list[dict], bool]:
    """Return (queued findings, read_was_observed) for the dead-letter queue.

    #13570 review: a failed GET and an empty queue were indistinguishable, and
    the caller then overwrote the key with whatever it had. A GET timing out
    while the SET succeeds — or a value that is not a list — therefore WIPED the
    queue, silently, and reported ``issues_deferred: 0`` as a success. Same
    defect class as the incident this issue is about: acting on an outcome that
    was never observed. Removing the TTL made it worse, because the key now
    holds more.

    ``read_was_observed`` is False when the queue could not be read; the caller
    must not persist over a queue it could not see.
    """
    if redis is None:
        return [], False
    queued = _redis_get(redis, _DEFERRED_FINDINGS_KEY)
    if queued is None:
        # Genuinely absent (never written) reads the same as unreachable, so a
        # missing key is checked explicitly before assuming the worst.
        try:
            if not redis.exists(_DEFERRED_FINDINGS_KEY):
                return [], True
        except Exception as exc:  # noqa: BLE001 - fall through to "unobserved"
            logger.error("audit: cannot determine whether %s exists: %s", _DEFERRED_FINDINGS_KEY, exc)
        return [], False
    if not isinstance(queued, list):
        logger.error(
            "audit: %s holds a %s, not a list — refusing to overwrite it",
            _DEFERRED_FINDINGS_KEY,
            type(queued).__name__,
        )
        return [], False
    return queued, True


def _persist_deferred(redis, deferred: list[dict]) -> int:
    """Persist unfileable findings for retry, deduped by title. Returns queue size.

    Enforces ``_MAX_DEFERRED`` by shedding the oldest findings first, logging the
    exact titles dropped and why — never a silent truncation (#12319).
    """
    by_title: dict[str, dict] = {}
    for finding in deferred:
        by_title[finding["title"]] = finding
    unique = list(by_title.values())

    if len(unique) > _MAX_DEFERRED:
        dropped = unique[: len(unique) - _MAX_DEFERRED]
        unique = unique[len(unique) - _MAX_DEFERRED :]
        logger.error(
            "audit dead-letter queue exceeded cap %d — shedding %d oldest finding(s) "
            "(set AUTOBOT_AUDIT_MAX_DEFERRED higher to retain them). Dropped titles: %s",
            _MAX_DEFERRED,
            len(dropped),
            [f["title"] for f in dropped],
        )

    # #13570: no TTL on the dead-letter queue. It carried the module's default
    # 14 days, so a filing credential that stayed broken for a fortnight — the
    # exact situation the queue exists for — silently expired everything in it.
    # Note this does NOT make the key durable: every deployment runs
    # maxmemory-policy allkeys-lru, which evicts untimed keys too. It removes a
    # guaranteed fortnightly loss, not the possibility of loss.
    if not _redis_set(redis, _DEFERRED_FINDINGS_KEY, unique, ttl=None):
        _log_unwritable_queue(unique, "Redis is unavailable or the write was rejected")
        return 0

    return len(unique)


def _log_unwritable_queue(findings: list[dict], why: str) -> None:
    """Dump findings that could not be queued, so the log is the queue (#13570).

    A bare count would leave nothing recoverable. Emits nothing when there is
    nothing to lose — an empty write is the normal drain path, and paging
    someone about zero lost findings is its own false alarm.
    """
    if not findings:
        return
    dump = json.dumps(findings, default=str)
    truncated = ""
    if len(dump) > _MAX_DEFERRED_LOG_CHARS:
        # Say so explicitly: a message promising "full findings" that silently
        # cuts off mid-JSON is the same lie this issue is about.
        truncated = f" [TRUNCATED at {_MAX_DEFERRED_LOG_CHARS} chars — not all of the {len(findings)} shown]"
        dump = dump[:_MAX_DEFERRED_LOG_CHARS]
    logger.critical(
        "audit: FAILED to persist %d deferred finding(s) to %s — they are NOT queued "
        "and will not be retried (%s). Findings follow so they are recoverable from "
        "this log%s: %s",
        len(findings),
        _DEFERRED_FINDINGS_KEY,
        why,
        truncated,
        dump,
    )


def _dedupe_and_file(
    findings: list[dict],
    existing_titles: set[str],
    label: str,
    redis=None,
) -> tuple[int, int]:
    """File GitHub issues for new findings; persist any that cannot be filed.

    Drains the dead-letter queue first (retrying previously deferred findings),
    then processes *findings*. A finding is *filed* when ``gh issue create``
    succeeds, *skipped* when its title already exists, and *deferred* to the
    Redis dead-letter queue when filing is impossible (unauthenticated gh) or
    fails. No finding is ever silently discarded (#12319).

    Returns ``(filed, deferred)`` where ``filed + deferred`` accounts for every
    non-duplicate finding drawn from both the queue and *findings*.
    """
    gh_ok = _gh_available()
    pending, queue_readable = _load_deferred(redis)

    filed = 0
    still_deferred: list[dict] = []

    def _attempt(title: str, body: str, lbl: str) -> None:
        nonlocal filed
        if title in existing_titles:
            return
        if gh_ok and _file_issue(title, body, lbl):
            existing_titles.add(title)
            filed += 1
        else:
            still_deferred.append({"title": title, "body": body, "label": lbl})

    for item in pending:
        _attempt(item["title"], item["body"], item.get("label", label))
    for finding in findings:
        _attempt(finding["title"], finding["body"], label)

    # #13570: persist FIRST, then report what actually happened. The old order
    # logged "deferred to the Redis dead-letter queue instead of being filed or
    # lost" before the write was attempted, so the reassuring message stood even
    # when the queue was empty — `LLEN audit:deferred_findings` was 0 on a host
    # whose logs claimed findings were preserved. A message about preservation
    # must be emitted only by the code path that observed it succeed.
    if queue_readable:
        deferred_count = _persist_deferred(redis, still_deferred)
    else:
        deferred_count = 0
        _log_unwritable_queue(still_deferred, "the existing queue could not be read")

    _report_deferral_outcome(gh_ok, still_deferred, deferred_count)
    return filed, deferred_count


def _report_deferral_outcome(gh_ok: bool, still_deferred: list[dict], deferred_count: int) -> None:
    """Say what actually happened to unfileable findings (#13570)."""
    if gh_ok or not still_deferred:
        return
    if deferred_count:
        logger.critical(
            "gh CLI unauthenticated — %d audit finding(s) queued to the Redis "
            "dead-letter queue (%s) instead of being filed or lost. Configure a "
            "GH_TOKEN for the worker to restore issue filing; queued findings "
            "are retried automatically once it is available.",
            deferred_count,
            _DEFERRED_FINDINGS_KEY,
        )
        return
    # The findings have already been dumped; this names the consequence so the
    # two failures are not read as one bad Redis blip.
    logger.critical(
        "gh CLI unauthenticated AND the dead-letter queue could not be written — "
        "%d audit finding(s) are LOST except for the dump above. Both the filing "
        "credential and Redis need attention.",
        len(still_deferred),
    )


# ---------------------------------------------------------------------------
# Task: audit_testgaps
# ---------------------------------------------------------------------------


def _changed_python_modules(since_iso: str | None, repo_root: Path) -> list[Path]:
    """Return Python source files (non-test) changed in Dev_new_gui since *since_iso*.

    Falls back to the last 6 hours when *since_iso* is None.
    """
    if since_iso:
        cmd = [
            "git",
            "log",
            "origin/Dev_new_gui",
            f"--since={since_iso}",
            "--name-only",
            "--pretty=format:",
            "--diff-filter=ACMR",
        ]
    else:
        cmd = [
            "git",
            "log",
            "origin/Dev_new_gui",
            "--since=6 hours ago",
            "--name-only",
            "--pretty=format:",
            "--diff-filter=ACMR",
        ]

    code, out, _ = _run(cmd, cwd=str(repo_root))
    if code != 0:
        return []

    paths = []
    for line in out.splitlines():
        line = line.strip()
        if not line or not line.endswith(".py"):
            continue
        if "_test" in line or "test_" in line or "/tests/" in line or "/conftest" in line:
            continue
        p = repo_root / line
        if p.is_file():
            paths.append(p)
    return list({p: None for p in paths}.keys())  # dedupe, preserve order


def _find_test_file(module: Path, repo_root: Path) -> Path | None:
    """Return the test file for *module* if it exists with ≥1 test function."""
    stem = module.stem
    parent = module.parent

    candidates = [
        parent / f"{stem}_test.py",
        parent / f"test_{stem}.py",
        parent / "tests" / f"{stem}_test.py",
        parent / "tests" / f"test_{stem}.py",
    ]
    for candidate in candidates:
        if candidate.is_file():
            content = candidate.read_text(errors="ignore")
            if re.search(r"^\s*def test_", content, re.MULTILINE):
                return candidate
    return None


def _testgap_findings(modules: list[Path], repo_root: Path) -> list[dict]:
    """Return one finding dict per module that lacks a test file with test functions."""
    findings = []
    for mod in modules:
        if _find_test_file(mod, repo_root) is None:
            rel = mod.relative_to(repo_root)
            title = f"discovery: test gap — {rel} has no test file"
            body = (
                f"## Test gap detected by audit_testgaps daemon\n\n"
                f"Module `{rel}` was recently changed in `Dev_new_gui` and has no "
                f"corresponding test file with test functions.\n\n"
                f"**Expected locations:**\n"
                f"- `{rel.parent}/{rel.stem}_test.py`\n"
                f"- `{rel.parent}/tests/{rel.stem}_test.py`\n\n"
                f"Filed by the `audit_testgaps` Celery Beat task (GH#7356)."
            )
            findings.append({"title": title, "body": body})
    return findings


@celery_app.task(bind=True, name="workers.audit_testgaps")
def audit_testgaps(self) -> dict:
    """Every-6h task: find Python modules changed since last run that lack tests."""
    # #13859: FIRST thing in the task. reset_gh_env_cache() used to live
    # inside _gh_available(), but every task calls _list_open_issues()
    # before that — so the run's first gh call carried the PREVIOUS run's
    # token. A revoked one there returns [], which empties existing_titles
    # and silently disables dedupe, re-filing every finding.
    reset_gh_env_cache()
    redis = _get_redis()
    last_run = _redis_get(redis, _TESTGAPS_LAST_RUN_KEY)
    run_at = utc_timestamp()

    repo_root = _repo_root()
    modules = _changed_python_modules(last_run, repo_root)

    findings = _testgap_findings(modules, repo_root)
    existing_titles = set(_list_open_issues(label="observability"))
    filed, deferred = _dedupe_and_file(findings, existing_titles, _AUDIT_LABELS, redis)

    _redis_set(redis, _TESTGAPS_LAST_RUN_KEY, run_at)

    result = {
        "status": "success",
        "run_at": run_at,
        "modules_checked": len(modules),
        "gaps_found": len(findings),
        "issues_filed": filed,
        "issues_deferred": deferred,
    }
    logger.info(
        "audit_testgaps complete: modules_checked=%d gaps_found=%d " "issues_filed=%d issues_deferred=%d",
        len(modules),
        len(findings),
        filed,
        deferred,
    )
    return result


# ---------------------------------------------------------------------------
# Task: audit_dead_code
# ---------------------------------------------------------------------------


def _run_vulture(repo_root: Path) -> list[str]:
    """Run vulture on the backend and return lines identifying dead code."""
    cmd = [
        sys.executable,
        "-m",
        "vulture",
        "autobot-backend",
        "--min-confidence",
        "80",
        "--exclude",
        "*/migrations/*,*/__pycache__/*,*/tests/*",
    ]
    code, out, err = _run(cmd, cwd=str(repo_root))
    if code not in (0, 1):  # vulture exits 1 when dead code found
        logger.warning("vulture exited %d: %s", code, err[:_MAX_LOG_CHARS])
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _dead_code_fingerprint(line: str) -> str:
    """Extract a stable key from a vulture output line for dedup comparison."""
    # lines look like: path/file.py:42: unused function 'foo' (80% confidence)
    m = re.match(r"^(.+?:\d+:.+?)(?:\s*\(\d+%.*\))?$", line)
    return m.group(1).strip() if m else line


@celery_app.task(bind=True, name="workers.audit_dead_code")
def audit_dead_code(self) -> dict:
    """Daily task: run vulture, file issues only for findings new since last run."""
    # #13859: FIRST thing in the task. reset_gh_env_cache() used to live
    # inside _gh_available(), but every task calls _list_open_issues()
    # before that — so the run's first gh call carried the PREVIOUS run's
    # token. A revoked one there returns [], which empties existing_titles
    # and silently disables dedupe, re-filing every finding.
    reset_gh_env_cache()
    redis = _get_redis()
    last_inventory: list[str] = _redis_get(redis, _DEAD_CODE_INVENTORY_KEY) or []
    last_set = set(last_inventory)

    repo_root = _repo_root()
    current_lines = _run_vulture(repo_root)
    current_fps = {_dead_code_fingerprint(ln): ln for ln in current_lines}

    new_findings_raw = [v for k, v in current_fps.items() if k not in last_set]

    findings = []
    for line in new_findings_raw[:50]:  # cap batch to avoid issue spam
        title = f"discovery: dead code — {line[:120]}"
        body = (
            f"## Dead code detected by audit_dead_code daemon\n\n"
            f"```\n{line}\n```\n\n"
            f"Vulture confidence ≥80%. Verify before removing — "
            f"this may be called via reflection or a plugin interface.\n\n"
            f"Filed by the `audit_dead_code` Celery Beat task (GH#7356)."
        )
        findings.append({"title": title, "body": body})

    existing_titles = set(_list_open_issues(label="observability"))
    filed, deferred = _dedupe_and_file(findings, existing_titles, _AUDIT_LABELS, redis)

    # Persist current full inventory for next run's diff
    _redis_set(redis, _DEAD_CODE_INVENTORY_KEY, list(current_fps.keys()))

    result = {
        "status": "success",
        "run_at": utc_timestamp(),
        "total_findings": len(current_lines),
        "new_findings": len(new_findings_raw),
        "issues_filed": filed,
        "issues_deferred": deferred,
    }
    logger.info(
        "audit_dead_code complete: total_findings=%d new_findings=%d " "issues_filed=%d issues_deferred=%d",
        len(current_lines),
        len(new_findings_raw),
        filed,
        deferred,
    )
    return result


# ---------------------------------------------------------------------------
# Task: audit_claims
# ---------------------------------------------------------------------------


def _extract_capability_claims(repo_root: Path) -> list[dict]:
    """Parse README.md and docs/ for documented capability claims.

    A claim is any markdown list item or heading that contains an HTTP method
    keyword, an endpoint path pattern, or the words 'endpoint', 'API', or
    'command'.  Returns list of dicts with keys: source, text.
    """
    claim_pattern = re.compile(
        r"(?:GET|POST|PUT|PATCH|DELETE|endpoint|API|command|\/[a-z][a-z0-9_/-]{2,})",
        re.IGNORECASE,
    )
    claims = []
    # Exclude the audit's own generated report so it does not re-audit its own
    # output — that self-reference inflated findings into five figures (#12319).
    self_report = (repo_root / "docs" / "verification.md").resolve()
    search_paths = [repo_root / "README.md"] + list((repo_root / "docs").glob("**/*.md"))

    for src in search_paths:
        if not src.is_file() or src.resolve() == self_report:
            continue
        rel = src.relative_to(repo_root)
        for lineno, line in enumerate(src.read_text(errors="ignore").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("-") or stripped.startswith("*"):
                if claim_pattern.search(stripped):
                    claims.append({"source": str(rel), "lineno": lineno, "text": stripped[:200]})
    return claims


def _verify_claim(claim: dict, repo_root: Path) -> bool:
    """Return True if a code path, test, or endpoint wiring the claim can be found."""
    text = claim["text"]
    # Extract a candidate symbol: path segment, function name, or keyword
    # e.g. "/api/git" → "git", "GET /api/llm" → "llm"
    token_match = re.search(r"/api/([a-z][a-z0-9_-]+)", text, re.IGNORECASE)
    if not token_match:
        # Try extracting any quoted identifier
        token_match = re.search(r"`([a-z][a-z0-9_]+)`", text, re.IGNORECASE)
    if not token_match:
        return True  # can't resolve — skip rather than false-positive

    token = token_match.group(1).replace("-", "_")
    # Search for the token in Python source files
    code, out, _ = _run(
        ["git", "grep", "-rl", "--", token, "autobot-backend/"],
        cwd=str(repo_root),
    )
    return code == 0 and bool(out.strip())


def _write_verification_doc(repo_root: Path, verified: list, unverified: list) -> Path:
    """Write docs/verification.md and return the path."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# AutoBot Capability Verification Report",
        "",
        f"Generated: {now} by `audit_claims` Celery Beat task (GH#7356).",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "|--------|-------|",
        f"| Verified | {len(verified)} |",
        f"| Unverified | {len(unverified)} |",
        "",
    ]
    if unverified:
        lines += ["## Unverified Claims", ""]
        for c in unverified:
            lines.append(f"- `{c['source']}:{c['lineno']}` — {c['text']}")
        lines.append("")
    if verified:
        lines += ["## Verified Claims", ""]
        for c in verified:
            lines.append(f"- `{c['source']}:{c['lineno']}` — {c['text']}")
        lines.append("")

    doc_path = repo_root / "docs" / "verification.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text("\n".join(lines))
    return doc_path


@celery_app.task(bind=True, name="workers.audit_claims")
def audit_claims(self) -> dict:
    """Weekly task: verify README/docs capability claims have wired implementations."""
    # #13859: FIRST thing in the task. reset_gh_env_cache() used to live
    # inside _gh_available(), but every task calls _list_open_issues()
    # before that — so the run's first gh call carried the PREVIOUS run's
    # token. A revoked one there returns [], which empties existing_titles
    # and silently disables dedupe, re-filing every finding.
    reset_gh_env_cache()
    redis = _get_redis()
    _redis_get(redis, _CLAIMS_LAST_RUN_KEY)
    run_at = utc_timestamp()

    repo_root = _repo_root()
    claims = _extract_capability_claims(repo_root)

    verified = []
    unverified = []
    for claim in claims:
        if _verify_claim(claim, repo_root):
            verified.append(claim)
        else:
            unverified.append(claim)

    doc_path = _write_verification_doc(repo_root, verified, unverified)

    # Load previous unverified set for dedup
    prev_unverified: list[str] = _redis_get(redis, _CLAIMS_LAST_RUN_KEY + ":unverified") or []
    prev_set = set(prev_unverified)

    findings = []
    for claim in unverified:
        key = f"{claim['source']}:{claim['lineno']}"
        if key in prev_set:
            continue
        title = f"discovery: undocumented claim — {claim['source']}:{claim['lineno']}"
        body = (
            f"## Unverified documentation claim detected by audit_claims daemon\n\n"
            f"**Source:** `{claim['source']}` line {claim['lineno']}\n\n"
            f"**Claim:** {claim['text']}\n\n"
            f"No wired endpoint, test, or code path was found for this claim. "
            f"Either implement the feature or update the documentation.\n\n"
            f"See `docs/verification.md` for the full report.\n\n"
            f"Filed by the `audit_claims` Celery Beat task (GH#7356)."
        )
        findings.append({"title": title, "body": body})

    existing_titles = set(_list_open_issues(label="observability"))
    filed, deferred = _dedupe_and_file(findings, existing_titles, _AUDIT_LABELS, redis)

    _redis_set(redis, _CLAIMS_LAST_RUN_KEY, run_at)
    _redis_set(
        redis,
        _CLAIMS_LAST_RUN_KEY + ":unverified",
        [f"{c['source']}:{c['lineno']}" for c in unverified],
    )

    result = {
        "status": "success",
        "run_at": run_at,
        "claims_checked": len(claims),
        "verified": len(verified),
        "unverified": len(unverified),
        "issues_filed": filed,
        "issues_deferred": deferred,
        "verification_doc": str(doc_path.relative_to(repo_root)),
    }
    logger.info(
        "audit_claims complete: claims_checked=%d verified=%d unverified=%d " "issues_filed=%d issues_deferred=%d",
        len(claims),
        len(verified),
        len(unverified),
        filed,
        deferred,
    )
    return result
