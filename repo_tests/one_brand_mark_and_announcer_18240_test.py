# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One brand mark, one screen-reader announcer (#18240, #15469).

Refined UI step 2 gave both frontends one logo (the kit's `BrandMark` /
`mark.svg`) and one `useAnnounce` (the kit's). Two ways for a fork to come back:

* the main app's `src/assets/logo.svg` reverting to the Vue scaffold, whose path
  starts `M161.096.001`;
* a second composable named `useAnnounce` (the SLM had its own until #18240)
  defined outside `libs/autobot-ui`. A re-export is not a definition.

The announcer detector matches a declaration (`function|const|let|var useAnnounce`)
on code lines only, so a comment or a `export { useAnnounce } from` re-export is not a copy.
"""

from __future__ import annotations

import functools
import hashlib
import re

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._comment_syntax import code_lines
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_LOGO = "autobot-frontend/src/assets/logo.svg"
_SCAFFOLD_PATH = "M161.096.001"
_KIT = "libs/autobot-ui/"
_KIT_ANNOUNCER = "libs/autobot-ui/src/composables/useAnnounce.ts"
_ROOTS = ("libs/autobot-ui", "autobot-frontend/src", "autobot-slm-frontend/src")
_SUFFIXES = (".ts", ".vue", ".js")
_DECLARATION = re.compile(r"\b(?:function|const|let|var)\s+useAnnounce\b")


def _defines_use_announce(source: str, name: str = "source.ts") -> bool:
    """True when a code line declares `useAnnounce` (comments and re-exports do not)."""
    return any(_DECLARATION.search(line.text) for line in code_lines(source, name=name, strip_trailing=True))


def _is_source(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    is_test = "__tests__" in rel or ".test." in name or ".spec." in name or ".stories." in name
    return rel.endswith(_SUFFIXES) and not is_test


def _source_population(root):
    try:
        tracked = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source(rel)]


REACH = declare(
    "brand-mark-announcer-scan",
    discover=_source_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=994,
    what="frontend and kit source",
    roots=_ROOTS,
    growth=150,
)


@functools.lru_cache(maxsize=1)
def _announcers() -> tuple[str, ...]:
    root = repo_root()
    found = []
    for rel in REACH.examined(root):
        if _defines_use_announce((root / rel).read_text(encoding="utf-8", errors="replace"), rel):
            found.append(rel)
    return tuple(found)


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a function declaration", "export function useAnnounce() {}\n", True),
        ("a const declaration", "export const useAnnounce = () => {}\n", True),
        ("a re-export", "export { useAnnounce } from '@autobot/ui'\n", False),
        ("an import", "import { useAnnounce } from '@autobot/ui'\n", False),
        ("a call site", "const { announce } = useAnnounce()\n", False),
        ("a comment", "// function useAnnounce() {}\n", False),
        ("a jsdoc line", "/**\n * export function useAnnounce\n */\n", False),
    ],
)
def test_the_matcher_tells_a_definition_from_a_use(label: str, source: str, expected: bool) -> None:
    assert _defines_use_announce(source) is expected, label


def test_the_scan_sees_the_kit_announcer() -> None:
    """The control: the canonical definition must be found, or the scan is blind."""
    assert _KIT_ANNOUNCER in _announcers()


def test_no_second_use_announce_outside_the_kit() -> None:
    copies = [rel for rel in _announcers() if not rel.startswith(_KIT)]
    assert not copies, (
        f"#18240: {copies} define useAnnounce; the one announcer lives in {_KIT_ANNOUNCER}. "
        "Import it from '@autobot/ui' instead."
    )


def test_main_app_logo_is_not_the_vue_scaffold() -> None:
    svg = (repo_root() / _LOGO).read_text(encoding="utf-8")
    assert (
        _SCAFFOLD_PATH not in svg
    ), f"#18240: {_LOGO} is the Vue scaffold logo again; use libs/autobot-ui/src/assets/brand/mark.svg."


_MARK = "libs/autobot-ui/src/assets/brand/mark.svg"
_SVG_ICONS = (
    "autobot-frontend/public/favicon.svg",
    "autobot-slm-frontend/public/favicon.svg",
    _LOGO,
)
_ICO = "autobot-frontend/public/favicon.ico"
#: The frames a browser or OS asks for; the main app's index.html serves the .ico with sizes="any".
_ICO_FRAMES = {16, 32, 48}
#: The .ico is a raster of the mark, so the two are pinned as a pair of content hashes
#: (public files, not secrets): change mark.svg and this fails until the .ico is
#: re-rendered from it (headless Chromium at 16-256, packed into one ICO) and both
#: hashes are updated together.
_RENDERED_FROM = {
    _MARK: "bf25c31d0e19e610d6c3a8e5ef2d8afa158ecea0ba03dcd2b01c9fb99c526d9c",  # pragma: allowlist secret
    _ICO: "26f342b18a9ef28558a1914435ad20ab4cf606982f06031b096711cda2c3bfc4",  # pragma: allowlist secret
}


@pytest.mark.parametrize("path", _SVG_ICONS)
def test_svg_icons_are_the_canonical_mark(path: str) -> None:
    """#15469: every SVG favicon / logo is byte-identical to the kit's mark.svg."""
    mark = (repo_root() / _MARK).read_bytes()
    assert (repo_root() / path).read_bytes() == mark, f"#15469: {path} drifted from {_MARK}; copy the mark over it."


def _ico_frame_sizes(data: bytes) -> set[int]:
    """Frame edge sizes from an ICO directory (ICONDIR + ICONDIRENTRY; a 0 byte means 256)."""
    assert data[:4] == b"\x00\x00\x01\x00", "not an ICO file"
    count = int.from_bytes(data[4:6], "little")
    return {data[6 + 16 * i] or 256 for i in range(count)}


def test_ico_favicon_carries_the_standard_frames() -> None:
    """#15469: the .ico the main app serves beside favicon.svg holds 16/32/48 frames of the mark."""
    frames = _ico_frame_sizes((repo_root() / _ICO).read_bytes())
    assert _ICO_FRAMES <= frames, f"#15469: {_ICO} has frames {sorted(frames)}; it needs {sorted(_ICO_FRAMES)}"


def test_ico_is_the_render_of_the_current_mark() -> None:
    """#15469: the .ico's frames are the mark's, not just the right sizes -- pinned as a pair."""
    actual = {path: hashlib.sha256((repo_root() / path).read_bytes()).hexdigest() for path in _RENDERED_FROM}
    assert actual == _RENDERED_FROM, (
        f"#15469: {_MARK} or {_ICO} changed without the other; re-render the .ico from the mark "
        "and update both hashes in _RENDERED_FROM."
    )


def test_the_ico_reader_rejects_a_non_ico() -> None:
    with pytest.raises(AssertionError, match="not an ICO"):
        _ico_frame_sizes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
