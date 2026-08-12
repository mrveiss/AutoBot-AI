# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default across the multi-source graph-building
helpers in ``api/knowledge_search_aggregator.py`` (#14047):

- ``_create_fact_node``
- ``_create_dynamic_category_nodes``
- ``_process_facts_into_nodes``
"""

from __future__ import annotations

from api.knowledge_search_aggregator import (
    _create_dynamic_category_nodes,
    _create_fact_node,
    _process_facts_into_nodes,
)
from constants.threshold_constants import CategoryDefaults


class TestCreateFactNode:
    def test_missing_category_defaults_to_general(self):
        node = _create_fact_node({"content": "hello", "id": "f1"})

        assert node["metadata"]["category"] == CategoryDefaults.GENERAL

    def test_explicit_category_overrides_default(self):
        node = _create_fact_node({"content": "hello", "id": "f1", "category": "security"})

        assert node["metadata"]["category"] == "security"


class TestCreateDynamicCategoryNodes:
    def test_missing_category_defaults_to_general(self):
        nodes: list = []
        edges: list = []

        category_map = _create_dynamic_category_nodes([{"content": "hello"}], nodes, edges)

        assert category_map == {CategoryDefaults.GENERAL: f"cat_{CategoryDefaults.GENERAL}"}
        assert nodes[0]["id"] == f"cat_{CategoryDefaults.GENERAL}"

    def test_explicit_category_overrides_default(self):
        nodes: list = []
        edges: list = []

        category_map = _create_dynamic_category_nodes([{"content": "hello", "category": "security"}], nodes, edges)

        assert category_map == {"security": "cat_security"}
        assert CategoryDefaults.GENERAL not in category_map


class TestProcessFactsIntoNodes:
    def test_missing_category_defaults_to_general_for_edge_lookup(self):
        nodes: list = []
        edges: list = []
        category_map = {CategoryDefaults.GENERAL: "cat_general"}

        fact_ids = _process_facts_into_nodes([{"content": "hello", "id": "f1"}], nodes, edges, category_map)

        assert fact_ids == ["f1"]
        assert edges == [{"from": "cat_general", "to": "f1", "type": "contains", "strength": 0.6}]

    def test_explicit_category_overrides_default(self):
        nodes: list = []
        edges: list = []
        category_map = {"security": "cat_security", CategoryDefaults.GENERAL: "cat_general"}

        _process_facts_into_nodes(
            [{"content": "hello", "id": "f1", "category": "security"}], nodes, edges, category_map
        )

        assert edges == [{"from": "cat_security", "to": "f1", "type": "contains", "strength": 0.6}]
