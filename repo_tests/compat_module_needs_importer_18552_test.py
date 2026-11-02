# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A backend module that declares backward compatibility must have an importer (#18552).

A compatibility facade exists so existing callers keep working. Once nothing imports it, it is
a second copy of the canonical module's surface that nothing exercises -- the #18552 audit
found 8 of them, each retired by repointing its importers and removing it.

WHAT COUNTS
-----------
* **Declares compatibility**: the *module docstring* (read from the syntax tree, not a comment
  or a string elsewhere) contains "backward compat", "re-export", "shim" or "facade". These are
  the phrasings the retired facades actually used.
* **Has an importer**: some OTHER tracked ``.py`` file -- test files included, because a test
  that imports a facade is the only reason several of them survived -- either imports the
  module (``import a.b``, ``from a import b``, ``from a.b import x``, relative forms resolved
  against the importing file's package) or names it as a dotted string (``importlib`` and
  ``mock.patch`` targets).

WHAT THIS CANNOT SEE, STATED
----------------------------
* The importer scan is textual (regex over source), so an import written inside a docstring
  example counts. That errs toward "has an importer", the safe direction for a deletion guard.
* A module reached only through a computed name (``import_module(prefix + name)``) has no
  importer here. Such a module goes on the allowlist with the issue that keeps it.
* A bare import of a module that lives on ``sys.path`` under a longer dotted name
  (``from architectural_pattern_analyzer import X``) is not matched to it. Such a module only
  needs an entry if its docstring declares compatibility.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_BACKEND = "autobot-backend/"

#: The phrasings the retired facades' docstrings used (checked against all 8, #18552).
_COMPAT_RE = re.compile(r"backward[- ]?compat|re-?export|\bshim\b|facade", re.IGNORECASE)

#: Modules that declare compatibility, have no importer, and are kept on purpose. Each value is
#: the issue that keeps it. An entry that gains an importer, stops declaring, or disappears
#: fails `test_every_allowlist_entry_is_still_needed` -- the list shrinks, it does not rot.
ALLOWLIST: dict[str, str] = {
    "autobot-backend/knowledge/memory_graph/__init__.py": "#12932 (decision-gated; pinned by its test)",
    "autobot-backend/async_work/__init__.py": "#18596 (not triaged: unified async-work facade, no static importer)",
}


def _is_source(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (
        name.endswith("_test.py") or name.startswith(("test_", "conftest")) or "/tests/" in rel
    )


def _declares_compat(source: str) -> bool:
    """True when the MODULE docstring declares backward compatibility."""
    if not _COMPAT_RE.search(source[:6000]):
        return False
    try:
        doc = ast.get_docstring(ast.parse(source)) or ""
    except SyntaxError:
        return False
    return bool(_COMPAT_RE.search(doc))


def _module_name(rel: str) -> str:
    """Dotted name of a backend file, relative to the backend root (its import root)."""
    parts = rel[len(_BACKEND) :].removesuffix(".py").split("/")
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


_FROM_RE = re.compile(r"^[ \t]*from[ \t]+(\.*)([\w.]*)[ \t]+import[ \t]+(\([^)]*\)|[^\n]*)", re.MULTILINE)
_IMPORT_RE = re.compile(r"^[ \t]*import[ \t]+([^\n#]+)", re.MULTILINE)
_DOTTED_STR_RE = re.compile(r"""["']([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)["']""")


def _package_parts(rel: str) -> list[str]:
    parts = rel.split("/")[:-1]
    return parts[1:] if rel.startswith(_BACKEND) else parts


def _import_refs(rel: str, text: str) -> set[str]:
    """Every dotted module name `text` (the source of `rel`) imports or names."""
    refs: set[str] = set()
    pkg = _package_parts(rel)
    for dots, mod, names in _FROM_RE.findall(text):
        if dots:
            base = pkg[: max(len(pkg) - (len(dots) - 1), 0)]
            target = ".".join([*base, *([mod] if mod else [])])
        else:
            target = mod
        refs.add(target)
        for item in re.sub(r"#[^\n]*", "", names).strip("() \t").replace("\n", " ").split(","):
            word = item.strip().split(" ")[0].strip()
            if word.isidentifier():
                refs.add(f"{target}.{word}" if target else word)
    for clause in _IMPORT_RE.findall(text):
        for item in clause.split(","):
            word = item.strip().split(" ")[0]
            if re.fullmatch(r"[\w.]+", word):
                refs.add(word)
    for dotted in _DOTTED_STR_RE.findall(text):
        parts = dotted.split(".")
        refs.update(".".join(parts[:i]) for i in range(1, len(parts) + 1))
    return refs


def _source_paths(root: Path) -> list[str]:
    try:
        return [rel for rel in tracked_paths(root, ".") if rel.endswith(".py")]
    except EmptyEnumeration:
        return []


def _compat_modules(root: Path) -> list[str]:
    """Backend source files whose module docstring declares backward compatibility."""
    found = []
    for rel in _source_paths(root):
        if rel.startswith(_BACKEND) and _is_source(rel):
            if _declares_compat((root / rel).read_text(encoding="utf-8", errors="replace")):
                found.append(rel)
    return found


REACH = declare(
    "compat-module-needs-importer",
    discover=_compat_modules,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=114,
    what="autobot-backend non-test python modules whose module docstring declares backward compatibility",
    roots=("autobot-backend",),
    growth=20,
)


def _unimported(root: Path, paths: list[str], candidates: list[str]) -> list[str]:
    """`candidates` that no OTHER file in `paths` imports or names."""
    wanted = {_module_name(rel): rel for rel in candidates}
    importers: dict[str, set[str]] = {name: set() for name in wanted}
    for rel in paths:
        for ref in _import_refs(rel, (root / rel).read_text(encoding="utf-8", errors="replace")):
            if ref in importers and rel != wanted[ref]:
                importers[ref].add(rel)
    return sorted(wanted[name] for name, who in importers.items() if not who)


@functools.lru_cache(maxsize=1)
def _live_unimported() -> tuple[str, ...]:
    root = repo_root()
    return tuple(_unimported(root, _source_paths(root), list(REACH.examined(root))))


def test_every_compat_module_has_an_importer_or_an_allowlist_entry() -> None:
    orphans = [rel for rel in _live_unimported() if rel not in ALLOWLIST]
    assert not orphans, (
        f"#18552: {orphans} declare backward compatibility but nothing imports them. Repoint the "
        "callers at the canonical module and remove the facade; if it must stay, add it to ALLOWLIST "
        "with the issue that keeps it."
    )


def test_every_allowlist_entry_is_still_needed() -> None:
    stale = sorted(rel for rel in ALLOWLIST if rel not in _live_unimported())
    assert not stale, f"#18552: ALLOWLIST entries that now have an importer, no compat docstring, or no file: {stale}"


# ---------------------------------------------------------------------------
# Contrast: the same synthetic facade fails bare and passes once allowlisted or imported.
# ---------------------------------------------------------------------------

_FACADE = '"""Old API -- backward compatibility shim over ``pkg.new``."""\nfrom pkg.new import thing\n'


def _tree(tmp_path: Path, **extra: str) -> tuple[list[str], list[str]]:
    files = {"autobot-backend/pkg/old.py": _FACADE, "autobot-backend/pkg/new.py": "thing = 1\n", **extra}
    for rel, body in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(body, encoding="utf-8")
    paths = sorted(files)
    return paths, [rel for rel in paths if _is_source(rel) and _declares_compat(files[rel])]


def _verdict(tmp_path: Path, allow: dict[str, str], **extra: str) -> list[str]:
    paths, candidates = _tree(tmp_path, **extra)
    return [rel for rel in _unimported(tmp_path, paths, candidates) if rel not in allow]


def test_a_facade_with_no_importer_fails(tmp_path: Path) -> None:
    assert _verdict(tmp_path, {}) == ["autobot-backend/pkg/old.py"]


def test_the_same_facade_allowlisted_passes(tmp_path: Path) -> None:
    assert _verdict(tmp_path, {"autobot-backend/pkg/old.py": "#1"}) == []


@pytest.mark.parametrize(
    ("label", "rel", "body"),
    [
        ("an absolute import", "autobot-backend/api/use.py", "from pkg.old import thing\n"),
        ("a package-level import", "autobot-backend/api/use.py", "from pkg import old\n"),
        ("a relative import", "autobot-backend/pkg/use.py", "from .old import thing\n"),
        ("a parenthesised relative import", "autobot-backend/pkg/use.py", "from . import (\n    old,\n)\n"),
        ("a test importer", "autobot-backend/pkg/old_test.py", "import pkg.old\n"),
        ("a dotted patch target", "autobot-backend/api/use_test.py", 'patch("pkg.old.thing")\n'),
    ],
)
def test_each_import_form_counts_as_an_importer(tmp_path: Path, label: str, rel: str, body: str) -> None:
    assert _verdict(tmp_path, {}, **{rel: body}) == [], label


def test_a_look_alike_name_is_not_an_importer(tmp_path: Path) -> None:
    other = {"autobot-backend/api/use.py": "from other.old import thing\nimport pkg.older\n"}
    assert _verdict(tmp_path, {}, **other) == ["autobot-backend/pkg/old.py"]


@pytest.mark.parametrize(
    ("doc", "expected"),
    [
        ('"""Backward-compatible shim."""\n', True),
        ('"""Re-exports the canonical class."""\n', True),
        ('"""A facade over x."""\n', True),
        ('"""Does real work."""\n# shim in a comment\nx = "backward compat"\n', False),
        ("x = 1\n", False),
    ],
)
def test_only_the_module_docstring_declares_compatibility(doc: str, expected: bool) -> None:
    assert _declares_compat(doc) is expected


def test_the_scan_is_not_vacuous() -> None:
    """The retired facades are gone, but the allowlisted ones still declare; fewer is a blind scan."""
    declared = set(REACH.examined(repo_root()))
    assert set(ALLOWLIST) <= declared, sorted(set(ALLOWLIST) - declared)
