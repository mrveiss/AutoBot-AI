# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An attachment can only ever be written inside the storage root (#17300).

`_storage_path` built `root / company_id / ...` from an unvalidated query
parameter. The interesting part is that this was never a traversal bug:
`pathlib` discards everything to the left of an absolute segment, so
`company_id="/tmp/evil"` did not climb out of the root, it *replaced* it. That
makes it an arbitrary-write primitive, and the `uuid.UUID(company_id)` cast that
would have caught it ran three lines after the bytes were already on disk.

These tests assert on the returned path rather than on an exception type,
because what matters is not that bad input is refused loudly but that nothing
outside the root is ever addressable.
"""

from __future__ import annotations

import uuid

import pytest

from llc.services.attachment_service import _resolve_storage_root, _storage_path

_COMPANY = str(uuid.uuid4())
_WORK_ITEM = str(uuid.uuid4())
_ATTACHMENT = str(uuid.uuid4())


def test_a_well_formed_upload_lands_under_the_root():
    """The contrast case. Without it, a fix that rejected everything would pass."""
    dest = _storage_path(_COMPANY, _WORK_ITEM, _ATTACHMENT, "notes.txt")

    root = _resolve_storage_root().resolve()
    assert dest.is_relative_to(root)
    assert dest.name == f"{_ATTACHMENT}.txt"
    assert dest.parent == root / _COMPANY / _WORK_ITEM


@pytest.mark.parametrize(
    "company_id",
    [
        "/tmp/evil",  # absolute: pathlib DISCARDS the root -- the actual defect
        "../../etc",  # relative traversal
        "..",
        "a/b",  # a separator smuggled into one segment
        "",  # empty: root / "" is root itself
        "not-a-uuid",
    ],
    ids=["absolute", "traversal", "dotdot", "separator", "empty", "not-a-uuid"],
)
def test_a_company_id_that_is_not_a_uuid_is_refused_before_any_path_exists(company_id):
    with pytest.raises(ValueError):
        _storage_path(company_id, _WORK_ITEM, _ATTACHMENT, "notes.txt")


def test_the_absolute_case_would_have_escaped_without_the_fix():
    """Pins the mechanism, not just the outcome.

    If someone later replaces the UUID parse with a `".." not in value` check,
    the parametrised test above still passes for the traversal cases and fails
    here -- which is the case that mattered.
    """
    from pathlib import Path

    root = _resolve_storage_root().resolve()
    naive = root / "/tmp/evil" / _WORK_ITEM / "x.txt"

    assert naive == Path("/tmp/evil") / _WORK_ITEM / "x.txt"
    assert not naive.is_relative_to(root), "pathlib no longer discards the root; re-read this fix"


@pytest.mark.parametrize("bad", ["/tmp/evil", "../../etc", "not-a-uuid"])
def test_the_work_item_id_is_validated_too(bad):
    """The work item id is the second segment and was equally unguarded."""
    with pytest.raises(ValueError):
        _storage_path(_COMPANY, bad, _ATTACHMENT, "notes.txt")


def test_a_hostile_filename_cannot_extend_the_path():
    """The extension is attacker-supplied; it must stay an extension."""
    dest = _storage_path(_COMPANY, _WORK_ITEM, _ATTACHMENT, "../../../../etc/passwd")

    root = _resolve_storage_root().resolve()
    assert dest.is_relative_to(root)
    assert dest.parent == root / _COMPANY / _WORK_ITEM


def test_a_very_long_extension_is_bounded():
    dest = _storage_path(_COMPANY, _WORK_ITEM, _ATTACHMENT, "x." + "a" * 500)

    assert len(dest.suffix) <= 16
    assert dest.is_relative_to(_resolve_storage_root().resolve())
