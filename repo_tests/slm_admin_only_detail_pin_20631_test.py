# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20631: the SLM store's copy of the admin-only detail equals the backend's.

``stores/auth.ts`` clears a stored admin only on this exact 403 detail, so a change to
the backend string alone would silently stop clearing it.
"""

import re

from repo_tests._paths import repo_root

_BACKEND = repo_root() / "autobot-slm-backend" / "services" / "auth.py"
_STORE = repo_root() / "autobot-slm-frontend" / "src" / "stores" / "auth.ts"
_ASSIGNMENT = re.compile(r"""\bADMIN_ONLY_DETAIL\b[^=\n]*=\s*(['"])(.+?)\1""")


def _detail(text: str) -> str:
    match = _ASSIGNMENT.search(text)
    assert match, "no ADMIN_ONLY_DETAIL assignment found"
    return match.group(2)


def test_the_parser_reads_both_quote_styles() -> None:
    """Control: the detector finds the value in each language's form, and refuses neither."""
    assert _detail('ADMIN_ONLY_DETAIL = "For admins."') == "For admins."
    assert _detail("const ADMIN_ONLY_DETAIL = 'For admins.'") == "For admins."


def test_the_store_copy_matches_the_backend() -> None:
    backend = _detail(_BACKEND.read_text(encoding="utf-8"))
    store = _detail(_STORE.read_text(encoding="utf-8"))
    assert store == backend, f"stores/auth.ts has {store!r}, the backend has {backend!r}"
