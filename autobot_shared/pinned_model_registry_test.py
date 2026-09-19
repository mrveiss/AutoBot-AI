# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pinned-model revision resolution and digest verification (#13034).

Builds a real HuggingFace-cache-shaped directory (models--org--name/snapshots/
<revision>/<file> -> blobs/<hash>) rather than mocking ``try_to_load_from_cache``,
so this exercises the actual cache layout the real library understands, not a
paraphrase of it. Weight content is synthetic; the registry entries used here
are temporary substitutes, not the real pinned digests (those are verified
against the live HuggingFace API -- see the module docstring for how).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from autobot_shared.pinned_model_registry import (
    ModelIntegrityError,
    PinnedModel,
    get_pinned_revision,
    load_verified,
    verify_cached_model,
)

_REPO_ID = "openai/clip-vit-base-patch32"
_REVISION = "3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268"


def _fake_cache(tmp_path: Path, filename: str, content: bytes) -> str:
    """Build a real HF-cache-shaped snapshot dir and return its cache_dir."""
    repo_folder = tmp_path / f"models--{_REPO_ID.replace('/', '--')}"
    blob_dir = repo_folder / "blobs"
    blob_dir.mkdir(parents=True)
    snapshot_dir = repo_folder / "snapshots" / _REVISION
    snapshot_dir.mkdir(parents=True)

    content_hash = hashlib.sha256(content).hexdigest()
    blob_path = blob_dir / content_hash
    blob_path.write_bytes(content)
    (snapshot_dir / filename).symlink_to(blob_path)
    return str(tmp_path)


# ---------------------------------------------------------------------------
# get_pinned_revision
# ---------------------------------------------------------------------------


def test_get_pinned_revision_returns_the_registered_sha():
    assert get_pinned_revision(_REPO_ID) == _REVISION


def test_get_pinned_revision_raises_for_an_unregistered_model():
    """A new call site cannot silently load an unpinned model by omission."""
    with pytest.raises(KeyError, match="not in the pinned-model registry"):
        get_pinned_revision("some-org/some-unregistered-model")


# ---------------------------------------------------------------------------
# verify_cached_model
# ---------------------------------------------------------------------------


def test_verify_cached_model_passes_when_the_cached_file_matches(tmp_path, monkeypatch):
    content = b"synthetic-weights-for-the-match-case"
    real_hash = hashlib.sha256(content).hexdigest()
    cache_dir = _fake_cache(tmp_path, "pytorch_model.bin", content)

    import autobot_shared.pinned_model_registry as pmr

    monkeypatch.setitem(
        pmr._REGISTRY,
        _REPO_ID,
        PinnedModel(repo_id=_REPO_ID, revision=_REVISION, weight_digests={"pytorch_model.bin": real_hash}),
    )
    verify_cached_model(_REPO_ID, cache_dir=cache_dir)  # must not raise


def test_verify_cached_model_fails_closed_on_a_digest_mismatch(tmp_path, monkeypatch):
    """The reproduction this issue exists for: a redeployed/tampered artifact must be refused."""
    content = b"synthetic-weights-that-do-not-match-the-pin"
    cache_dir = _fake_cache(tmp_path, "pytorch_model.bin", content)

    import autobot_shared.pinned_model_registry as pmr

    monkeypatch.setitem(
        pmr._REGISTRY,
        _REPO_ID,
        PinnedModel(repo_id=_REPO_ID, revision=_REVISION, weight_digests={"pytorch_model.bin": "0" * 64}),
    )
    with pytest.raises(ModelIntegrityError, match="sha256 mismatch"):
        verify_cached_model(_REPO_ID, cache_dir=cache_dir)


def test_verify_cached_model_fails_closed_when_nothing_was_cached(tmp_path):
    """No file to check is a failure, not a silent pass -- 'not verified' is not 'safe'."""
    with pytest.raises(ModelIntegrityError, match="none of the registered weight files"):
        verify_cached_model(_REPO_ID, cache_dir=str(tmp_path))


def test_verify_cached_model_checks_whichever_registered_filename_is_present(tmp_path, monkeypatch):
    """A model with both a .bin and a .safetensors entry: only one need be cached to pass."""
    content = b"synthetic-safetensors-content"
    real_hash = hashlib.sha256(content).hexdigest()
    cache_dir = _fake_cache(tmp_path, "model.safetensors", content)

    import autobot_shared.pinned_model_registry as pmr

    monkeypatch.setitem(
        pmr._REGISTRY,
        _REPO_ID,
        PinnedModel(
            repo_id=_REPO_ID,
            revision=_REVISION,
            weight_digests={
                "pytorch_model.bin": "1" * 64,  # not cached -- must be skipped, not required
                "model.safetensors": real_hash,
            },
        ),
    )
    verify_cached_model(_REPO_ID, cache_dir=cache_dir)  # must not raise


def test_verify_cached_model_raises_for_an_unregistered_model(tmp_path):
    with pytest.raises(KeyError, match="not in the pinned-model registry"):
        verify_cached_model("some-org/some-unregistered-model", cache_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# Registry data integrity
# ---------------------------------------------------------------------------


def test_every_registered_revision_is_a_git_sha_shape():
    """40 lowercase hex chars -- catches a truncated/typo'd or branch-name-shaped pin."""
    import re

    import autobot_shared.pinned_model_registry as pmr

    sha_re = re.compile(r"^[0-9a-f]{40}$")
    for repo_id, pinned in pmr._REGISTRY.items():
        assert sha_re.match(pinned.revision), f"{repo_id}: revision {pinned.revision!r} is not a git SHA"


def test_every_registered_digest_is_a_sha256_shape():
    import re

    import autobot_shared.pinned_model_registry as pmr

    digest_re = re.compile(r"^[0-9a-f]{64}$")
    for repo_id, pinned in pmr._REGISTRY.items():
        for filename, digest in pinned.weight_digests.items():
            assert digest_re.match(digest), f"{repo_id}::{filename}: digest {digest!r} is not sha256-shaped"


def test_every_registered_model_declares_at_least_one_weight_digest():
    """A model with neither weight_digests nor no_weight_files=True is a
    silent gap (#17087): verify_cached_model can never pass for it, and
    nothing here says that's intentional."""
    import autobot_shared.pinned_model_registry as pmr

    for repo_id, pinned in pmr._REGISTRY.items():
        assert pinned.weight_digests or pinned.no_weight_files, (
            f"{repo_id}: no weight_digests and no_weight_files is not set -- verify_cached_model "
            "can never pass. If this repo genuinely ships no weights of its own, set "
            "no_weight_files=True explicitly with a comment saying why."
        )


def test_no_weight_files_entries_are_actually_empty():
    """The inverse gap: no_weight_files=True on a model that DOES have
    digests would silently skip verifying them (#17087)."""
    import autobot_shared.pinned_model_registry as pmr

    for repo_id, pinned in pmr._REGISTRY.items():
        if pinned.no_weight_files:
            assert not pinned.weight_digests, (
                f"{repo_id}: no_weight_files=True but weight_digests is non-empty -- "
                "verify_cached_model would skip checking them. Drop no_weight_files instead."
            )


def test_verify_cached_model_is_a_noop_for_a_no_weight_files_entry(tmp_path):
    """Proves the exemption actually short-circuits verify_cached_model,
    rather than happening to pass because the registry entry is malformed."""
    import autobot_shared.pinned_model_registry as pmr

    fake_repo_id = "test-org/pipeline-definition-only"
    original = pmr._REGISTRY.get(fake_repo_id)
    pmr._REGISTRY[fake_repo_id] = pmr.PinnedModel(repo_id=fake_repo_id, revision="deadbeef", no_weight_files=True)
    try:
        pmr.verify_cached_model(fake_repo_id, cache_dir=str(tmp_path))  # no cache dir populated at all
    finally:
        if original is None:
            del pmr._REGISTRY[fake_repo_id]
        else:
            pmr._REGISTRY[fake_repo_id] = original


# ---------------------------------------------------------------------------
# load_verified (#17124 -- shared load-then-verify-then-assign helper)
# ---------------------------------------------------------------------------


def test_load_verified_calls_each_loader_with_the_pinned_revision_and_returns_results(monkeypatch):
    import autobot_shared.pinned_model_registry as pmr

    monkeypatch.setattr(pmr, "get_pinned_revision", lambda repo_id: _REVISION)
    monkeypatch.setattr(pmr, "verify_cached_model", lambda repo_id: None)

    seen_revisions = []

    def make_loader(marker):
        def loader(revision):
            seen_revisions.append(revision)
            return marker

        return loader

    results = load_verified(_REPO_ID, make_loader("processor"), make_loader("model"))

    assert results == ("processor", "model")
    assert seen_revisions == [_REVISION, _REVISION]


def test_load_verified_raises_and_returns_nothing_when_verification_fails(monkeypatch):
    """The #17124 fail-open regression this helper exists to close: a caller
    that only assigns from this function's return value must never receive a
    partial result when the integrity check fails."""
    import autobot_shared.pinned_model_registry as pmr

    monkeypatch.setattr(pmr, "get_pinned_revision", lambda repo_id: _REVISION)

    def failing_verify(repo_id):
        raise ModelIntegrityError("tampered")

    monkeypatch.setattr(pmr, "verify_cached_model", failing_verify)

    loader_calls = []
    with pytest.raises(ModelIntegrityError):
        load_verified(_REPO_ID, lambda revision: loader_calls.append(revision) or "unverified-result")

    assert loader_calls == [_REVISION], "the loader itself still runs -- verification happens after loading"
