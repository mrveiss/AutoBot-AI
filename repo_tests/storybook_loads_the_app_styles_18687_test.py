# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Storybook loads the app's global stylesheets from the same list the app does (#18687).

`autobot-frontend/.storybook/preview.ts` imported `../src/assets/main.css` on its
own. When #17613 folded that file away, Storybook could no longer build, and the
visual-regression job -- the safety net for GUI convergence -- compared nothing
from 2026-10-11 until this was found. The app's list (`src/main.ts`) and
Storybook's had drifted because there were two.

Now both import `src/assets/global-styles.ts`. This keeps it that way:

* both entries import the shared module;
* `main.ts` imports no stylesheet directly, so a new global sheet cannot be
  added to the app alone;
* every relative import in `preview.ts` names a file that exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_FRONTEND = Path("autobot-frontend")
_MAIN = _FRONTEND / "src" / "main.ts"
_PREVIEW = _FRONTEND / ".storybook" / "preview.ts"
_MODULE = _FRONTEND / "src" / "assets" / "global-styles.ts"
_IMPORT = re.compile(r"^\s*import\s+(?:[^'\"]*?\sfrom\s+)?['\"]([^'\"]+)['\"]", re.M)
_SUFFIXES = ("", ".ts", ".js", ".mjs", ".vue", ".css", "/index.ts")


def _imports(path: Path) -> list[str]:
    return _IMPORT.findall((repo_root() / path).read_text(encoding="utf-8"))


def _resolves(importer: Path, spec: str) -> bool:
    """A relative import resolves when some file the bundler would try exists."""
    base = (repo_root() / importer).parent / spec
    return any(Path(f"{base}{suffix}").is_file() for suffix in _SUFFIXES)


def test_the_shared_module_exists_and_lists_stylesheets() -> None:
    specs = _imports(_MODULE)
    assert any(s.endswith(".css") for s in specs), f"{_MODULE} imports no stylesheet"


def test_the_app_loads_its_global_styles_from_the_shared_module() -> None:
    assert "./assets/global-styles" in _imports(_MAIN)


def test_storybook_loads_the_same_shared_module() -> None:
    assert "../src/assets/global-styles" in _imports(_PREVIEW)


def test_main_ts_imports_no_stylesheet_directly() -> None:
    direct = [s for s in _imports(_MAIN) if s.endswith(".css") or s.startswith("@autobot/ui/")]
    assert (
        not direct
    ), f"#18687: {direct} are imported by main.ts alone; add them to {_MODULE.name} so Storybook loads them too"


def test_every_relative_import_in_the_storybook_preview_resolves() -> None:
    missing = [s for s in _imports(_PREVIEW) if s.startswith(".") and not _resolves(_PREVIEW, s)]
    assert not missing, f"#18687: .storybook/preview.ts imports files that do not exist: {missing}"


@pytest.mark.parametrize(
    ("spec", "expected"),
    [("../src/assets/global-styles", True), ("../src/assets/main.css", False), ("../src/assets/base.css", True)],
)
def test_the_resolver_tells_a_present_file_from_a_missing_one(spec: str, expected: bool) -> None:
    """The control: main.css (the file that broke Storybook) must read as missing."""
    assert _resolves(_PREVIEW, spec) is expected
