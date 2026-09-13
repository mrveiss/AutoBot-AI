# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The destructive-migration guard, proved in both directions (#15776).

Every fixture is synthetic. A guard seeded from the live set of destructive
migrations goes vacuous the moment the backlog is worked -- and this one reports
clean against the tree today, so "it passes" is evidence of nothing until it is
shown to fail on the shapes it exists to catch.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parent / "check_destructive_migration_marker.py"
_spec = importlib.util.spec_from_file_location("check_destructive_migration_marker", _MODULE_PATH)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def _migration(tmp_path: Path, body: str, name: str = "20260901_090_sample.py") -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


_ABOVE_FLOOR_UNMARKED = """
revision: str = "20260901_090"

def upgrade():
    op.drop_table("legacy")
"""

_ABOVE_FLOOR_MARKED = '''
"""Something. NO DATA LOSS: the table was never written by any release."""
revision: str = "20260901_090"

def upgrade():
    op.drop_table("legacy")
'''

_BELOW_FLOOR_UNMARKED = """
revision: str = "20260820_080"

def upgrade():
    op.drop_table("legacy")
"""

_ABOVE_FLOOR_NON_DESTRUCTIVE = """
revision: str = "20260901_090"

def upgrade():
    op.create_table("brand_new")
"""

_SUFFIXED_MARKED = '''
"""NO DATA LOSS: additive."""
revision: str = "20260826_086b"

def upgrade():
    op.drop_column("t", "c")
'''

_ALEMBIC_HEX_LOW = """
revision: str = "0a1b2c3d4e5f"

def upgrade():
    op.drop_table("legacy")
"""

_ALEMBIC_HEX_HIGH = """
revision: str = "a1b2c3d4e5f6"

def upgrade():
    op.drop_table("legacy")
"""

_BARE_NUMERIC = """
revision = "9"

def upgrade():
    op.drop_table("legacy")
"""

_NO_REVISION = """
def upgrade():
    op.drop_column("t", "c")
"""


class TestTheMarkerIsRequiredAboveTheFloor:
    def test_an_unmarked_destructive_migration_is_rejected(self, tmp_path):
        findings = guard.check(_migration(tmp_path, _ABOVE_FLOOR_UNMARKED))

        assert len(findings) == 1
        assert guard.MARKER in findings[0]

    def test_the_marked_form_is_accepted(self, tmp_path):
        """The contrast. Without it the guard could reject everything and pass."""
        assert guard.check(_migration(tmp_path, _ABOVE_FLOOR_MARKED)) == []

    def test_a_non_destructive_migration_needs_no_marker(self, tmp_path):
        assert guard.check(_migration(tmp_path, _ABOVE_FLOOR_NON_DESTRUCTIVE)) == []

    def test_a_letter_suffixed_revision_sorts_above_the_floor(self, tmp_path):
        """086b lands after 086 and before 087, and is judged accordingly."""
        assert guard.check(_migration(tmp_path, _SUFFIXED_MARKED)) == []

    @pytest.mark.parametrize("body", [_ABOVE_FLOOR_UNMARKED, _SUFFIXED_MARKED])
    def test_the_filename_is_never_consulted(self, tmp_path, body):
        """The `revision` string decides the verdict, so a misleading filename
        cannot mask a violation -- which is the whole reason this reads the
        authoritative value rather than parsing names."""

        def verdict(name: str) -> list[str]:
            # The filename appears in the message, for the operator; strip it so
            # the comparison is over the finding itself.
            return [f.split(": ", 1)[1] for f in guard.check(_migration(tmp_path, body, name=name))]

        assert verdict("zzz_not_a_migration_name.py") == verdict("20260901_090_sample.py")


class TestTheFloorExemptsHistory:
    def test_a_destructive_migration_below_the_floor_is_left_alone(self, tmp_path):
        """The 75 predating the convention are below a stated line, not exempt by silence."""
        assert guard.check(_migration(tmp_path, _BELOW_FLOOR_UNMARKED)) == []

    def test_the_two_pre_convention_ids_are_accepted(self, tmp_path):
        for revision in guard.PRE_CONVENTION:
            body = f'revision = "{revision}"\n\ndef upgrade():\n    op.drop_table("t")\n'
            assert guard.check(_migration(tmp_path, body)) == [], revision


class TestAnUnorderableRevisionFailsRatherThanSlipping:
    """Condition 3 structurally cannot judge a revision condition 2 cannot order.

    Lexical comparison is only correct for the dated shape. Measured against the
    floor: a bare `9` sorts ABOVE it because '9' > '2', and alembic's own default
    hex id sorts either side depending on its first character -- so a stock
    `alembic revision` migration would be silently exempted one time in eight.
    """

    @pytest.mark.parametrize(
        ("label", "body"),
        [
            ("alembic hex id sorting below the floor", _ALEMBIC_HEX_LOW),
            ("alembic hex id sorting above the floor", _ALEMBIC_HEX_HIGH),
            ("a bare numeric revision", _BARE_NUMERIC),
        ],
    )
    def test_an_undated_revision_is_rejected(self, tmp_path, label, body):
        findings = guard.check(_migration(tmp_path, body))

        assert len(findings) == 1, label
        assert "YYYYMMDD_NNN" in findings[0], "the message must name the convention, not the floor"

    def test_a_missing_revision_is_rejected_rather_than_skipped(self, tmp_path):
        """An input that cannot be read and reports clean is indistinguishable
        from a clean input."""
        findings = guard.check(_migration(tmp_path, _NO_REVISION))

        assert len(findings) == 1
        assert "revision" in findings[0]

    def test_the_two_failure_classes_carry_different_messages(self, tmp_path):
        """A missing marker and an unorderable revision are different defects."""
        unmarked = guard.check(_migration(tmp_path, _ABOVE_FLOOR_UNMARKED))[0]
        undated = guard.check(_migration(tmp_path, _ALEMBIC_HEX_LOW))[0]

        assert unmarked != undated
        assert guard.MARKER in unmarked and guard.MARKER not in undated


class TestReach:
    def test_the_repository_is_above_the_migration_floor(self):
        """A sweep that parses nothing reports clean; this is what separates them."""
        repo_root = Path(__file__).resolve().parents[2]
        migrations = sorted((repo_root / "autobot-backend" / "migrations" / "versions").glob("*.py"))

        assert len(migrations) >= guard.MIGRATION_FLOOR, f"only {len(migrations)} migrations reached"

    def test_the_live_tree_is_clean(self):
        assert guard.main([]) == 0

    def test_every_live_migration_has_a_readable_revision(self):
        """The condition the guard leans on, asserted over the real population."""
        repo_root = Path(__file__).resolve().parents[2]
        migrations = sorted((repo_root / "autobot-backend" / "migrations" / "versions").glob("*.py"))
        unreadable = [p.name for p in migrations if guard.revision_of(p.read_text(encoding="utf-8")) is None]

        assert unreadable == [], f"these carry no readable revision: {unreadable}"


class TestOnlyUpgradeCounts:
    """A `downgrade()` that drops a column is reversing an `upgrade()` that
    added one -- the model *should* still declare it, and treating that as a
    violation is how a guard earns its first `# noqa`.

    Measured on the live tree while building the cross-source check:
    `20260824_084_device_capability_scoping.py` has all three of its drops in
    `downgrade()`, and `MobileDevice` still declares all three columns.
    """

    def test_a_drop_only_in_downgrade_needs_no_marker(self, tmp_path):
        body = """
revision: str = "20260901_090"

def upgrade():
    op.add_column("t", sa.Column("c", sa.String()))

def downgrade():
    op.drop_column("t", "c")
"""
        assert guard.check(_migration(tmp_path, body)) == []

    def test_the_same_drop_in_upgrade_does_need_one(self, tmp_path):
        """The contrast: it is the function it sits in that decides."""
        body = """
revision: str = "20260901_090"

def upgrade():
    op.drop_column("t", "c")

def downgrade():
    op.add_column("t", sa.Column("c", sa.String()))
"""
        findings = guard.check(_migration(tmp_path, body))

        assert len(findings) == 1
        assert guard.MARKER in findings[0]


class TestTheCrossSourceColumnCheck:
    """The marker is a sentence a human writes; this is a fact about the code."""

    @pytest.fixture(autouse=True)
    def _synthetic_model_tree(self, monkeypatch):
        """The matcher is under test here, not the reach floor -- that has its
        own test below. Narrowing the roots and the floor keeps this suite from
        depending on the live model tree's size."""
        monkeypatch.setattr(guard, "MODEL_ROOTS", ("autobot-backend/models",))
        monkeypatch.setattr(guard, "MIN_MODEL_FILES", 1)
        guard._model_index.cache_clear()
        yield
        guard._model_index.cache_clear()

    def _model_tree(self, tmp_path, tablename: str, column: str, declaration: str | None = None) -> Path:
        root = tmp_path / "repo"
        models = root / "autobot-backend" / "models"
        models.mkdir(parents=True)
        body = declaration or f"    {column} = Column(String())"
        (models / "thing.py").write_text(
            "from sqlalchemy import Column, String\n\n"
            "class Thing(Base):\n"
            f'    __tablename__ = "{tablename}"\n'
            f"{body}\n",
            encoding="utf-8",
        )
        return root

    def test_dropping_a_column_the_model_still_declares_is_reported(self, tmp_path):
        repo_root = self._model_tree(tmp_path, "things", "still_used")
        body = '''
"""NO DATA LOSS: it says so, which is exactly why the sentence is not enough."""
revision: str = "20260901_090"

def upgrade():
    op.drop_column("things", "still_used")
'''
        findings = guard.check(_migration(tmp_path, body), repo_root)

        assert len(findings) == 1
        assert "things.still_used" in findings[0]
        assert "Thing" in findings[0], "the offending model must be named"

    def test_a_column_the_model_no_longer_declares_is_accepted(self, tmp_path):
        """The contrast, so the check cannot pass by reporting every drop."""
        repo_root = self._model_tree(tmp_path, "things", "something_else")
        body = '''
"""NO DATA LOSS: the model stopped writing it in the previous release."""
revision: str = "20260901_090"

def upgrade():
    op.drop_column("things", "still_used")
'''
        assert guard.check(_migration(tmp_path, body), repo_root) == []

    def test_a_same_named_column_on_a_different_table_is_not_a_match(self, tmp_path):
        """`name` and `status` exist on everything; the table ties them together."""
        repo_root = self._model_tree(tmp_path, "other_table", "name")
        body = '''
"""NO DATA LOSS."""
revision: str = "20260901_090"

def upgrade():
    op.drop_column("things", "name")
'''
        assert guard.check(_migration(tmp_path, body), repo_root) == []

    def test_the_two_checks_carry_different_messages(self, tmp_path):
        """A missing sentence and a column the release still writes are
        different defects, and only the second one loses data."""
        repo_root = self._model_tree(tmp_path, "things", "still_used")
        body = """
revision: str = "20260901_090"

def upgrade():
    op.drop_column("things", "still_used")
"""
        findings = guard.check(_migration(tmp_path, body), repo_root)

        assert len(findings) == 2
        assert any(guard.MARKER in f for f in findings)
        assert any("running release writes this column" in f for f in findings)


class TestTheModelScanMustHaveReach:
    """The cross-source check is only as good as the files it reads.

    With none, `models_still_declaring` finds no declarers and the data-loss
    check passes **having scanned nothing** -- a violation-bound floor one layer
    inside the guard, and the same defect this whole issue is about.
    """

    def _migration_dropping(self, tmp_path) -> Path:
        return _migration(
            tmp_path,
            '\n"""NO DATA LOSS."""\nrevision: str = "20260901_090"\n\ndef upgrade():\n    op.drop_column("t", "c")\n',
        )

    def test_a_missing_model_root_is_reported_not_silently_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(guard, "MODEL_ROOTS", ("does/not/exist",))
        guard._model_index.cache_clear()

        findings = guard.check(self._migration_dropping(tmp_path), tmp_path)

        assert len(findings) == 1
        assert "cannot run" in findings[0] and "does/not/exist" in findings[0]
        guard._model_index.cache_clear()

    def test_a_root_that_exists_but_holds_too_few_files_is_reported(self, tmp_path, monkeypatch):
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "one.py").write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(guard, "MODEL_ROOTS", ("models",))
        monkeypatch.setattr(guard, "MIN_MODEL_FILES", 5)
        guard._model_index.cache_clear()

        findings = guard.check(self._migration_dropping(tmp_path), tmp_path)

        assert len(findings) == 1
        assert "floor is 5" in findings[0]
        guard._model_index.cache_clear()

    def test_the_live_model_tree_clears_the_floor(self):
        """The floor means nothing if the real scan only just reaches it."""
        repo_root = Path(__file__).resolve().parents[2]
        guard._model_index.cache_clear()

        assert len(guard._model_files(repo_root)) >= guard.MIN_MODEL_FILES
        guard._model_index.cache_clear()


class TestRawSQLCountsAsDestructive:
    """`op.execute("ALTER TABLE t DROP COLUMN c")` contains none of the op names."""

    def test_raw_sql_drop_in_upgrade_needs_a_marker(self, tmp_path):
        body = """
revision: str = "20260901_090"

def upgrade():
    op.execute("ALTER TABLE things DROP COLUMN legacy")
"""
        findings = guard.check(_migration(tmp_path, body))

        assert len(findings) == 1
        assert guard.MARKER in findings[0]

    def test_raw_sql_that_drops_nothing_is_left_alone(self, tmp_path):
        """The contrast: it is DROP that matters, not raw SQL."""
        body = """
revision: str = "20260901_090"

def upgrade():
    op.execute("UPDATE things SET status = 'x'")
"""
        assert guard.check(_migration(tmp_path, body)) == []

    def test_raw_sql_drop_in_downgrade_is_left_alone(self, tmp_path):
        body = """
revision: str = "20260901_090"

def upgrade():
    op.execute("ALTER TABLE things ADD COLUMN c TEXT")

def downgrade():
    op.execute("ALTER TABLE things DROP COLUMN c")
"""
        assert guard.check(_migration(tmp_path, body)) == []


class TestTheMarkerMustBeInTheDocstring:
    def test_the_words_in_a_comment_do_not_satisfy_the_gate(self, tmp_path):
        """`MARKER in source` was satisfied by a comment, a column name, or a
        migration that merely mentions the convention."""
        body = """
revision: str = "20260901_090"

def upgrade():
    # NO DATA LOSS: asserting it in a comment is not stating it to the reader
    op.drop_table("legacy")
"""
        findings = guard.check(_migration(tmp_path, body))

        assert len(findings) == 1

    def test_the_docstring_form_is_accepted(self, tmp_path):
        body = '''
"""Drop the legacy table. NO DATA LOSS: nothing has written it since 081."""
revision: str = "20260901_090"

def upgrade():
    op.drop_table("legacy")
'''
        assert guard.check(_migration(tmp_path, body)) == []

    def test_every_live_marked_migration_still_passes(self):
        """The five that carry the marker put it where the policy says."""
        repo_root = Path(__file__).resolve().parents[2]
        versions = repo_root / "autobot-backend" / "migrations" / "versions"
        marked = [p for p in versions.glob("*.py") if guard.MARKER in p.read_text(encoding="utf-8")]

        assert marked, "precondition: some live migrations carry the marker"
        assert all(guard._marker_in_docstring(p.read_text(encoding="utf-8")) for p in marked)


class TestColumnDeclarationForms:
    """`_declared_columns` has branches the single-fixture suite never reached."""

    @pytest.fixture(autouse=True)
    def _synthetic_roots(self, monkeypatch):
        monkeypatch.setattr(guard, "MODEL_ROOTS", ("autobot-backend/models",))
        monkeypatch.setattr(guard, "MIN_MODEL_FILES", 1)
        guard._model_index.cache_clear()
        yield
        guard._model_index.cache_clear()

    def _tree(self, tmp_path, declaration: str) -> Path:
        root = tmp_path / "repo"
        models = root / "autobot-backend" / "models"
        models.mkdir(parents=True)
        (models / "thing.py").write_text(
            "from sqlalchemy.orm import mapped_column\n"
            "from sqlalchemy import Column, String\n\n"
            "class Thing(Base):\n"
            '    __tablename__ = "things"\n'
            f"{declaration}\n",
            encoding="utf-8",
        )
        return root

    _DROPS_TARGET = '''
"""NO DATA LOSS."""
revision: str = "20260901_090"

def upgrade():
    op.drop_column("things", "target")
'''

    @pytest.mark.parametrize(
        ("label", "declaration"),
        [
            ("Column bound to the attribute name", "    target = Column(String())"),
            ("mapped_column", "    target: Mapped[str] = mapped_column(String())"),
            ('Column("explicit_name")', '    other = Column("target", String())'),
        ],
    )
    def test_each_declaration_form_is_seen(self, tmp_path, label, declaration):
        findings = guard.check(_migration(tmp_path, self._DROPS_TARGET), self._tree(tmp_path, declaration))

        assert len(findings) == 1, label
        assert "things.target" in findings[0]

    def test_a_call_that_is_not_a_column_is_not_seen(self, tmp_path):
        """The contrast: any Call would match a looser implementation."""
        tree = self._tree(tmp_path, "    target = relationship('Other')")

        assert guard.check(_migration(tmp_path, self._DROPS_TARGET), tree) == []
