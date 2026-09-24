# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A work product's `storage_path` cannot name a file outside the LLC root (#17302).

`storage_path` is a free-form optional string on the agent request model
(`llc/api/agent_api.py`), stored unvalidated by `WorkProductService.create` and
opened later by the ingestor. Nothing in this codebase ever produces one -- the
field is only ever set from a caller's request body -- so an authenticated agent
could name any path on the host and have its contents read into the knowledge
index, where they become retrievable.

The only gate between the two was `_is_text_path`, an extension allowlist. That
is the near-miss worth naming: validation existed, and it was not the validation
that was needed. `.yaml`, `.toml`, `.ini`, `.cfg`, `.py`, `.sh` and `.sql` are all
allowlisted, so "is this a shape we can parse" was answering "are we allowed to
read this".
The two questions do not overlap at all.

Why these assert on `open` rather than on a return value: a refusal that
returns None after reading the file is indistinguishable from one that never
read it, if you only check the result. The property is that the bytes are never
touched, so the tests check that the bytes are never touched.
"""

from __future__ import annotations

import builtins
import pathlib
import uuid
from typing import List, Optional

import pytest

from llc.kb.artifact_ingestor import ArtifactIngestor, _contained_storage_path


def _plant(path: pathlib.Path, text: str) -> pathlib.Path:
    """Create a file for a test to point at.

    A plain sync function on purpose: these writes are arrangement, not the
    behaviour under test, and #7444's guard correctly refuses blocking I/O
    inside an `async def`. Keeping the setup out of the coroutine satisfies it
    without a `# noqa`, which would have claimed something untrue -- the calls
    do not run in a thread.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class _Product:
    """The two fields `_resolve_text` reads, and an id for the log line."""

    def __init__(self, storage_path: Optional[str]) -> None:
        self.id = uuid.uuid4()
        self.content_text = None
        self.storage_path = storage_path


@pytest.fixture()
def llc_root(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    root = tmp_path / "llc-storage"
    root.mkdir()
    monkeypatch.setenv("LLC_STORAGE_PATH", str(root))
    return root


@pytest.fixture()
def opened(monkeypatch: pytest.MonkeyPatch) -> List[str]:
    """Every path handed to `open`, so "was it read" is answerable directly."""
    seen: List[str] = []
    real_open = builtins.open

    def spy(file, *args, **kwargs):
        seen.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    return seen


@pytest.mark.asyncio
async def test_an_absolute_path_outside_the_root_is_never_opened(
    llc_root: pathlib.Path, tmp_path: pathlib.Path, opened: List[str]
) -> None:
    """The defect proper, with an allowlisted extension so only containment can refuse it."""
    secret = _plant(tmp_path / "elsewhere" / "credentials.yaml", "token: hunter2\n")

    text = await ArtifactIngestor()._resolve_text(_Product(str(secret)))

    assert text is None, "the file outside the storage root must not be ingested"
    assert str(secret) not in opened, (
        "the file was opened before being refused -- a refusal after the read still leaks it "
        "into memory and into any log that echoes content"
    )


@pytest.mark.asyncio
async def test_a_traversal_out_of_the_root_is_never_opened(
    llc_root: pathlib.Path, tmp_path: pathlib.Path, opened: List[str]
) -> None:
    """The relative form, which an absolute-path check alone would miss."""
    secret = _plant(tmp_path / "elsewhere" / "config.toml", "key = 'value'\n")
    traversal = str(llc_root / ".." / "elsewhere" / "config.toml")

    text = await ArtifactIngestor()._resolve_text(_Product(traversal))

    assert text is None
    assert not any("elsewhere" in path for path in opened)


@pytest.mark.asyncio
async def test_an_in_root_product_still_ingests(llc_root: pathlib.Path) -> None:
    """The contrast, without which "refuses everything" passes every test above."""
    product_file = _plant(llc_root / "tenant" / "artifact.md", "# real content\n")

    text = await ArtifactIngestor()._resolve_text(_Product(str(product_file)))

    assert text == "# real content\n"


@pytest.mark.asyncio
async def test_a_row_stored_before_the_fix_still_ingests_when_it_is_in_root(
    llc_root: pathlib.Path,
) -> None:
    """#17302 AC5. The fix must not orphan rows that were always legitimate.

    Containment is decided by where the path points, not by when the row was
    written, so an existing in-root row is indistinguishable from a new one --
    which is the property that makes this safe to deploy without a migration.
    """
    legacy = _plant(llc_root / "legacy-company" / "legacy-item" / "old.txt", "written before #17302\n")

    assert await ArtifactIngestor()._resolve_text(_Product(str(legacy))) == "written before #17302\n"


def test_the_returned_string_is_the_validated_one(llc_root: pathlib.Path) -> None:
    """THREAT_MODEL section 1: the validated string is the string used.

    Pinned because the bypass this shape invites is validating one path and then
    opening something rebuilt from the original input. The helper returns the
    resolved path so the caller cannot reach for the raw one, and this asserts
    the redundant components are actually gone from what it hands back.
    """
    target = _plant(llc_root / "sub" / "file.txt", "x\n")
    noisy = str(llc_root / "sub" / "." / "file.txt")

    contained = _contained_storage_path(noisy, "product-1")

    assert contained == str(target.resolve())
    assert "/./" not in contained


def test_an_extension_check_is_not_a_containment_check(llc_root: pathlib.Path) -> None:
    """The two gates answer different questions, and one used to stand in for the other.

    `_is_text_path` says yes to a path it has no business reading; that is not a
    bug in `_is_text_path`, it is the reason it cannot be the only gate.
    """
    from llc.kb.artifact_ingestor import _is_text_path

    outsider = "/etc/anything.yaml"
    assert _is_text_path(outsider) is True, "premise: the allowlist admits it"
    assert _contained_storage_path(outsider, "product-1") is None, "and containment refuses it"


@pytest.mark.asyncio
async def test_the_path_opened_is_the_decoded_one_not_the_raw_string(llc_root: pathlib.Path) -> None:
    """THREAT_MODEL section 1, asserted at the CALL SITE rather than on the helper.

    Written because a mutation found the gap: reverting the `open()` back to
    `product.storage_path` left every other test in this file passing. They all
    used paths whose raw and validated forms are identical, so "which string is
    opened" was never observable -- the helper was tested, the wiring was not.

    A percent-encoded in-root path makes the two forms differ. `_canonicalize`
    decodes `%73ub` to `sub` before resolving (decode-before-resolve is the
    house rule), so the validated path exists and the raw string does not. Open
    the wrong one and this returns None instead of the content.
    """
    target = _plant(llc_root / "sub" / "file.txt", "real content\n")
    encoded = str(llc_root / "%73ub" / "file.txt")

    assert not pathlib.Path(encoded).exists(), "premise: the raw string names nothing on disk"

    assert await ArtifactIngestor()._resolve_text(_Product(encoded)) == "real content\n"


@pytest.mark.asyncio
async def test_a_refusal_is_a_clean_skip_not_a_swallowed_exception(
    llc_root: pathlib.Path, tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The explicit `if contained is None` guard, which a mutation showed was unpinned.

    Without it, a refused path falls through to `open(None)`, raises TypeError,
    and is swallowed by the broad `except Exception` -- same return value, so
    every assertion on the result still passed. The difference is entirely in
    what an operator sees: a warning naming containment and #17302, versus an
    exception traceback saying the file could not be read, which reads like a
    missing file rather than a rejected one and sends the reader somewhere else.
    """
    import logging

    # `.ini`, not `.json`: #17302's text names `.json` and `.csv` as admitted
    # extensions and neither is in `_TEXT_EXTENSIONS`. The real list still
    # carries plenty -- `.ini`, `.cfg`, `.yaml`, `.toml`, `.sh`, `.py`, `.sql` --
    # so the threat stands; only the issue's examples were off.
    secret = _plant(tmp_path / "elsewhere" / "service.ini", "[auth]\ntoken = hunter2\n")

    with caplog.at_level(logging.DEBUG):
        assert await ArtifactIngestor()._resolve_text(_Product(str(secret))) is None

    assert "#17302" in caplog.text, "the refusal must say why it refused"
    assert (
        "could not read storage_path" not in caplog.text
    ), "a refused path was reported as an unreadable file -- the operator is told the wrong thing"
