# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An Ollama ``/api/<path>`` URL is built in ``autobot_shared/ollama_urls.py`` only (#21856).

A base that already ends in ``/api`` turns a hand-built ``{base}/api/generate`` into
``/api/api/generate``. The one rule lives in ``ollama_urls``; this guard fails when a
module appends an Ollama path to a base by f-string (also with a suffix such as
``?stream=1``), ``+``, ``%`` or ``str.format``.

Detected: those four forms. NOT detected: ``urljoin``, ``"/".join``, a path held in a
variable or constant, and a complete literal URL with no interpolated base.

Scope: backend, SLM backend, shared and ``autobot-infrastructure`` (its scripts import
``autobot_shared`` after a repo-root ``sys.path`` insert, #18289). Every ``tests``
directory and ``*_test.py`` module is skipped on purpose: tests assert the wire URL
literally, and the guard protects production builders. A script that cannot import
``autobot_shared`` is listed in ``CANNOT_IMPORT_SHARED`` with its reason.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.testfile_names import is_test_filename
from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared", "autobot-infrastructure")
#: Scripts that run before the repo (and so ``autobot_shared``) exists on the host. Empty today.
CANNOT_IMPORT_SHARED: frozenset[str] = frozenset()
OWNER_REL = "autobot_shared/ollama_urls.py"
OLLAMA_PATH = re.compile(r"^/api/(generate|tags|pull|embeddings|embed|show|ps)(\?.*)?$")
#: Measured: 3883 of 7317 tracked ``.py`` under ROOTS are scanned (0.53); 0.45 leaves room for a shift into tests.
MIN_FRACTION = 0.45
TEMPLATE = re.compile(r"(%(\(\w+\))?s|\{[^{}]*\})/api/(generate|tags|pull|embeddings|embed|show|ps)(\?.*)?$")
SKIP_PARTS = {"node_modules", "tests", "__pycache__", ".venv", "venv"}


def _is_scanned(rel: str) -> bool:
    """A production ``.py`` under ``ROOTS``. The ``tests`` directory skip stays: ``is_test_filename`` sees names only."""
    parts = set(rel.split("/"))
    name = rel.rsplit("/", 1)[-1]
    return not (SKIP_PARTS & parts or is_test_filename(name) or rel == OWNER_REL or rel in CANNOT_IMPORT_SHARED)


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
    "ollama-urls-single-builder",
    discover=_source_population,
    reference=_all_python,
    min_fraction=MIN_FRACTION,
    what="production python",
    roots=ROOTS,
)


def _is_path(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and bool(OLLAMA_PATH.match(node.value))


def hand_built_lines(tree: ast.AST) -> list[int]:
    """Lines where an Ollama path follows an interpolated base (f-string, ``+``, ``%``, ``.format``)."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            found += [node.lineno for i, part in enumerate(node.values) if i and _is_path(part)]
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) and _is_path(node.right):
            found.append(node.lineno)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and _templated(node.left):
            found.append(node.lineno)
        elif _is_format_call(node):
            found.append(node.lineno)
    return found


def _templated(node: ast.AST) -> bool:
    """A string whose placeholder is followed by an Ollama path: ``"%s/api/tags"`` / ``"{}/api/tags"``."""
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and bool(TEMPLATE.search(node.value))


def _is_format_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
        and _templated(node.func.value)
    )


@pytest.mark.parametrize(
    "source",
    [
        'f"{base}/api/generate"',
        'base + "/api/tags"',
        'f"http://{h}:{p}/api/embeddings"',
        '"%s/api/x" % base'.replace("x", "tags"),
        '"{}/api/tags".format(b)',
        '"%(base)s/api/tags" % {"base": b}',
        '"{base!s}/api/tags".format(base=b)',
        'f"{base}/api/generate?stream=1"',
    ],
)
def test_the_detector_sees_a_hand_built_ollama_url(source):
    assert hand_built_lines(parse_cache.parse(source))


@pytest.mark.parametrize(
    "source",
    ["ollama_generate_url(base)", 'f"{base}/api/chat/sessions"', '"/api/generate"'],
)
def test_the_detector_ignores_the_helper_other_routes_and_bare_paths(source):
    assert not hand_built_lines(parse_cache.parse(source))


def test_no_hand_built_ollama_api_url_outside_ollama_urls():
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
        offenders += [f"{rel}:{line}" for line in hand_built_lines(tree)]
    assert not unparsed, "production modules the guard could not parse: " + "; ".join(unparsed)
    REACH.completed(parsed, root)
    assert not offenders, "build Ollama URLs with autobot_shared.ollama_urls (ollama_api_url): " + ", ".join(offenders)
