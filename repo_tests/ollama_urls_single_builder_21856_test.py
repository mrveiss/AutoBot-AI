# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An Ollama ``/api/<path>`` URL is built in ``autobot_shared/ollama_urls.py`` only (#21856).

A base that already ends in ``/api`` turns a hand-built ``{base}/api/generate`` into
``/api/api/generate``. The one rule lives in ``ollama_urls``; this guard fails when a
backend or shared module appends an Ollama path to a base by f-string or ``+``.
Test modules and the standalone ``autobot-infrastructure`` scripts are out of scope.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
OWNER = REPO / "autobot_shared" / "ollama_urls.py"
OLLAMA_PATH = re.compile(r"^/api/(generate|chat|tags|pull|embeddings|embed|show|ps)$")
MIN_SOURCES = 2500  # the three roots hold ~3800 first-party modules
SKIP_PARTS = {"node_modules", "tests", "__pycache__", ".venv", "venv"}


def _sources():
    for root in ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            if SKIP_PARTS & set(path.parts) or path.name.endswith("_test.py") or path == OWNER:
                continue
            yield path


def _is_path(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and bool(OLLAMA_PATH.match(node.value))


def hand_built_lines(tree: ast.AST) -> list[int]:
    """Lines where an Ollama path follows an interpolated base (f-string) or ``+``."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            found += [node.lineno for i, part in enumerate(node.values) if i and _is_path(part)]
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) and _is_path(node.right):
            found.append(node.lineno)
    return found


@pytest.mark.parametrize(
    "source",
    ['f"{base}/api/generate"', 'base + "/api/tags"', 'f"http://{h}:{p}/api/embeddings"'],
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
