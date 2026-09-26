# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`dpkg -l` answers whether dpkg KNOWS a package, not whether it is installed (#17387).

A package removed without `--purge` stays in dpkg's database in `rc` state
(`deinstall ok config-files`), and `dpkg -l <pkg>` still exits 0 for it. Measured,
not assumed -- on the host where this was written:

    $ dpkg-query -W --showformat='${Status}' musl:amd64
    deinstall ok config-files          # and `dpkg -l musl:amd64` exits 0

So `rc` collapses three states into two and groups the wrong two. Fleet
provisioning died on it: `roles/postgresql/tasks/install.yml` skipped the install
on a node whose PostgreSQL was removed-not-purged, so the `postgres` system user
was never created and `pg_createcluster` -- `become_user: postgres` -- failed with
`sudo: unknown user postgres`. Late, and naming the wrong thing: the message
points at a missing user, and the missing user is a symptom of a skipped install.

Self-perpetuating, which is why it is a guard and not a one-line fix: the run
fails before anything installs PostgreSQL, so the next run finds the same `rc`
package and skips the install again. Re-provisioning cannot clear it.

**It was a pattern, not a typo, and the pattern was documented.** Four roles
carried the same detection and the same comment asserting the false premise --
"dpkg exits rc=1 when package is not installed" (#2872). The wrong belief was
written down once and copied three times, so a fix to one site would have left
three, each with a comment explaining why it was correct.

Two things this guard deliberately does NOT flag, both verified rather than
assumed, because a guard that cries wolf gets its exemptions widened until it
means nothing:

* **`install.sh`'s purge loop.** It gates `apt-get purge` on `dpkg -l`, and there
  "does dpkg know this package" is exactly the right question -- purging a
  removed-but-not-purged package is the entire point. Fixing it would be the
  regression.
* **`which ufw` registered as `ufw_installed`.** Five `*_installed.rc` gates read
  like this defect and are not: `which` exits non-zero when the binary is absent,
  and an `rc`-state package leaves no binary. So the rule below keys on the
  COMMAND, never on the variable's name.

Mutation check: revert `roles/postgresql/tasks/install.yml`'s detection to
`dpkg -l postgresql-{{ postgresql_version }}` and `test_no_dpkg_registration_is_gated_on_rc`
goes red naming that file and task.
"""

from __future__ import annotations

import ast
import functools
import pathlib
import re
from typing import Iterator, List, Sequence, Tuple

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_SCANNED_SUFFIXES = (".yml", ".yaml", ".sh", ".py")
_DPKG_LIST = re.compile(r"\bdpkg\s+-l\b")
#: A dpkg *listing query*, not any mention of dpkg. `fuser /var/lib/dpkg/lock`
#: is a lock check whose `.rc` gate is correct, and matching on the substring
#: "dpkg" called it a defect -- the path contains the word.
_DPKG_QUERY = re.compile(r"\bdpkg\s+-l\b|\bdpkg-query\b")
_INSTALLED_ANCHOR = re.compile(r"\^ii")
_RC_GATE = re.compile(r"\.rc\s*(?:!=|==)")
#: The quoted literal in an installed-test gate: `'<literal>' in|not in <var>.stdout`.
_STATUS_GATE = re.compile(r"'([^']+)'\s+(?:not\s+)?in\s+\w+\.stdout")

#: dpkg's Status field is `<want> <error> <status>`; only the third says whether
#: the package is installed. `hold ok installed` is the row that matters: a held
#: package IS installed, and a gate keyed on the whole `install ok installed`
#: string calls it absent and re-runs the install.
_DPKG_STATUS_TRUTH = {
    "install ok installed": True,
    "hold ok installed": True,
    "deinstall ok config-files": False,
    "unknown ok not-installed": False,
    "install ok half-installed": False,
    "install ok half-configured": False,
}

#: Lines where "does dpkg KNOW this package" is the correct question. Keyed by
#: exact text rather than line number, so the exemption travels with the line and
#: dies when the line changes -- see `test_every_exemption_still_exists`.
_KNOWLEDGE_IS_THE_RIGHT_QUESTION = {
    'if dpkg -l "${pkg}" &>/dev/null 2>&1; then': (
        "install.sh's purge loop: `apt-get purge` SHOULD run for a package in `rc` state, "
        "so dpkg's knowledge is the right test and anchoring on `^ii` would skip exactly "
        "the packages the loop exists to clean up"
    ),
}


#: Memoized by root (#17411). Widening to `.py` made these enumerations rglob
#: the whole repository, and they are called once per test and once per
#: parametrised case -- the suite went to 137s against pre-push's 128s budget,
#: and a guard slow enough to be noticed is one someone narrows. 35s memoized.
#:
#: Keyed on root, so the empty-tree calls `reach_declarations_test` makes and
#: the tmp_path fixtures below each get their own entry. The returned lists are
#: shared between callers: nothing here mutates them, and nothing should.
@functools.lru_cache(maxsize=None)
def _scanned_files(root: pathlib.Path) -> List[pathlib.Path]:
    """Files under *root* -- the root given, never `repo_root()` (#17387 review).

    The first version took no root and read `repo_root()` itself, so both
    declarations below returned the same items for an empty directory as for
    the repository. `reach_declarations_test` caught it: "a floor it clears
    unconditionally measures nothing". The underscore on the unused `_root`
    parameter was the tell -- the signature accepted a root to satisfy the
    protocol and the body ignored it.
    """
    out: List[pathlib.Path] = []
    for suffix in _SCANNED_SUFFIXES:
        out.extend(
            path
            for path in root.rglob(f"*{suffix}")
            if not any(part in {"venv", ".venv", "node_modules", ".git"} for part in path.parts)
        )
    return sorted(out)


def _python_dpkg_strings(text: str) -> List[Tuple[int, str]]:
    """`dpkg -l` inside a Python STRING that is code, not a docstring (#17411).

    `.py` joined this guard's domain because the pattern was fixed where the
    guard looked and left standing where it did not --
    `services/advanced_workflow/step_generator.py` generated
    `dpkg -l | grep {package}` as a workflow validation command, and `.py` was
    outside `_SCANNED_SUFFIXES`.

    Parsed rather than grepped, because a line scan over Python reports this
    guard's own docstring and its test literals. `ast` separates a string that
    is executed from one that documents: module, class and function docstrings
    are excluded by identity, so prose describing the defect does not read as
    the defect. An f-string's literal parts are joined, since
    `f"dpkg -l | grep {pkg}"` carries the pattern across a placeholder.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    docstring_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                docstring_nodes.add(id(node.body[0].value))
    # An f-string is both a JoinedStr and a set of Constant children, so a naive
    # walk reports it twice. The literal parts are only meaningful joined.
    inside_fstring = {id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for part in node.values}
    found: List[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if id(node) in docstring_nodes or id(node) in inside_fstring:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _DPKG_LIST.search(node.value):
                found.append((node.lineno, node.value.strip()[:70]))
        elif isinstance(node, ast.JoinedStr):
            literal = "".join(
                part.value for part in node.values if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
            if _DPKG_LIST.search(literal):
                found.append((node.lineno, literal.strip()[:70]))
    return found


@functools.lru_cache(maxsize=None)
def _code_lines_using_dpkg_list(root: pathlib.Path | None = None) -> List[Tuple[str, int, str]]:
    """Every non-comment line invoking `dpkg -l`, as (relative path, lineno, text).

    Comments are excluded by position, not by stripping: this guard's own
    docstring and the explanatory comments it required in four roles all contain
    the literal `dpkg -l`, and a naive scan flags its own documentation.
    """
    base = root or repo_root()
    found: List[Tuple[str, int, str]] = []
    for path in _scanned_files(base):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if path.suffix == ".py":
            # Substring first, AST second. Parsing every .py in the repo took the
            # guard past 120s; almost none of them mention dpkg at all, and a
            # file that does not contain the literal cannot contain it inside a
            # string either. The parse is only needed to tell a docstring from
            # code, which is a question about the few files that match.
            if not _DPKG_LIST.search(text):
                continue
            if path.name == pathlib.Path(__file__).name:
                # This guard's own fixtures, `what=` text and assertion messages
                # all contain `dpkg -l` as DATA about the pattern. Scanning them
                # reported six hits in itself -- an exemption dict key, a reach
                # description, two failure messages. A file whose subject is a
                # pattern necessarily contains it.
                continue
            found.extend(
                (str(path.relative_to(base)), number, snippet) for number, snippet in _python_dpkg_strings(text)
            )
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            match = _DPKG_LIST.search(line)
            if not match:
                continue
            comment = line.find("#")
            if comment != -1 and comment < match.start():
                continue
            # Prose naming the command rather than running it. A YAML `msg:`
            # block is not a comment, so the position check above does not see
            # it -- this guard's own failure message quotes `dpkg -l` and was
            # the first thing it flagged.
            if line[match.end() : match.end() + 1] == "`":
                continue
            found.append((str(path.relative_to(base)), number, line.strip()))
    return found


def _walk_tasks(node: object) -> Iterator[dict]:
    """Every task mapping in a task file or a playbook, including inside blocks."""
    if isinstance(node, list):
        for item in node:
            yield from _walk_tasks(item)
    elif isinstance(node, dict):
        if any(key in node for key in ("register", "command", "ansible.builtin.command", "shell")):
            yield node
        for key in ("tasks", "pre_tasks", "post_tasks", "handlers", "block", "rescue", "always"):
            if key in node:
                yield from _walk_tasks(node[key])


@functools.lru_cache(maxsize=None)
def _dpkg_registrations(root: pathlib.Path | None = None) -> List[Tuple[str, str]]:
    """(relative path, registered var) for each task whose command runs dpkg.

    Keyed on the command, never on the variable's name: `which ufw` registered as
    `ufw_installed` is gated on `.rc` correctly, and a name-based rule would call
    five sound gates defects.
    """
    base = root or repo_root()
    found: List[Tuple[str, str]] = []
    for path in _scanned_files(base):
        if path.suffix not in (".yml", ".yaml") or "ansible" not in path.parts:
            continue
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            continue
        for task in _walk_tasks(document):
            variable = task.get("register")
            if not isinstance(variable, str):
                continue
            rendered = " ".join(str(value) for value in task.values())
            if _DPKG_QUERY.search(rendered):
                found.append((str(path.relative_to(base)), variable))
    return found


#: 4 today: setup_browser_vnc.sh, secure-vm-exec.sh, decommission-node.yml
#: (all three anchored on `^ii`) and install.sh's exempt purge loop.
DPKG_LIST_CALL_SITES = declare(
    "dpkg-list-call-sites",
    discover=_code_lines_using_dpkg_list,
    floor=3,
    growth=3,
    what="`dpkg -l` invocations in shell/YAML lines and Python strings (#17387, #17411)",
)

#: 6 today: the four rewritten by #17387 (postgresql, grafana, redis,
#: disable-idle-nginx) plus check-system-updates' ESM version lookup and
#: decommission-node's `^ii`-anchored check. Floor 4 rather than 3: at 3 the
#: window was exactly the growth allowance, so a single removal reddened it.
DPKG_REGISTRATIONS = declare(
    "dpkg-ansible-registrations",
    discover=_dpkg_registrations,
    floor=4,
    growth=3,
    what="ansible tasks registering the result of a dpkg query (#17387)",
)


def test_the_sweep_actually_reaches_something() -> None:
    """`nothing found` and `did not look` must not be the same green."""
    DPKG_LIST_CALL_SITES.verify_floor(repo_root())
    DPKG_REGISTRATIONS.verify_floor(repo_root())


def test_every_dpkg_list_is_anchored_on_the_installed_state() -> None:
    offenders = [
        (path, number, line)
        for path, number, line in _code_lines_using_dpkg_list()
        if not _INSTALLED_ANCHOR.search(line) and line not in _KNOWLEDGE_IS_THE_RIGHT_QUESTION
    ]
    assert not offenders, (
        "`dpkg -l` used as an installed-test without anchoring on `^ii` -- it also matches a "
        f"package in `rc` state, removed but not purged (#17387): {offenders}"
    )


def test_no_dpkg_registration_is_gated_on_rc() -> None:
    """The defect proper: `rc` cannot distinguish `rc` state from installed."""
    offenders = []
    for path, variable in _dpkg_registrations():
        text = (repo_root() / path).read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if variable in line and _RC_GATE.search(line):
                offenders.append((path, number, line.strip()))
    assert not offenders, (
        "an ansible task gates on the `rc` of a dpkg query -- `dpkg -l` exits 0 for a package "
        f"in `rc` state, so this reads 'installed' on a node that has none (#17387): {offenders}"
    )


@pytest.mark.parametrize("line", sorted(_KNOWLEDGE_IS_THE_RIGHT_QUESTION))
def test_every_exemption_still_exists(line: str) -> None:
    """An exemption outliving its line is a hole nobody reopened deliberately."""
    present: Sequence[Tuple[str, int, str]] = [site for site in _code_lines_using_dpkg_list() if site[2] == line]
    assert present, (
        f"exempted line is gone from the tree; delete the entry rather than leaving it to "
        f"exempt a line that may come back for another reason: {line!r}"
    )


def _installed_test_literals() -> List[str]:
    """Quoted status literals gating on a variable registered from a DPKG query.

    Scoped through `_dpkg_registrations()` rather than scanning every
    `'x' in y.stdout` in the tree. The first version did the latter and
    collected `PONG`, `active (running)`, `role:master` and twenty others --
    unrelated gates, then checked against a dpkg Status truth table they have
    no reason to satisfy. The test failed, which is the only reason the scan
    was caught being wrong rather than the code.
    """
    found: List[str] = []
    for relative, variable in _dpkg_registrations():
        try:
            text = (repo_root() / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        gate = re.compile(r"'([^']+)'\s+(?:not\s+)?in\s+" + re.escape(variable) + r"\.stdout")
        found.extend(gate.findall(text))
    return sorted(set(found))


def test_the_gate_literals_were_actually_found() -> None:
    """Otherwise the parametrised test below passes by iterating an empty set."""
    literals = _installed_test_literals()
    assert literals, "no `'<status>' in <var>.stdout` gate found -- the scan matched nothing"


@pytest.mark.parametrize(("status", "is_installed"), sorted(_DPKG_STATUS_TRUTH.items()))
def test_every_gate_literal_classifies_every_dpkg_status(status: str, is_installed: bool) -> None:
    """The gate must agree with dpkg about what "installed" means, for every Status.

    `hold ok installed` is why this exists. #17387 replaced an `rc`-based check
    with `'install ok installed' in stdout`, which is False for a held package
    -- so a package that IS installed read as absent and the role re-ran its
    install. The `rc` check it replaced got that case RIGHT, so the fix was a
    regression on the one input nobody thought to try.

    dpkg's Status is `<want> <error> <status>`. `want` is install/hold/deinstall
    and says nothing about presence; only the third field does. `'ok installed'`
    matches `install ok installed` and `hold ok installed`, and no other row --
    `half-installed` and `not-installed` do not contain it.
    """
    for literal in _installed_test_literals():
        assert (literal in status) is is_installed, (
            f"gate literal {literal!r} classifies {status!r} as "
            f"{literal in status}, but dpkg says installed={is_installed}"
        )
