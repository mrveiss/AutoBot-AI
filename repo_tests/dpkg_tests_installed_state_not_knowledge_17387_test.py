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

import pathlib
import re
from typing import Iterator, List, Sequence, Tuple

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_SCANNED_SUFFIXES = (".yml", ".yaml", ".sh")
_DPKG_LIST = re.compile(r"\bdpkg\s+-l\b")
#: A dpkg *listing query*, not any mention of dpkg. `fuser /var/lib/dpkg/lock`
#: is a lock check whose `.rc` gate is correct, and matching on the substring
#: "dpkg" called it a defect -- the path contains the word.
_DPKG_QUERY = re.compile(r"\bdpkg\s+-l\b|\bdpkg-query\b")
_INSTALLED_ANCHOR = re.compile(r"\^ii")
_RC_GATE = re.compile(r"\.rc\s*(?:!=|==)")

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


def _scanned_files() -> List[pathlib.Path]:
    root = repo_root()
    out: List[pathlib.Path] = []
    for suffix in _SCANNED_SUFFIXES:
        out.extend(
            path
            for path in root.rglob(f"*{suffix}")
            if not any(part in {"venv", ".venv", "node_modules", ".git"} for part in path.parts)
        )
    return sorted(out)


def _code_lines_using_dpkg_list(_root: pathlib.Path | None = None) -> List[Tuple[str, int, str]]:
    """Every non-comment line invoking `dpkg -l`, as (relative path, lineno, text).

    Comments are excluded by position, not by stripping: this guard's own
    docstring and the explanatory comments it required in four roles all contain
    the literal `dpkg -l`, and a naive scan flags its own documentation.
    """
    found: List[Tuple[str, int, str]] = []
    for path in _scanned_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
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
            found.append((str(path.relative_to(repo_root())), number, line.strip()))
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


def _dpkg_registrations(_root: pathlib.Path | None = None) -> List[Tuple[str, str]]:
    """(relative path, registered var) for each task whose command runs dpkg.

    Keyed on the command, never on the variable's name: `which ufw` registered as
    `ufw_installed` is gated on `.rc` correctly, and a name-based rule would call
    five sound gates defects.
    """
    found: List[Tuple[str, str]] = []
    for path in _scanned_files():
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
                found.append((str(path.relative_to(repo_root())), variable))
    return found


#: 4 today: setup_browser_vnc.sh, secure-vm-exec.sh, decommission-node.yml
#: (all three anchored on `^ii`) and install.sh's exempt purge loop.
DPKG_LIST_CALL_SITES = declare(
    "dpkg-list-call-sites",
    discover=_code_lines_using_dpkg_list,
    floor=3,
    growth=3,
    what="non-comment lines invoking `dpkg -l` (#17387)",
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
