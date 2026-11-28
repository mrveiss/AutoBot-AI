# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The workspace-lease model and migration 097 declare the same index (#16818).

093 created ``uq_llc_workspace_leases_path`` as a table-wide UNIQUE while the model's own
comment on that column said *live* leases. The constraint and the comment disagreed, and a
path could be leased exactly once in the lifetime of an installation.

097 fixes the schema. The first version of this check compared the model to **literals
written in the test**, which meant editing 097 left it green — the divergence it exists to
catch could return through the file it was supposed to be watching. So both sides are read
from their own files here, and neither is restated.

The predicate is also compared exactly, not by substring: ``released_at IS NULL`` is a
substring of ``released_at IS NULL AND expires_at > now()``, which is both a divergence and
impossible as a partial index, and a substring check would pass it.
"""

import re
from pathlib import Path

from repo_tests._paths import repo_root

_MODEL = Path("autobot-backend/llc/models/workspace_lease.py")
_MIGRATION = Path("autobot-backend/migrations/versions/20260928_097_workspace_lease_live_path_unique.py")


def _read(relative: Path) -> str:
    path = repo_root() / relative
    assert path.is_file(), f"{relative} has moved; this guard reads it by path"
    return path.read_text(encoding="utf-8")


def _quoted(source: str, pattern: str) -> str:
    """The single captured quoted value of *pattern*, or fail saying what was searched."""
    match = re.search(pattern, source)
    assert match, f"no match for {pattern!r} — the declaration has moved or changed shape"
    return match.group(1)


def _model_index() -> tuple[str, str]:
    source = _read(_MODEL)
    name = _quoted(source, r'sa\.Index\(\s*"([^"]+)"')
    predicate = _quoted(source, r'postgresql_where=sa\.text\("([^"]+)"\)')
    return name, predicate


def _migration_index() -> tuple[str, str]:
    source = _read(_MIGRATION)
    name = _quoted(source, r'_NEW_INDEX\s*=\s*"([^"]+)"')
    predicate = _quoted(source, r'postgresql_where=sa\.text\("([^"]+)"\)')
    return name, predicate


class TestTheModelAndTheMigrationAgree:
    """A database built from the models must get the shape alembic builds."""

    def test_the_index_name_is_the_same_in_both(self):
        model_name, _ = _model_index()
        migration_name, _ = _migration_index()
        assert model_name == migration_name

    def test_the_partial_predicate_is_identical_not_merely_similar(self):
        _, model_predicate = _model_index()
        _, migration_predicate = _migration_index()
        assert model_predicate == migration_predicate, (
            "model and migration predicates differ; a create_all database and an alembic "
            "database would then enforce different rules on the same table"
        )

    def test_the_predicate_cannot_reference_now(self):
        """A partial index predicate must be immutable.

        ``is_live()`` is ``released_at IS NULL AND expires_at > now``, and this index can
        only express the first half — Postgres rejects a volatile function in a partial
        index, so a predicate that grew a ``now()`` would fail at migration time on a real
        database and pass every test that only compared strings.
        """
        _, predicate = _migration_index()
        assert "now" not in predicate.lower()

    def test_the_old_table_wide_unique_is_not_reintroduced_by_the_model(self):
        """The original defect, watched at its source: `unique=True` on the column."""
        source = _read(_MODEL)
        path_line = next(line for line in source.splitlines() if line.strip().startswith("path:"))
        assert "unique=True" not in path_line, "a table-wide UNIQUE on path burns the directory on its first release"
