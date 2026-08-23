# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A deployment script's inline Python must import modules that exist (#14866).

`validate_access_control.sh` is the post-deployment validation the access-control
runbook tells operators to run. Every one of its nine inline imports named a
`backend.*` package that has never existed in this repo, and each block ran with
its output discarded — so the suite reported without validating anything. The
enforcement mode it was supposed to set was therefore never set, leaving
ownership checks off.

The guard added in #14841 covers `autobot-backend/` Python files. It cannot see
imports embedded in shell heredocs under `autobot-infrastructure/`, which is
exactly where this one hid.

Scope: resolves the **module**, not the imported name, and never imports
anything — importing would execute package `__init__` side effects, which a
static check has no business doing.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_DIR = _REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts"

# The roots a deployment script puts on PYTHONPATH before running inline Python.
_IMPORT_ROOTS = [_REPO_ROOT / "autobot-backend", _REPO_ROOT]

_IMPORT = re.compile(r"^\s*from\s+([a-zA-Z_][\w.]*)\s+import\s+", re.M)

# Inline imports that genuinely name nothing, each with the issue tracking it.
# Every entry is a live bug, not an accepted exception — the parametrized test
# below asserts each is STILL broken, so a fix that leaves its entry behind
# fails here rather than silently un-guarding that script.
_KNOWN_BROKEN = {
    ("check_ai_stack_health.sh", "src.prompt_manager"): "#14867",
    ("database/reindex_claude_md.sh", "src.knowledge_base"): "#14867",
    ("diagnose_startup_performance.sh", "backend"): "#14867",
    ("restore_kb_backup.sh", "backup.engine"): "#14867",
    ("setup/setup_tier2_research.sh", "src.agents.advanced_web_research"): "#14867",
    ("setup/verify_installation.sh", "src.config"): "#14867",
    ("setup/verify_installation.sh", "src.agents"): "#14867",
    ("test-service-auth-deployment.sh", "backend.utils.async_redis_manager"): "#14867",
    ("test_startup_coordinator.sh", "scripts.startup_coordinator"): "#14867",
}

# Third-party and stdlib names an inline block may legitimately import.
_EXTERNAL_PREFIXES = {
    "asyncio", "sys", "os", "json", "time", "datetime", "pathlib", "re",
    "redis", "requests", "httpx", "aiohttp", "yaml", "sqlalchemy", "fastapi",
    "pydantic", "prometheus_client", "click", "typing", "collections",
    "llama_index",
}


def _resolves(module: str) -> bool:
    for root in _IMPORT_ROOTS:
        base = root / Path(*module.split("."))
        if base.with_suffix(".py").exists() or (base / "__init__.py").exists():
            return True
    return False


def _shell_scripts() -> list[Path]:
    return sorted(p for p in _SCRIPT_DIR.rglob("*.sh"))


def _unresolvable() -> tuple[list[str], int, int]:
    """(offenders, scripts scanned, first-party imports seen)."""
    offenders: list[str] = []
    scanned = 0
    seen = 0
    for script in _shell_scripts():
        scanned += 1
        text = script.read_text(encoding="utf-8", errors="replace")
        for match in _IMPORT.finditer(text):
            module = match.group(1)
            top = module.split(".")[0]
            # Anything not known-external is checked. Deliberately NOT filtered
            # to packages that exist on disk: the original bug imported
            # `backend.services.*`, and there is no `backend` package — so a
            # "does this top-level package exist?" filter skips precisely the
            # typo it is looking for. Asked the other way round, a name that
            # resolves to nothing and is not a known third party IS the finding.
            if top in _EXTERNAL_PREFIXES:
                continue
            seen += 1
            if not _resolves(module):
                rel_to_scripts = str(script.relative_to(_SCRIPT_DIR))
                if (rel_to_scripts, module) in _KNOWN_BROKEN:
                    continue
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{script.relative_to(_REPO_ROOT)}:{line}  from {module} import ...")
    return offenders, scanned, seen


def test_the_sweep_actually_reached_the_scripts() -> None:
    """A discovery floor. An empty walk reports clean having asserted nothing."""
    offenders, scanned, seen = _unresolvable()

    assert _SCRIPT_DIR.is_dir(), f"{_SCRIPT_DIR} has moved — re-point this guard rather than scanning nothing"
    assert scanned > 10, f"only walked {scanned} shell scripts — the search path is wrong"
    assert seen > 0, (
        "no first-party import was found in any deployment script. Either the "
        "scripts stopped embedding Python, or the pattern no longer matches — "
        "both make every assertion below vacuous."
    )


def test_every_inline_first_party_import_resolves() -> None:
    offenders, _, _ = _unresolvable()

    assert not offenders, (
        "these deployment scripts import first-party modules that do not exist. "
        "Inline Python in a shell heredoc fails at run time, and these scripts "
        "routinely discard output — so the check reports without ever running "
        "(#14866):\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(
    "module",
    ["services.feature_flags", "security.session_ownership", "services.audit_logger", "autobot_shared.redis_client"],
)
def test_the_access_control_validator_can_reach_what_it_imports(module: str) -> None:
    """Pins the specific four #14866 was filed for, by name.

    The sweep above would catch a regression here anyway; naming them means a
    failure says *which* validation stopped working, not just that something did.
    """
    assert _resolves(module), f"{module} is unreachable from the roots validate_access_control.sh exports"


@pytest.mark.parametrize("entry,issue", sorted(_KNOWN_BROKEN.items()))
def test_each_exemption_is_still_broken(entry: tuple[str, str], issue: str) -> None:
    """An exemption that no longer applies exempts nothing, silently."""
    rel, module = entry
    script = _SCRIPT_DIR / rel

    assert script.is_file(), f"{rel} moved or was deleted — update or drop this exemption ({issue})"
    assert not _resolves(module), (
        f"{module} now resolves, so the exemption for {rel} ({issue}) is obsolete — "
        "remove it from _KNOWN_BROKEN so that script is guarded again"
    )


# --------------------------------------------------------------------------
# The call layer. Resolving the import is necessary and not sufficient: #14868
# fixed the imports and left `await get_redis_manager()` calling the SYNC client
# (`async_client` defaults to False) and then `.main()` on the result, which
# exists on neither client. CI stayed green because the guard above only checked
# that the module could be found. A failure that moves from import time to call
# time is the same defect one step later.
# --------------------------------------------------------------------------

_PY_BLOCK = re.compile(r'python3 -c "(.*?)"\s*(?:\|\||>|2>|$)', re.S)

# The canonical accessor is `get_redis_client(async_client=False, database="main")`,
# aliased to `get_redis_manager` in the scripts. Awaiting it without
# `async_client=True` yields a sync client and raises TypeError.
_ASYNC_REDIS_ACCESSORS = {"get_redis_manager", "get_redis_client"}


def _embedded_python(script: Path) -> list[str]:
    text = script.read_text(encoding="utf-8", errors="replace")
    return [m.group(1) for m in _PY_BLOCK.finditer(text)]


def _awaited_sync_redis_calls() -> tuple[list[str], int]:
    """Awaited accessor calls that would return a SYNC client. (offenders, blocks parsed)."""
    offenders: list[str] = []
    parsed = 0
    for script in _shell_scripts():
        for block in _embedded_python(script):
            try:
                tree = ast.parse(block)
            except SyntaxError:
                continue  # heredoc interpolation we cannot parse; not our concern
            parsed += 1
            for node in ast.walk(tree):
                if not isinstance(node, ast.Await) or not isinstance(node.value, ast.Call):
                    continue
                fn = node.value.func
                name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
                if name not in _ASYNC_REDIS_ACCESSORS:
                    continue
                kwargs = {k.arg: k.value for k in node.value.keywords}
                truthy = isinstance(kwargs.get("async_client"), ast.Constant) and kwargs["async_client"].value is True
                if not truthy:
                    offenders.append(
                        f"{script.relative_to(_REPO_ROOT)}: await {name}(...) without async_client=True"
                    )
    return offenders, parsed


def test_the_embedded_python_was_actually_parsed() -> None:
    """Discovery floor: an extractor that matches nothing asserts nothing."""
    _, parsed = _awaited_sync_redis_calls()

    assert parsed > 3, f"only parsed {parsed} embedded python blocks — the extractor is not matching"


def test_no_script_awaits_the_sync_redis_client() -> None:
    offenders, _ = _awaited_sync_redis_calls()

    assert not offenders, (
        "these await the canonical Redis accessor without async_client=True, which "
        "returns a SYNC client and raises TypeError at call time — an import-layer "
        "guard cannot see this (#14866):\n  " + "\n  ".join(offenders)
    )
