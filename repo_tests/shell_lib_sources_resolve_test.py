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

The walk finds shell scripts by shebang, not by suffix (#14891). It used to be
`rglob("*.sh")`, and every pre-commit hook under
`autobot-infrastructure/shared/scripts/hooks/` is **extensionless** — so 16 real
call sites sat outside a guard whose reach floors were all satisfied by the
`.sh` population alone. It reported healthy coverage over its own blind spot,
which is the defect under guard one level up.

Widening it needed a third category rather than a wider glob. A failure block
that ends in `exit 0` is normally the silent-degrade bug, but
`pre-commit-warn-untracked`'s documented contract is that it must never block a
commit, so `exit 0` is correct *there*. That is encoded as an asserted category —
the block has to carry the `lib-source-contract: non-blocking` marker, announce
the skip on stderr, and exit 0 explicitly — never as a filename allowlist, and
the category is bounded so it cannot become the escape hatch for everything.

Reach floors are asserted throughout. An empty walk reports "no offenders" while
having checked nothing, which is the same shape of bug as the one under guard.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_INFRA = _REPO_ROOT / "autobot-infrastructure"
_SKIP_PARTS = {".git", "node_modules", "__pycache__", ".worktrees", "venv", ".venv"}

# A `source` statement and the (possibly quoted) word that follows it.
_SOURCE = re.compile(r'(?<!\w)source\s+(?:"([^"\n]+)"|\'([^\'\n]+)\'|([^\s;&|"\'\n]+))')

# A shebang naming a shell. The hooks are extensionless, so suffix is not a
# usable tell; the file's own first line is (#14891).
_SHELL_SHEBANG = re.compile(rb"^#!.*\b(ba|da|k|z)?sh\b")

# Marker a call site puts INSIDE its failure block to declare that it refuses to
# report clean but deliberately does not block. Asserted together with the
# behaviour it claims, never trusted on its own.
_NON_BLOCKING_MARKER = "lib-source-contract: non-blocking"

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
        expanded = expanded.replace("${%s}" % name, str(script.parent)).replace("$%s" % name, str(script.parent))
    for name in _ROOT_NAMES:
        expanded = expanded.replace("${%s}" % name, str(_REPO_ROOT)).replace("$%s" % name, str(_REPO_ROOT))
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


def _is_shell_script(path: Path) -> bool:
    """A `.sh` file, or any file whose own shebang names a shell (#14891).

    Detection is by shebang rather than by a name list because every hook under
    `autobot-infrastructure/shared/scripts/hooks/` is extensionless. A name list
    would have to be maintained, and the failure mode of a stale one is silence.
    """
    if path.suffix == ".sh":
        return True
    try:
        with path.open("rb") as handle:
            return _SHELL_SHEBANG.match(handle.readline(256)) is not None
    except OSError:  # pragma: no cover - unreadable file
        return False


def _collect() -> tuple[list[_Site], set[Path]]:
    """Every lib source site under autobot-infrastructure/, plus the files walked.

    Returns the walked paths rather than a count so the reach check can name
    exactly which scripts the walk failed to see (#15079).
    """
    sites: list[_Site] = []
    walked: set[Path] = set()
    for script in sorted(_INFRA.rglob("*")):
        if not script.is_file():
            continue
        # Relative parts, never the absolute path: this checkout may itself sit
        # under a directory named `.worktrees` or `venv`, which would otherwise
        # skip the entire tree and report clean.
        rel_parts = script.relative_to(_REPO_ROOT).parts
        if any(part in _SKIP_PARTS for part in rel_parts):
            continue
        if not _is_shell_script(script):
            continue
        walked.add(script)
        try:
            text = script.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            code = _strip_comment(line)
            matches = [m for m in _SOURCE.finditer(code) if not _is_nested_shell_string(code, m.start())]
            lib_matches = [m for m in matches if "/lib/" in (m.group(1) or m.group(2) or m.group(3) or "")]
            for match in lib_matches:
                raw = match.group(1) or match.group(2) or match.group(3)
                sites.append(_Site(script, lineno, raw, code, match is lib_matches[-1]))
    return sites, walked


def _looks_like_shell(path: Path) -> bool:
    """Second opinion on "is this a shell script", for the reach check only.

    Deliberately not ``_is_shell_script``: see ``_tracked_shell_scripts``. Kept
    plainer than the walk's own detector — a literal ``#!`` prefix and a shell
    word — so the two can disagree, which is the entire point of comparing them.
    """
    if path.suffix == ".sh":
        return True
    try:
        with path.open("rb") as handle:
            head = handle.readline(256)
    except OSError:  # pragma: no cover - unreadable file
        return False
    return head.startswith(b"#!") and re.search(rb"\b(ba|da|k|z)?sh\b", head) is not None


def _tracked_shell_scripts() -> set[Path]:
    """Shell scripts under autobot-infrastructure/ that git knows about.

    Independent of the walk in BOTH dimensions that break, which is why it does
    not call ``_is_shell_script``. Sharing that classifier would make the
    comparison self-confirming: a shebang detector that stopped seeing
    extensionless hooks would shrink the walk and the expectation by the same
    files, and the check would stay green over its own blind spot — the exact
    defect #14891 fixed one level up. The second opinion below is deliberate
    duplication: git supplies the paths, and a plainer predicate classifies them.
    """
    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "--", "autobot-infrastructure"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=_REPO_ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {result.stderr.strip()}")
    found: set[Path] = set()
    for relative in result.stdout.split():
        if any(part in _SKIP_PARTS for part in Path(relative).parts):
            continue
        path = _REPO_ROOT / relative
        if path.is_file() and _looks_like_shell(path):
            found.add(path)
    return found


_SITES, _WALKED = _collect()
_SCANNED = len(_WALKED)


def test_the_sweep_actually_reached_the_tree() -> None:
    """Discovery floor. An empty walk asserts nothing while reading as clean.

    Three independent floors, because a single one can be satisfied by a walk
    that is still broken: the file count catches a skip list eating the tree,
    the site count catches a regex that stopped matching, and the named script
    catches a walk that reaches files but not the ones this guard is about.
    """
    # Derived from the tree, not a magic minimum (#15079). This was `>= 180`,
    # a number bumped by hand in #14909 and sitting at exactly the tree's size
    # with zero headroom — so the first legitimate retirement of a script took
    # it under the floor and turned a correct deletion into a red build. A floor
    # that has to be re-tuned after every deletion gets tuned to whatever the
    # tree holds, and stops being a guard.
    #
    # The exact comparison is strictly stronger than the count it replaces: it
    # still catches both failure modes the old message named, and it names the
    # scripts that went missing instead of a bare number. Extra files are not an
    # error — an untracked script exists in the walk and not in git.
    expected = _tracked_shell_scripts()
    assert expected, (
        "git listed no shell script under autobot-infrastructure/ — the enumeration "
        "is broken, and an empty expectation would make the reach check below vacuous"
    )
    missed = sorted(path.relative_to(_REPO_ROOT).as_posix() for path in expected - _WALKED)
    assert not missed, (
        f"the walk reached {_SCANNED} of {len(expected)} tracked shell scripts and missed "
        f"{len(missed)} — the skip list is eating the tree, or the shebang detector "
        f"stopped recognising extensionless scripts (#14891):\n  " + "\n  ".join(missed[:20])
    )
    assert len(_SITES) >= 78, (
        f"only found {len(_SITES)} lib source sites — expected >= 78 "
        "(#14041 enumerated 56 scripts; #14891 added 17 sites in 16 extensionless "
        "hooks); the matcher has regressed"
    )
    rels = {site.rel for site in _SITES}
    # 55, not 56: #14371 retired
    # autobot-infrastructure/shared/scripts/detect-hardcoded-values.sh, a dormant
    # unwired fork whose rules moved into scripts/lib/hardcoded-value-rules.sh.
    # The floor is left AT the current count rather than lowered for headroom, so
    # it still catches a regressed matcher; a future legitimate retirement has to
    # come here and say so, which is the point.
    assert len(rels) >= 71, f"only {len(rels)} distinct scripts"
    assert (
        "autobot-infrastructure/shared/scripts/vm-management/status-all-vms.sh" in rels
    ), "the walk no longer reaches a known call site"

    # The #14891 floor specifically: the `.sh` population alone satisfies every
    # count above, so a regression to `rglob("*.sh")` has to fail on something
    # that only an extensionless script can satisfy.
    extensionless = {rel for rel in rels if not Path(rel).suffix}
    assert len(extensionless) >= 16, (
        f"only {len(extensionless)} extensionless call sites — the walk has "
        "narrowed back to files with a suffix and the 16 hooks are outside it again"
    )
    assert (
        "autobot-infrastructure/shared/scripts/hooks/pre-commit-warn-untracked" in rels
    ), "the walk no longer reaches the extensionless hooks (#14891)"


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
            unresolvable.append(f"{rel}:{lineno} -> " + " | ".join(str(t) for t in known))

    assert checked >= 73, (
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
            offenders.append(f"{site.rel}:{site.lineno} does not end in an explicit `|| {{` failure block")
    return offenders, checked


def test_a_missing_lib_is_never_swallowed() -> None:
    """The `|| true` shape that made #14041 invisible may not come back (#14172)."""
    offenders, checked = _shape_offenders()
    assert checked >= 73, f"only checked {checked} sites — this would pass vacuously"
    assert not offenders, (
        "a lib bootstrap whose failure is discarded turns a deployment error "
        "into a wrong-value-at-runtime. The final attempt in the chain must keep "
        "its stderr and end in an explicit `|| {` block that exits non-zero "
        "(#14172):\n  " + "\n  ".join(offenders)
    )


def _failure_block(site: _Site) -> str:
    """Body of the `|| {` block that follows a decisive source, up to its `}`."""
    lines = site.script.read_text(encoding="utf-8").splitlines()
    block = lines[site.lineno : site.lineno + 6]
    end = next((i for i, ln in enumerate(block) if ln.strip() == "}"), len(block))
    return "\n".join(block[:end])


def _classify(site: _Site) -> str:
    """`blocks`, `non-blocking`, or `silent` — what this failure block does.

    `blocks` is the normal answer: the script stops. `non-blocking` is the third
    category #14891 needed — a hook whose documented contract forbids it from
    failing a commit still has to refuse to report clean, so it announces the
    skip on stderr and exits 0 on purpose. It is earned by three properties of
    the block itself, never by the filename: the marker, a message on stderr,
    and an explicit zero exit. `silent` is everything else, which is the
    #14172 defect.
    """
    body = _failure_block(site)
    if re.search(r"\b(exit|return)\s+[1-9]", body):
        return "blocks"
    announces = ">&2" in body and re.search(r"\b(echo|printf)\b", body) is not None
    deliberate = re.search(r"\b(exit|return)\s+0\b", body) is not None
    if _NON_BLOCKING_MARKER in body and announces and deliberate:
        return "non-blocking"
    return "silent"


@pytest.mark.parametrize("site", [s for s in _SITES if s.is_last], ids=lambda s: f"{s.rel}:{s.lineno}")
def test_each_failure_block_actually_stops_or_says_why_it_does_not(site: _Site) -> None:
    """`|| {` is only loud if the block inside it either stops or announces.

    Checked per site rather than in aggregate so a failure names the one script
    that regressed. A block that merely echoes and falls through is the same
    silent-degrade defect wearing a louder coat.
    """
    assert site.script.is_file(), f"{site.rel} vanished — this test has no subject"
    verdict = _classify(site)
    assert verdict != "silent", (
        f"{site.rel}:{site.lineno} announces the failure but does not stop — the "
        f"script continues on hardcoded fallbacks anyway (#14172). A hook whose "
        f"contract forbids blocking may exit 0 instead, but only by carrying "
        f"`{_NON_BLOCKING_MARKER}` in the block, writing the skip to stderr and "
        f"exiting 0 explicitly. Block:\n{_failure_block(site)}"
    )


def test_the_non_blocking_category_is_earned_and_bounded() -> None:
    """The third category must not become the escape hatch (#14891).

    Two independent guards on it. Behaviour: each member is re-checked here
    against the properties `_classify` used, so the marker alone can never buy
    an exemption. Population: the category is bounded above, because a sweep
    that reclassified the whole tree as "deliberately does not block" would
    otherwise turn the whole guard green while deleting it.
    """
    decisive = [s for s in _SITES if s.is_last]
    assert len(decisive) >= 73, f"only {len(decisive)} decisive sites — vacuous"

    non_blocking = [s for s in decisive if _classify(s) == "non-blocking"]
    assert non_blocking, (
        "no site is in the non-blocking category, so the classification branch "
        "that #14891 added is untested — pre-commit-warn-untracked should be here"
    )
    assert len(non_blocking) <= 2, (
        "the non-blocking category has grown beyond the hooks whose contract "
        f"actually forbids blocking: {[s.rel for s in non_blocking]}. Each entry "
        "is a lib bootstrap failure that does NOT stop the script — justify it "
        "here rather than adding another marker"
    )
    for site in non_blocking:
        body = _failure_block(site)
        assert ">&2" in body, f"{site!r} exits 0 without saying so on stderr"
        assert re.search(r"\b(echo|printf)\b", body), f"{site!r} announces nothing"
        assert re.search(
            r"\b(exit|return)\s+0\b", body
        ), f"{site!r} carries the marker but falls through instead of exiting 0"


def test_the_two_offenders_are_fixed() -> None:
    """#14891's two live offenders, pinned so the fix cannot quietly revert.

    Both sit in extensionless hooks, so before the walk widened neither was
    visible to any assertion above.
    """
    by_rel = {site.rel: site for site in _SITES if site.is_last}
    for rel, expected in (
        ("autobot-infrastructure/shared/scripts/hooks/post-commit-doc-sync", "blocks"),
        (
            "autobot-infrastructure/shared/scripts/hooks/pre-commit-warn-untracked",
            "non-blocking",
        ),
    ):
        assert rel in by_rel, f"{rel} is no longer reached by the walk (#14891)"
        assert _classify(by_rel[rel]) == expected, f"{rel} is {_classify(by_rel[rel])}, expected {expected}"
