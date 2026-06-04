"""Shared parsing context — AST cache + target file iteration."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

_EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        ".git",
        "dist",
        "build",
        ".tox",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".worktrees",
        "htmlcov",
    }
)


@dataclass
class Context:
    repo_root: Path
    _ast_cache: dict[Path, ast.AST | None] = field(default_factory=dict)

    def parse(self, file_path: Path) -> ast.AST | None:
        if file_path in self._ast_cache:
            return self._ast_cache[file_path]
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, OSError, UnicodeDecodeError):
            self._ast_cache[file_path] = None
            return None
        self._ast_cache[file_path] = tree
        return tree

    def iter_targets(self, targets: list[str], *, suffixes: set[str]) -> Iterator[Path]:
        for target in targets:
            base = self.repo_root / target
            if not base.exists():
                continue
            yield from _walk(base, suffixes)


def _walk(base: Path, suffixes: set[str]) -> Iterator[Path]:
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in suffixes:
            continue
        try:
            rel = path.relative_to(base)
        except ValueError:
            continue
        if any(part in _EXCLUDED_DIRS for part in rel.parts):
            continue
        yield path


def file_in_targets(file_path: Path, targets: list[str], *, repo_root: Path) -> bool:
    try:
        rel = file_path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    rel_str = str(rel)
    return any(rel_str == t or rel_str.startswith(f"{t}/") for t in targets)
