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

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

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


# --- nothing is written when ANY id is malformed (#17300 review) ------------


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["uploaded_by_agent_id", "uploaded_by_user_id"])
async def test_a_malformed_uploader_id_leaves_no_file_behind(tmp_path, field):
    """The orphaned-file DoS: these two ids are not path segments, so
    `_storage_path` does not see them, and they used to be cast AFTER the write.
    A malformed one then raised with the file already on disk — repeatably.

    Asserts on the DIRECTORY, not on the exception: that a ValueError is raised
    was already true before the fix. What changed is that nothing was written.
    """
    from llc.services import attachment_service as svc_mod

    svc = svc_mod.AttachmentService()
    kwargs = {
        "company_id": _COMPANY,
        "work_item_id": _WORK_ITEM,
        "filename": "notes.txt",
        "content_type": "text/plain",
        "content": b"data",
        field: "not-a-uuid",
    }

    with patch.object(svc_mod, "_LOCAL_STORAGE_PATH", tmp_path):
        with pytest.raises(ValueError):
            await svc.upload(AsyncMock(), **kwargs)

    assert list(tmp_path.rglob("*")) == [], "a file was written before the id was validated"


@pytest.mark.asyncio
async def test_a_well_formed_upload_still_writes(tmp_path):
    """The contrast. Without it, a change that refused every upload would pass."""
    from llc.services import attachment_service as svc_mod

    svc = svc_mod.AttachmentService()
    with patch.object(svc_mod, "_LOCAL_STORAGE_PATH", tmp_path):
        await svc.upload(
            AsyncMock(),
            company_id=_COMPANY,
            work_item_id=_WORK_ITEM,
            filename="notes.txt",
            content_type="text/plain",
            content=b"data",
            uploaded_by_user_id=str(uuid.uuid4()),
        )

    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert len(written) == 1
    # to_thread: #7444's guard covers test files too, and a bare read_bytes in an
    # async test trips it.
    assert await asyncio.to_thread(written[0].read_bytes) == b"data"


# ---------------------------------------------------------------------------
# What routing containment through `validate_path` actually changed (#17302)
# ---------------------------------------------------------------------------


def test_a_percent_encoded_extension_is_decoded_before_the_write():
    """#17302 moved containment onto `validate_path`, and that is NOT behaviour-preserving here.

    Recorded because I claimed it was, on the evidence that all 16 tests above
    passed. They did, and that was not evidence: none of them uses a filename
    containing `%` or a non-ASCII character, so none exercises the input class
    that changed. A suite passing over inputs that do not reach the change
    says nothing about the change.

    `validate_path` runs `_canonicalize` -- multi-round percent-decode plus
    NFKC -- before resolving. The old local `is_relative_to` check did not.
    So an extension of `.%74xt` now persists as `.txt` where it previously
    persisted literally. Decoding before resolving is the house rule
    (THREAT_MODEL.md section 1) and a literal `%74` on disk was never wanted,
    so this is the better behaviour -- but it is a behaviour change, and it
    belongs in a test rather than in a claim.
    """
    dest = _storage_path(_COMPANY, _WORK_ITEM, _ATTACHMENT, "notes.%74xt")

    assert dest.name.endswith(".txt")
    assert "%" not in dest.name


@pytest.mark.parametrize("groups", [1, 2, 3, 4, 5])
def test_an_extension_that_decodes_into_a_traversal_is_refused_at_every_depth(groups: int):
    """Every traversal depth, because the depth decides WHERE it lands.

    This is the case a review caught and the single-depth version of this test
    missed. The extension `.／﹒﹒` repeated N times normalises to N `..`
    segments, and the file is built at `<root>/<company>/<item>/<name>`:

        1 group  -> <root>/<company>/<item>/x     same dir
        2        -> <root>/<company>/x            escapes the work item
        3        -> <root>/x                      escapes the tenant, ON the root
        4, 5     -> above <root>                  escapes the root entirely

    The original test used **five**, which climbs above the root and is refused
    by a root-level containment check. The reviewer used **three**, which stops
    exactly on the root -- so `is_relative_to(root)` was True and the file
    landed outside its tenant's directory while still "in the root". The
    assertion passed for the wrong reason and the defect sat one repetition
    away from it.

    Containment is now to the tenant directory, so every depth that leaves
    `<root>/<company>/<item>/` is refused, not only the ones that leave the root.
    """
    hostile = "notes." + "\uff0f\ufe52\ufe52" * groups

    with pytest.raises(ValueError):
        _storage_path(_COMPANY, _WORK_ITEM, _ATTACHMENT, hostile)


def test_a_well_formed_upload_still_lands_in_its_tenant_directory():
    """The contrast. Tenant-level containment must not refuse ordinary uploads."""
    dest = _storage_path(_COMPANY, _WORK_ITEM, _ATTACHMENT, "notes.txt")

    assert dest.parent == (_resolve_storage_root() / _COMPANY / _WORK_ITEM).resolve()
    assert dest.name.endswith(".txt")
