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

#14880 finished the reporting layer and emptied ``_KNOWN_FABRICATING``. Two
things changed with it:

* the import pattern now matches plain ``import X`` as well as
  ``from X import ...``. ``access_control_monitor.sh``'s pre-flight used the
  other spelling — ``import backend.services.feature_flags`` — so it failed on
  every run and the dashboard below it was never reached, while this guard
  looked straight past it;
* with no script fabricating a result any more, "the sweep found offenders" can
  no longer stand in for "the detector works". The floor is now a positive
  control driven against synthetic samples of both block shapes, plus a negative
  control asserting that an honest ``unavailable`` fallback is NOT flagged.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_DIR = _REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts"

# The roots a deployment script puts on PYTHONPATH before running inline Python.
_IMPORT_ROOTS = [_REPO_ROOT / "autobot-backend", _REPO_ROOT]

# Both spellings. `from X import ...` was all the original guard matched, and
# access_control_monitor.sh's pre-flight used the other one —
# `import backend.services.feature_flags`, a package that has never existed. It
# failed on every run and the guard could not see it, because it was looking for
# the wrong keyword (#14880).
_IMPORT = re.compile(r"^\s*(?:from\s+([a-zA-Z_][\w.]*)\s+import\s+|import\s+([a-zA-Z_][\w.]*))", re.M)

# Inline imports that genuinely name nothing, each with the issue tracking it.
# Every entry is a live bug, not an accepted exception — the parametrized test
# below asserts each is STILL broken, so a fix that leaves its entry behind
# fails here rather than silently un-guarding that script.
#
# EMPTY. The seven siblings went with #14877; the last two went here: the KB
# restore script now drives ``knowledge._composed``, the engine that
# ``backup/scheduler.py`` and the maintenance UI already use, and
# ``verify_installation.sh`` now imports ``agents.agent_orchestration`` plus
# ``autobot_shared.ssot_config`` in place of a ``src.agents`` package that never
# existed (#14875).
#
# An empty allowlist costs this dict its parametrized positive control — see
# ``test_the_import_pattern_matches_both_spellings`` and
# ``test_the_resolver_still_reports_a_missing_module`` below, which drive the
# matcher and the resolver against synthetic samples instead.
_KNOWN_BROKEN: dict[tuple[str, str], str] = {}

# Third-party names an inline block may legitimately import. The stdlib half of
# this set used to be hand-listed, which was survivable while only
# `from X import ...` was matched; extending the pattern to plain `import X`
# immediately produced seven false positives (traceback, cProfile, pstats,
# argparse) whose only fault was being absent from a hand-maintained list. A
# guard that has to be taught each stdlib name will eventually be taught to
# ignore a first-party one, so the stdlib half is derived.
_THIRD_PARTY_PREFIXES = {
    "redis",
    "requests",
    "httpx",
    "aiohttp",
    "yaml",
    "sqlalchemy",
    "fastapi",
    "pydantic",
    "prometheus_client",
    "click",
    "llama_index",
    "bcrypt",
}
_EXTERNAL_PREFIXES = _THIRD_PARTY_PREFIXES | set(sys.stdlib_module_names)


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


def _imported_modules(script: Path) -> list[tuple[str, int, str]]:
    """(module, line, statement) for every import this script embeds.

    Two passes, deduplicated by module. The raw text catches a multi-line
    heredoc block, whose imports are lines in their own right. A SINGLE-LINE
    ``python3 -c "import x.y"`` is not: the statement sits mid-line behind the
    shell quoting, so a line-anchored pattern slides straight past it. That is
    precisely where ``access_control_monitor.sh``'s pre-flight hid — it imported
    a ``backend.*`` package that has never existed, failed on every run, and
    this guard could not see it (#14880).
    """
    text = script.read_text(encoding="utf-8", errors="replace")
    found: dict[str, tuple[int, str]] = {}

    def _record(module: str, line: int, statement: str) -> None:
        found.setdefault(module, (line, statement))

    for match in _IMPORT.finditer(text):
        _record(match.group(1) or match.group(2), text[: match.start()].count("\n") + 1, match.group(0).strip())

    for block in _embedded_python(script):
        idx = text.find(block)
        base = text[:idx].count("\n") + 1 if idx != -1 else 1
        for match in _IMPORT.finditer(block):
            module = match.group(1) or match.group(2)
            _record(module, base + block[: match.start()].count("\n"), match.group(0).strip())

    return [(module, line, statement) for module, (line, statement) in found.items()]


def _unresolvable() -> tuple[list[str], int, int]:
    """(offenders, scripts scanned, first-party imports seen)."""
    offenders: list[str] = []
    scanned = 0
    seen = 0
    for script in _shell_scripts():
        scanned += 1
        for module, line, statement in _imported_modules(script):
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
                offenders.append(f"{script.relative_to(_REPO_ROOT)}:{line}  {statement}")
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


@pytest.mark.parametrize(
    "statement,expected",
    [
        ("from services.feature_flags import get_feature_flags", "services.feature_flags"),
        ("import backend.services.feature_flags", "backend.services.feature_flags"),
        ("    import services.audit_logger", "services.audit_logger"),
    ],
)
def test_the_import_pattern_matches_both_spellings(statement: str, expected: str) -> None:
    """Positive control for the pattern itself.

    The plain-``import`` branch is new, and a branch that silently stops matching
    turns every assertion above into a pass over nothing — the sweep counts
    matches, so it cannot tell "no offenders" from "no matches".
    """
    match = _IMPORT.search(statement + "\n")
    assert match is not None, f"the import pattern no longer matches {statement!r}"
    assert (match.group(1) or match.group(2)) == expected


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


@pytest.mark.parametrize(
    "module",
    ["backend.services.feature_flags", "src.agents", "backup.engine", "autobot_absent_pkg_14875"],
)
def test_the_resolver_still_reports_a_missing_module(module: str) -> None:
    """Positive control for ``_resolves``, replacing the emptied ``_KNOWN_BROKEN``.

    While that dict held live defects, "these two are still unresolvable" proved
    the resolver worked. It is empty now, so a ``_resolves`` that started
    answering True for everything would make the sweep above report clean over
    a tree full of broken imports, and nothing here would say so.

    The first three are the real historical offenders — the ``backend.*``
    prefix that has never existed, the ``src.`` layout that is gone, and the
    backup engine that was never built.
    """
    assert not _resolves(module, _SCRIPT_DIR), (
        f"{module} now resolves — if a package by that name was genuinely added, "
        "update this control; if not, the resolver has regressed and the sweep "
        "above is reporting clean over real defects"
    )


@pytest.mark.parametrize("module", ["services.feature_flags", "autobot_shared.redis_client", "knowledge._composed"])
def test_the_resolver_still_finds_a_real_module(module: str) -> None:
    """Negative control: a resolver that answered False for everything would also
    satisfy the control above while flooding the sweep with false findings."""
    assert _resolves(module, _SCRIPT_DIR), f"{module} exists but the resolver no longer finds it"


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
                    offenders.append(f"{script.relative_to(_REPO_ROOT)}: await {name}(...) without async_client=True")
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


# A backtick or `$(...)` inside a DOUBLE-QUOTED `python3 -c "..."` argument is
# command substitution: bash runs the words between them and hands python
# whatever is left. `$VAR` is different — several scripts interpolate a value
# into the program deliberately (a password to hash, a hostname to resolve) — so
# only the two command-substitution forms are flagged.
_SHELL_SUBSTITUTION = ("`", "$(")


def _shell_active_in_text(text: str) -> list[tuple[int, str]]:
    """(line, form) for each python block in ``text`` the shell would rewrite."""
    found: list[tuple[int, str]] = []
    for pattern in (_PY_BLOCK_MULTILINE, _PY_BLOCK_INLINE):
        for match in pattern.finditer(text):
            for form in _SHELL_SUBSTITUTION:
                if form in match.group(1):
                    found.append((text[: match.start()].count("\n") + 1, form))
    return found


def _shell_active_python_blocks() -> list[tuple[str, int, str]]:
    """(script, line, form) across every deployment script."""
    offenders: list[tuple[str, int, str]] = []
    for script in _shell_scripts():
        text = script.read_text(encoding="utf-8", errors="replace")
        rel = str(script.relative_to(_SCRIPT_DIR))
        offenders.extend((rel, line, form) for line, form in _shell_active_in_text(text))
    return offenders


def test_no_inline_python_block_is_rewritten_by_the_shell() -> None:
    """#14880: found by RUNNING the monitor, not by reading it.

    #14877 added an explanatory comment to three of these blocks that quoted
    ``await`` and ``.main()`` in backticks. Inside a double-quoted argument that
    is command substitution, so bash tried to run them: ``await: command not
    found``, then a syntax error, and python received a mangled program. Two of
    the three sit in ``validate_access_control.sh`` — the post-deployment
    validation an operator is told to run — whose ownership-coverage and
    ownership-performance tests therefore could not pass for any reason at all.
    Under the old fallback that surfaced as a clean-looking ``0|0|0``.

    Every other check in this file reads these blocks as Python. Nothing read
    them as the shell strings they actually are.
    """
    offenders = _shell_active_python_blocks()

    assert not offenders, (
        "these inline python blocks contain shell command substitution, so bash "
        "rewrites the program before python ever sees it (#14880):\n  "
        + "\n  ".join(f"{rel}:{line}  contains {form!r}" for rel, line, form in offenders)
    )


@pytest.mark.parametrize("form", _SHELL_SUBSTITUTION)
def test_the_shell_substitution_detector_still_fires(form: str) -> None:
    """Positive control. The sweep above is clean, so it proves nothing alone."""
    sample = 'x=$(python3 -c "\nprint(1)  # ' + form + 'oops\n")\n'

    assert _count_blocks(sample) == 1, "the block extractor no longer matches this shape"
    assert _shell_active_in_text(sample), f"the detector no longer flags {form!r} inside a python block"


def test_a_deliberate_variable_interpolation_is_not_flagged() -> None:
    """Negative control, and the reason the rule stops at command substitution.

    Three scripts interpolate a shell value into the program on purpose — a
    password to hash, a hostname to resolve. A detector that flagged ``$VAR``
    would be switched off rather than fixed.
    """
    sample = "x=$(python3 -c \"import socket; print(socket.gethostbyname('$name'))\")\n"

    assert _count_blocks(sample) == 1
    assert not _shell_active_in_text(sample), "a plain $VAR interpolation is deliberate, not a defect"


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
#
# #14880 emptied it: access_control_monitor.sh was the last entry, and its three
# sentinels are gone. Empty is the goal state, which is why the discovery floor
# below no longer asserts that the sweep FOUND something — see
# test_the_fabrication_detector_still_fires.
_KNOWN_FABRICATING: dict[str, str] = {}


def _fabricated_in_text(text: str) -> list[tuple[int, str]]:
    """(line, sentinel) for each python block in ``text`` answered by a sentinel.

    Split out from the sweep so the detector can be driven directly by the
    positive control below. With no script fabricating any more, "the sweep
    found offenders" can no longer serve as proof the matcher still works — and
    a matcher that quietly stops matching reports every script clean.

    Reuses the two block regexes above rather than scanning a single line. The
    first draft matched ``python3 -c`` to end-of-line, which finds nothing for a
    MULTI-LINE block — the fallback sits after the closing quote, several lines
    down. It reported zero fabricated results on a file that had three, and only
    a positive control caught it.
    """
    found: list[tuple[int, str]] = []
    for pattern in (_PY_BLOCK_MULTILINE, _PY_BLOCK_INLINE):
        for match in pattern.finditer(text):
            newline = text.find("\n", match.end())
            tail = text[match.end() : newline if newline != -1 else len(text)]
            echo = _FALLBACK_ECHO.search(tail)
            if echo and _SENTINEL.match(echo.group(2).strip()):
                found.append((text[: match.start()].count("\n") + 1, echo.group(2).strip()))
    return found


def _count_blocks(text: str) -> int:
    return sum(len(pattern.findall(text)) for pattern in (_PY_BLOCK_MULTILINE, _PY_BLOCK_INLINE))


def _fabricated_results() -> tuple[list[tuple[str, int, str]], int]:
    """(sites answering a failed python check with a sentinel, blocks seen)."""
    sites: list[tuple[str, int, str]] = []
    blocks = 0
    for script in _shell_scripts():
        text = script.read_text(encoding="utf-8", errors="replace")
        blocks += _count_blocks(text)
        rel = str(script.relative_to(_SCRIPT_DIR))
        sites.extend((rel, line, value) for line, value in _fabricated_in_text(text))
    return sites, blocks


# Assembled from fragments so this file never contains the literal shape it
# bans — a fixture quoting a banned pattern trips the lint that reads it.
_SAMPLE_SENTINELS = ["{" + "}", "0|0" + "|0", "UNK" + "NOWN"]


@pytest.mark.parametrize("sentinel", _SAMPLE_SENTINELS)
def test_the_fabrication_detector_still_fires(sentinel: str) -> None:
    """Positive control, replacing 'the sweep found offenders'.

    That floor was only meaningful while a script was still fabricating. Now
    that none are, an extractor that stopped matching would sail through the
    check below having read nothing. This drives the detector against both block
    shapes directly, so it fails when the detector breaks rather than when the
    codebase regresses.
    """
    inline = 'value=$(python3 -c "import sys" || ' + f'echo "{sentinel}")\n'
    multiline = 'value=$(python3 -c "\nimport sys\nprint(sys.argv)\n" || ' + f'echo "{sentinel}")\n'

    for sample, shape in ((inline, "single-line"), (multiline, "multi-line")):
        assert _count_blocks(sample) == 1, f"the {shape} block extractor no longer matches its own shape"
        hits = _fabricated_in_text(sample)
        assert hits, f"the detector no longer flags {sentinel!r} on a {shape} block"
        assert hits[0][1] == sentinel


def test_a_legitimate_fallback_is_not_flagged() -> None:
    """Negative control: the rule is 'impersonates a measurement', not 'has a fallback'."""
    sample = 'value=$(python3 -c "import sys" || echo "unavailable")\n'
    assert _count_blocks(sample) == 1
    assert not _fabricated_in_text(sample), "a fallback that says 'unavailable' is the fix, not the bug"


def test_the_fabrication_sweep_reached_the_scripts() -> None:
    """Discovery floor — an extractor that stops matching reports clean."""
    _, blocks = _fabricated_results()
    assert blocks >= 20, (
        f"only extracted {blocks} inline python blocks — the matcher has "
        "regressed and the check below would pass having read nothing"
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
        "non-zero exit status instead of a sentinel (#14867):\n  " + "\n  ".join(offenders)
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
