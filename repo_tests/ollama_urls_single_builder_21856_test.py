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

REPO = Path(__file__).resolve().parent.parent
ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared", "autobot-infrastructure")
#: Scripts that run before the repo (and so ``autobot_shared``) exists on the host. Empty today.
CANNOT_IMPORT_SHARED: frozenset[str] = frozenset()
OWNER = REPO / "autobot_shared" / "ollama_urls.py"
OLLAMA_PATH = re.compile(r"^/api/(generate|tags|pull|embeddings|embed|show|ps)(\?.*)?$")
MIN_SOURCES = 2500  # the three roots hold ~3800 first-party modules
TEMPLATE = re.compile(r"(%s|\{\w*\})/api/(generate|tags|pull|embeddings|embed|show|ps)(\?.*)?$")
SKIP_PARTS = {"node_modules", "tests", "__pycache__", ".venv", "venv"}


def _sources():
    for root in ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            if (
                SKIP_PARTS & set(path.parts)
                or path.name.endswith("_test.py")
                or path == OWNER
                or path.relative_to(REPO).as_posix() in CANNOT_IMPORT_SHARED
            ):
                continue
            yield path


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
        'f"{base}/api/generate?stream=1"',
    ],
)
def test_the_detector_sees_a_hand_built_ollama_url(source):
    assert hand_built_lines(ast.parse(source))


@pytest.mark.parametrize(
    "source",
    ["ollama_generate_url(base)", 'f"{base}/api/chat/sessions"', '"/api/generate"'],
)
def test_the_detector_ignores_the_helper_other_routes_and_bare_paths(source):
    assert not hand_built_lines(ast.parse(source))


def test_no_hand_built_ollama_api_url_outside_ollama_urls():
    sources = list(_sources())
    assert len(sources) >= MIN_SOURCES, f"scanned only {len(sources)} modules; the guard no longer reaches the tree"
    offenders = [
        f"{path.relative_to(REPO)}:{line}"
        for path in sources
        for line in hand_built_lines(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert not offenders, "build Ollama URLs with autobot_shared.ollama_urls (ollama_api_url): " + ", ".join(offenders)
