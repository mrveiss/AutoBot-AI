# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every `source .../lib/*.sh` under autobot-infrastructure/ must resolve, and fail
loudly when it does not (#14041, #14172).

56 scripts sourced `lib/ssot-config.sh` for years while that file did not exist
anywhere in the repository. Nobody noticed, because every one of them wrote the
source as::

    source "${SCRIPT_DIR}/lib/ssot-config.sh" 2>/dev/null || true

`|| true` turns a missing config bootstrap into a normal, expected condition.
The script continues, every ``${AUTOBOT_X:-literal}`` in it takes the literal
right-hand side, and the run reports success. A reviewer reading the diff sees
a config lookup; the machine only ever runs the hardcode. #14041 built the
library; this guard is the half that stops the class recurring.

Two independent failure modes, so two independent checks:

* **resolution** — a `source` naming a path that is not in the tree. This is
  what went wrong originally, and it is invisible to shellcheck, which does not
  follow a dynamic source path.
* **shape** — a `source` whose failure is discarded. This is what made the first
  failure survivable for so long. Resolution alone is not enough: it only sees
  *this* checkout at PR time, and cannot see a deploy that ships a partial tree,
  a `.gitignore` regression, or a rename downstream.

Reach floors are asserted throughout. An empty walk reports "no offenders" while
having checked nothing, which is the same shape of bug as the one under guard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_INFRA = _REPO_ROOT / "autobot-infrastructure"
_SKIP_PARTS = {".git", "node_modules", "__pycache__", ".worktrees", "venv", ".venv"}

# A `source` statement and the (possibly quoted) word that follows it.
_SOURCE = re.compile(r'(?<!\w)source\s+(?:"([^"\n]+)"|\'([^\'\n]+)\'|([^\s;&|"\'\n]+))')

# Variables a call site uses to reach its library, and what each resolves to.
# SCRIPT_DIR (and the SCRIPT_DIR_UTIL spelling one script uses) is always the
# sourcing script's own directory; the PROJECT_ROOT spellings are the repo root.
_SCRIPT_DIR_NAMES = ("SCRIPT_DIR", "SCRIPT_DIR_UTIL")
_ROOT_NAMES = ("_PROJECT_ROOT", "PROJECT_ROOT")


def _strip_comment(line: str) -> str:
    """Drop an unquoted trailing comment.

    Needed for correctness in both directions: `lib/ssot-config.sh` appears
    inside the library's own header comment and inside hooks/lib/_common.sh's
    usage note, and counting either as a call site would make this test fail on
    a path that is documentation.
    """
    out: list[str] = []
    quote: str | None = None
    for char in line:
        if quote:
            out.append(char)
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            out.append(char)
            continue
        if char == "#":
            break
        out.append(char)
    return "".join(out)


def _is_nested_shell_string(line: str, start: int) -> bool:
    """True when this `source` lives inside another shell command's string.

    `autobot-infrastructure/shared/tests/test_ssot_config_lib.sh` drives the
    real shapes through `bash -c "..."`, including a deliberately missing path.
    A fixture that quotes the pattern it exists to test must not trip the lint
    for that pattern, and the tell is structural rather than a filename
    allowlist: the inner `source` is either preceded by an unbalanced quote on
    the same line, or written with backslash-escaped quotes, neither of which
    occurs in a real source statement.
    """
    if '\\"' in line:
        return True
    before = line[:start]
    return before.count('"') % 2 == 1 or before.count("'") % 2 == 1


def _resolve(script: Path, raw: str) -> Path | None:
    """Filesystem path a source expression names, or None if not resolvable here."""
    expanded = raw
    for name in _SCRIPT_DIR_NAMES:
        expanded = expanded.replace("${%s}" % name, str(script.parent)).replace(
            "$%s" % name, str(script.parent)
        )
    for name in _ROOT_NAMES:
        expanded = expanded.replace("${%s}" % name, str(_REPO_ROOT)).replace(
            "$%s" % name, str(_REPO_ROOT)
        )
    if "$" in expanded:
        return None
    return Path(expanded)


class _Site:
    """One `source <lib>` occurrence, with everything the checks need."""

    def __init__(self, script: Path, lineno: int, raw: str, line: str, is_last: bool):
        self.script = script
        self.rel = str(script.relative_to(_REPO_ROOT))
        self.lineno = lineno
        self.raw = raw
        self.line = line
        self.is_last = is_last

    def __repr__(self) -> str:  # pragma: no cover - failure output only
        return f"{self.rel}:{self.lineno}"


def _collect() -> tuple[list[_Site], int]:
    """Every lib source site under autobot-infrastructure/, plus files walked."""
    sites: list[_Site] = []
    scanned = 0
    for script in sorted(_INFRA.rglob("*.sh")):
        # Relative parts, never the absolute path: this checkout may itself sit
        # under a directory named `.worktrees` or `venv`, which would otherwise
        # skip the entire tree and report clean.
        rel_parts = script.relative_to(_REPO_ROOT).parts
        if any(part in _SKIP_PARTS for part in rel_parts):
            continue
        scanned += 1
        try:
            text = script.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            code = _strip_comment(line)
            matches = [
                m
                for m in _SOURCE.finditer(code)
                if not _is_nested_shell_string(code, m.start())
            ]
            lib_matches = [
                m
                for m in matches
                if "/lib/" in (m.group(1) or m.group(2) or m.group(3) or "")
            ]
            for match in lib_matches:
                raw = match.group(1) or match.group(2) or match.group(3)
                sites.append(
                    _Site(script, lineno, raw, code, match is lib_matches[-1])
                )
    return sites, scanned


_SITES, _SCANNED = _collect()


def test_the_sweep_actually_reached_the_tree() -> None:
    """Discovery floor. An empty walk asserts nothing while reading as clean.

    Three independent floors, because a single one can be satisfied by a walk
    that is still broken: the file count catches a skip list eating the tree,
    the site count catches a regex that stopped matching, and the named script
    catches a walk that reaches files but not the ones this guard is about.
    """
    assert _SCANNED > 120, f"only walked {_SCANNED} shell scripts — the skip list is eating the tree"
    assert len(_SITES) >= 60, (
        f"only found {len(_SITES)} lib source sites — expected >= 60 "
        "(#14041 enumerated 56 scripts); the matcher has regressed"
    )
    rels = {site.rel for site in _SITES}
    # 55, not 56: #14371 retired
    # autobot-infrastructure/shared/scripts/detect-hardcoded-values.sh, a dormant
    # unwired fork whose rules moved into scripts/lib/hardcoded-value-rules.sh.
    # The floor is left AT the current count rather than lowered for headroom, so
    # it still catches a regressed matcher; a future legitimate retirement has to
    # come here and say so, which is the point.
    assert len({site.rel for site in _SITES}) >= 55, f"only {len(rels)} distinct scripts"
    assert (
        "autobot-infrastructure/shared/scripts/vm-management/status-all-vms.sh" in rels
    ), "the walk no longer reaches a known call site"


def test_no_lib_source_is_documentation_or_a_fixture() -> None:
    """The two exclusions above must exclude exactly what they claim.

    A comment-stripper or nested-string detector that over-matches would silently
    shrink this guard's reach, so both are asserted on the real files that
    motivated them rather than trusted.
    """
    excluded = {
        # the library's own header quotes the call-site shape it replaces
        "autobot-infrastructure/shared/scripts/lib/ssot-config.sh",
        # hooks/lib/_common.sh documents how to source itself
        "autobot-infrastructure/shared/scripts/hooks/lib/_common.sh",
        # the ssot-config suite drives the shapes through `bash -c`
        "autobot-infrastructure/shared/tests/test_ssot_config_lib.sh",
    }
    present = {site.rel for site in _SITES} & excluded
    assert not present, (
        "these files only mention a lib source in a comment or a nested shell "
        f"string, so treating them as call sites is a false positive: {sorted(present)}"
    )


def test_every_lib_source_resolves_to_a_real_file() -> None:
    """A `source` naming a path that is not in the tree (#14041).

    Alternatives in a `||` chain are grouped by line: a two-path site tries the
    same library at two depths because its callers sit at two depths, so the
    site is satisfied when *one* of them resolves.
    """
    by_line: dict[tuple[str, int], list[_Site]] = {}
    for site in _SITES:
        by_line.setdefault((site.rel, site.lineno), []).append(site)

    unresolvable: list[str] = []
    checked = 0
    for (rel, lineno), group in sorted(by_line.items()):
        targets = [_resolve(group[0].script, site.raw) for site in group]
        known = [t for t in targets if t is not None]
        if not known:
            continue  # path built from a variable this guard cannot resolve
        checked += 1
        if not any(t.is_file() for t in known):
            unresolvable.append(
                f"{rel}:{lineno} -> " + " | ".join(str(t) for t in known)
            )

    assert checked >= 55, (
        f"only resolved {checked} source sites — the expander has regressed and "
        "this test would pass having checked almost nothing"
    )
    assert not unresolvable, (
        "these scripts source a library that does not exist. Every "
        "${VAR:-literal} in them takes its hardcoded right-hand side "
        "instead (#14041):\n  " + "\n  ".join(unresolvable)
    )


def _shape_offenders() -> tuple[list[str], int]:
    """Sites whose failure is discarded, and the number of sites checked."""
    offenders: list[str] = []
    checked = 0
    for site in _SITES:
        if not site.is_last:
            # Not the final alternative in a `||` chain: this miss is expected,
            # so discarding its stderr is correct. Only the decisive attempt
            # has to be loud.
            continue
        checked += 1
        tail = site.line[site.line.rindex("source ") :]
        decisive = tail.split("||")[0]
        if "2>/dev/null" in decisive or "2> /dev/null" in decisive:
            offenders.append(f"{site.rel}:{site.lineno} discards stderr on the last attempt")
        elif re.search(r"\|\|\s*(true|:)\s*$", site.line):
            offenders.append(f"{site.rel}:{site.lineno} ends in `|| true`")
        elif not site.line.rstrip().endswith("|| {"):
            offenders.append(
                f"{site.rel}:{site.lineno} does not end in an explicit `|| {{` failure block"
            )
    return offenders, checked


def test_a_missing_lib_is_never_swallowed() -> None:
    """The `|| true` shape that made #14041 invisible may not come back (#14172)."""
    offenders, checked = _shape_offenders()
    assert checked >= 55, f"only checked {checked} sites — this would pass vacuously"
    assert not offenders, (
        "a lib bootstrap whose failure is discarded turns a deployment error "
        "into a wrong-value-at-runtime. The final attempt in the chain must keep "
        "its stderr and end in an explicit `|| {` block that exits non-zero "
        "(#14172):\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(
    "site", [s for s in _SITES if s.is_last], ids=lambda s: f"{s.rel}:{s.lineno}"
)
def test_each_failure_block_actually_exits(site: _Site) -> None:
    """`|| {` is only loud if the block inside it stops the script.

    Checked per site rather than in aggregate so a failure names the one script
    that regressed. A block that merely echoes and falls through is the same
    silent-degrade defect wearing a louder coat.
    """
    lines = site.script.read_text(encoding="utf-8").splitlines()
    block = lines[site.lineno : site.lineno + 6]
    body = "\n".join(block[: next((i for i, ln in enumerate(block) if ln.strip() == "}"), len(block))])
    assert re.search(r"\b(exit|return)\s+[1-9]", body), (
        f"{site.rel}:{site.lineno} announces the failure but does not stop — "
        f"the script continues on hardcoded fallbacks anyway (#14172). Block:\n{body}"
    )
