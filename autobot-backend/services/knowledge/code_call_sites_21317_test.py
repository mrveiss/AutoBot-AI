# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21317: one call edge per (scope, target) carries every call-site line.

Pre-fix, ``_record_call_edge`` returned on a repeated pair, so the extracted edge had only the
first line: ``test_three_calls_store_all_three_lines`` failed (``lines`` absent, ``line`` == first
only) and every cap/dropped assertion had nothing to count.
"""

import json

import pytest

from autobot_shared.code_graph import ResolvedCall
from services.knowledge import code_call_sites
from services.knowledge.code_call_sites import add_call_site, call_site_metadata, decode_edge_metadata
from services.knowledge.code_indexer import _build_edge_metadata, extract_javascript, extract_python

pytest.importorskip("tree_sitter_python")

_THREE_CALLS = b"""def helper():
    return 1


def caller():
    helper()
    x = 2
    helper()
    return helper()
"""


def _edges_to(extracted: dict, target: str) -> list[dict]:
    return [e for e in extracted["edges"] if e["target_name"] == target]


def test_three_calls_store_all_three_lines() -> None:
    edges = _edges_to(extract_python("pkg/mod.py", _THREE_CALLS), "helper")

    assert len(edges) == 1, "still ONE edge per (scope, target)"
    assert edges[0]["lines"] == [6, 8, 9]
    assert edges[0]["dropped_call_sites"] == 0


def test_javascript_calls_share_the_same_edge_shape() -> None:
    pytest.importorskip("tree_sitter_javascript")
    source = b"function f() {\n  g();\n  g();\n}\n"
    edges = _edges_to(extract_javascript("src/a.js", source), "g")

    assert [e["lines"] for e in edges] == [[2, 3]]


def test_calls_past_the_cap_are_counted_as_dropped(monkeypatch) -> None:
    monkeypatch.setattr(code_call_sites, "MAX_CALL_SITES_PER_EDGE", 2)
    edge = {"lines": [1], "dropped_call_sites": 0}
    for line in (2, 3, 4):
        add_call_site(edge, line)

    assert edge == {"lines": [1, 2], "dropped_call_sites": 2}


def test_metadata_is_scalar_and_round_trips_through_the_one_decoder() -> None:
    meta = call_site_metadata({"lines": [6, 8, 9], "dropped_call_sites": 4})

    assert all(isinstance(v, (str, int)) for v in meta.values())
    assert meta["call_line"] == 6 and meta["dropped_call_sites"] == 4
    assert json.loads(meta["call_lines"]) == [6, 8, 9]
    assert decode_edge_metadata(meta)["call_lines"] == [6, 8, 9]


def test_a_record_written_before_call_lines_decodes_to_its_single_site() -> None:
    assert decode_edge_metadata({"call_line": 3})["call_lines"] == [3]
    assert decode_edge_metadata({})["call_lines"] == []
    assert decode_edge_metadata({"call_lines": "not json", "call_line": 0})["call_lines"] == []


def test_extracted_edge_persists_every_line_and_reads_back_whole() -> None:
    """Extraction -> persisted metadata -> the decoder every reader uses."""
    edge = _edges_to(extract_python("pkg/mod.py", _THREE_CALLS), "helper")[0]
    resolved = ResolvedCall(target_id="pkg.mod.helper", origin="extracted", candidate_count=1)

    stored = _build_edge_metadata("pkg.mod.caller", edge, resolved, "pkg/mod.py")

    assert decode_edge_metadata(stored)["call_lines"] == [6, 8, 9]
