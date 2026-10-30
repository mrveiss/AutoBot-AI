# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One accessor for where a stored fact came from (#17527, #17618).

Five intake legs write provenance in five dialects (see `knowledge/provenance.py`). Every
consumer that wants an origin must go through `document_origin`, or it re-learns the dialects
and the next leg's vocabulary is a sixth thing to learn. A hand-rolled READ of a key that only
some dialects write -- `source_type`, `source_connector_id`, `connector_type`, `recording_id`,
`recording_filename`, `folder_id` -- is the marker. The bare `source` key is not: it is also a
category bucket and a trust-score input, which are other questions.

The detector reads the syntax tree: a `.get("<key>")`, a `["<key>"]` load or a `"<key>" in x`
test. A writer's dict literal or subscript store is not a read.

`_OTHER_QUESTIONS` is a ratchet: each entry reads a provenance key to answer something that is
NOT "where did this come from" (a visibility class, an ownership rule, a metrics label). It may
shrink; a new file does not join it without a reason, and an entry that no longer reads the key
fails, so the list cannot rot into an exemption nobody checks.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CANONICAL = "autobot-backend/knowledge/provenance.py"
_KEYS = frozenset(
    {"source_type", "source_connector_id", "connector_type", "recording_id", "recording_filename", "folder_id"}
)

#: Readers of a provenance key whose question is not "where did this come from".
_OTHER_QUESTIONS = {
    "autobot-backend/knowledge/ingest_sanitize.py": "the sanitizer's route label: a bounded metrics label, where an origin would be per-item",
    "autobot-backend/knowledge/ingestion_visibility.py": "which ownerless facts are visible to everyone (#16693): a visibility class",
    "autobot-backend/knowledge/ownership.py": "ownership rules keyed on how a fact entered",
    "autobot-backend/knowledge/fact_projection.py": "a projection's source_type/category grouping key",
    "autobot-backend/knowledge/facts.py": "dedupe: a connector item's unique key",
    "autobot-backend/api/knowledge_organization.py": "a count of facts per source_type",
    "autobot-backend/services/research/orchestrator.py": "the research result's own source_type, not a stored fact's",
    "autobot-backend/api/knowledge_verification.py": "a claim-source record's `source_type` field, defaulted for display",
    "autobot-backend/services/claim_verifier.py": "a claim-source record's `source_type` field, defaulted for display",
    "autobot-backend/knowledge/adapters/okf_adapter.py": "OKF frontmatter `type`: a document-kind field, not an origin",
}


def _is_metadata(receiver: ast.AST) -> bool:
    """True when the mapping read is a fact's metadata (`metadata`, `meta`, `r.metadata`, ...).

    Bounded by name because `"folder_id"` and `"source_type"` are also keys of config dicts,
    events and request bodies, none of which are a stored fact's provenance.
    """
    return "meta" in ast.unparse(receiver).lower()


def _reads_key(node: ast.AST) -> bool:
    """True when `node` reads one of the provenance keys from a fact's metadata."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"get", "pop"}:
        first = node.args[0] if node.args else None
        return isinstance(first, ast.Constant) and first.value in _KEYS and _is_metadata(node.func.value)
    if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
        return isinstance(node.slice, ast.Constant) and node.slice.value in _KEYS and _is_metadata(node.value)
    if isinstance(node, ast.Compare) and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops):
        left = node.left
        return isinstance(left, ast.Constant) and left.value in _KEYS and _is_metadata(node.comparators[0])
    return False


def _hand_rolled_reads(source: str) -> int:
    return sum(1 for node in ast.walk(ast.parse(source)) if _reads_key(node))


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "provenance-accessor-scan",
    discover=_population,
    # Mid-window, from REACH.window() at 2,510 files: (2210, 2510, 2360).
    floor=2604,  # mid-window: population 2754, window (2454, 2754)
    what="non-test python source",
    roots=("autobot-backend",),
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _readers() -> dict[str, int]:
    found: dict[str, int] = {}
    for rel in REACH.examined(repo_root()):
        text = (repo_root() / rel).read_text(encoding="utf-8")
        if not any(key in text for key in _KEYS):
            continue
        count = _hand_rolled_reads(text)
        if count:
            found[rel] = count
    return found


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a get", 'metadata.get("source_type")\n', 1),
        ("a get with default", 'metadata.get("connector_type", "x")\n', 1),
        ("a subscript load", 'meta["recording_id"]\n', 1),
        ("a membership test", 'if "folder_id" in meta: pass\n', 1),
        ("a chained read", 'r.metadata.get("connector_type")\n', 1),
        ("a config dict, not metadata", 'cfg.get("source_type", "mydrive")\n', 0),
        ("a writer's dict literal", 'meta = {"source_type": "transcript", "recording_id": 4}\n', 0),
        ("a subscript store", 'meta["source_type"] = "connector"\n', 0),
        ("the bare source key", 'metadata.get("source")\n', 0),
        ("a comment naming a key", '# metadata.get("source_type")\nx = 1\n', 0),
    ],
)
def test_the_matcher_tells_a_read_from_a_write(label: str, source: str, expected: int) -> None:
    assert _hand_rolled_reads(source) == expected, label


def test_the_scan_is_not_vacuous() -> None:
    """The ratchet's own entries read a key; a scan finding none of them looked at nothing."""
    assert len(_readers()) >= len(_OTHER_QUESTIONS) // 2


def _stray(readers: dict[str, int]) -> list[str]:
    return sorted(set(readers) - set(_OTHER_QUESTIONS) - {_CANONICAL})


def test_a_sixth_hand_rolled_read_is_caught() -> None:
    """Contrast pair: the real tree is clean, and the same tree plus one new reader is not."""
    assert _stray(_readers()) == []
    planted = {
        **_readers(),
        "autobot-backend/api/new_endpoint.py": _hand_rolled_reads('fact.metadata.get("source_type")\n'),
    }
    assert _stray(planted) == ["autobot-backend/api/new_endpoint.py"]


def test_no_new_consumer_hand_rolls_a_provenance_read() -> None:
    stray = _stray(_readers())
    assert not stray, (
        f"#17527: {stray} read a provenance-dialect key directly. Ask "
        "`knowledge.provenance.document_origin(metadata)` instead, or -- if the question is not "
        "'where did this come from' -- add the file to _OTHER_QUESTIONS with the question it asks."
    )


def test_no_exemption_outlives_its_read() -> None:
    gone = sorted(set(_OTHER_QUESTIONS) - set(_readers()))
    assert not gone, f"{gone} no longer read a provenance key; remove them from _OTHER_QUESTIONS"


def test_the_consumers_of_the_accessor_use_it() -> None:
    for rel in (
        "autobot-backend/llc/kb/context_builder.py",
        "autobot-backend/knowledge/search_components/agentic_search.py",
    ):
        assert "knowledge.provenance import" in (repo_root() / rel).read_text(encoding="utf-8"), rel
