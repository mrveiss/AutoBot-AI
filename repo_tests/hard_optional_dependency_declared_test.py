# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A dependency a first-party module RAISES without must be declared (#14872).

The Docker SDK was imported by four modules under ``autobot-backend/`` and
declared in no requirements file anywhere in the repository. Every one of them
guarded the import and raised on the degraded path, which reads as correct
handling in isolation. Taken together it meant sandboxed code execution
downgraded to uncontainerised subprocess execution in any environment that did
not happen to have the SDK — and no environment was guaranteed to, because
nothing declared it. ``secure_sandbox_executor.py`` even swallowed its own raise
in the singleton factory and logged "SECURITY RISK" exactly once per process.

The distinction this guard draws is between the two things a ``try: import X /
except ImportError`` can mean:

* **genuinely optional** — the module carries on without ``X``, feature reduced.
  Nothing to declare, and this guard says nothing about it.
* **required, imported defensively** — the module RAISES when ``X`` is missing,
  usually so that *importing* it stays cheap for unrelated callers. That is a
  hard dependency wearing an optional coat, and a hard dependency that nothing
  declares is a feature that is off by default with no way to find out.

So: a module-level ``try/except ImportError`` whose except branch binds a flag,
where the module later raises on that flag, is a hard dependency — and its
distribution has to be named in a requirements file.

Discovery is by AST over tracked Python, never a hand-listed set of files: a
guard that has to be told which modules to watch will not be told about the
next one.
"""

from __future__ import annotations

import ast
import functools
import re
import subprocess  # nosec B404 — fixed argv, no shell, no caller input
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKIP_PARTS = {".git", "node_modules", "__pycache__", ".worktrees", ".claude", "venv", ".venv"}

_ROOTS = (
    _REPO_ROOT,
    _REPO_ROOT / "autobot-backend",
    _REPO_ROOT / "autobot-slm-backend",
    _REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts",
)

_DIST_ALIASES = {
    "yaml": "pyyaml",
    "dotenv": "python_dotenv",
    "PIL": "pillow",
    "cv2": "opencv_python",
    "sklearn": "scikit_learn",
    "psycopg2": "psycopg2_binary",
    "jwt": "pyjwt",
    "bs4": "beautifulsoup4",
    "saml2": "pysaml2",
}

# Hard dependencies still declared nowhere, each with the issue tracking it.
# Same self-guarding contract as the sibling guards: the parametrized test below
# asserts each entry is STILL undeclared, so declaring one forces its exemption
# out rather than leaving this file quietly guarding one path less than it
# claims. THIS DICT ONLY SHRINKS.
_KNOWN_UNDECLARED = {
    ("autobot-backend/knowledge/tiering.py", "diskann"): "#15035",
    ("autobot-backend/multimodal_processor/processors/voice.py", "librosa"): "#15035",
    ("autobot-backend/services/execution/modal_backend.py", "modal"): "#15035",
    ("autobot-infrastructure/shared/scripts/monitor_services.py", "flask"): "#15035",
    ("autobot-infrastructure/shared/scripts/monitor_services.py", "flask_cors"): "#15035",
}

_STDLIB = set(sys.stdlib_module_names) | {"__future__"}


def _tracked_python() -> list[Path]:
    """Tracked ``*.py``, from git rather than a walk — see the note in the sibling guard."""
    out = subprocess.run(  # nosec B603 — fixed argv
        ["git", "-C", str(_REPO_ROOT), "ls-files", "*.py"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [_REPO_ROOT / line for line in out.splitlines() if line]


def _declared_distributions() -> tuple[set[str], int]:
    """Every distribution named by a requirements file or pyproject in this checkout."""
    names: set[str] = set()
    files = 0
    for path in sorted(_REPO_ROOT.rglob("requirements*.txt")) + sorted(_REPO_ROOT.rglob("pyproject.toml")):
        if any(part in _SKIP_PARTS for part in path.relative_to(_REPO_ROOT).parts):
            continue
        files += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r'^["\']?([A-Za-z0-9][A-Za-z0-9._-]*)', line)
            if match:
                names.add(match.group(1).lower().replace("-", "_"))
    return names, files


_DECLARED, _REQUIREMENTS_FILES = _declared_distributions()


def _is_declared(top: str) -> bool:
    normalised = top.lower().replace("-", "_")
    if normalised in _DECLARED:
        return True
    alias = _DIST_ALIASES.get(top)
    if alias is not None and alias in _DECLARED:
        return True
    return any(declared.startswith(normalised + "_") for declared in _DECLARED)


def _resolves(module: str, own_dir: Path) -> bool:
    parts = module.split(".")
    for root in (*_ROOTS, own_dir):
        base = root.joinpath(*parts)
        if base.with_suffix(".py").exists() or (base / "__init__.py").exists():
            return True
    return False


def _guarded_import_blocks(tree: ast.Module) -> list[tuple[set[str], set[str]]]:
    """(top-level import names, flag names) for each module-level try/except ImportError.

    Module level only. A guarded import inside a function is a deferred import,
    a different shape with a different failure mode (#14839 covers it), and
    folding the two together would blur what a finding here means.
    """
    blocks: list[tuple[set[str], set[str]]] = []
    for node in tree.body:
        if not isinstance(node, ast.Try):
            continue
        caught: set[str] = set()
        for handler in node.handlers:
            for sub in ast.walk(handler.type) if handler.type else []:
                if isinstance(sub, ast.Name):
                    caught.add(sub.id)
        # Deliberately NOT bare `Exception`: a broad handler is not a
        # declaration that an import is optional, and treating it as one would
        # make this guard blind where it matters most.
        if not ({"ImportError", "ModuleNotFoundError"} & caught):
            continue
        modules: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Import):
                modules |= {alias.name.split(".")[0] for alias in sub.names}
            elif isinstance(sub, ast.ImportFrom) and sub.module and not sub.level:
                modules.add(sub.module.split(".")[0])
        flags: set[str] = set()
        for handler in node.handlers:
            for sub in ast.walk(handler):
                if isinstance(sub, ast.Assign):
                    flags |= {t.id for t in sub.targets if isinstance(t, ast.Name)}
        blocks.append((modules, flags))
    return blocks


def _flags_that_raise(tree: ast.Module, flags: set[str]) -> set[str]:
    """Flags whose ``if`` branch contains a ``raise`` — i.e. the import was required."""
    raising: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        mentioned = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)} & flags
        if mentioned and any(isinstance(child, ast.Raise) for child in ast.walk(node)):
            raising |= mentioned
    return raising


def _hard_dependencies_in_source(source: str, own_dir: Path) -> set[str]:
    """Third-party names this source guard-imports and then raises without.

    Split out from the sweep so the detector can be driven against a synthetic
    sample: with every real offender either declared or allowlisted, "the sweep
    found one" no longer proves the detector works.
    """
    tree = ast.parse(source)
    found: set[str] = set()
    for modules, flags in _guarded_import_blocks(tree):
        if not _flags_that_raise(tree, flags):
            continue
        found |= {m for m in modules if m not in _STDLIB and not _resolves(m, own_dir)}
    return found


@functools.lru_cache(maxsize=1)
def _sweep() -> tuple[tuple[tuple[str, str], ...], int, int]:
    """((relative path, package) tuple, files scanned, hard-dependency sites found).

    Memoised: this is a ~5000-file AST walk and every test below needs it.
    Returns tuples rather than lists so the cached value cannot be mutated
    by one test and read short by the next.
    """
    found: list[tuple[str, str]] = []
    scanned = 0
    for path in _tracked_python():
        rel = path.relative_to(_REPO_ROOT)
        if any(part in _SKIP_PARTS for part in rel.parts):
            continue
        try:
            hard = _hard_dependencies_in_source(path.read_text(encoding="utf-8"), path.parent)
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        scanned += 1
        found.extend((str(rel), package) for package in sorted(hard))
    return tuple(found), scanned, len(found)


def test_the_sweep_reached_the_tree() -> None:
    """Discovery floors, each guarding a different way to go quietly blind."""
    found, scanned, sites = _sweep()

    assert scanned > 4000, f"only parsed {scanned} tracked python files — git ls-files is not returning the tree"
    assert sites > 15, (
        f"only {sites} hard-guarded dependency sites found. Either the codebase "
        "stopped using the try/except-ImportError-then-raise shape, or the "
        "detector stopped recognising it — the second makes every assertion "
        "below pass over nothing"
    )
    assert _REQUIREMENTS_FILES >= 15, (
        f"only read {_REQUIREMENTS_FILES} requirements/pyproject files — the "
        "declaration oracle has gone blind and would report false findings"
    )
    assert len(_DECLARED) > 100, f"only {len(_DECLARED)} declared distributions found"


def test_the_sandbox_modules_are_still_discovered() -> None:
    """The four #14872 was filed for, named — discovery must keep reaching them.

    The sweep above would catch a regression anyway; naming these means a
    failure says *which* hard dependency stopped being watched, rather than
    that the count moved.
    """
    found, _, _ = _sweep()
    docker_sites = {rel for rel, package in found if package == "docker"}

    for expected in (
        "autobot-backend/secure_sandbox_executor.py",
        "autobot-backend/services/execution/docker_backend.py",
        "autobot-backend/services/docker_task_workspace.py",
    ):
        assert expected in docker_sites, (
            f"{expected} no longer registers as a hard docker dependency. If the "
            "guard-import was removed that is fine; if the detector stopped "
            "seeing it, the sandbox is unwatched again (#14872)"
        )


def test_every_hard_dependency_is_declared() -> None:
    """The #14872 defect: a dependency a module refuses to run without, declared nowhere."""
    found, _, _ = _sweep()
    offenders = [
        f"{rel}  ->  {package}"
        for rel, package in found
        if not _is_declared(package) and (rel, package) not in _KNOWN_UNDECLARED
    ]

    assert not offenders, (
        "these modules guard-import a package and then RAISE when it is absent, "
        "so it is a hard dependency — but no requirements file in this "
        "repository declares it. Nothing installs it, nothing records that it "
        "is needed, and the feature it powers is off by default with no way to "
        "tell (#14872):\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("entry,issue", sorted(_KNOWN_UNDECLARED.items()))
def test_each_exemption_is_still_undeclared(entry: tuple[str, str], issue: str) -> None:
    """An exemption that no longer applies exempts nothing, silently."""
    rel, package = entry
    path = _REPO_ROOT / rel

    assert path.is_file(), f"{rel} moved or was deleted — update or drop this exemption ({issue})"
    assert not _is_declared(package), (
        f"{package} is now declared, so the exemption for {rel} ({issue}) is "
        "obsolete — remove it from _KNOWN_UNDECLARED so the dependency is guarded again"
    )
    hard = _hard_dependencies_in_source(path.read_text(encoding="utf-8"), path.parent)
    assert package in hard, (
        f"{rel} no longer treats {package} as a hard dependency, so the "
        f"exemption ({issue}) is obsolete — remove it from _KNOWN_UNDECLARED"
    )


_SYNTHETIC_HARD = (
    "try:\n"
    "    import autobot_absent_pkg_14872\n"
    "    HAVE_IT = True\n"
    "except ImportError:\n"
    "    HAVE_IT = False\n"
    "\n"
    "def use():\n"
    "    if not HAVE_IT:\n"
    "        raise RuntimeError('not installed')\n"
    "    return autobot_absent_pkg_14872\n"
)

_SYNTHETIC_OPTIONAL = (
    "try:\n"
    "    import autobot_absent_pkg_14872\n"
    "    HAVE_IT = True\n"
    "except ImportError:\n"
    "    HAVE_IT = False\n"
    "\n"
    "def use():\n"
    "    if not HAVE_IT:\n"
    "        return None\n"
    "    return autobot_absent_pkg_14872\n"
)


def test_the_detector_still_fires_on_a_hard_dependency() -> None:
    """Positive control, replacing 'the sweep found an undeclared one'.

    Every real site is now either declared or allowlisted, so a detector that
    stopped recognising the shape would sail through the check above having
    found nothing — indistinguishable from a clean tree.
    """
    assert _hard_dependencies_in_source(_SYNTHETIC_HARD, _REPO_ROOT) == {"autobot_absent_pkg_14872"}


def test_the_detector_leaves_a_genuinely_optional_dependency_alone() -> None:
    """Negative control, and the whole point of the distinction.

    Same import, same flag — the only difference is that this one degrades
    instead of raising. A guard that flagged both would demand a declaration for
    every optional integration in the repo and be switched off within a week.
    """
    assert _hard_dependencies_in_source(_SYNTHETIC_OPTIONAL, _REPO_ROOT) == set()
