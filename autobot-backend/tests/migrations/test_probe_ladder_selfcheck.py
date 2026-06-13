# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Probe-ladder self-check (#10001): the ladder must stay exact as the chain grows.

The baseline adoption logic AST-extracts ``op.create_table`` /
``op.add_column`` artifacts from every migration. That extraction is only
sound while table names are string literals. These tests fail the moment a
new migration breaks that contract or escapes the ladder — the permanent
guard the mission requires ("if the probe ladder cannot be kept strong,
strict mode must not ship").

No database needed — pure static analysis.
"""

import ast
from pathlib import Path

import pytest

pytest.importorskip("alembic", reason="probe-ladder self-checks need alembic")

from migrations.baseline import (  # noqa: E402 — after importorskip by design
    TIMESTAMPTZ_MARKERS,
    Artifacts,
    _script_directory,
    extract_artifacts,
    iter_upgrade_nodes,
)

VERSIONS_DIR = Path(__file__).resolve().parents[2] / "migrations" / "versions"


def _count_calls(path: Path, attr: str) -> int:
    """Count op.<attr> calls in the upgrade scope (downgrade excluded)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(
        1
        for node in iter_upgrade_nodes(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attr
    )


def test_every_revision_has_a_ladder_entry():
    """Every revision in the chain is known to the ladder."""
    script = _script_directory()
    artifacts = extract_artifacts(script)
    chain = {sc.revision for sc in script.walk_revisions()}
    assert set(artifacts) == chain
    assert len(chain) >= 59  # sanity: the whole chain was loaded (59 as of 054)


def test_create_table_calls_are_all_literal():
    """AST extraction must see every create_table call.

    A migration creating a table the ladder cannot see would let adoption
    stamp below it and crash the subsequent upgrade with DuplicateTable.
    create_table is therefore strictly literal-only.

    add_column may use helpers (e.g. 011's _add_timestamp_columns), but then
    the revision must still be observable through other artifacts — otherwise
    the bracket widens silently.
    """
    script = _script_directory()
    artifacts = extract_artifacts(script)
    for sc in script.walk_revisions():
        path = Path(sc.path)
        art = artifacts[sc.revision]
        assert len(art.tables) == _count_calls(path, "create_table"), (
            f"{path.name}: create_table call with a non-literal table name — "
            "the probe ladder cannot see it; use a string literal"
        )
        if len(art.columns) != _count_calls(path, "add_column"):
            observable = art.tables or art.columns or sc.revision in TIMESTAMPTZ_MARKERS
            assert observable, (
                f"{path.name}: add_column calls the ladder cannot extract AND "
                "no other artifact makes this revision observable — use "
                "literal names or add a structural marker"
            )


def test_known_anchor_revisions():
    """Spot-check ladder content against hand-verified chain facts."""
    artifacts = extract_artifacts(_script_directory())
    assert "users" in artifacts["001"].tables
    assert "process_runs" in artifacts["20260315_010"].tables
    assert "canvas" in artifacts["20260516_019"].tables
    assert "llc_work_items" in artifacts["20260523_022"].tables
    assert ("agent_wakeup_requests", "merged_count") in artifacts["20260522_021"].columns
    assert ("llc_work_items", "checkout_intent") in artifacts["20260611_054"].columns


def test_observability_coverage():
    """Nearly every revision must be observable (artifacts or type markers).

    Unobservable revisions widen adoption brackets (they re-run on adoption,
    so they must stay no-op/idempotent). If this list grows, either add a
    TIMESTAMPTZ/structural marker for the new revision or verify it is safe
    to re-run and extend the allowlist consciously.
    """
    script = _script_directory()
    artifacts = extract_artifacts(script)
    unobservable = {
        rev for rev, art in artifacts.items() if not art.tables and not art.columns and rev not in TIMESTAMPTZ_MARKERS
    }
    allowed = {
        "20260525_043",  # guarded enum-value add — idempotent re-run
        "20260526_045",  # agent_runtime_state data migration — idempotent UPDATE
        "20260608_052",  # merge revision — no-op
    }
    assert unobservable <= allowed, (
        f"new unobservable revisions: {sorted(unobservable - allowed)} — "
        "add a structural marker or consciously extend the allowlist"
    )


def test_artifacts_dataclass_shape():
    """extract_artifacts returns immutable artifact tuples."""
    artifacts = extract_artifacts(_script_directory())
    sample = artifacts["001"]
    assert isinstance(sample, Artifacts)
    assert isinstance(sample.tables, tuple)
    assert isinstance(sample.columns, tuple)
