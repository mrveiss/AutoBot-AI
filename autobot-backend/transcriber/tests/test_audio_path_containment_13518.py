# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Audio paths stay inside the upload directory, via the canonical helper (#13518).

`_resolve_audio_path` was a second, hand-rolled implementation of path
containment — `resolve()` + `relative_to()` — alongside
`autobot_shared/security/path_validator.py`, which 30+ call sites use. It was
correct, but a second implementation of one invariant does not inherit the
shared one's future hardening.

It also carried an explicit symlink rejection that a scan triage described as
making it *stronger* than the canonical helper. **That check could never fire.**
It ran on the output of `.resolve()`, which follows symlinks, so the value tested
is always the target and never a link. `test_the_symlink_check_it_replaced_was_dead_code`
pins that, because the claim is plausible enough to be re-added by someone
reading the old code.

Containment against symlinks holds regardless, and for a better reason: a link
pointing outside the upload directory resolves to a path that fails the
containment check, and one pointing inside is harmless.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException  # noqa: E402

from transcriber.routes.recordings import _resolve_audio_path  # noqa: E402


@pytest.fixture()
def upload_dir(tmp_path):
    d = tmp_path / "uploads"
    d.mkdir()
    return d


def test_a_file_inside_the_upload_dir_resolves(upload_dir):
    audio = upload_dir / "take-1.wav"
    audio.write_bytes(b"RIFF")

    assert _resolve_audio_path(str(audio), upload_dir) == audio.resolve()


def test_a_path_outside_the_upload_dir_is_rejected(upload_dir, tmp_path):
    outside = tmp_path / "elsewhere.wav"
    outside.write_bytes(b"RIFF")

    with pytest.raises(HTTPException) as exc:
        _resolve_audio_path(str(outside), upload_dir)
    assert exc.value.status_code == 404


def test_traversal_out_of_the_upload_dir_is_rejected(upload_dir, tmp_path):
    escaped = tmp_path / "secret.wav"
    escaped.write_bytes(b"RIFF")

    with pytest.raises(HTTPException) as exc:
        _resolve_audio_path(str(upload_dir / ".." / "secret.wav"), upload_dir)
    assert exc.value.status_code == 404


def test_a_symlink_escaping_the_upload_dir_is_rejected(upload_dir, tmp_path):
    """The case the deleted `is_symlink()` check was reaching for.

    Containment catches it without a dedicated check: `realpath` follows the
    link, and the *target* is what must fall under the upload directory.
    """
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"RIFF")
    link = upload_dir / "innocent.wav"
    link.symlink_to(outside)

    with pytest.raises(HTTPException) as exc:
        _resolve_audio_path(str(link), upload_dir)
    assert exc.value.status_code == 404


def test_a_symlink_staying_inside_the_upload_dir_is_allowed(upload_dir):
    """Harmless, and the old blanket rejection would have been wrong to block it."""
    real = upload_dir / "real.wav"
    real.write_bytes(b"RIFF")
    link = upload_dir / "alias.wav"
    link.symlink_to(real)

    assert _resolve_audio_path(str(link), upload_dir) == real.resolve()


def test_a_missing_file_is_rejected(upload_dir):
    with pytest.raises(HTTPException) as exc:
        _resolve_audio_path(str(upload_dir / "gone.wav"), upload_dir)
    assert exc.value.status_code == 404


def test_a_directory_is_not_accepted_as_audio(upload_dir):
    (upload_dir / "subdir").mkdir()

    with pytest.raises(HTTPException) as exc:
        _resolve_audio_path(str(upload_dir / "subdir"), upload_dir)
    assert exc.value.status_code == 404


def test_the_symlink_check_it_replaced_was_dead_code(tmp_path):
    """Pins why the explicit `is_symlink()` rejection was dropped, not ported.

    A triage described it as making the hand-rolled helper stronger than the
    canonical one. It ran *after* `.resolve()`, which follows symlinks — so the
    value tested is the target, never the link. Recorded here because the claim
    is plausible enough that someone reading the old code would re-add it.
    """
    real = tmp_path / "real.wav"
    real.write_bytes(b"RIFF")
    link = tmp_path / "link.wav"
    link.symlink_to(real)

    assert link.is_symlink() is True, "the link itself is a symlink"
    assert (
        Path(str(link)).resolve().is_symlink() is False
    ), "resolve() follows symlinks, so the old check could never fire"

    dangling = tmp_path / "dangling.wav"
    dangling.symlink_to(tmp_path / "nope.wav")
    assert (
        Path(str(dangling)).resolve().is_symlink() is False
    ), "not even a dangling link survives resolve() as a symlink"


def test_it_delegates_to_the_canonical_helper_rather_than_re_implementing():
    """The point of the change: one implementation of path containment."""
    import inspect

    from transcriber.routes import recordings

    source = inspect.getsource(recordings._resolve_audio_path)

    assert "validate_path(" in source, (
        "_resolve_audio_path no longer delegates to path_validator — a second "
        "implementation will not inherit the shared helper's hardening"
    )
    assert ".relative_to(" not in source, "containment is re-implemented locally again"
