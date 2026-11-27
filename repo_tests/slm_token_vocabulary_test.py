# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No custom property exists only in the SLM unless it is documented (#17566).

The SLM must declare the same token names as the user frontend and supply its own values;
a name declared only in the SLM stylesheets is a second vocabulary. The deliberate exceptions
(the dark identity bar, and Tailwind's own ``--color-white`` / ``--color-black``) are listed in
``DESIGN_SYSTEM.md`` under "SLM token vocabulary". This guard derives both sides from the
files, so it cannot drift from them: the names declared in the SLM stylesheets minus the names
declared anywhere in the user frontend's or the kit's CSS must equal the documented set.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

_ROOT = repo_root()
_DOC = _ROOT / "docs" / "developer" / "DESIGN_SYSTEM.md"
_SLM_STYLES = _ROOT / "autobot-slm-frontend" / "src" / "assets" / "styles"
_SHARED_CSS = (_ROOT / "autobot-frontend" / "src", _ROOT / "libs" / "autobot-ui" / "src")
_DECLARATION = re.compile(r"^\s*(--[\w-]+)\s*:", re.MULTILINE)
_SECTION = "## SLM token vocabulary (#17566)"
_ONLY = "**What is still SLM-only, on purpose**"


def _declared(css_files) -> set[str]:
    names: set[str] = set()
    for path in css_files:
        names.update(_DECLARATION.findall(path.read_text(encoding="utf-8")))
    return names


def _slm_only() -> set[str]:
    slm = _declared(sorted(_SLM_STYLES.glob("*.css")))
    shared = _declared(p for root in _SHARED_CSS for p in sorted(root.rglob("*.css")))
    return slm - shared


def _documented() -> set[str]:
    """Backticked `--name` tokens in the table that follows the SLM-only marker, to the next heading."""
    text = _DOC.read_text(encoding="utf-8")
    body = text[text.index(_SECTION) :]
    body = body[body.index(_ONLY) :]
    table = body.split("\n## ", 1)[0]
    rows = [ln for ln in table.splitlines() if ln.startswith("| `")]
    return {name for ln in rows for name in re.findall(r"`(--[\w-]+)`", ln.split("|")[1])}


def test_the_population_is_measured() -> None:
    """A derivation that finds nothing would pass the next two tests for the wrong reason."""
    assert len(_declared(sorted(_SLM_STYLES.glob("*.css")))) > 200
    assert len(_documented()) >= 10


def test_every_slm_only_name_is_documented() -> None:
    undocumented = sorted(_slm_only() - _documented())
    assert not undocumented, (
        f"{undocumented} exist only in the SLM stylesheets. Declare the shared name with the SLM's value "
        f"(see DESIGN_SYSTEM.md, '{_SECTION[3:]}'), or document the name there with the reason it has no "
        "user-frontend counterpart."
    )


def test_every_documented_name_still_exists_only_in_the_slm() -> None:
    stale = sorted(_documented() - _slm_only())
    assert not stale, f"{stale} are documented as SLM-only but are shared or gone; drop them from the table."
