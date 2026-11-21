# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A production read of ``config.ollama_host`` is refused: the Ollama host is ``config.vm.ollama`` (#21859).

``config.ollama_host`` (alias ``OLLAMA_HOST``) is a different field from the SSOT host ``config.vm.ollama``
(alias ``AUTOBOT_OLLAMA_HOST``), so a deployment that sets only the SSOT variable is ignored by a reader of
the former. Build a URL with ``config.ollama_url`` or ``config.vm.ollama``.

Detected: ``<name>.ollama_host`` where ``<name>`` is bound by ``from autobot_shared.ssot_config import config``
(under any alias), as a read (a write or ``del`` is not one). A function or lambda that binds the same name locally
(a parameter, an assignment, an import) shadows the SSOT object inside it. NOT detected: a read through ``getattr``,
or through ``ssot_config.config.ollama_host`` held in a variable.

Excluded on purpose, as a different concept: ``SlmLLMConfig.ollama_host`` in ``autobot-slm-backend/api/llm_config.py``
is the SLM's own LLM-settings field, the host Ollama LISTENS on (default: all interfaces), stored as a setting. It is
not the address a client calls, so ``config.vm.ollama`` is not its replacement. That module binds the SSOT object as
``_ssot_config`` and uses ``config`` for a ``SlmLLMConfig`` instance, so the detector (which follows the SSOT import
only) does not see it; a control below pins that shape.

Scope: backend, SLM backend and shared; every ``tests`` directory and test module is skipped on purpose.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.testfile_names import is_test_filename
from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
SSOT_MODULE = "autobot_shared.ssot_config"
FIELD = "ollama_host"
SKIP_PARTS = {"node_modules", "tests", "__pycache__", ".venv", "venv"}
#: Measured: 3754 of 7131 tracked ``.py`` under ROOTS are scanned (0.53); 0.45 leaves room for a shift into tests. A
#: relative floor, because an exact pin goes stale on every merge of main (#19676).
MIN_FRACTION = 0.45


def _is_scanned(rel: str) -> bool:
    parts = set(rel.split("/"))
    return not (SKIP_PARTS & parts or is_test_filename(rel.rsplit("/", 1)[-1]))


def _source_population(root: Path) -> list[str]:
    try:
        return [rel for rel in tracked_paths(root, *ROOTS) if rel.endswith(".py") and _is_scanned(rel)]
    except EmptyEnumeration:
        return []


def _all_python(root: Path) -> int:
    try:
        return sum(1 for rel in tracked_paths(root, *ROOTS) if rel.endswith(".py"))
    except EmptyEnumeration:
        return 0


REACH = declare(
    "ollama-host-reads-ssot-host-21859",
    discover=_source_population,
    reference=_all_python,
    min_fraction=MIN_FRACTION,
    roots=ROOTS,
    what="production python",
)


def _config_aliases(tree: ast.AST) -> set[str]:
    """The names this module binds the SSOT ``config`` object to."""
    return {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == SSOT_MODULE
        for alias in node.names
        if alias.name == "config"
    }


_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _own_bindings(scope: ast.AST) -> frozenset[str]:
    """Names a function or lambda binds itself: parameters, stores, imports, nested defs; nested scopes are skipped."""
    args = scope.args
    bound = {a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg] if a}
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bound.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        if not isinstance(node, (*_SCOPES, ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(node))
    return frozenset(bound)


def ollama_host_reads(tree: ast.AST) -> list[int]:
    """Lines that READ ``.ollama_host`` off the SSOT config object, where it is not shadowed by a local binding."""
    names, found, stack = _config_aliases(tree), [], [(tree, frozenset())]
    while stack:
        node, shadowed = stack.pop()
        if isinstance(node, _SCOPES):
            shadowed = shadowed | _own_bindings(node)
        if (
            isinstance(node, ast.Attribute)
            and node.attr == FIELD
            and isinstance(node.ctx, ast.Load)
            and isinstance(node.value, ast.Name)
            and node.value.id in names - shadowed
        ):
            found.append(node.lineno)
        stack.extend((child, shadowed) for child in ast.iter_child_nodes(node))
    return sorted(found)


@pytest.mark.parametrize(
    "source",
    [
        "from autobot_shared.ssot_config import config\nh = config.ollama_host",
        "from autobot_shared.ssot_config import config as _cfg\nh = _cfg.ollama_host or 'x'",
    ],
)
def test_the_detector_sees_a_read_of_the_ssot_field(source):
    assert ollama_host_reads(parse_cache.parse(source))


@pytest.mark.parametrize(
    "source",
    [
        "from autobot_shared.ssot_config import config\nh = config.vm.ollama",
        "def f(config):\n    return config.ollama_host",
        "from autobot_shared.ssot_config import config as _s\ndef f(config):\n    return config.ollama_host",
        # the SSOT import is named `config`, and a parameter, a local or a lambda argument shadows it
        "from autobot_shared.ssot_config import config\ndef f(config):\n    return config.ollama_host",
        "from autobot_shared.ssot_config import config\ndef f():\n    config = make()\n    return config.ollama_host",
        "from autobot_shared.ssot_config import config\nh = lambda config: config.ollama_host",
        # a write or a deletion is not a read
        "from autobot_shared.ssot_config import config\nconfig.ollama_host = 'localhost'",
        "from autobot_shared.ssot_config import config\ndel config.ollama_host",
        # the SLM listen-host shape (different concept, see the module docstring): the SSOT object is `_ssot_config`
        "from autobot_shared.ssot_config import config as _ssot_config\nasync def f(db):\n"
        "    config = await _load(db)\n    return config.ollama_host",
    ],
)
def test_the_detector_still_sees_an_unshadowed_read_beside_a_shadowing_function():
    source = (
        "from autobot_shared.ssot_config import config\n"
        "def shadowed(config):\n    return config.ollama_host\n"
        "def real():\n    return config.ollama_host\n"
    )
    assert ollama_host_reads(parse_cache.parse(source)) == [5]


def test_the_detector_ignores_the_ssot_host_and_a_foreign_config_object(source):
    assert not ollama_host_reads(parse_cache.parse(source))


def test_no_production_module_reads_config_ollama_host():
    root = repo_root()
    offenders, unparsed, parsed = [], [], 0
    for rel in REACH.examined(root):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        try:
            tree = parse_cache.parse(text)
        except SyntaxError as exc:
            unparsed.append(f"{rel}: {exc.msg} (line {exc.lineno})")
            continue
        parsed += 1
        offenders += [f"{rel}:{line}" for line in ollama_host_reads(tree)]
    assert not unparsed, "production modules the guard could not parse: " + "; ".join(unparsed)
    REACH.completed(parsed, root)
    assert not offenders, "read the Ollama host from config.vm.ollama (or config.ollama_url): " + ", ".join(offenders)
