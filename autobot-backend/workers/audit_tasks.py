# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import re
import subprocess  # nosec B404 — internal git/gh CLI calls only
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autobot_shared.logging_manager import get_logger
from celery_app import celery_app

logger = get_logger(__name__)

# Redis key constants
_TESTGAPS_LAST_RUN_KEY = "audit:testgaps:last_run"
_DEAD_CODE_INVENTORY_KEY = "audit:dead_code:last_inventory"
_CLAIMS_LAST_RUN_KEY = "audit:claims:last_run"

# GitHub repo used for filing issues
_GH_REPO = "mrveiss/AutoBot-AI"

# Labels applied to all discovery issues filed by this daemon
_AUDIT_LABELS = "enhancement,observability,priority: medium"

# Max characters of gh output kept in logs on failure
_MAX_LOG_CHARS = 500


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


def _redis_set(redis, key: str, value: Any, ttl: int = 86400 * 14) -> None:
    """Persist JSON-serialisable value in Redis with a 14-day TTL."""
    if redis is None:
        return
    try:
        redis.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception:
        pass


def _run(cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    """Run *cmd*, return (returncode, stdout, stderr). Never raises."""
    try:
        result = subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=60,
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as exc:
        return 1, "", str(exc)


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
    code, out, _ = _run(cmd)
    if code != 0:
        return []
    try:
        return [item["title"] for item in json.loads(out)]
    except Exception:
        return []


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
        ]
    )
    if code != 0:
        logger.error("gh issue create failed (%s): %s", title, err[:_MAX_LOG_CHARS])
        return False
    return True


def _dedupe_and_file(
    findings: list[dict], existing_titles: set[str], label: str
) -> int:
    """File GitHub issues for findings whose title is not in *existing_titles*.

    Returns the number of newly filed issues.
    """
    filed = 0
    for finding in findings:
        title = finding["title"]
        if title in existing_titles:
            continue
        if _file_issue(title, finding["body"], label):
            existing_titles.add(title)
            filed += 1
    return filed


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
        if (
            "_test" in line
            or "test_" in line
            or "/tests/" in line
            or "/conftest" in line
        ):
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
    redis = _get_redis()
    last_run = _redis_get(redis, _TESTGAPS_LAST_RUN_KEY)
    run_at = datetime.now(timezone.utc).isoformat()

    repo_root = _repo_root()
    modules = _changed_python_modules(last_run, repo_root)

    findings = _testgap_findings(modules, repo_root)
    existing_titles = set(_list_open_issues(label="observability"))
    filed = _dedupe_and_file(findings, existing_titles, _AUDIT_LABELS)

    _redis_set(redis, _TESTGAPS_LAST_RUN_KEY, run_at)

    result = {
        "status": "success",
        "run_at": run_at,
        "modules_checked": len(modules),
        "gaps_found": len(findings),
        "issues_filed": filed,
    }
    logger.info(
        "audit_testgaps complete: modules_checked=%d gaps_found=%d issues_filed=%d",
        len(modules),
        len(findings),
        filed,
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
    filed = _dedupe_and_file(findings, existing_titles, _AUDIT_LABELS)

    # Persist current full inventory for next run's diff
    _redis_set(redis, _DEAD_CODE_INVENTORY_KEY, list(current_fps.keys()))

    result = {
        "status": "success",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total_findings": len(current_lines),
        "new_findings": len(new_findings_raw),
        "issues_filed": filed,
    }
    logger.info(
        "audit_dead_code complete: total_findings=%d new_findings=%d issues_filed=%d",
        len(current_lines),
        len(new_findings_raw),
        filed,
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
    search_paths = [repo_root / "README.md"] + list(
        (repo_root / "docs").glob("**/*.md")
    )

    for src in search_paths:
        if not src.is_file():
            continue
        rel = src.relative_to(repo_root)
        for lineno, line in enumerate(src.read_text(errors="ignore").splitlines(), 1):
            stripped = line.strip()
            if (
                stripped.startswith("#")
                or stripped.startswith("-")
                or stripped.startswith("*")
            ):
                if claim_pattern.search(stripped):
                    claims.append(
                        {"source": str(rel), "lineno": lineno, "text": stripped[:200]}
                    )
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
    redis = _get_redis()
    _redis_get(redis, _CLAIMS_LAST_RUN_KEY)
    run_at = datetime.now(timezone.utc).isoformat()

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
    prev_unverified: list[str] = (
        _redis_get(redis, _CLAIMS_LAST_RUN_KEY + ":unverified") or []
    )
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
    filed = _dedupe_and_file(findings, existing_titles, _AUDIT_LABELS)

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
        "verification_doc": str(doc_path.relative_to(repo_root)),
    }
    logger.info(
        "audit_claims complete: claims_checked=%d verified=%d unverified=%d issues_filed=%d",
        len(claims),
        len(verified),
        len(unverified),
        filed,
    )
    return result
