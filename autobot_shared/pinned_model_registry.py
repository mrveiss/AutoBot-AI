# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Revision-pinned, integrity-verified HuggingFace model registry (#13034).

Every ``from_pretrained`` call in this repo resolved a bare model name against
the upstream default branch, which is mutable -- the same call could return
different weights on different days, and 18 ``# nosec B615`` suppressions
asserted "revision pinning managed operationally" with no registry, lockfile,
or bump procedure actually implementing that.

Split out of ``ssot_config.py`` rather than added inline: that file is
ratchet-frozen at 3298 lines with no slack, and the ratchet forbids raising a
ceiling to make room -- the same reason ``env_registry_slm.py`` exists as its
own module instead of growing ``env_registry.py``.

How a pin was obtained (the bump procedure -- do this, don't guess a SHA):
see ``docs/developer/MODEL_REVISION_PINNING.md``'s "Bump procedure" section
for the exact commands. Kept in one place rather than duplicated here so the
two copies can't drift.

Every value in ``_REGISTRY`` below was obtained exactly this way against the
live HuggingFace API, not guessed or reconstructed -- a fabricated hash here
would be worse than no pin at all, since it would either never verify (fail
closed permanently) or, if it happened to be wrong in a way that still let
some load through, provide false assurance.

Owner: whoever adds or bumps an entry recorded their name/date in the entry's
comment below (#13034 AC5, "document who owns the bump procedure"). A pin
with no bump procedure rots and gets re-suppressed -- recording the mechanism
here is part of the fix, not a nice-to-have.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class ModelIntegrityError(RuntimeError):
    """A downloaded model's weights don't match its pinned digest, or nothing
    matched at all -- fail closed rather than load an unverified artifact."""


@dataclass(frozen=True)
class PinnedModel:
    """One registered model: an exact revision plus the weight file(s) whose
    content is verified against the pinned revision after download.

    ``weight_digests`` deliberately allows more than one filename: some repos
    ship both ``pytorch_model.bin`` and ``model.safetensors`` for the same
    weights, and which one ``from_pretrained`` actually fetches can depend on
    the installed ``transformers``/``safetensors`` versions. Verification
    checks whichever of these files the local cache actually has.

    ``no_weight_files`` is the one legitimate reason to register a model with
    an empty ``weight_digests`` (#17087): a repo that is a pipeline/config
    definition rather than a set of weights (no ``pytorch_model.bin`` /
    ``*.safetensors`` of its own) has nothing for ``verify_cached_model`` to
    hash. Set explicitly and reviewed, not inferred from an empty dict, so a
    model that should have digests but is missing them by omission still
    fails ``test_every_registered_model_declares_at_least_one_weight_digest``.
    """

    repo_id: str
    revision: str
    weight_digests: dict[str, str] = field(default_factory=dict)
    no_weight_files: bool = False


# Bumped by: mrveiss, 2026-09-17, via the procedure in this module's docstring.
_REGISTRY: dict[str, PinnedModel] = {
    "openai/clip-vit-base-patch32": PinnedModel(
        repo_id="openai/clip-vit-base-patch32",
        revision="3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268",
        weight_digests={
            "pytorch_model.bin": "a63082132ba4f97a80bea76823f544493bffa8082296d62d71581a4feff1576f",
        },
    ),
    "facebook/wav2vec2-base-960h": PinnedModel(
        repo_id="facebook/wav2vec2-base-960h",
        revision="22aad52d435eb6dbaf354bdad9b0da84ce7d6156",
        weight_digests={
            "model.safetensors": "8aa76ab2243c81747a1f832954586bc566090c83a0ac167df6f31f0fa917d74a",
        },
    ),
    "openai/whisper-base": PinnedModel(
        repo_id="openai/whisper-base",
        revision="e37978b90ca9030d5170a5c07aadb050351a65bb",
        weight_digests={
            "model.safetensors": "07cadb9f25677c8d50df603e66a98fbd842cce45047139baeb16e6219a1e807b",
        },
    ),
    "Salesforce/blip2-opt-2.7b": PinnedModel(
        repo_id="Salesforce/blip2-opt-2.7b",
        revision="59a1ef6c1e5117b3f65523d1c6066825bcf315e3",
        weight_digests={
            "model-00001-of-00002.safetensors": "b81228c9ac1b3dee1731ee71d51fe3b2c34f915019c44c25a793b51300ae24fc",
            "model-00002-of-00002.safetensors": "536bd73b8f1de7d94f503b23fea2eaa4f7f3ea5f74f8f874fcb21d6df1555a19",
        },
    ),
    "microsoft/codebert-base": PinnedModel(
        repo_id="microsoft/codebert-base",
        revision="3b0952feddeffad0063f274080e3c23d75e7eb39",
        weight_digests={
            "pytorch_model.bin": "28b61fd8fa069f6bc966f4cb9572a4026ab2a784fca8fb224020d91b744e32d6",
        },
    ),
    # Bumped by: mrveiss, 2026-09-19, via the procedure in this module's docstring (#17087).
    # no_weight_files: this repo ships a pyannote Pipeline *definition*
    # (config.yaml + benchmark data), not weights -- nothing for
    # verify_cached_model() to hash. config.yaml itself is gated (requires an
    # authenticated, license-accepted HF session to read), so the sub-model
    # repos it points to for the actual segmentation/embedding weights cannot
    # be resolved and pinned from here -- a stated gap, not a silent one; see
    # diarization_service.py's own comment.
    "pyannote/speaker-diarization-3.1": PinnedModel(
        repo_id="pyannote/speaker-diarization-3.1",
        revision="84fd25912480287da0247647c3d2b4853cb3ee5d",
        no_weight_files=True,
    ),
}


def get_pinned_revision(repo_id: str) -> str:
    """The exact commit SHA to pass as ``revision=`` for *repo_id*.

    Raises :class:`KeyError` for an unregistered model -- deliberately, so a
    new call site cannot silently load an unpinned model by omission. Add the
    model to ``_REGISTRY`` first, via this module's docstring procedure.
    """
    try:
        return _REGISTRY[repo_id].revision
    except KeyError:
        raise KeyError(
            f"{repo_id!r} is not in the pinned-model registry (autobot_shared/pinned_model_registry.py). "
            "Add it there before loading it -- see the module docstring for how to obtain a real pin."
        ) from None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_cached_model(repo_id: str, *, cache_dir: str | None = None) -> None:
    """Verify the locally-cached weights for *repo_id*'s pinned revision.

    Call this AFTER ``from_pretrained(repo_id, revision=get_pinned_revision(repo_id))``
    has run, so the file is already in the local HuggingFace cache. Checks
    whichever of the registered filenames the cache actually has -- see
    :class:`PinnedModel`. Raises :class:`ModelIntegrityError` if none of the
    registered files were found in the cache (verification could not run at
    all -- treated as a failure, not a pass, since "nothing to check" is not
    the same guarantee as "checked and matched") or if a found file's digest
    does not match. A no-op for a :attr:`PinnedModel.no_weight_files` entry --
    there is nothing to hash by design, not by omission (#17087).
    """
    from huggingface_hub import try_to_load_from_cache  # noqa: PLC0415 -- optional/heavy at import time

    pinned = _REGISTRY.get(repo_id)
    if pinned is None:
        raise KeyError(f"{repo_id!r} is not in the pinned-model registry; nothing to verify against")

    if pinned.no_weight_files:
        logger.info("%s has no weight files of its own; revision pin only, nothing to verify", repo_id)
        return

    checked_any = False
    for filename, expected_digest in pinned.weight_digests.items():
        local_path = try_to_load_from_cache(repo_id, filename, revision=pinned.revision, cache_dir=cache_dir)
        if not isinstance(local_path, str):
            continue  # not cached under this filename -- from_pretrained used a different one
        checked_any = True
        actual_digest = _sha256_file(Path(local_path))
        if actual_digest != expected_digest:
            raise ModelIntegrityError(
                f"{repo_id!r} revision {pinned.revision}: {filename} sha256 mismatch -- "
                f"expected {expected_digest}, got {actual_digest}. Refusing to load a model whose "
                "weights do not match the pinned digest."
            )
        logger.info("Verified %s (%s) against pinned digest", repo_id, filename)

    if not checked_any:
        raise ModelIntegrityError(
            f"{repo_id!r} revision {pinned.revision}: none of the registered weight files "
            f"({sorted(pinned.weight_digests)}) were found in the local cache -- verification did not "
            "run. Refusing to treat an unverified download as safe."
        )
