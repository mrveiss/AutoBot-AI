# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A host+port Ollama base URL is wrapped by an ``ollama_urls`` builder (#21768).

``f"http://{host}:{port}"`` built for Ollama in the listed modules must be an argument of an
``ollama_*`` call, so a configured endpoint that already carries an API path cannot double it.
Detected: an ``http://{..}:{..}`` f-string in the listed files that is not a direct argument of an
``ollama_*`` call. NOT detected: other modules (``ollama_urls_single_builder_21856_test`` covers path
appends); non-Ollama f-strings in these files are told apart by naming the Ollama variables.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

ROUTED_FILES = (
    "autobot-backend/code_analysis/src/env_analyzer.py",
    "autobot-backend/config/defaults.py",
    "autobot-backend/config/model_config.py",
    "autobot-backend/config/service_config.py",
)
OLLAMA_NAMES = ("ollama", "OLLAMA", "llm_host", "llm_port")


def _is_host_port(node: ast.AST) -> bool:
    if not (isinstance(node, ast.JoinedStr) and len(node.values) >= 4):
        return False
    first = node.values[0]
    if not (isinstance(first, ast.Constant) and first.value == "http://"):
        return False
    return any(name in ast.unparse(node) for name in OLLAMA_NAMES)


def _unrouted(tree: ast.AST) -> list[int]:
    routed = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "").startswith("ollama_"):
            routed.update(id(arg) for arg in node.args)
    return [n.lineno for n in ast.walk(tree) if _is_host_port(n) and id(n) not in routed]


def test_every_ollama_host_port_url_goes_through_ollama_urls():
    root = repo_root()
    found = {}
    for rel in ROUTED_FILES:
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        if lines := _unrouted(tree):
            found[rel] = lines
    assert not found, f"host+port Ollama URL not routed through autobot_shared.ollama_urls: {found}"


def test_detector_flags_an_unrouted_builder():
    assert _unrouted(ast.parse('u = f"http://{ollama_host}:{ollama_port}"'))
    assert not _unrouted(ast.parse('u = ollama_base_url(f"http://{ollama_host}:{ollama_port}")'))
