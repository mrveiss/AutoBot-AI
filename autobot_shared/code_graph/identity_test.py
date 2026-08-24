# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the canonical code-graph node identity (#13470)."""

from autobot_shared.code_graph.identity import compute_node_id, module_path_from_rel_path


def test_module_path_from_rel_path_python() -> None:
    assert module_path_from_rel_path("services/knowledge/code_indexer.py") == "services.knowledge.code_indexer"


def test_module_path_from_rel_path_vue() -> None:
    assert module_path_from_rel_path("src/components/Foo.vue") == "src.components.Foo"


def test_module_path_from_rel_path_normalises_backslashes() -> None:
    assert module_path_from_rel_path("services\\knowledge\\code_indexer.py") == "services.knowledge.code_indexer"


def test_compute_node_id_module_level() -> None:
    assert compute_node_id("greet", "module") == "module.greet"


def test_compute_node_id_method() -> None:
    assert compute_node_id("run", "module", parent_class="Greeter") == "module.Greeter.run"


def test_compute_node_id_is_stable() -> None:
    first = compute_node_id("run", "pkg.module", parent_class="Greeter")
    second = compute_node_id("run", "pkg.module", parent_class="Greeter")
    assert first == second


def test_compute_node_id_disambiguates_same_basename_files() -> None:
    """The stem-only scheme this replaces collided here; the dotted one does not (#13470)."""
    a = compute_node_id("run", module_path_from_rel_path("pkg_a/utils.py"))
    b = compute_node_id("run", module_path_from_rel_path("pkg_b/utils.py"))
    assert a != b
