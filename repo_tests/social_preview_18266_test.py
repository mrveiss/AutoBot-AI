# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The GitHub social preview is the render of the current brand mark (#18266, #15469).

`docs/assets/social-preview.png` is produced by `scripts/brand/render_social_preview.mjs`
from `libs/autobot-ui/src/assets/brand/mark.svg`, never redrawn. The pair is pinned like the
favicon .ico (one_brand_mark_and_announcer_18240_test.py): a new mark without a new preview,
or a hand-edited preview, fails here. Re-run the script and update both hashes.
"""

from __future__ import annotations

import hashlib
import struct

from repo_tests._paths import repo_root

_MARK = "libs/autobot-ui/src/assets/brand/mark.svg"
_PREVIEW = "docs/assets/social-preview.png"
_RENDERED_FROM = {
    _MARK: "bf25c31d0e19e610d6c3a8e5ef2d8afa158ecea0ba03dcd2b01c9fb99c526d9c",  # pragma: allowlist secret
    _PREVIEW: "52fa118196c0f14044f4325d809480b5815baa077a9c489a95ce68ced5f9f920",  # pragma: allowlist secret
}


_GITHUB_PREVIEW_SIZE = (1280, 640)


def png_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) from a PNG's IHDR, or None for bytes that are not a PNG."""
    if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def drifted(blobs: dict[str, bytes], pinned: dict[str, str]) -> list[str]:
    """The pinned paths whose bytes no longer hash to the pin (a mark or preview changed alone)."""
    return sorted(p for p, digest in pinned.items() if hashlib.sha256(blobs[p]).hexdigest() != digest)


def readme_uses_mark(readme: str) -> bool:
    """The README header (its first 600 characters) shows the canonical mark."""
    return f'src="{_MARK}"' in readme[:600]


def test_the_preview_is_the_size_github_expects() -> None:
    """GitHub's social preview is 1280x640."""
    assert png_size((repo_root() / _PREVIEW).read_bytes()) == _GITHUB_PREVIEW_SIZE


def test_the_preview_is_the_render_of_the_current_mark() -> None:
    blobs = {path: (repo_root() / path).read_bytes() for path in _RENDERED_FROM}
    assert not drifted(blobs, _RENDERED_FROM), (
        f"#18266: {_MARK} or {_PREVIEW} changed without the other; re-run "
        "scripts/brand/render_social_preview.mjs and update both hashes in _RENDERED_FROM."
    )


def test_the_readme_header_uses_the_canonical_mark() -> None:
    assert readme_uses_mark((repo_root() / "README.md").read_text(encoding="utf-8"))


def _png(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height)


def test_contrast_each_preview_guard_fires() -> None:
    """Each guard rejects the change it exists to catch and accepts the matching good input."""
    assert png_size(_png(*_GITHUB_PREVIEW_SIZE)) == _GITHUB_PREVIEW_SIZE
    assert png_size(_png(1200, 630)) != _GITHUB_PREVIEW_SIZE
    assert png_size(b"GIF89a" + bytes(18)) is None
    pinned = {"mark": hashlib.sha256(b"mark").hexdigest(), "preview": hashlib.sha256(b"png").hexdigest()}
    assert drifted({"mark": b"mark", "preview": b"png"}, pinned) == []
    assert drifted({"mark": b"new mark", "preview": b"png"}, pinned) == ["mark"]
    assert readme_uses_mark(f'<p align="center"><img src="{_MARK}"></p>')
    assert not readme_uses_mark('<p align="center"><img src="docs/old-logo.png"></p>')
    assert not readme_uses_mark("x" * 600 + f'<img src="{_MARK}">')
