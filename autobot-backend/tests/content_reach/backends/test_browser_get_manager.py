# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Smoke test: the research-browser import path resolves to the singleton (#11078).

This originally covered `content_reach.backends.browser._get_manager`. That
helper is gone — `content_reach` reaches the browser through the canonical
interface now (#13236, ADR-009 step 3) rather than importing one stack.

The property #11078 cared about is unchanged and still worth covering: the lazy
import actually resolves, and it resolves to the *singleton* rather than a
fresh manager (a second instance would mean per-caller browser sessions). It
just lives one layer down, in the in-process backend `content_reach` routes to.
"""

from __future__ import annotations


def test_in_process_backend_resolves_the_research_manager_singleton():
    """The backend's lazy accessor returns the ResearchBrowserManager singleton."""
    from browser_backends import InProcessBrowserBackend
    from research_browser_manager import ResearchBrowserManager, get_research_browser_manager

    manager = InProcessBrowserBackend._manager()

    assert manager is get_research_browser_manager()
    assert isinstance(manager, ResearchBrowserManager)


def test_content_reach_no_longer_imports_a_stack_directly():
    """ADR-009's goal, asserted structurally: no caller names a stack."""
    import ast
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[3] / "content_reach/backends/browser.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module} | {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    }

    assert "research_browser_manager" not in imported, "content_reach must route through the interface"
