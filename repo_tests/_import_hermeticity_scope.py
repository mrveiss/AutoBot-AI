# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What the import-hermeticity sweep examines, and how much of it one diff reaches (#16198).

Split out of ``import_hermeticity_test.py`` so the workflow can choose a pull
request's mode before the dependency install: this module needs only the standard
library. The sweep and the workflow both read the population from :func:`entries`,
so there is one definition of "a swept module", not a second list in YAML.

:func:`plan` picks the mode from a pull request's changed files:

* **full** -- the diff touches the sweep itself (:data:`SELF_FILES`). Only a full run
  can check the known-offender baseline for entries that no longer fail.
* **subset** -- the diff changes swept modules. The test examines those plus their
  direct importers (:func:`with_direct_importers`): if B calls into A at import, a
  change that makes A connect fails B's import, not A's.
* **none** -- no swept module changed. Nothing is examined, and the run says so.

What a subset does NOT reach. Each is a stated gap, not a blind spot, and the full
sweep on every push to Dev_new_gui covers it:

* a module that reaches the changed one only through an intermediate's *function*
  called at import time -- only direct importers are added;
* a change confined to a module outside the swept packages, such as a backend
  ``services/`` module an ``api/`` module imports -- it has no entry to match;
* a deleted module -- its former importers are not re-examined;
* a change to the declared dependencies alone -- no module changed;
* an import the AST cannot see, such as ``importlib.import_module`` on a computed name.
"""

from __future__ import annotations

import ast
import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from repo_tests._paths import repo_root

#: ``(sys.path entry relative to the repo root, package directory)``. Each backend
#: puts its own directory on ``sys.path``, so ``api`` means a different package in
#: each -- which is exactly why both are swept rather than one standing in for both.
ROOTS: tuple[tuple[str, str], ...] = (
    ("autobot-backend", "api"),
    ("autobot-slm-backend", "api"),
    (".", "autobot_shared"),
)

#: The sweep's own files. A pull request touching any of them runs the full sweep:
#: each can change the answer for every module, and only a full run checks the
#: baseline for stale entries. ``test_every_self_file_exists_and_triggers_the_workflow``
#: pins each one to the workflow's ``paths:`` filters.
SELF_FILES: frozenset[str] = frozenset(
    {
        ".github/workflows/import-hermeticity-sweep.yml",
        "repo_tests/_import_hermeticity_scope.py",
        "repo_tests/import_hermeticity_known_offenders.py",
        "repo_tests/import_hermeticity_test.py",
    }
)


@dataclass(frozen=True)
class Entry:
    """One swept module."""

    #: The ``sys.path`` entry it imports from, repo-relative: ``autobot-backend``,
    #: ``autobot-slm-backend`` or ``.``. The two backends share names -- ``api.auth``
    #: is two modules -- so a module is the pair, never the name alone.
    tree: str
    #: Its dotted name from that entry.
    module: str
    #: Its source, repo-relative and POSIX: the spelling ``git diff --name-only`` prints.
    path: str

    def path_entry(self, root: Path) -> str:
        """The absolute ``sys.path`` entry under *root*."""
        return str(root if self.tree == "." else root / self.tree)

    @property
    def package(self) -> str:
        """The package a relative import in this module resolves against."""
        if self.path.endswith("/__init__.py"):
            return self.module
        return self.module.rpartition(".")[0]


def module_name(package: str, path: Path, package_dir: Path) -> str:
    """Dotted name for *path*, which lives under *package_dir*."""
    rel = path.relative_to(package_dir)
    parts = [package] + list(rel.parts)
    if parts[-1] == "__init__.py":
        parts.pop()
    else:
        parts[-1] = parts[-1][: -len(".py")]
    return ".".join(parts)


def entries(root: Path) -> list[Entry]:
    """Every non-test module in scope, in probe order.

    Returns an empty list on a tree that holds none, and never raises: the reach
    meta-test hands every declaration an empty repository to prove the floor can
    actually fire (#16154).
    """
    found: list[Entry] = []
    for tree, package in ROOTS:
        package_dir = (root if tree == "." else root / tree) / package
        if not package_dir.is_dir():
            continue
        for path in sorted(package_dir.rglob("*.py")):
            if "__pycache__" in path.parts or path.name.endswith("_test.py") or path.name.startswith("test_"):
                continue
            found.append(Entry(tree, module_name(package, path, package_dir), path.relative_to(root).as_posix()))
    return found


def listed_paths(raw: str) -> list[str]:
    """The newline-separated paths the workflow hands the sweep, as a sorted set."""
    return sorted({line.strip() for line in raw.splitlines() if line.strip()})


def matching(population: Sequence[Entry], listed: Iterable[str]) -> list[Entry]:
    """The population entries whose source file is one of *listed*."""
    wanted = set(listed)
    return [entry for entry in population if entry.path in wanted]


def _absolute(entry: Entry, module: str | None, level: int) -> str | None:
    """The absolute name ``from <dots><module> import`` refers to inside *entry*.

    None when the dots climb above the top-level package: that is an ImportError at
    run time, not an edge.
    """
    if level == 0:
        return module
    parts = entry.package.split(".")
    keep = len(parts) - (level - 1)
    if keep <= 0 or not parts[0]:
        return None
    base = ".".join(parts[:keep])
    return f"{base}.{module}" if module else base


def imported_names(entry: Entry, source: str) -> set[str]:
    """Every dotted name *source* imports, relative imports resolved.

    The whole module is read, function bodies included: a function called at top
    level runs its imports at import time, so reading only the module body would
    under-select. ``import a.b`` names ``a`` and ``a.b``; ``from a import b`` names
    ``a`` and ``a.b``, which is either a submodule or matches nothing.
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(source, filename=entry.path)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                names.update(".".join(parts[:end]) for end in range(1, len(parts) + 1))
        elif isinstance(node, ast.ImportFrom):
            base = _absolute(entry, node.module, node.level)
            if base:
                names.add(base)
                names.update(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")
    return names


def direct_importers(root: Path, population: Sequence[Entry], targets: Iterable[Entry]) -> set[Entry]:
    """The population entries that import one of *targets* directly.

    A name resolves the way the probe's ``sys.path`` does: in the importer's own
    tree first, then the repository root. So the SLM's ``api.auth`` is never taken
    for the backend's, and either backend's import of ``autobot_shared`` is seen.
    """
    wanted = set(targets)
    index = {(entry.tree, entry.module): entry for entry in population}
    found: set[Entry] = set()
    for entry in population:
        for name in imported_names(entry, (root / entry.path).read_text(encoding="utf-8")):
            target = index.get((entry.tree, name)) or index.get((".", name))
            if target in wanted and target != entry:
                found.add(entry)
                break
    return found


def with_direct_importers(root: Path, population: Sequence[Entry], changed: Sequence[Entry]) -> list[Entry]:
    """*changed* plus every module that imports one of them directly, in probe order."""
    selected = set(changed) | direct_importers(root, population, changed)
    return [entry for entry in population if entry in selected]


def plan(changed: Iterable[str], population: Sequence[Entry]) -> tuple[str, list[str]]:
    """``(mode, paths)`` for a pull request whose diff lists *changed*.

    Only population files are handed on, so the test can require every one of them
    to match a module.
    """
    paths = {path.strip() for path in changed if path.strip()}
    if paths & SELF_FILES:
        return "full", []
    swept = sorted(paths & {entry.path for entry in population})
    return ("subset", swept) if swept else ("none", [])


_SUMMARY = {
    "full": "Full sweep: this pull request changes the sweep itself, so every module is examined.\n",
    "subset": "Subset sweep: {count} changed module(s), plus every module importing one directly.\n",
    "none": "No swept module changed, nothing examined. A run that did not look, not a clean result.\n",
}


def main(argv: Sequence[str]) -> int:
    """Workflow entry point: ``python -m repo_tests._import_hermeticity_scope <changed-files>``.

    Reads ``git diff --name-only`` output; writes ``mode`` and ``modules`` to
    ``GITHUB_OUTPUT`` and the decision to ``GITHUB_STEP_SUMMARY``.
    """
    changed = Path(argv[0]).read_text(encoding="utf-8").splitlines()
    mode, paths = plan(changed, entries(repo_root()))
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write(f"mode={mode}\nmodules<<MODULES_EOF\n" + "".join(f"{path}\n" for path in paths) + "MODULES_EOF\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write("## Import-hermeticity sweep\n\n" + _SUMMARY[mode].format(count=len(paths)))
        summary.write("".join(f"- `{path}`\n" for path in paths))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
