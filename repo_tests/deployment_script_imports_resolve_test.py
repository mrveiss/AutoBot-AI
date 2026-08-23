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

#14877 merged its own copy of this guard into this file rather than shipping a
second one (consolidate, never fork). It added three things:

* the importing script's **own directory** counts as an import root, because
  these scripts export ``${SCRIPT_DIR}`` on PYTHONPATH. Without it the guard
  reported a false positive on ``test_startup_coordinator.sh``, whose
  ``startup_coordinator.py`` is a sibling;
* ``test_no_inline_check_fabricates_its_own_result`` — #14867's second
  acceptance criterion. Resolving the import is half the job: #14868 fixed
  these imports and removed the stderr suppression, but left ``|| echo "{}"``
  in place, so a check that cannot run still reports a value indistinguishable
  from a clean result (#14880);
* seven of the nine ``_KNOWN_BROKEN`` entries below were retired, because
  #14877 fixed those imports.
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
    # Seven siblings were retired by #14877, which repaired those imports.
    # These two name a backup engine and an agent-orchestrator accessor that
    # were never built — zero hits repo-wide — so the fix is a logic change,
    # not an import rewrite.
    ("restore_kb_backup.sh", "backup.engine"): "#14875",
    ("setup/verify_installation.sh", "src.agents"): "#14875",
}

# Third-party and stdlib names an inline block may legitimately import.
_EXTERNAL_PREFIXES = {
    "asyncio", "sys", "os", "json", "time", "datetime", "pathlib", "re",
    "redis", "requests", "httpx", "aiohttp", "yaml", "sqlalchemy", "fastapi",
    "pydantic", "prometheus_client", "click", "typing", "collections",
    "llama_index",
}


def _resolves(module: str, script_dir: Path | None = None) -> bool:
    """Resolve against the roots these scripts actually export on PYTHONPATH.

    ``script_dir`` is the importing script's own directory. Several of these
    scripts export ``${SCRIPT_DIR}`` (see test_startup_coordinator.sh:15) and
    import a sibling module, so omitting it makes the guard report a false
    positive on a script that runs perfectly well (#14877).
    """
    roots = list(_IMPORT_ROOTS) + ([script_dir] if script_dir else [])
    for root in roots:
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
            if not _resolves(module, script.parent):
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

# Two real shapes, and the delimiter matters more than it looks. A naive
# `python3 -c "(.*?)"` stops at the first quote *inside* the Python (these blocks
# contain `database="main"`), and keying on what follows the closing quote —
# `2>`, `>`, `||` — silently broke the moment output suppression was removed from
# these very scripts, collapsing seven blocks into one unparseable blob that the
# SyntaxError branch then skipped. The guard went green while checking nothing.
#
# A multi-line block therefore closes on a quote that is alone at the start of a
# line, which is unambiguous regardless of what follows it.
_PY_BLOCK_MULTILINE = re.compile(r'python3 -c "\n(.*?)\n"', re.S)
# ...and a single-line block cannot contain a quote or a newline at all.
_PY_BLOCK_INLINE = re.compile(r'python3 -c "([^"\n]+)"')

# The canonical accessor is `get_redis_client(async_client=False, database="main")`,
# aliased to `get_redis_manager` in the scripts. Awaiting it without
# `async_client=True` yields a sync client and raises TypeError.
_ASYNC_REDIS_ACCESSORS = {"get_redis_manager", "get_redis_client"}


def _embedded_python(script: Path) -> list[str]:
    text = script.read_text(encoding="utf-8", errors="replace")
    blocks = [m.group(1) for m in _PY_BLOCK_MULTILINE.finditer(text)]
    blocks += [m.group(1) for m in _PY_BLOCK_INLINE.finditer(text)]
    return blocks


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


_ACCESS_CONTROL_SCRIPTS = [
    "deployment/validate_access_control.sh",
    "monitoring/access_control_monitor.sh",
]


@pytest.mark.parametrize("rel", _ACCESS_CONTROL_SCRIPTS)
def test_the_embedded_python_of_each_target_script_parses(rel: str) -> None:
    """Per-file floor, not a tree-wide sum.

    A total across every script hid the real state: the two files this guard
    exists for contributed **zero** parseable blocks while the total still
    cleared the threshold. A floor has to measure the thing that can go to zero,
    and here that is per script.
    """
    script = _SCRIPT_DIR / rel
    assert script.is_file(), f"{rel} moved — re-point this guard rather than checking nothing"

    blocks = _embedded_python(script)
    assert blocks, f"no embedded python extracted from {rel} — the extractor is not matching"

    parsed = 0
    for block in blocks:
        try:
            ast.parse(block)
        except SyntaxError:
            continue
        parsed += 1

    assert parsed >= 3, (
        f"only {parsed} of {len(blocks)} extracted blocks in {rel} parse as Python. "
        "Unparseable blocks are skipped, so a low count means the call-layer check "
        "below is inspecting almost nothing."
    )


def test_no_script_awaits_the_sync_redis_client() -> None:
    offenders, _ = _awaited_sync_redis_calls()

    assert not offenders, (
        "these await the canonical Redis accessor without async_client=True, which "
        "returns a SYNC client and raises TypeError at call time — an import-layer "
        "guard cannot see this (#14866):\n  " + "\n  ".join(offenders)
    )


# --------------------------------------------------------------------------
# The reporting layer (#14867, #14877). Resolving the import and letting the
# error reach stderr are both necessary and still not sufficient: what a caller
# downstream READS must also change when the check could not run. #14868 fixed
# these imports and removed the `2>/dev/null`, but left `|| echo "{}"`, so the
# monitor still answers a failed check with a value that reads as "no findings".
# That is the specific thing #14866 cost: `0|0|0` violations reported *because*
# the imports were broken.
# --------------------------------------------------------------------------

# A literal that impersonates a successful measurement. Deliberately not every
# `|| echo` — a fallback that says "unavailable" is fine; one that says "0" or
# "{}" is a fabricated clean result.
_SENTINEL = re.compile(r'^(?:[0-9|.]+|UNKNOWN|N/?A|\{\}|\[\]|""|null)$', re.IGNORECASE)
_FALLBACK_ECHO = re.compile(r'\|\|\s*(?:echo|printf)\s+(["\']?)([^"\'\n;]*)\1')

# Scripts still doing this, each with its tracking issue. Same self-guarding
# contract as _KNOWN_BROKEN: asserted STILL fabricating, so a fix forces the
# entry out rather than leaving the guard quietly narrower than it claims.
_KNOWN_FABRICATING = {"monitoring/access_control_monitor.sh": "#14880"}


def _fabricated_results() -> tuple[list[tuple[str, int, str]], int]:
    """(sites answering a failed python check with a sentinel, blocks seen).

    Reuses the two block regexes above rather than scanning a single line. The
    first draft of this function matched ``python3 -c`` to end-of-line, which
    finds nothing for a MULTI-LINE block — the ``|| echo "{}"`` sits after the
    closing quote, several lines down. It reported zero fabricated results on a
    file that has three, and only the positive control below caught it. That is
    the same shape as the delimiter trap documented for the call layer.
    """
    sites: list[tuple[str, int, str]] = []
    blocks = 0
    for script in _shell_scripts():
        text = script.read_text(encoding="utf-8", errors="replace")
        for pattern in (_PY_BLOCK_MULTILINE, _PY_BLOCK_INLINE):
            for match in pattern.finditer(text):
                blocks += 1
                newline = text.find("\n", match.end())
                tail = text[match.end() : newline if newline != -1 else len(text)]
                echo = _FALLBACK_ECHO.search(tail)
                if echo and _SENTINEL.match(echo.group(2).strip()):
                    sites.append(
                        (str(script.relative_to(_SCRIPT_DIR)),
                         text[: match.start()].count("\n") + 1,
                         echo.group(2).strip())
                    )
    return sites, blocks


def test_the_fabrication_sweep_reached_the_scripts() -> None:
    """Discovery floor — an extractor that stops matching reports clean."""
    sites, blocks = _fabricated_results()
    assert blocks >= 20, (
        f"only extracted {blocks} inline python blocks — the matcher has "
        "regressed and the check below would pass having read nothing"
    )
    assert sites, (
        "the sweep found no fabricated results at all, but _KNOWN_FABRICATING "
        "is not empty — the matcher has regressed"
    )


def test_no_inline_check_fabricates_its_own_result() -> None:
    """A check that could not run must not report a reassuring value (#14867)."""
    sites, _ = _fabricated_results()
    offenders = [
        f"{rel}:{line}  answers a failed python block with {value!r}"
        for rel, line, value in sites
        if rel not in _KNOWN_FABRICATING
    ]
    assert not offenders, (
        "a failed check must be distinguishable from a clean one by what it "
        "REPORTS, not only by what reaches stderr. Emit an explicit error and a "
        "non-zero exit status instead of a sentinel (#14867):\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("rel,issue", sorted(_KNOWN_FABRICATING.items()))
def test_each_fabrication_exemption_is_still_broken(rel: str, issue: str) -> None:
    """An obsolete exemption exempts nothing, and is this check's positive control."""
    assert (_SCRIPT_DIR / rel).is_file(), f"{rel} moved or was deleted — update this exemption ({issue})"
    sites, _ = _fabricated_results()
    assert any(r == rel for r, _, _ in sites), (
        f"{rel} no longer fabricates a result, so the exemption ({issue}) is "
        "obsolete — remove it from _KNOWN_FABRICATING so the script is guarded again"
    )
