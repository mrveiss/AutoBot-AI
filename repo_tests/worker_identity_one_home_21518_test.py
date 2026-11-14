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
body is a scope too), a host-name read -- ``gethostname()`` / ``getfqdn()`` on any receiver,
``platform.node()``, ``.nodename``, ``uname()[1]`` or ``uname().node`` -- together with a ``getpid()`` call
(``os.getpid()`` or a bare ``getpid()``).

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

_TEST_PARTS = ("/tests/", "repo_tests/")
_HOST_CALLS = frozenset({"gethostname", "getfqdn"})
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _is_test(path: str) -> bool:
    return is_test_filename(path) or any(part in f"/{path}" for part in _TEST_PARTS)


def _python_files(root: Path) -> list[str]:
    """Every tracked non-test Python file, the population this sweep reads."""
    try:
        return [p for p in tracked_paths(root, "*.py") if not _is_test(p)]
    except EmptyEnumeration:
        return []  # the declared fraction below raises the typed refusal for an empty tree


def _non_test_python_count(root: Path) -> int:
    """The same population, independent of the GLOB only: every tracked file, filtered by suffix in Python.

    The sweep asks git for ``*.py``; this lists the whole tree and filters here, so a broken glob moves
    only one of the two numbers. Numerator and denominator are the same population (RATCHET_BASELINES
    rule 7), so adding tests moves neither.

    NOT proven here: the test-file predicate. Both counts call ``_is_test()``, so an over-broad predicate
    that dropped production files would cancel out at ``min_fraction=1.0``. There is no second canonical
    predicate to count with (a third copy of the rule would be a fork); the predicate itself is pinned by
    ``autobot_shared/testfile_names_test.py`` and ``test_name_predicate_single_home_21078_test.py``.
    """
    try:
        return sum(1 for rel in tracked_paths(root) if rel.endswith(".py") and not _is_test(rel))
    except EmptyEnumeration:
        return 0


#: Every file in the reference must be read: the fraction is 1.0, not a tolerance, because the two counts
#: enumerate one population (`_reach_policy`: SUBSET_DRIFTS applies only when the reference is a different,
#: larger class).
REACH = declare(
    "worker-identity-one-home-21518",
    discover=_python_files,
    reference=_non_test_python_count,
    min_fraction=1.0,
    what="tracked non-test python files swept for a hand-built host-and-process identity",
)


def _is_uname_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) == "uname"


def _is_host_read(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr == "nodename" or (node.attr == "node" and _is_uname_call(node.value))
    if isinstance(node, ast.Subscript):  # os.uname()[1]
        return _is_uname_call(node.value) and isinstance(node.slice, ast.Constant) and node.slice.value == 1
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in _HOST_CALLS
    if isinstance(func, ast.Attribute):
        return func.attr in _HOST_CALLS or (
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


def _outside_the_home(sites: list[str]) -> list[str]:
    return [s for s in sites if s.rsplit(":", 1)[0] != HOME]


def test_no_identity_is_built_outside_the_helper() -> None:
    outside = sorted(_outside_the_home(_tree_sites()))
    assert (
        outside == []
    ), f"#21518: build the host-and-process identity with worker_identity() in {HOME}:\n  " + "\n  ".join(outside)


def test_the_helper_is_found_by_the_sweep() -> None:
    """The contrast: the one legitimate construction is seen, so a green result is not blindness."""
    assert _files(_tree_sites())[HOME] == 1


def test_a_planted_identity_fails_the_sweep(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text(
        "import os\nimport socket\n\n\ndef holder():\n    return '%s-%d' % (socket.gethostname(), os.getpid())\n",
        encoding="utf-8",
    )
    sites = sweep(tmp_path, ["bad.py"])
    assert sites == ["bad.py:6"]
    with pytest.raises(AssertionError):
        assert list(_outside_the_home(sites)) == []


@pytest.mark.parametrize(
    "source",
    [
        "import os, socket\n\ndef f():\n    return os.uname().nodename + str(os.getpid())\n",
        "from socket import gethostname\nfrom os import getpid\n\nasync def f():\n    return gethostname(), getpid()\n",
        "import os, platform\nx = (platform.node(), os.getpid())\n",
        "import os\n\ndef f():\n    return os.uname()[1], os.getpid()\n",
        "import os, platform\n\ndef f():\n    return platform.uname().node, os.getpid()\n",
        "import os, socket\n\ndef f():\n    return socket.getfqdn(), os.getpid()\n",
    ],
    ids=[
        "uname-nodename",
        "bare-names-async",
        "platform-node-module-level",
        "uname-subscript",
        "uname-node",
        "getfqdn",
    ],
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
