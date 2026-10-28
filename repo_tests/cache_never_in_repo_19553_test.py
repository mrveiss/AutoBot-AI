# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A cache never resolves inside the repository (#19553, owner ruling 2026-10-25).

"If it can be regenerated it has no place in repo." The one home is
``autobot_shared.paths.cache_root()`` / ``shared_cache_path()``: ``AUTOBOT_CACHE_DIR``,
else the user cache, else a temp dir -- and a candidate inside a checkout is skipped.

The sweep reads every non-test Python module of the backends and ``autobot_shared``
for the two shapes that put a cache under the checkout: a relative ``data/...cache``
literal (resolved against the cwd, i.e. the code tree), and ``PATH.DATA_DIR`` /
``PATH.PROJECT_ROOT`` joined with a cache-named path. Contrast tests rebuild each
shape so a clean live run cannot come from a detector that lost its teeth.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared import paths
from autobot_shared.isolated_git import make_repo

_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
_TEST = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$|conftest\.py$)")
_CACHE_NAME = re.compile(r"cache|hashes\.json", re.IGNORECASE)
_RELATIVE_DATA = re.compile(r"^(\./)?data/")
_REPO_ANCHORS = frozenset({"DATA_DIR", "PROJECT_ROOT"})


def _modules(root: Path) -> list[Path]:
    found = []
    for top in _ROOTS:
        base = root / top
        if base.is_dir():
            found += [p for p in sorted(base.rglob("*.py")) if not _TEST.search(p.relative_to(root).as_posix())]
    return found


REACH = declare(
    "cache-never-in-repo",
    discover=_modules,
    floor=3278,
    growth=300,  # ~9%: ordinary backend growth between repins must not turn an unrelated PR red
    what="non-test backend and shared modules",
    roots=_ROOTS,
)


def _is_repo_anchor(node: ast.AST) -> bool:
    """``PATH.DATA_DIR`` / ``DATA_DIR`` / ``PROJECT_ROOT``, or ``Path("data")`` -- a base inside the checkout."""
    if isinstance(node, ast.Attribute | ast.Name):
        return getattr(node, "attr", getattr(node, "id", "")) in _REPO_ANCHORS
    is_path_call = isinstance(node, ast.Call) and getattr(node.func, "id", "") in {"Path", "PurePath"}
    return is_path_call and bool(node.args) and _text(node.args[0]) in {"data", "./data"}


def _text(node: ast.AST) -> str:
    """The literal text of a string or f-string node (formatted parts become ``{}``)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(_text(v) if isinstance(v, ast.Constant) else "{}" for v in node.values)
    return ""


def _path_operands(node: ast.AST) -> list[ast.AST]:
    """``a / b / c`` flattened to ``[a, b, c]``; ``os.path.join(a, b)`` to its args; else ``[node]``."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _path_operands(node.left) + [node.right]
    if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in {"join", "joinpath"} and node.args:
        base = [node.func.value] if getattr(node.func, "attr", "") == "joinpath" else []
        return base + list(node.args)
    return [node]


def _hit(node: ast.AST) -> str | None:
    """Why *node* puts a cache under the checkout, or None."""
    text = _text(node)
    if text and _RELATIVE_DATA.match(text) and _CACHE_NAME.search(text):
        return f"relative cache path {text!r}"
    if isinstance(node, ast.JoinedStr) and any(
        isinstance(v, ast.FormattedValue) and _is_repo_anchor(v.value) for v in node.values
    ):
        return f"f-string under a repo anchor: {text!r}" if _CACHE_NAME.search(text) else None
    operands = _path_operands(node)
    if len(operands) > 1 and _is_repo_anchor(operands[0]) and any(_CACHE_NAME.search(_text(o)) for o in operands[1:]):
        return "cache path joined under a repo anchor"
    return None


def repo_caches(source: str, rel: str) -> list[str]:
    """Each place *source* puts a cache under the checkout (outermost expression only, no double count)."""
    found, seen = [], set()
    for node in ast.walk(ast.parse(source)):
        if id(node) in seen or not isinstance(node, ast.expr):
            continue
        reason = _hit(node)
        if reason:
            found.append(f"{rel}:{node.lineno}: {reason}")
            seen.update(id(child) for child in ast.walk(node))
    return found


def test_no_cache_resolves_inside_the_repo_on_the_live_tree() -> None:
    root = repo_root()
    files = REACH.examined(root)
    found = [hit for p in files for hit in repo_caches(p.read_text(encoding="utf-8"), p.relative_to(root).as_posix())]
    REACH.completed(files)
    assert (
        not found
    ), f"use autobot_shared.paths.shared_cache_path() -- a cache never goes in the repo (#19553): {found}"


def test_the_cache_dir_variable_is_registered() -> None:
    """``paths`` reads it through ``CACHE_DIR_ENV``, which the literal-scanning registry check cannot see."""
    from autobot_shared.env_registry import REGISTRY

    assert (
        paths.CACHE_DIR_ENV in REGISTRY
    ), f"register {paths.CACHE_DIR_ENV} in autobot_shared/env_registry_knowledge.py"


def test_the_shared_cache_path_is_outside_this_checkout() -> None:
    assert not paths.shared_cache_path("probe").resolve().is_relative_to(repo_root().resolve())


@pytest.mark.parametrize(
    "source",
    [
        'CACHE = "data/cache/claude_responses"\n',
        'def f(cache_dir: str = "data/openvino_cache"): ...\n',
        'CACHE = PATH.DATA_DIR / ".code_index_hashes.json"\n',
        'CACHE = PATH.PROJECT_ROOT / "embeddings_cache"\n',
        'CACHE = os.path.join(PATH.DATA_DIR, "cache")\n',
        'CACHE = Path("data") / "cache"\n',
        'CACHE = PATH.DATA_DIR / "models" / "cache"\n',
        'CACHE = f"{PATH.DATA_DIR}/cache"\n',
        'CACHE = DATA_DIR / "cache"\n',
        'CACHE = PATH.DATA_DIR.joinpath("x", "cache")\n',
    ],
)
def test_each_repo_cache_shape_is_flagged(source: str) -> None:
    assert repo_caches(source, "x.py")


def test_data_that_is_not_a_cache_and_the_helper_are_not_flagged() -> None:
    assert not repo_caches('DB = PATH.DATA_DIR / "chromadb"\nC = shared_cache_path("x", "cache.json")\n', "x.py")


def test_a_cache_dir_inside_this_checkout_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(paths.CACHE_DIR_ENV, str(repo_root() / "data" / "cache"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert paths.cache_root() == (tmp_path / "xdg" / "autobot").resolve()


def test_an_unrelated_git_repo_above_the_cache_is_not_this_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dotfiles ``~/.git`` must not push the cache into a temp dir a reboot empties."""
    home = tmp_path / "home"
    make_repo(home)
    monkeypatch.setenv(paths.CACHE_DIR_ENV, str(home / ".cache" / "autobot"))
    assert paths.cache_root() == (home / ".cache" / "autobot").resolve()


def test_a_relative_cache_dir_is_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(paths.CACHE_DIR_ENV, "data/cache")
    monkeypatch.setenv("XDG_CACHE_HOME", "relative-xdg")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.cache_root() == (tmp_path / ".cache" / "autobot").resolve()


def test_no_candidate_outside_the_code_falls_back_to_temp_with_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(paths.CACHE_DIR_ENV, str(repo_root() / "c1"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(repo_root() / "c2"))
    monkeypatch.setenv("HOME", str(repo_root()))
    with pytest.warns(RuntimeWarning, match="AUTOBOT_CACHE_DIR"):
        assert paths.cache_root().name == "autobot-cache"


def test_the_key_does_not_depend_on_the_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    here = paths.shared_cache_path("probe")
    monkeypatch.chdir(tmp_path)
    assert paths.shared_cache_path("probe") == here


def test_an_operator_cache_dir_outside_any_checkout_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(paths.CACHE_DIR_ENV, str(tmp_path / "var-cache"))
    assert paths.cache_root() == (tmp_path / "var-cache").resolve()
