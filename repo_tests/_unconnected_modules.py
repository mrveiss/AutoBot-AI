# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backend modules nothing in production imports or launches (#20512).

The population form of ``pipeline-scripts/check-new-module-callers.sh``: the same question
("does this module have a production caller?"), the same production filter (no test, fixture or
conftest file counts as a caller), but asked of the whole tree and compared with a frozen
baseline instead of asked of one PR's ``git diff --diff-filter=A``. A new module with no caller
is simply a module that is not in the baseline. The script's matcher is a bare substring grep
(``from.*STEM|import.*STEM``), so the stem ``utils`` is "called" by anything; this one resolves
the dotted name, relative imports included.

WHAT A CALLER IS
----------------
* another production ``.py`` file that imports the module (``import a.b``, ``from a import b``,
  ``from a.b import x``, relative forms resolved against the importer's package) or names it as a
  dotted string (``importlib.import_module("a.b")``, the router registry's string entries);
* a production non-Python file (shell, YAML, systemd unit, Jinja, TOML, Dockerfile, Makefile)
  that names the dotted module (``python -m a.b``, ``uvicorn a.b:app``, a celery ``include``) or
  its path (``autobot-backend/a/b.py``, ``a/b.py``).

WHAT IS NOT CANDIDATE
---------------------
``__init__.py`` (a package is live when anything under it is); any module with an
``if __name__ == "__main__"`` guard (a launchable entry point; whether anything launches it is
not decidable from here); anything under a ``migrations/`` directory (a runner loads those by
scanning the directory, and ``orphaned_database_migrations_test`` owns that wiring); and
``testkit/`` (test support, which only tests import).

WHAT THIS CANNOT SEE
--------------------
* **Transitive death**: ``A`` imported only by ``B``, ``B`` imported by nobody, counts ``A`` as
  connected. Only the leaf is reported.
* **Name collisions**: backend and SLM modules share dotted names (``api.foo``); an import of
  either marks both connected, the safe direction for a guard that must not false-fail.
* **Loading by directory scan** (``pkgutil.iter_modules``, glob-and-import, plugin directories):
  a module loaded that way has no textual reference and is reported. It belongs in the baseline
  with its issue, or gains a reference.
* An import inside a docstring or a comment counts as a caller.
* Whether a connected module is *used*: an imported name nobody calls is invisible.
"""

from __future__ import annotations

import re

from repo_tests._unconnected_common import Tree

#: Trees whose modules are candidates. The first two are not packages (dashed names), so their
#: dotted names are relative to the directory; ``autobot_shared`` is a package and keeps its name.
BACKEND_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
_NON_PACKAGE_ROOTS = ("autobot-backend", "autobot-slm-backend")

#: Non-Python production files that launch or configure Python modules.
_LAUNCHER_SUFFIXES = (
    ".sh",
    ".yml",
    ".yaml",
    ".service",
    ".j2",
    ".conf",
    ".toml",
    ".ini",
    ".cfg",
    "Dockerfile",
    "Makefile",
)

_FROM_RE = re.compile(r"from[ \t]+(\.*)([\w.]*)[ \t]+import[ \t]+(.*)", re.DOTALL)
_DOTTED_STR_RE = re.compile(r"""["']([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)["']""")
_MAIN_GUARD_RE = re.compile(r"""^if\s+__name__\s*==\s*["']__main__["']""", re.MULTILINE)
_TOKEN_RE = re.compile(r"[\w./\-]+")


def module_name(rel: str) -> str:
    """Dotted import name of a candidate file (relative to its import root)."""
    parts = rel.split("/")
    if parts[0] in _NON_PACKAGE_ROOTS:
        parts = parts[1:]
    parts[-1] = parts[-1].removesuffix(".py")
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _package_parts(rel: str) -> list[str]:
    parts = rel.split("/")[:-1]
    return parts[1:] if parts and parts[0] in _NON_PACKAGE_ROOTS else parts


def _statements(text: str):
    """Import statements of *text*, one string each; a parenthesised list is joined across its lines."""
    lines = iter(text.split("\n"))
    for line in lines:
        stripped = line.lstrip()
        if not stripped.startswith(("from ", "import ")):
            continue
        while "(" in stripped and ")" not in stripped:
            stripped += " " + next(lines, ")").strip()
        yield stripped


def import_refs(rel: str, text: str) -> set[str]:
    """Every dotted module name *text* (the source of *rel*) imports or names."""
    refs: set[str] = set()
    pkg = _package_parts(rel)
    for stmt in _statements(text):
        stmt = stmt.split("#", 1)[0]
        if stmt.startswith("import "):
            for item in stmt[len("import ") :].split(","):
                word = item.strip().split(" ")[0]
                if re.fullmatch(r"[\w.]+", word):
                    refs.add(word)
            continue
        found = _FROM_RE.match(stmt)
        if not found:
            continue
        dots, mod, names = found.groups()
        if dots:
            target = ".".join([*pkg[: max(len(pkg) - (len(dots) - 1), 0)], *([mod] if mod else [])])
        else:
            target = mod
        refs.add(target)
        for item in names.strip("() \t").split(","):
            word = item.strip().split(" ")[0].strip()
            if word.isidentifier():
                refs.add(f"{target}.{word}" if target else word)
    for dotted in _DOTTED_STR_RE.findall(text):
        parts = dotted.split(".")
        refs.update(".".join(parts[:i]) for i in range(1, len(parts) + 1))
    return refs


def candidates(tree: Tree) -> list[str]:
    """Production backend modules that could have a caller: not ``__init__``, not a ``__main__`` script."""
    return [
        rel
        for rel in tree.select(".py", under=BACKEND_ROOTS)
        if not rel.endswith("/__init__.py") and "/migrations/" not in rel and not _MAIN_GUARD_RE.search(tree.text(rel))
    ]


def _path_suffixes(tree: Tree) -> set[str]:
    """Every trailing path of every ``.py`` token a launcher file mentions (``a/b/c.py`` -> ``b/c.py``, ``c.py``)."""
    out: set[str] = set()
    for rel in tree.select(*_LAUNCHER_SUFFIXES):
        for token in _TOKEN_RE.findall(tree.text(rel)):
            if token.endswith(".py"):
                pieces = token.split("/")
                out.update("/".join(pieces[i:]) for i in range(len(pieces)))
    return out


def _launcher_tokens(tree: Tree) -> set[str]:
    out: set[str] = set()
    for rel in tree.select(*_LAUNCHER_SUFFIXES):
        out.update(t for t in _TOKEN_RE.findall(tree.text(rel)) if "." in t)
    return out


def unconnected(tree: Tree, cands: list[str] | None = None) -> list[str]:
    """Candidates with no production caller, sorted."""
    cands = candidates(tree) if cands is None else cands
    wanted = {module_name(rel): rel for rel in cands}
    called: set[str] = set()
    for rel in tree.select(".py"):
        for ref in import_refs(rel, tree.text(rel)):
            if ref in wanted and wanted[ref] != rel:
                called.add(ref)
    suffixes, tokens = _path_suffixes(tree), _launcher_tokens(tree)
    out = []
    for name, rel in wanted.items():
        in_root = rel.split("/", 1)[1] if rel.split("/")[0] in _NON_PACKAGE_ROOTS else rel
        # `in_root` is `x.py` for a module at the top of its import root, so a bare `python x.py` names it.
        launched = name in tokens or rel in suffixes or in_root in suffixes
        if name not in called and not launched:
            out.append(rel)
    return sorted(out)
