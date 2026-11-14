# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
""" "This host, this process" is built in ONE place: ``worker_identity()`` (#21518).

``autobot_shared/leader_lease.worker_identity`` names a worker by host and pid. Three more modules
built the same pair by hand, with two host sources and two separators, so the one concept had
four spellings. This sweep fails when a function reads a host name AND a process id and so builds
an identity of its own.

THE RULE (AST, not text): within one function body (nested functions are their own scope; the module
body is a scope too), a host-name read -- ``gethostname()`` on any receiver, ``platform.node()``, or an
``.nodename`` attribute -- together with a ``getpid()`` call.

STATED LIMITATIONS: an identity assembled across scopes (a module constant holding the pid, the host
read in a function) is not seen; a host name from an environment variable is not a host read here.
Test files are outside the population -- they patch both to pin a value.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.testfile_names import is_test_filename
from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
HOME = "autobot_shared/leader_lease.py"

#: Sites still building their own identity, each with the reason it is not converted yet. SHRINK ONLY:
#: ``test_every_pending_site_still_builds_its_own`` fails when an entry stops matching.
PENDING: dict[str, str] = {
    "autobot-backend/knowledge/embedding_switch.py": (
        "#21518 -- its owner is 'host:pid:suffix' (colons), the helper's is 'host-pid'; converting changes the "
        "stored value, which is an owner decision recorded on the issue"
    ),
}

_TEST_PARTS = ("/tests/", "repo_tests/")
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _is_test(path: str) -> bool:
    return is_test_filename(path) or any(part in f"/{path}" for part in _TEST_PARTS)


def _python_files(root: Path) -> list[str]:
    """Every tracked non-test Python file, the population this sweep reads."""
    try:
        return [p for p in tracked_paths(root, "*.py") if not _is_test(p)]
    except EmptyEnumeration:
        return []  # the declared fraction below raises the typed refusal for an empty tree


def _all_python(root: Path) -> int:
    """Every tracked Python file, tests included: the reference population."""
    try:
        return len(tracked_paths(root, "*.py"))
    except EmptyEnumeration:
        return 0


#: Relative to all tracked Python because non-test Python is a proper subset of it. The fraction is a
#: tolerance, not a count: it fires once the sweep stops reading a large share of the production code.
REACH = declare(
    "worker-identity-one-home-21518",
    discover=_python_files,
    reference=_all_python,
    min_fraction=0.4,
    what="tracked non-test python files swept for a hand-built host-and-process identity",
)


def _is_host_read(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute) and node.attr == "nodename":
        return True
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "gethostname"
    if isinstance(func, ast.Attribute):
        return func.attr == "gethostname" or (
            func.attr == "node" and isinstance(func.value, ast.Name) and func.value.id == "platform"
        )
    return False


def _is_pid_read(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == "getpid") or (
        isinstance(func, ast.Attribute) and func.attr == "getpid"
    )


def _own_nodes(scope: ast.AST) -> list[ast.AST]:
    """The nodes of *scope*, not those inside a nested function (that is its own scope)."""
    found: list[ast.AST] = []
    pending = list(ast.iter_child_nodes(scope))
    while pending:
        node = pending.pop()
        if isinstance(node, _FUNCTIONS):
            continue
        found.append(node)
        pending.extend(ast.iter_child_nodes(node))
    return found


def identity_sites(source: str) -> list[int]:
    """Line numbers of each scope that reads a host name and a pid, as the first pid read."""
    tree = parse_cache.parse(source)
    scopes = [tree, *(n for n in ast.walk(tree) if isinstance(n, _FUNCTIONS))]
    lines: list[int] = []
    for scope in scopes:
        nodes = _own_nodes(scope)
        pids = sorted(n.lineno for n in nodes if _is_pid_read(n))
        if pids and any(_is_host_read(n) for n in nodes):
            lines.append(pids[0])
    return sorted(lines)


def sweep(root: Path, paths: list[str]) -> list[str]:
    """``path:line`` of every identity built, over *paths* under *root*."""
    found: list[str] = []
    for rel in paths:
        source = (root / rel).read_text(encoding="utf-8")
        found.extend(f"{rel}:{line}" for line in identity_sites(source))
    return found


def _tree_sites() -> list[str]:
    files = REACH.examined(_ROOT)
    sites = sweep(_ROOT, list(files))
    REACH.completed(files, _ROOT)
    return sites


def _files(sites: list[str]) -> Counter[str]:
    return Counter(site.rsplit(":", 1)[0] for site in sites)


def test_no_identity_is_built_outside_the_helper() -> None:
    outside = sorted(s for s in _tree_sites() if s.rsplit(":", 1)[0] not in {HOME, *PENDING})
    assert (
        outside == []
    ), f"#21518: build the host-and-process identity with worker_identity() in {HOME}:\n  " + "\n  ".join(outside)


def test_the_helper_is_found_by_the_sweep() -> None:
    """The contrast: the one legitimate construction is seen, so a green result is not blindness."""
    assert _files(_tree_sites())[HOME] == 1


def test_every_pending_site_still_builds_its_own() -> None:
    seen = _files(_tree_sites())
    stale = sorted(path for path in PENDING if seen[path] == 0)
    assert stale == [], f"these PENDING entries no longer build an identity; delete them: {stale}"


def test_a_planted_identity_fails_the_sweep(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text(
        "import os\nimport socket\n\n\ndef holder():\n    return '%s-%d' % (socket.gethostname(), os.getpid())\n",
        encoding="utf-8",
    )
    sites = sweep(tmp_path, ["bad.py"])
    assert sites == ["bad.py:6"]
    with pytest.raises(AssertionError):
        assert [s for s in sites if s.rsplit(":", 1)[0] not in {HOME, *PENDING}] == []


@pytest.mark.parametrize(
    "source",
    [
        "import os, socket\n\ndef f():\n    return os.uname().nodename + str(os.getpid())\n",
        "from socket import gethostname\nfrom os import getpid\n\nasync def f():\n    return gethostname(), getpid()\n",
        "import os, platform\nx = (platform.node(), os.getpid())\n",
    ],
    ids=["uname-nodename", "bare-names-async", "platform-node-module-level"],
)
def test_each_spelling_of_the_pair_is_caught(source: str) -> None:
    assert len(identity_sites(source)) == 1


@pytest.mark.parametrize(
    "source",
    [
        "import socket\n\ndef f():\n    return socket.gethostname()\n",
        "import os\n\ndef f():\n    return os.getpid()\n",
        "import os, socket\n\ndef a():\n    return socket.gethostname()\n\ndef b():\n    return os.getpid()\n",
    ],
    ids=["host-only", "pid-only", "split-across-functions"],
)
def test_one_half_alone_is_not_an_identity(source: str) -> None:
    assert identity_sites(source) == []
