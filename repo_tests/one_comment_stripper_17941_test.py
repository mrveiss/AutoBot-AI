# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No new hand-rolled comment stripper (#17941).

The defect class is "a guard keyed on text is satisfied by its own comment".
The *enabler* is that stripping comments was reimplemented in every guard that
needed it, so each new one rediscovered the hazard, re-solved it, or forgot --
and forgetting is silent, because the guard then passes.

#17941 listed seven copies. Scanning for the shape found **31 files**, so the
catalogue was not the population; the duplication was four times wider than the
issue that described it. This guard exists so the number only goes down.

## Why this is an AST guard and not a grep

A text scan for the stripping idiom matches **this file**, which necessarily
spells the idiom it forbids, and every allowlist entry below. That is the
#17941 defect reproducing itself inside its own fix. The detector reads the
syntax tree and looks at call nodes, so prose naming the pattern is data.

## What this is, and is not, as the #17941 meta-guard

The issue asks for a guard that fails when a guard greps a whole file for a
literal without the helper, "or, if that is not statically decidable, the
limitation recorded explicitly". The general form is NOT statically decidable:
`"flag" in text` is indistinguishable from a legitimate membership test, so
no AST rule can say which are source scans. What IS decidable, and what this
module enforces, is the *enabler*: a hand-rolled comment skip (a call testing
a string against a comment marker). A guard that never strips at all, and so
is satisfied by its own comment, is invisible here --
`test_a_plain_substring_search_is_the_recorded_blind_spot` pins that limit so
it is read, not implied.
"""

from __future__ import annotations

import ast
import re

import pytest
from repo_tests._paths import repo_root

from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()

#: Comment markers a hand-rolled stripper tests for.
_MARKERS = frozenset({"#", "//", "/*"})

#: Files that still carry their own comment skip, pending migration to
#: `tools.lint._comment_syntax`. **This list only ever shrinks.** An entry is
#: removed when that file adopts the shared helper; nothing may be added.
#:
#: NOT EVERY ENTRY IS THE SAME DEFECT, and migrating them alike would be an
#: error. Three shapes are mixed in here:
#:
#:   (a) SOURCE SCANNERS -- read a source file looking for a construct. These
#:       carry the #17941 hazard: the file's own comment about the construct
#:       satisfies the search. Migrate these.
#:
#:   (b) FORMAT PARSERS -- read a line-oriented config where a leading `#` is
#:       part of the format (`requirements.txt`, the CodeQL ceiling list, a
#:       distributions list). There is no prose to be fooled by; the concept
#:       is "parse a config line", not "ignore a comment". Forcing these onto
#:       a comment-syntax helper conflates two concepts, which is the error
#:       this module exists to stop, pointed the other way. They need their
#:       own shared parser, or they stay.
#:
#:   (d) DEPENDENCY-CONSTRAINED -- `check_ci_system_package_provisioning`
#:       runs in a CI job that installs linters and NOT the application's
#:       dependencies, and `ci_system_package_provisioning_test` enforces
#:       that with a stdlib-only import check plus a second test keeping its
#:       one exemption (`_scan_helpers`) dependency-free. Importing the shared
#:       helper there means relaxing both guards to buy a straight move that
#:       fixes no bug. The deliberate boundary wins; this entry stays.
#:
#:   (c) COMMENTS AS DATA -- `detect-hardcoded-values_test` extracts a comment
#:       HEADER; `comment_line_number_citations_test`'s whole subject is
#:       comment line numbers. Migrating these would delete their input.
#:
#: So an entry leaving this list must be argued, not batched. The count going
#: down is necessary but not sufficient.
#: The canonical implementation itself. It necessarily tests strings against
#: comment markers -- that is what it is for -- so it is exempt by identity,
#: not pending migration. Kept separate from the shrink list below on purpose:
#: an entry there is a debt that must eventually go, and this one must not.
#: `test_the_shared_helper_is_the_only_exemption` pins that this stays a set of
#: one, so "exempt" cannot quietly become a second place comment logic lives.
_CANONICAL = frozenset({"tools/lint/_comment_syntax.py"})

_PENDING_PRIVATE_STRIPPERS = frozenset(
    {
        # BLOCKED BY THE SIZE RATCHET, not by the concept (#17941). The file
        # sits at its recorded ceiling of 1424 exactly, and adopting the shared
        # helper costs two lines it cannot spend: the import, plus the blank
        # isort requires between import groups. A file pinned at its ceiling
        # cannot adopt a shared helper until it is split -- the dedup goal and
        # the size ratchet pull against each other here, and the ratchet wins
        # because it only ever turns down. Split the file, then migrate.
        "pipeline-scripts/ci_dispatch_watchdog.py",
        "pipeline-scripts/detect-hardcoded-values_test.py",
        "pipeline-scripts/detect_hardcoded_values_audit_test.py",
        "repo_tests/comment_line_number_citations_test.py",
        "repo_tests/declared_distributions.py",
        "repo_tests/mcp_verification_script_coverage_14219_test.py",
        "repo_tests/test_dockerignore_test_file_coverage_14127.py",
        "tools/lint/_scan_helpers.py",
        "tools/lint/check_git_write_env_scrubbed_test.py",
    }
)


def _strips_comments_by_hand(tree: ast.AST) -> bool:
    """True if the module tests a string against a comment marker itself.

    Matches `x.startswith("#")` and its siblings on any receiver, including
    inside a comprehension or an `if`. Reads call nodes, so a docstring or a
    comment naming the idiom -- as this module's own do -- cannot satisfy it.
    """
    # An `assert line.startswith("#")` is a control ASSERTING something is a
    # comment, not logic stripping one -- `git_repo_root_calls_are_guarded`
    # asserts exactly that about its own fixture. Flagging it is a false
    # positive, and a guard with false positives gets muted, which costs more
    # than the copy it would have caught.
    asserted: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            asserted.update(id(child) for child in ast.walk(node))

    path_vars = _path_valued_names(tree)
    for node in ast.walk(tree):
        if id(node) in asserted:
            continue
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "startswith":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and arg.value in _MARKERS:
                return True
            if (
                isinstance(arg, ast.Tuple)
                and _tuple_has_marker(arg)
                and not _is_url_or_path(node.func.value, path_vars)
            ):
                return True
    return False


#: Name tokens that make a receiver provably a URL or a path.
_URL_PATH_HINTS = ("url", "href", "path", "uri", "link", "route")
#: Constructors and attributes whose result is a URL or a path.
_URL_PATH_CALLS = frozenset({"Path", "PurePath", "PurePosixPath", "PureWindowsPath", "urlparse", "urlsplit"})
_URL_PATH_ATTRS = frozenset({"path", "url"})


def _name_is_url_or_path(name: str) -> bool:
    """True if a `_`/camelCase token of the name starts or ends with a URL/path hint.

    Token edges, not raw substrings: `during` contains `uri` and `pathology` is not a path.
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()
    return any(t.startswith(h) or t.endswith(h) for t in spaced.split("_") for h in _URL_PATH_HINTS)


def _is_path_valued(value: ast.AST) -> bool:
    """True if an assigned value comes from a Path/urlparse call or a `.path`/`.url` attribute."""
    if isinstance(value, ast.Attribute) and value.attr in _URL_PATH_ATTRS:
        return True
    for n in ast.walk(value):
        if isinstance(n, ast.Call):
            fn = n.func
            if (isinstance(fn, ast.Name) and fn.id in _URL_PATH_CALLS) or (
                isinstance(fn, ast.Attribute) and fn.attr in _URL_PATH_CALLS
            ):
                return True
    return False


def _path_valued_names(tree: ast.AST) -> set[str]:
    """Names assigned (anywhere in the module) from a provable URL or path value."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_path_valued(node.value):
            found.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and node.value is not None and _is_path_valued(node.value):
            if isinstance(node.target, ast.Name):
                found.add(node.target.id)
    return found


def _is_url_or_path(receiver: ast.AST, path_vars: set[str]) -> bool:
    """True if the startswith receiver is provably a URL or path; anything else is unproven."""
    if _is_path_valued(receiver):
        return True
    for n in ast.walk(receiver):
        if isinstance(n, ast.Name) and (n.id in path_vars or _name_is_url_or_path(n.id)):
            return True
        if isinstance(n, ast.Attribute) and (n.attr in _URL_PATH_ATTRS or _name_is_url_or_path(n.attr)):
            return True
    return False


def _tuple_has_marker(arg: ast.Tuple) -> bool:
    """A tuple of prefixes that includes a comment marker (`#`, `//`, `/*`...).

    The default is unsafe-to-ignore: sibling prefixes such as `http` or `/api` do not exempt
    the tuple, because a line filter `("//", "http")` carries them too. Only a receiver that is
    provably a URL or path is exempt, decided by `_is_url_or_path`.
    """
    return any(isinstance(e, ast.Constant) and e.value in _MARKERS for e in arg.elts)


def _files_with_private_strippers() -> set[str]:
    found: set[str] = set()
    candidates = tracked_paths(_ROOT, "repo_tests/*.py", "tools/lint/*.py", "pipeline-scripts/*.py")
    # Non-vacuity: an empty sweep satisfies every assertion below by looking at
    # nothing. MEASUREMENT_DISCIPLINE.md -- "nothing found" must not read like
    # "did not look".
    assert len(candidates) > 200, f"only {len(candidates)} files swept -- the patterns or the root are wrong"
    for rel in candidates:
        path = _ROOT / rel
        try:
            tree = parse_cache.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        if _strips_comments_by_hand(tree):
            found.add(rel)
    return found


def test_no_new_file_strips_comments_by_hand() -> None:
    """The ratchet. A new private copy fails here; a migrated one must be delisted."""
    found = _files_with_private_strippers()
    added = sorted(found - _PENDING_PRIVATE_STRIPPERS - _CANONICAL)

    assert not added, (
        f"{len(added)} file(s) test a string against a comment marker directly instead of using "
        f"`tools.lint._comment_syntax`:\n  " + "\n  ".join(added) + "\n\n"
        "#17941: seven copies were catalogued and thirty-one existed. Each one re-derives "
        "quote handling, or skips it -- and a stripper that misses a `#` inside a string "
        "reintroduces the class one level down. Use the shared helper."
    )


def test_the_pending_list_only_shrinks() -> None:
    """Direction, not agreement (#17970).

    A mirrored pair of hand-kept records detects transcription errors and not
    movement. This compares the record against the LIVE tree, so an entry that
    has been migrated must be deleted here or the guard fails -- which is what
    makes the list a ratchet rather than a note.
    """
    found = _files_with_private_strippers()
    stale = sorted(_PENDING_PRIVATE_STRIPPERS - found)

    assert not stale, (
        f"{len(stale)} entr(y/ies) in `_PENDING_PRIVATE_STRIPPERS` no longer carry a private "
        f"stripper:\n  " + "\n  ".join(stale) + "\n\nDelete them. The list is a ratchet; leaving a "
        "migrated file listed lets a future one be re-added under cover of an entry that is "
        "already spent."
    )


@pytest.mark.parametrize(
    "label,source,expected",
    [
        ("a hash startswith", 'if line.startswith("#"):\n    pass\n', True),
        ("a slash-slash startswith", 'if line.startswith("//"):\n    pass\n', True),
        ("a tuple of markers", 'if line.startswith(("#", "//")):\n    pass\n', True),
        ("a URL or path-prefix check", 'if url.startswith(("/api", "http", "//")):\n    pass\n', False),
        ("a tuple of comment markers beside a URL prefix", 'if p.startswith(("http", "#")):\n    pass\n', True),
        (
            "a line filter with an api sibling",
            'k = [l for l in lines if not l.lstrip().startswith(("//", "/api"))]\n',
            True,
        ),
        (
            "a line filter with an http sibling",
            'k = [l for l in text.splitlines() if not l.startswith(("//", "http"))]\n',
            True,
        ),
        (
            "the phase-validation path check",
            'ok = joined_path and not joined_path.startswith(("/api", "http", "//"))\n',
            False,
        ),
        (
            "a line variable bound through an alias",
            'ls = text.splitlines()\nfor s in ls:\n    if s.startswith(("//", "http")):\n        pass\n',
            True,
        ),
        (
            "a loop over a split of data",
            'for s in data.split("\\n"):\n    if s.startswith(("//", "/api")):\n        pass\n',
            True,
        ),
        ("a url receiver", 'if url.startswith(("//", "http")):\n    pass\n', False),
        ("a Path chain receiver", 'if Path(p).as_posix().startswith(("//",)):\n    pass\n', False),
        (
            "a receiver assigned from urlparse",
            'u = urlparse(x)\nif u.netloc.startswith(("//", "#")):\n    pass\n',
            False,
        ),
        (
            "a receiver assigned from a .path attribute",
            'q = req.path\nif q.startswith(("//", "#")):\n    pass\n',
            False,
        ),
        ("a context name is not a url", 'if context.startswith(("//", "http")):\n    pass\n', True),
        ("a name merely containing uri is not a url", 'if during.startswith(("//", "http")):\n    pass\n', True),
        ("the href link filter", 'if not href or href.startswith(("#", "javascript:", "mailto:")):\n    pass\n', False),
        ("a block-doc marker beside slash-slash", 'if p.startswith(("//", "/**")):\n    pass\n', True),
        ("a triple slash beside slash-slash", 'if p.startswith(("//", "///")):\n    pass\n', True),
        ("a bare slash-slash skip stays a stripper", 'if p.startswith("//"):\n    pass\n', True),
        ("startswith on something else", 'if name.startswith("test_"):\n    pass\n', False),
        ("a comment naming the idiom", '# we used to call line.startswith("#") here\nx = 1\n', False),
        ("a docstring naming the idiom", '"""Avoid line.startswith(\\"#\\") -- use the helper."""\nx = 1\n', False),
        ("the marker as a plain string", 'MARKER = "#"\nx = 1\n', False),
    ],
)
def test_the_detector_reads_code_and_not_prose(label: str, source: str, expected: bool) -> None:
    """The contrast set, including the two cases this very file contains.

    The prose rows are not hypothetical: the module docstring above and the
    comments inside `_PENDING_PRIVATE_STRIPPERS` both spell the idiom. A
    text-keyed version of this guard would flag itself and then be muted.
    """
    assert _strips_comments_by_hand(parse_cache.parse(source)) is expected, label


def test_the_shared_helper_is_the_only_exemption() -> None:
    """Exempt-by-identity must stay a set of one.

    The failure mode this forecloses: a second module gets added here because
    it "also legitimately handles comments", and then there are two canonical
    homes, which is the duplication this whole change removed.
    """
    assert _CANONICAL == {"tools/lint/_comment_syntax.py"}, (
        f"the canonical exemption grew to {sorted(_CANONICAL)}. If a second module genuinely "
        "needs to own comment logic, that is a decision to record on #17941, not an entry to add."
    )
    assert (_ROOT / "tools/lint/_comment_syntax.py").exists(), (
        "the canonical module is exempted but does not exist -- the exemption would silently "
        "cover nothing while the guard reported clean"
    )


def test_a_plain_substring_search_is_the_recorded_blind_spot() -> None:
    """The limit named in the module docstring, pinned (#17941).

    A guard that searches a whole file with `in` and never strips is the
    original defect, and no call-node rule can tell it from a membership test.
    If this ever flips to True the docstring's claim is stale.
    """
    assert _strips_comments_by_hand(parse_cache.parse('assert "flag" in source_text\n')) is False
    stripped = "kept = [x for x in lines if not x.startswith('#')]\n"
    assert _strips_comments_by_hand(parse_cache.parse(stripped)) is True
