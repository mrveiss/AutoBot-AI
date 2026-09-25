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

import ast
import pathlib

from repo_tests._paths import repo_root
from repo_tests._reach import declare

#: `repo_root()`, never `__file__.parents[N]` -- #15925 pins one spelling.
_ROOT = repo_root()

_SCRIPT_DIRS = ("autobot-slm-backend/scripts", "autobot-backend/scripts")


#: Parsed, not grepped. A regex on `^\s*(from|import) services` missed
#: `import os, services.git_subprocess` -- `services` in any clause but the
#: first -- so a script could import the package and never be scanned.
def _imports_services(tree: ast.AST) -> bool:
    """True if any import clause names the `services` package (#17452 review)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "services" or a.name.startswith("services.") for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level == 0 and (mod == "services" or mod.startswith("services.")):
                return True
    return False


#: `parents[2]` / a three-deep `.parent` chain. Applied ONLY to the expression
#: actually handed to `sys.path`, never to the file at large.
def _expression_reaches_repo_root(expr: ast.AST) -> bool:
    src = ast.unparse(expr)
    if ".parent.parent.parent" in src:
        return True
    for node in ast.walk(expr):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            if node.value.attr == "parents" and isinstance(node.slice, ast.Constant):
                if isinstance(node.slice.value, int) and node.slice.value >= 2:
                    return True
    return False


def _syspath_insertions(tree: ast.AST) -> list[ast.AST]:
    """Every expression that FLOWS INTO `sys.path.insert` / `.append` (#17452 review).

    Checking the file for a `parents[2]` token anywhere accepted a script whose
    `sys.path` received only `parents[1]` while an unrelated expression carried
    the token -- a guard satisfiable without the thing it guards being true.

    One hop of indirection is followed, because the canonical shape in this repo
    (`dump_openapi.py`, and the fix this guard pins) inserts a loop variable:

        for _path in (str(_REPO_ROOT), str(_BACKEND_ROOT)):
            sys.path.insert(0, _path)

    A bare name that is a `for` target resolves to the loop's iterable. Anything
    further -- a name assigned three functions away -- is deliberately NOT
    followed: the check would stop being decidable and start being a guess.
    """
    loop_iter: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            loop_iter[node.target.id] = node.iter

    out: list[ast.AST] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"insert", "append"}:
            continue
        target = node.func.value
        if not (isinstance(target, ast.Attribute) and target.attr == "path"):
            continue
        if not (isinstance(target.value, ast.Name) and target.value.id == "sys"):
            continue
        for arg in node.args[1:] if node.func.attr == "insert" else node.args:
            if isinstance(arg, ast.Name) and arg.id in loop_iter:
                out.append(loop_iter[arg.id])
            else:
                out.append(arg)
    return out


def _code_lines(text: str) -> str:
    """Whole-line comments stripped, so a comment about the shape is not a finding (#16750)."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _parse(path: pathlib.Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _scripts_importing_services(root: pathlib.Path | None = None) -> tuple[str, ...]:
    """`discover` is called with the tree root, so it must accept one (#17452)."""
    root = pathlib.Path(root) if root is not None else _ROOT
    hits = []
    for rel in _SCRIPT_DIRS:
        base = root / rel
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            tree = _parse(path)
            if tree is not None and _imports_services(tree):
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
        tree = _parse(_ROOT / rel)
        if tree is None:
            continue
        inserts = _syspath_insertions(tree)
        if not any(_expression_reaches_repo_root(e) for e in inserts):
            offenders.append(rel)
    assert not offenders, (
        "these scripts import `services.*` but no `sys.path` insertion reaches the repo root, "
        "so `autobot_shared` is unreachable and the script dies at import under ansible "
        f"(#17452): {offenders}"
    )


def _one(src: str) -> ast.AST:
    return ast.parse(src)


def test_the_import_detector_sees_services_in_any_clause() -> None:
    """A regex anchored on the first clause missed `import os, services.x` (#17452 review)."""
    assert _imports_services(_one("import os, services.git_subprocess"))
    assert _imports_services(_one("from services.git_subprocess import ensure_full_history"))
    assert _imports_services(_one("import services"))
    assert not _imports_services(_one("import os, sys"))
    assert not _imports_services(_one("from myservices import x"))


def test_the_path_check_reads_the_inserted_expression_only() -> None:
    """A `parents[2]` token elsewhere must NOT satisfy the check (#17452 review).

    The shape this rejects is the one that shipped past the first detector: the
    expression handed to `sys.path` reaches only the backend root, while an
    unrelated line in the same file mentions `parents[2]`.
    """
    bad = _one(
        "import sys\n"
        "from pathlib import Path\n"
        "UNRELATED = Path(__file__).resolve().parents[2]\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
    )
    assert not any(_expression_reaches_repo_root(e) for e in _syspath_insertions(bad))

    good = _one(
        "import sys\n" "from pathlib import Path\n" "sys.path.insert(0, str(Path(__file__).resolve().parents[2]))\n"
    )
    assert any(_expression_reaches_repo_root(e) for e in _syspath_insertions(good))


def test_the_path_check_accepts_both_repo_root_spellings() -> None:
    """`parents[2]` and a three-deep `.parent` chain are the same reach."""
    chain = _one("import sys\nsys.path.append(str(P.parent.parent.parent))\n")
    assert any(_expression_reaches_repo_root(e) for e in _syspath_insertions(chain))
    idx = _one("import sys\nsys.path.insert(0, str(_S.parents[2]))\n")
    assert any(_expression_reaches_repo_root(e) for e in _syspath_insertions(idx))


def test_an_unparseable_script_is_skipped_not_silently_counted() -> None:
    """`nothing found` and `could not read` must not produce the same answer."""
    assert _parse(_ROOT / "does-not-exist.py") is None
