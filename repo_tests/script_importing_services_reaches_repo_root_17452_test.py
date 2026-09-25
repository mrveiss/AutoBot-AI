# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A script importing `services.*` must put the REPO root on `sys.path` (#17452).

`autobot-slm-backend/services/__init__.py` imports `AuthService`, which imports
`autobot_shared.auth.jwt_core`. So `from services.<anything> import ...` -- even a
leaf git helper -- executes that chain and needs **`autobot_shared`**, which lives
at the repo root, one level ABOVE the backend root.

`sync_deletion_planner.py` inserted only the backend root. Every code-sync run
therefore died in the `[PRE-FLIGHT] Ensure code_source has full history` task:

    ModuleNotFoundError: No module named 'autobot_shared'
    PLAY RECAP: localhost  ok=1  failed=1

The failure is invisible to unit tests, which run from a repo-root cwd where
`autobot_shared` is importable anyway. It only appears when the script is invoked
by absolute path with an interpreter whose `sys.path` does not already contain the
repo root -- which is exactly how ansible invokes it.

`dump_openapi.py` already carried the correct shape and its reasoning; this guard
pins it as a rule rather than leaving the next author to rediscover it. Backend
root precedes the repo root so the backend package wins over a repo-root shim of
the same name.
"""

import pathlib
import re

from repo_tests._paths import repo_root
from repo_tests._reach import declare

#: `repo_root()`, never `__file__.parents[N]` -- #15925 pins one spelling.
_ROOT = repo_root()

_SCRIPT_DIRS = ("autobot-slm-backend/scripts", "autobot-backend/scripts")

#: `from services.x import y` / `import services.x` -- the import that drags
#: `services/__init__.py` and therefore `autobot_shared`.
_IMPORTS_SERVICES = re.compile(r"^\s*(?:from\s+services[.\s]|import\s+services\b)", re.MULTILINE)

#: Any expression reaching two levels up from the script: `parents[2]`, or a
#: `parent.parent.parent` chain. `parents[1]` / `parent.parent` is the backend
#: root and is NOT enough.
_REACHES_REPO_ROOT = re.compile(r"parents\[\s*[2-9]\s*\]|(?:\.parent){3,}")


def _code_lines(text: str) -> str:
    """Whole-line comments stripped, so a comment about the shape is not a finding (#16750)."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _scripts_importing_services(root: pathlib.Path | None = None) -> tuple[str, ...]:
    """`discover` is called with the tree root, so it must accept one (#17452)."""
    root = pathlib.Path(root) if root is not None else _ROOT
    hits = []
    for rel in _SCRIPT_DIRS:
        base = root / rel
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if _IMPORTS_SERVICES.search(_code_lines(path.read_text(encoding="utf-8"))):
                hits.append(str(path.relative_to(root)))
    return tuple(hits)


#: The floor separates "every script is correct" from "no script was read".
#: Measured at 1 when this landed; a findings-floor could not make that distinction.
SERVICE_IMPORTING_SCRIPTS = declare(
    "slm-scripts-importing-services",
    discover=_scripts_importing_services,
    floor=1,
    growth=20,
    what="scripts importing `services.*`, which pulls in `autobot_shared` (#17452)",
)


def test_the_sweep_actually_reaches_the_tree() -> None:
    """ "every script is correct" must be distinguishable from "no script was read"."""
    SERVICE_IMPORTING_SCRIPTS.verify_floor(_ROOT)


def test_every_script_importing_services_reaches_the_repo_root() -> None:
    """Backend root alone raises ModuleNotFoundError under ansible's invocation."""
    offenders = []
    for rel in _scripts_importing_services():
        code = _code_lines((_ROOT / rel).read_text(encoding="utf-8"))
        if not _REACHES_REPO_ROOT.search(code):
            offenders.append(rel)
    assert not offenders, (
        "these scripts import `services.*` but never put the repo root on sys.path, so "
        "`autobot_shared` is unreachable and the script dies at import under ansible "
        f"(#17452): {offenders}"
    )


def test_the_detector_rejects_the_backend_root_only_shape() -> None:
    """The shape that shipped must be recognised, or the guard proves nothing."""
    assert not _REACHES_REPO_ROOT.search("sys.path.insert(0, str(Path(__file__).resolve().parent.parent))")
    assert not _REACHES_REPO_ROOT.search("parents[1]")


def test_the_detector_accepts_both_repo_root_spellings() -> None:
    """`parents[2]` and a three-deep `.parent` chain are the same reach."""
    assert _REACHES_REPO_ROOT.search("_SCRIPT.parents[2]")
    assert _REACHES_REPO_ROOT.search("Path(__file__).resolve().parent.parent.parent")


def test_a_comment_describing_the_forbidden_shape_is_not_a_finding() -> None:
    """#16750: a whole-line comment is prose, not code."""
    assert _IMPORTS_SERVICES.search(_code_lines("# from services.x import y\n")) is None
