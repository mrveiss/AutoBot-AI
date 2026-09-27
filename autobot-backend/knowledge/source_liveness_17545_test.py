#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Source-liveness detection (#17545).

The whole value of this module is a distinction, so the tests are mostly about
which inputs must **not** collapse into each other:

* *gone* vs *could not reach* -- an unmounted share answers ENOENT for every
  path beneath it, so a missing file whose parent is also unresolvable is
  evidence of nothing.
* *did not look* vs *looked and found nothing* -- `never_checked` and
  `no_locator` are their own states, because a retention decision made on a
  number that merged them would act on facts nobody has examined.
* *observation* vs *event* -- no sequence of probe outcomes may produce `gone`.
  That one is asserted by walking the module's own AST as well as its behaviour,
  because "the probe must never write this column" is a property a reviewer
  cannot re-check on every future edit.

The permission case is skipped under euid 0 rather than asserted, and says so:
root ignores the mode bits, so the assertion would pass for the wrong reason,
which is worse than not running.
"""

from __future__ import annotations

import ast
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from knowledge.source_liveness import (
    LOCATOR_KEY,
    PROBE_ABSENT,
    PROBE_OUTCOMES,
    PROBE_PARENT_UNRESOLVABLE,
    PROBE_RESOLVED,
    PROBE_UNREADABLE,
    SOURCE_STATES,
    STATE_ABSENT,
    STATE_GONE,
    STATE_NEVER_CHECKED,
    STATE_NO_LOCATOR,
    STATE_RESOLVED,
    STATE_UNREACHABLE,
    _census_rows,
    _parent_resolves,
    apply_observation,
    derive_source_state,
    ingest_class_of,
    locator_of,
    probe_path,
    state_of,
)
from models.knowledge_fact import KnowledgeFact

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
EARLIER = NOW - timedelta(days=7)

#: The only columns a probe may write. `source_gone_at` is deliberately absent.
OBSERVATION_COLUMNS = {
    "source_checked_at",
    "source_seen_at",
    "source_last_probe",
    "source_check_failures",
}


def _fact(**metadata) -> KnowledgeFact:
    """An unsaved row, which is how a never-probed fact actually looks.

    `source_check_failures` has a server default, so on an instance that has
    never been flushed it is None -- the state the increment has to survive.
    """
    return KnowledgeFact(id="fact-1", content="c", metadata_json=dict(metadata))


class TestProbeOutcomes:
    """One look at one locator, and what it is allowed to conclude."""

    def test_a_present_file_resolves(self, tmp_path: Path) -> None:
        target = tmp_path / "doc.pdf"
        target.write_text("x", encoding="utf-8")
        assert probe_path(str(target)) == PROBE_RESOLVED

    def test_a_missing_file_with_a_present_parent_is_absent(self, tmp_path: Path) -> None:
        """The only outcome that is positive evidence of absence."""
        assert probe_path(str(tmp_path / "deleted.pdf")) == PROBE_ABSENT

    def test_a_missing_file_under_a_missing_parent_is_not_evidence(self, tmp_path: Path) -> None:
        """The unmounted-share case: ENOENT for everything beneath the mount.

        Reported as `parent_unresolvable`, never `absent` -- this is the input
        that would otherwise let a retention sweep delete a document that was on
        disk the whole time.
        """
        assert probe_path(str(tmp_path / "unmounted" / "doc.pdf")) == PROBE_PARENT_UNRESOLVABLE

    def test_a_dangling_symlink_is_absent(self, tmp_path: Path) -> None:
        """The document is the target, and `os.stat` follows the link."""
        link = tmp_path / "link.pdf"
        link.symlink_to(tmp_path / "never-existed.pdf")
        assert probe_path(str(link)) == PROBE_ABSENT

    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the mode bits, so this would pass for the wrong reason")
    def test_an_unreadable_parent_is_not_evidence(self, tmp_path: Path) -> None:
        """EACCES means the probe could not see, not that the file is gone."""
        closed = tmp_path / "closed"
        closed.mkdir()
        target = closed / "doc.pdf"
        target.write_text("x", encoding="utf-8")
        closed.chmod(0o000)
        try:
            assert probe_path(str(target)) == PROBE_UNREADABLE
        finally:
            closed.chmod(0o700)

    @pytest.mark.parametrize("path", [None, "", "   ", "relative/doc.pdf", "./doc.pdf"])
    def test_an_unusable_locator_is_never_evidence_of_absence(self, path) -> None:
        """A relative locator would be read against the backend's own cwd."""
        assert probe_path(path) == PROBE_UNREADABLE

    def test_a_child_of_a_regular_file_is_not_evidence_of_absence(self, tmp_path: Path) -> None:
        """#17615 review: the case a bare parent `stat` called `absent`.

        `/some-file/child` raises ENOTDIR, which is an absence errno, and the
        parent then stats fine because it exists -- so the old form reported
        positive evidence that a document had been deleted, for a locator that
        was simply malformed.
        """
        regular = tmp_path / "not-a-dir.pdf"
        regular.write_text("x", encoding="utf-8")
        assert probe_path(str(regular / "child.pdf")) == PROBE_PARENT_UNRESOLVABLE

    def test_a_regular_file_is_not_a_resolvable_parent(self, tmp_path: Path) -> None:
        regular = tmp_path / "f.txt"
        regular.write_text("x", encoding="utf-8")
        assert _parent_resolves(str(tmp_path / "child")) is True
        assert _parent_resolves(str(regular / "child")) is False

    def test_a_directory_is_not_absent(self, tmp_path: Path) -> None:
        """A locator that resolves to a directory still resolves."""
        assert probe_path(str(tmp_path)) == PROBE_RESOLVED


class TestApplyObservation:
    """What one probe writes, and what it must leave alone."""

    def test_a_resolve_records_the_sighting(self) -> None:
        row = _fact(**{LOCATOR_KEY: "/srv/doc.pdf"})
        apply_observation(row, PROBE_RESOLVED, now=NOW)
        assert (row.source_seen_at, row.source_checked_at) == (NOW, NOW)
        assert row.source_last_probe == PROBE_RESOLVED
        assert row.source_check_failures == 0

    def test_a_failure_counts_from_an_unflushed_row(self) -> None:
        """`source_check_failures` is None until the server default applies."""
        row = _fact(**{LOCATOR_KEY: "/srv/doc.pdf"})
        apply_observation(row, PROBE_ABSENT, now=NOW)
        assert row.source_check_failures == 1

    def test_a_failure_leaves_the_last_sighting_intact(self) -> None:
        """A later failure does not un-observe an earlier success."""
        row = _fact(**{LOCATOR_KEY: "/srv/doc.pdf"})
        apply_observation(row, PROBE_RESOLVED, now=EARLIER)
        apply_observation(row, PROBE_PARENT_UNRESOLVABLE, now=NOW)
        assert row.source_seen_at == EARLIER
        assert row.source_checked_at == NOW
        assert row.source_check_failures == 1

    def test_failures_accumulate_and_a_success_resets_them(self) -> None:
        row = _fact(**{LOCATOR_KEY: "/srv/doc.pdf"})
        for _ in range(3):
            apply_observation(row, PROBE_ABSENT, now=NOW)
        assert row.source_check_failures == 3
        apply_observation(row, PROBE_RESOLVED, now=NOW)
        assert row.source_check_failures == 0

    @pytest.mark.parametrize("outcome", PROBE_OUTCOMES)
    def test_no_outcome_ever_marks_a_source_gone(self, outcome: str) -> None:
        """`source_gone_at` is an event. A probe may not write one."""
        row = _fact(**{LOCATOR_KEY: "/srv/doc.pdf"})
        for _ in range(10):
            apply_observation(row, outcome, now=NOW)
        assert row.source_gone_at is None


class TestDerivedState:
    """The states a consumer reads, and the pairs that must stay distinct."""

    def test_never_checked_is_not_unreachable(self) -> None:
        """*Did not look* is a different answer from *looked and could not*."""
        never = derive_source_state(has_locator=True, checked_at=None, last_probe=None, gone_at=None)
        looked = derive_source_state(has_locator=True, checked_at=NOW, last_probe=PROBE_UNREADABLE, gone_at=None)
        assert never == STATE_NEVER_CHECKED
        assert looked == STATE_UNREACHABLE
        assert never != looked

    def test_no_locator_is_its_own_state(self) -> None:
        """Nothing to probe is not the same as probed and fine."""
        assert (
            derive_source_state(has_locator=False, checked_at=None, last_probe=None, gone_at=None) == STATE_NO_LOCATOR
        )

    def test_absent_is_distinct_from_unreachable(self) -> None:
        assert derive_source_state(has_locator=True, checked_at=NOW, last_probe=PROBE_ABSENT, gone_at=None) == (
            STATE_ABSENT
        )
        assert derive_source_state(
            has_locator=True, checked_at=NOW, last_probe=PROBE_PARENT_UNRESOLVABLE, gone_at=None
        ) == (STATE_UNREACHABLE)

    def test_a_resolve_reads_as_resolved(self) -> None:
        assert derive_source_state(has_locator=True, checked_at=NOW, last_probe=PROBE_RESOLVED, gone_at=None) == (
            STATE_RESOLVED
        )

    def test_gone_comes_only_from_the_event(self) -> None:
        """Even a resolving probe cannot un-witness a deletion."""
        assert (
            derive_source_state(has_locator=True, checked_at=NOW, last_probe=PROBE_RESOLVED, gone_at=NOW) == STATE_GONE
        )

    def test_an_unknown_probe_value_is_not_evidence(self) -> None:
        """A value written by a future version must not read as absence."""
        assert derive_source_state(has_locator=True, checked_at=NOW, last_probe="something_new", gone_at=None) == (
            STATE_UNREACHABLE
        )

    def test_state_of_a_row_agrees_with_the_derivation(self) -> None:
        row = _fact(**{LOCATOR_KEY: "/srv/doc.pdf"})
        assert state_of(row) == STATE_NEVER_CHECKED
        apply_observation(row, PROBE_ABSENT, now=NOW)
        assert state_of(row) == STATE_ABSENT

    def test_a_row_without_a_locator_reads_as_no_locator(self) -> None:
        assert state_of(_fact(source="manual")) == STATE_NO_LOCATOR


class TestLocatorAndIngestClass:
    """Reading the two metadata keys the detector depends on."""

    def test_the_watch_folder_locator_is_found(self) -> None:
        assert locator_of({LOCATOR_KEY: "/srv/kb/doc.pdf"}) == "/srv/kb/doc.pdf"

    @pytest.mark.parametrize("metadata", [None, {}, {LOCATOR_KEY: ""}, {LOCATOR_KEY: "   "}, {LOCATOR_KEY: 7}])
    def test_a_missing_or_unusable_locator_is_none(self, metadata) -> None:
        assert locator_of(metadata) is None

    def test_the_ingest_class_is_the_policy_axis(self) -> None:
        assert ingest_class_of({"source": "watch_folder"}) == "watch_folder"

    @pytest.mark.parametrize("metadata", [None, {}, {"source": ""}, {"source": None}])
    def test_an_unnamed_ingest_class_is_explicit(self, metadata) -> None:
        """Explicitly "unknown", not a silent empty key -- a census needs a bucket."""
        assert ingest_class_of(metadata) == "unknown"


class TestCensus:
    """The #17538 measurement: no two buckets may collapse."""

    ROWS = [
        # (metadata, checked_at, last_probe, gone_at) -- the RAW metadata, so the
        # census decides locator and ingest class with the same predicates the
        # row read uses (#17615 review).
        ({"source": "watch_folder", LOCATOR_KEY: "/srv/a.pdf"}, NOW, PROBE_RESOLVED, None),
        ({"source": "watch_folder", LOCATOR_KEY: "/srv/b.pdf"}, NOW, PROBE_ABSENT, None),
        ({"source": "watch_folder", LOCATOR_KEY: "/srv/c.pdf"}, NOW, PROBE_PARENT_UNRESOLVABLE, None),
        ({"source": "watch_folder", LOCATOR_KEY: "/srv/d.pdf"}, None, None, None),
        ({"source": "watch_folder", LOCATOR_KEY: "/srv/e.pdf"}, NOW, PROBE_ABSENT, NOW),
        ({"source": "uploads"}, None, None, None),
    ]

    def test_every_state_is_counted_once(self) -> None:
        census = _census_rows(self.ROWS)
        assert census["total"] == len(self.ROWS)
        assert census["states"] == {
            STATE_RESOLVED: 1,
            STATE_ABSENT: 1,
            STATE_UNREACHABLE: 1,
            STATE_NEVER_CHECKED: 1,
            STATE_GONE: 1,
            STATE_NO_LOCATOR: 1,
        }

    def test_never_checked_is_not_folded_into_anything(self) -> None:
        """The bucket a retention decision must not mistake for evidence."""
        census = _census_rows(self.ROWS)
        assert census["states"][STATE_NEVER_CHECKED] == 1
        assert census["states"][STATE_ABSENT] == 1

    def test_counts_split_by_ingest_class(self) -> None:
        census = _census_rows(self.ROWS)
        assert census["by_ingest_class"]["watch_folder"][STATE_ABSENT] == 1
        assert census["by_ingest_class"]["uploads"][STATE_NO_LOCATOR] == 1
        assert census["by_ingest_class"]["watch_folder"][STATE_NO_LOCATOR] == 0

    def test_an_unnamed_class_gets_its_own_bucket(self) -> None:
        census = _census_rows([({LOCATOR_KEY: "/srv/x.pdf"}, None, None, None)])
        assert census["by_ingest_class"]["unknown"][STATE_NEVER_CHECKED] == 1

    def test_a_row_with_no_metadata_at_all_is_still_counted(self) -> None:
        census = _census_rows([(None, None, None, None)])
        assert census["total"] == 1
        assert census["by_ingest_class"]["unknown"][STATE_NO_LOCATOR] == 1

    def test_an_empty_table_reports_zero_rather_than_nothing(self) -> None:
        """A census over no facts must still name every bucket."""
        census = _census_rows([])
        assert census["total"] == 0
        assert set(census["states"]) == {
            STATE_RESOLVED,
            STATE_ABSENT,
            STATE_UNREACHABLE,
            STATE_NEVER_CHECKED,
            STATE_GONE,
            STATE_NO_LOCATOR,
        }


class TestTheCensusAgreesWithTheRowRead:
    """The `.astext` divergence (#17615 review): SQL coerced, Python did not.

    `metadata_json[...].astext` renders a JSON number as a string, so a numeric
    `file_path` of `7` arrived as `"7"` -- truthy, therefore a locator -- while
    `locator_of` rejects any non-string and `state_of` called the same row
    `no_locator`. A numeric `source` opened a `"7"` bucket that `ingest_class_of`
    defines as `"unknown"`. One question answered two ways, in one module.

    The census now takes raw metadata and applies those two predicates, so every
    case below is a *table* of the agreement rather than a re-test of SQL.
    """

    @pytest.mark.parametrize("bad_locator", [7, 0, 1.5, True, [], {}, "", "   ", None])
    def test_a_non_string_locator_is_no_locator_in_both(self, bad_locator) -> None:
        metadata = {LOCATOR_KEY: bad_locator, "source": "watch_folder"}
        census = _census_rows([(metadata, NOW, PROBE_RESOLVED, None)])
        assert locator_of(metadata) is None
        assert state_of(_fact(**metadata)) == STATE_NO_LOCATOR
        assert census["states"][STATE_NO_LOCATOR] == 1
        assert census["states"][STATE_RESOLVED] == 0

    @pytest.mark.parametrize("bad_class", [7, 0, 1.5, True, [], {}, "", "   ", None])
    def test_a_non_string_ingest_class_buckets_as_unknown_in_both(self, bad_class) -> None:
        metadata = {LOCATOR_KEY: "/srv/a.pdf", "source": bad_class}
        census = _census_rows([(metadata, NOW, PROBE_RESOLVED, None)])
        assert ingest_class_of(metadata) == "unknown"
        assert list(census["by_ingest_class"]) == ["unknown"]
        assert census["by_ingest_class"]["unknown"][STATE_RESOLVED] == 1

    def test_the_census_state_is_the_row_state_for_every_row(self) -> None:
        """Whatever the census counts, `state_of` says of the same row."""
        rows = [
            ({LOCATOR_KEY: "/srv/a.pdf"}, NOW, PROBE_RESOLVED, None),
            ({LOCATOR_KEY: 7}, NOW, PROBE_RESOLVED, None),
            ({LOCATOR_KEY: "/srv/b.pdf"}, NOW, PROBE_ABSENT, None),
            ({LOCATOR_KEY: "/srv/c.pdf"}, None, None, None),
            ({}, None, None, None),
        ]
        tallied = {state: 0 for state in SOURCE_STATES}
        for metadata, checked_at, last_probe, gone_at in rows:
            fact = _fact(**metadata)
            fact.source_checked_at = checked_at
            fact.source_last_probe = last_probe
            fact.source_gone_at = gone_at
            tallied[state_of(fact)] += 1
        assert _census_rows(rows)["states"] == tallied


class TestTheModuleCannotActOnAFact:
    """Source-level guards for the two properties a review cannot re-check.

    #17545's acceptance says no path deletes or rewrites a fact because its
    source vanished, and that the probe never writes the event column. Both are
    properties of the whole module rather than of one call, so they are asserted
    against its AST -- a future edit that breaks either fails here instead of
    passing review on a reader's memory.
    """

    @staticmethod
    def _tree() -> ast.Module:
        source = Path(__file__).with_name("source_liveness.py").read_text(encoding="utf-8")
        return ast.parse(source)

    def _stored_attributes(self) -> set:
        stored = set()
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
                stored.add(node.attr)
        return stored

    def test_only_the_observation_columns_are_written(self) -> None:
        assert self._stored_attributes() <= OBSERVATION_COLUMNS

    def test_the_event_column_is_never_assigned(self) -> None:
        """Reading `source_gone_at` is required; writing it is #17546's alone."""
        assert "source_gone_at" not in self._stored_attributes()

    def test_nothing_deletes(self) -> None:
        """No delete of any shape -- a vanished source is marked, never swept.

        Removing stored data is proposed by an agent and approved by a human
        through the review queue (#17038); this module reports, it does not act.
        """
        called = set()
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Call):
                target = node.func
                if isinstance(target, ast.Name):
                    called.add(target.id)
                elif isinstance(target, ast.Attribute):
                    called.add(target.attr)
        assert not {"delete", "sql_delete", "remove", "unlink", "rmtree"} & called

    def test_the_probe_does_not_touch_the_filesystem_beyond_stat(self) -> None:
        """A liveness probe reads metadata, never contents -- a 2GB video's
        source is checked at the same cost as a text file's."""
        used = {
            node.func.attr
            for node in ast.walk(self._tree())
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert not {"open", "read_bytes", "read_text", "walk", "listdir", "scandir"} & used
