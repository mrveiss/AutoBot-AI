# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#17856 row 8: one auth-token reader per frontend app.

Main app: only ``utils/authToken.ts`` reads ``autobot_auth`` from storage;
``stores/useUserStore.ts`` is the writer and restores its own state, the one
recorded exception. ApiClient carried a second reader with an expiry check the
canonical one lacked, so ``fetchWithAuth`` kept sending expired tokens.

SLM: only ``utils/authStorage.ts`` names the session keys. LoginView and
SSOCallbackView wrote ``sessionStorage`` behind the store, where ``checkAuth()``
could not see the token; ``useAutobotApi`` read an ``autobot_access_token`` that
nothing writes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from tools.lint._comment_syntax import code_lines

_ROOT = repo_root()
_MAIN_SRC = _ROOT / "autobot-frontend" / "src"
_SLM_SRC = _ROOT / "autobot-slm-frontend" / "src"

#: Root-relative, one pair per tree: the python path filter covers both `src/**`
#: trees, so this guard runs whenever either changes (#15900). A bare `*.ts` would
#: probe outside them and read as uncovered.
_GLOBS = {
    _MAIN_SRC: ("autobot-frontend/src/**/*.ts", "autobot-frontend/src/**/*.vue"),
    _SLM_SRC: ("autobot-slm-frontend/src/**/*.ts", "autobot-slm-frontend/src/**/*.vue"),
}

#: A storage access naming the main-app auth key.
_MAIN_READ = re.compile(r"""localStorage\.getItem\(\s*['"]autobot_auth['"]""")
#: Any literal naming an SLM session key, or the dead autobot_access_token.
_SLM_KEY = re.compile(r"""['"](slm_access_token|slm_user|autobot_access_token)['"]""")

_MAIN_ALLOWED = {"utils/authToken.ts", "stores/useUserStore.ts"}
_SLM_ALLOWED = {"utils/authStorage.ts"}


def _is_test(path: Path) -> bool:
    return "__tests__" in path.parts or re.search(r"\.(test|spec)\.ts$", path.name) is not None


def _sources(src: Path):
    for path in sorted(p for glob in _GLOBS[src] for p in _ROOT.glob(glob)):
        if not _is_test(path) and "types/generated" not in path.as_posix():
            yield path


def _hits(src: Path, pattern: re.Pattern[str]) -> set[str]:
    """Source files whose code (not comments) matches; comments may name a key to explain it."""
    return {
        path.relative_to(src).as_posix()
        for path in _sources(src)
        if any(pattern.search(line.text) for line in code_lines(path, strip_trailing=True))
    }


@pytest.mark.parametrize(
    ("src", "pattern", "allowed"),
    [(_MAIN_SRC, _MAIN_READ, _MAIN_ALLOWED), (_SLM_SRC, _SLM_KEY, _SLM_ALLOWED)],
    ids=["main-app", "slm"],
)
def test_only_the_canonical_module_touches_the_token(src, pattern, allowed):
    hits = _hits(src, pattern)
    assert hits, f"no file under {src.name} matches -- the detector or the tree moved, so a pass would be vacuous"
    assert hits <= allowed, f"token read outside the canonical module: {sorted(hits - allowed)}"


def test_the_detectors_catch_a_second_reader():
    """Contrast: the shapes removed by #17856 are matched."""
    assert _MAIN_READ.search("const stored = localStorage.getItem('autobot_auth');")
    assert _SLM_KEY.search("const token = sessionStorage.getItem('slm_access_token')")
    assert _SLM_KEY.search("authStore.token || localStorage.getItem('autobot_access_token')")
