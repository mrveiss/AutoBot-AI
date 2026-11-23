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
it is read, not implied. A prefix is resolved when it is a literal, a
module-level `NAME = ...` or annotated `NAME: T = ...` constant (string or
tuple/list/set), optionally starred or wrapped in `tuple(...)`; one built in a
function, imported or concatenated is not followed (an AST rule cannot
evaluate it), and is a second recorded limit.

## The regex shape (#21569)

A comment can also be stripped by a pattern. `_comment_regex_detect` reads `re.compile`, `re.sub`,
`re.subn`, `re.finditer`, `re.findall`, `re.match`, `re.search` and `re.split` calls whose first
argument is a string literal or a module string constant, and flags one that names a `//` line, a
`/\\*` block, a `<!--` HTML or a `^\\s*#` / `#.*` line comment. A URL scheme (`https://`), a
division and a CSS id selector (`#id`) are not comments and do not trip it. What it still cannot
see: a pattern built at run time (joined, formatted, passed in), a `from re import sub` alias, a
compiled pattern held on another object, a non-`re` engine (`regex`), a `//` with nothing
after it that consumes the comment (`(?m)^\\s*//`), and a marker inside a character class
(`[#;].*`). It does flag a `/\\*\\*` glob that is not anchored with `\\Z`. `<!--`:
`tools/lint/_comment_syntax.py` already has `strip_html_comments` and `strip_html_and_block_comments`,
so an HTML hit migrates to those rather than keeping its own pattern.
"""

from __future__ import annotations

import ast
import re

import pytest
from repo_tests._comment_regex_detect import strips_comments_by_regex
from repo_tests._comment_regex_pending import PENDING_REGEX_STRIPPERS
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

#: The regex-shaped strippers (#21569) are pending in `_comment_regex_pending`: 39 files measured when
#: the regex shape was added, on top of the 9 below. Same rule: shrink only.
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


_PENDING = _PENDING_PRIVATE_STRIPPERS | PENDING_REGEX_STRIPPERS


def _asserted_ids(tree: ast.AST) -> set[int]:
    """Node ids under an `assert`: a control ASSERTING a comment, not logic stripping one.

    `git_repo_root_calls_are_guarded` asserts exactly that about its own fixture. Flagging it is
    a false positive, and a guard with false positives gets muted, which costs more than the
    copy it would have caught.
    """
    asserted: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            asserted.update(id(child) for child in ast.walk(node))
    return asserted


def _module_constants(tree: ast.AST) -> dict[str, ast.expr]:
    """Module-level `NAME = <literal>` / `NAME: T = <literal>` constants (string, tuple, list, set)."""
    found: dict[str, ast.expr] = {}
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if isinstance(value, (ast.Constant, ast.Tuple, ast.List, ast.Set)):
            found.update({t.id: value for t in targets if isinstance(t, ast.Name)})
    return found


def _resolve_prefixes(arg: ast.expr, consts: dict[str, ast.expr]) -> ast.expr:
    """Unwrap `*P` and `tuple(P)`, then follow a module constant name to its literal."""
    if isinstance(arg, ast.Starred):
        arg = arg.value
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id == "tuple" and len(arg.args) == 1:
        arg = arg.args[0]
    return consts.get(arg.id, arg) if isinstance(arg, ast.Name) else arg


def _scopes(tree: ast.AST) -> list[ast.AST]:
    """The module plus every function: the units a name's assignments are judged within."""
    return [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _scope_nodes(scope: ast.AST):
    """Nodes of one scope, not descending into nested functions (they are scopes of their own)."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            stack.extend(ast.iter_child_nodes(node))


def _is_marker_check(
    node: ast.AST, consts: dict[str, ast.expr], path_vars: set[str], content_vars: set[str] = frozenset()
) -> bool:
    """True if `node` is a `.startswith(...)` call testing against a comment marker."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr != "startswith":
        return False
    for arg in node.args:
        resolved = _resolve_prefixes(arg, consts)
        if isinstance(resolved, ast.Constant) and resolved.value in _MARKERS:
            return True
        if isinstance(resolved, (ast.Tuple, ast.List, ast.Set)) and _tuple_has_marker(resolved):
            if not _is_url_or_path(node.func.value, path_vars, content_vars):
                return True
    return False


def _strips_comments_by_hand(tree: ast.AST) -> bool:
    """True if the module tests a string against a comment marker itself.

    Matches `x.startswith("#")` and its siblings on any receiver, including
    inside a comprehension or an `if`. Reads call nodes, so a docstring or a
    comment naming the idiom -- as this module's own do -- cannot satisfy it.
    """
    asserted = _asserted_ids(tree)
    consts = _module_constants(tree)
    if strips_comments_by_regex(tree, asserted, consts):
        return True
    for scope in _scopes(tree):
        good, bad, content_vars = _bindings(scope)
        path_vars = good - bad
        if any(
            id(n) not in asserted and _is_marker_check(n, consts, path_vars, content_vars) for n in _scope_nodes(scope)
        ):
            return True
    return False


#: Whole name tokens that make a receiver a URL or a path. Exact membership, plurals listed:
#: `pathology` and `linked` are not hints, and `during` is not `uri`.
_URL_PATH_HINTS = frozenset({"url", "urls", "href", "path", "paths", "uri", "link", "links", "route", "routes"})
#: A name carrying one of these tokens holds file CONTENT (`url_lines` is lines that mention a
#: URL), so a URL/path token beside it does not make it a path. Any content token defeats the
#: exemption: a false "flagged" costs one reviewed migration, a false "exempt" hides a stripper.
_CONTENT_TOKENS = frozenset({"line", "lines", "text", "content", "contents", "source", "src", "body"})
#: Methods whose result is file or line CONTENT; a receiver that passed through one is not the path.
_CONTENT_METHODS = frozenset(
    {"read_text", "read_bytes", "read", "readlines", "splitlines", "strip", "lstrip", "rstrip", "decode", "open"}
)
#: Constructors and attributes whose result is a URL or a path.
_URL_PATH_CALLS = frozenset({"Path", "PurePath", "PurePosixPath", "PureWindowsPath", "urlparse", "urlsplit"})
_URL_PATH_ATTRS = frozenset({"path", "url"})
#: Attributes that hold CONTENT (`resp.text`, `node.body`): a path-named root beneath one is not the value.
_CONTENT_ATTRS = frozenset({"text", "content", "body"})


def _name_is_url_or_path(name: str) -> bool:
    """True if a whole `_`/camelCase token of the name is a URL/path hint and none is content."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()
    tokens = set(spaced.split("_"))
    return bool(tokens & _URL_PATH_HINTS) and not tokens & _CONTENT_TOKENS


def _name_is_path(name: str, path_vars: set[str], content_vars: set[str]) -> bool:
    """A name proven path-valued here, or path-named and not bound to content in this scope."""
    return name in path_vars or (name not in content_vars and _name_is_url_or_path(name))


def _is_path_valued(value: ast.AST, path_vars: set[str] = frozenset(), content_vars: set[str] = frozenset()) -> bool:
    """True if the expression's own ROOT value is a URL or path, not something derived from content.

    Peels the chain from the outside in. Reaching a `Path(...)`/`urlparse(...)` call, a
    `.path`/`.url` attribute or a path-named/path-valued name proves it; passing through a content
    method (`read_text`, `splitlines`, `strip`...) first means the receiver is content.
    `Path(p).as_posix()` is not a content method, so it stays a path. A name bound in this
    function to provable content (`path = p.read_text()`) is content whatever it is called.
    """
    node = value
    while True:
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
            if name in _URL_PATH_CALLS:
                return True
            if not isinstance(fn, ast.Attribute) or name in _CONTENT_METHODS:
                return False
            node = fn.value
        elif isinstance(node, ast.Attribute):
            if node.attr in _CONTENT_ATTRS:
                return False
            if node.attr in _URL_PATH_ATTRS or _name_is_url_or_path(node.attr):
                return True
            node = node.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        else:
            return isinstance(node, ast.Name) and _name_is_path(node.id, path_vars, content_vars)


def _param_names(scope: ast.AST) -> set[str]:
    """Parameters of a function scope (and everything nested), or of the lambdas in a module scope."""
    roots = [scope] if _is_function(scope) else [n for n in _scope_nodes(scope) if isinstance(n, ast.Lambda)]
    return {a.arg for root in roots for a in ast.walk(root) if isinstance(a, ast.arg)}


def _is_content_valued(value: ast.AST) -> bool:
    """True if the expression provably passed through a content method or `.text`-style attribute."""
    node = value
    while isinstance(node, (ast.Call, ast.Attribute, ast.Subscript)):
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Attribute):
                return False
            if node.func.attr in _CONTENT_METHODS:
                return True
            node = node.func.value
        elif isinstance(node, ast.Attribute) and node.attr in _CONTENT_ATTRS:
            return True
        else:
            node = node.value
    return False


def _bindings(scope: ast.AST) -> tuple[set[str], set[str], set[str]]:
    """(provably path-valued, unproven, bound-to-content) names bound in ONE scope.

    A name that is also a for-target, part of a tuple unpacking, a walrus, an augmented
    assignment, a `with`/comprehension target or a parameter (lambda parameters included, at
    module scope too) has a binding that is not proven, so it is not path-valued.
    """
    good: set[str] = set()
    content: set[str] = set()
    bad: set[str] = _param_names(scope)
    simple: set[int] = set()
    for node in _scope_nodes(scope):
        targets = (
            node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        )
        value = getattr(node, "value", None)
        for t in targets:
            if isinstance(t, ast.Name) and value is not None:
                simple.add(id(t))
                (good if _is_path_valued(value) else bad).add(t.id)
                if _is_content_valued(value):
                    content.add(t.id)
    bad.update(
        n.id
        for n in _scope_nodes(scope)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and id(n) not in simple
    )
    return good, bad, content


def _is_function(scope: ast.AST) -> bool:
    return isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef))


def _is_url_or_path(receiver: ast.AST, path_vars: set[str], content_vars: set[str] = frozenset()) -> bool:
    """True if the startswith receiver's own root value is provably a URL or path."""
    return _is_path_valued(receiver, path_vars, content_vars)


def _tuple_has_marker(arg: ast.Tuple | ast.List | ast.Set) -> bool:
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
    added = sorted(found - _PENDING - _CANONICAL)

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
    stale = sorted(_PENDING - found)

    assert not stale, (
        f"{len(stale)} entr(y/ies) in `_PENDING_PRIVATE_STRIPPERS` or `_comment_regex_pending.py` no longer "
        "carry a private "
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
        ("pathology is not a path", 'if pathology.startswith(("//", "http")):\n    pass\n', True),
        ("url_lines is content, not a url", 'if url_lines.startswith(("//", "http")):\n    pass\n', True),
        ("linked_lines is content, not a link", 'if linked_lines.startswith(("//", "http")):\n    pass\n', True),
        ("plural urls is a url", 'if urls.startswith(("//", "http")):\n    pass\n', False),
        (
            "a read file stripped then tested",
            'if Path(f).read_text().lstrip().startswith(("//", "#")):\n    pass\n',
            True,
        ),
        ("a self.path read as content", 'if self.path.read_text().startswith(("#",)):\n    pass\n', True),
        ("a .path attribute receiver", 'if req.path.startswith(("/api", "//")):\n    pass\n', False),
        (
            "a name also bound as a for-target is unproven",
            'q = req.path\nfor q in lines:\n    if q.startswith(("//", "#")):\n        pass\n',
            True,
        ),
        (
            "a name path-valued in another function does not carry over",
            'def a():\n    q = req.path\ndef b(q):\n    return q.startswith(("//", "#"))\n',
            True,
        ),
        (
            "a module tuple constant of markers",
            'PREFIXES = ("#", "//")\nif line.startswith(PREFIXES):\n    pass\n',
            True,
        ),
        (
            "a module tuple constant on a url receiver",
            'PREFIXES = ("#", "//")\nif url.startswith(PREFIXES):\n    pass\n',
            False,
        ),
        ("a module string constant", 'COMMENT = "#"\nif line.startswith(COMMENT):\n    pass\n', True),
        ("an annotated module string constant", 'C: str = "//"\nif line.startswith(C):\n    pass\n', True),
        (
            "an annotated module tuple constant",
            'P: tuple[str, ...] = ("#",)\nif line.startswith(P):\n    pass\n',
            True,
        ),
        ("a starred module tuple", 'P = ("#", "//")\nif line.startswith(*P):\n    pass\n', True),
        ("a tuple() wrapped list", 'if line.startswith(tuple(["#", "//"])):\n    pass\n', True),
        ("a string constant on a url receiver", 'C = "//"\nif url.startswith((C, "x")):\n    pass\n', False),
        ("an annotated tuple on a url receiver", 'P: tuple = ("#",)\nif url.startswith(P):\n    pass\n', False),
        (
            "a path-named name bound to file content",
            'path = p.read_text()\nif path.startswith(("#", "//")):\n    pass\n',
            True,
        ),
        ("a path-named parameter stays a path", 'def f(path):\n    return path.startswith(("#", "//"))\n', False),
        ("a path under a .text attribute", 'if self.path.text.startswith(("#", "//")):\n    pass\n', True),
        ("a path under a .content attribute", 'if self.path.content.startswith(("#",)):\n    pass\n', True),
        ("a path under a .body attribute", 'if self.path.body.startswith(("#",)):\n    pass\n', True),
        (
            "a lambda parameter shadowing a path-valued name",
            'q = req.path\nf = lambda q: q.startswith(("//", "#"))\n',
            True,
        ),
        ("startswith on something else", 'if name.startswith("test_"):\n    pass\n', False),
        ("a comment naming the idiom", '# we used to call line.startswith("#") here\nx = 1\n', False),
        ("a docstring naming the idiom", '"""Avoid line.startswith(\\"#\\") -- use the helper."""\nx = 1\n', False),
        ("the marker as a plain string", 'MARKER = "#"\nx = 1\n', False),
        ("a regex stripping a line comment", 'import re\nx = re.sub(r"//[^\\n]*", "", s)\n', True),
        ("a regex stripping a block comment", 'import re\nx = re.sub(r"/\\*.*?\\*/", "", s)\n', True),
        ("a regex stripping an HTML comment", 'import re\nx = re.sub(r"<!--.*?-->", "", s)\n', True),
        ("a regex skipping a hash line", 'import re\nx = re.compile(r"^\\s*#")\n', True),
        ("a regex stripping a trailing hash comment", 'import re\nx = re.sub(r"#.*", "", s)\n', True),
        ("an escaped-slash line comment", 'import re\nx = re.sub(r"\\/\\/.*", "", s)\n', True),
        ("a pattern held in a module constant", 'import re\nP = r"^\\s*#"\nx = re.search(P, s)\n', True),
        ("a URL scheme is not a comment", 'import re\nx = re.match(r"https://example", s)\n', False),
        ("a division is not a comment", 'import re\nx = re.findall(r"(\\d+)/(\\d+)", s)\n', False),
        ("a CSS id selector is not a comment", 'import re\nx = re.split(r"#id", s)\n', False),
        ("a regex comment control under an assert", 'import re\nassert re.sub(r"//.*", "", s)\n', False),
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
