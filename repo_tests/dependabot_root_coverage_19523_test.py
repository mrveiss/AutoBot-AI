# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every tracked package root is in ``dependabot.yml`` for its ecosystem, or excused (#19523).

``.mcp``, ``mcp-autobot-tracker`` and ``mcp-structured-thinking`` were never configured,
so their lockfiles kept 3 high and 12 low/medium alerts that one refresh would have
closed (#19477). Nothing failed. A root with no dependabot entry produces no PR and no
error, so a missing one looks the same as a quiet week.

``dependabot_requirements_coverage_test.py`` already guards pip's ``requirements*.txt``
and models its ``-r``/``-c`` reach. This sibling covers the ecosystems whose reach is a
single directory: npm (``package.json``), docker (any Dockerfile or Containerfile),
uv (``uv.lock``) and pip's ``pyproject.toml``. It reads the config through that guard's
``dependabot_directories``, so both guards parse ``dependabot.yml`` the same way.

The reach model is dependabot's own: an ecosystem block reads the manifests sitting
directly in its ``directory`` and does not walk subdirectories. The one exception is
npm workspaces, where a covered root's ``workspaces`` list brings its members along.
#19477 moves the three MCP servers into a workspace, and this guard has to accept
that shape.

Roots are enumerated with ``git ls-files``, never a hand-listed set: a guard that has to
be told which roots exist will not be told about the next one.
"""

from __future__ import annotations

import fnmatch
import functools
import json
import posixpath
import re
from pathlib import Path
from typing import Callable

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.dependabot_requirements_coverage_test import _SKIP_PARTS, dependabot_directories

from autobot_shared.isolated_git import git, make_repo
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_REPO_ROOT = repo_root()
_CONFIG_REL = Path(".github/dependabot.yml")

#: The follow-up value for a root that pins nothing, so has nothing to update.
NO_DEPENDENCIES = "no dependencies"

#: dependabot-core's docker fetcher matches ``dockerfile``/``containerfile`` anywhere in a
#: file name, case-insensitively, so ``Dockerfile-ci`` and ``app_dockerfile`` are manifests too.
_DOCKERFILE = re.compile(r"(?:docker|container)file", re.IGNORECASE)

#: Which ecosystems' blocks cover a root of each kind. A ``pyproject.toml`` is read by
#: a pip block, or by a uv block when the root is a uv project.
_COVERED_BY = {"npm": ("npm",), "docker": ("docker",), "uv": ("uv",), "pip": ("pip", "uv")}

#: Uncovered roots, each with its follow-up (an issue, or NO_DEPENDENCIES) and the reason.
#: THIS ONLY SHRINKS: ``test_each_exemption_is_still_needed`` fails once an entry is
#: covered or its root is gone, so the follow-up's PR has to delete the entry.
_KNOWN_UNCOVERED: dict[tuple[str, str], tuple[str, str]] = {
    ("npm", ".mcp"): ("#19477", "MCP server; joins the MCP npm workspace that #19477 adds to dependabot.yml"),
    ("npm", "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker"): (
        "#19477",
        "MCP server; joins the MCP npm workspace that #19477 adds to dependabot.yml",
    ),
    ("npm", "autobot-infrastructure/shared/mcp/tools/mcp-structured-thinking"): (
        "#19477",
        "MCP server; joins the MCP npm workspace that #19477 adds to dependabot.yml",
    ),
    ("npm", "autobot-infrastructure/shared/config"): ("#16512", "1 devDependency and a tracked lockfile"),
    ("npm", "autobot-infrastructure/shared/ide-extensions/vscode-autobot"): (
        "#16512",
        "1 dependency and 7 devDependencies, no lockfile",
    ),
    ("npm", "autobot-plugins/terminal"): ("#16512", "8 devDependencies and 5 peerDependencies, no lockfile"),
    ("npm", "autobot-plugins/vnc"): ("#16512", "4 devDependencies and 1 peerDependency, no lockfile"),
    ("npm", "libs/autobot-sdk-ts"): ("#16512", "5 devDependencies and a tracked lockfile"),
    ("npm", "libs/autobot-ui"): ("#16512", "8 devDependencies and 2 peerDependencies, no lockfile"),
    ("docker", "autobot-infrastructure/autobot-backend/docker"): ("#19570", "sandbox.Dockerfile: FROM alpine:3.18"),
    ("docker", "autobot-infrastructure/autobot-frontend/docker"): (
        "#19570",
        "frontend.Dockerfile: FROM node:18-alpine",
    ),
    ("docker", "autobot-infrastructure/shared/docker"): ("#19570", "secure-sandbox.Dockerfile: FROM alpine:3.18"),
    ("pip", "libs/autobot-sdk-python"): ("#19570", "pyproject.toml declares httpx and pydantic"),
}


def _kind(name: str) -> str | None:
    """The ecosystem a tracked file name makes its directory a root of, if any."""
    if name == "package.json":
        return "npm"
    if name == "uv.lock":
        return "uv"
    if name == "pyproject.toml":
        return "pip"
    return "docker" if _DOCKERFILE.search(name) else None


def _roots(root: Path) -> list[tuple[str, str]]:
    """Every ``(ecosystem, directory)`` package root among the tracked files."""
    try:
        tracked = tracked_paths(root)
    except EmptyEnumeration:
        return []
    found = set()
    for rel in tracked:
        parts = rel.split("/")
        kind = _kind(parts[-1])
        if kind and not any(part in _SKIP_PARTS for part in parts):
            found.add((kind, posixpath.dirname(rel)))
    return sorted(found)


REACH = declare(
    "dependabot-package-roots",
    discover=_roots,
    floor=27,  # mid-window: population 27, window (27, 27)
    what="tracked (ecosystem, directory) package roots",
)


def _normalise(directory: str) -> str:
    return directory.strip("/")


def _glob_matches(path: str, pattern: str) -> bool:
    """Whether ``pattern`` matches ``path`` one segment at a time: ``*`` never crosses ``/``.

    ``fnmatch`` lets ``*`` match ``/``, so ``packages/*`` would also reach
    ``packages/a/nested``; npm and dependabot globs match one level per ``*``. A ``**``
    segment matches zero or more whole segments.
    """
    return _match_segments(path.split("/") if path else [], pattern.split("/") if pattern else [])


def _match_segments(path: list[str], pattern: list[str]) -> bool:
    if not pattern:
        return not path
    if pattern[0] == "**":
        return any(_match_segments(path[i:], pattern[1:]) for i in range(len(path) + 1))
    return bool(path) and fnmatch.fnmatchcase(path[0], pattern[0]) and _match_segments(path[1:], pattern[1:])


def _workspace_members(root: Path, directory: str, candidates: set[str]) -> set[str]:
    """The npm roots a covered root's ``workspaces`` brings into dependabot's reach."""
    manifest = root / directory / "package.json"
    if not manifest.is_file():
        return set()
    workspaces = json.loads(manifest.read_text(encoding="utf-8")).get("workspaces", [])
    if isinstance(workspaces, dict):
        workspaces = workspaces.get("packages", [])
    patterns = [posixpath.normpath(posixpath.join(directory, p)) for p in workspaces]
    return {c for c in candidates if any(_glob_matches(c, p) for p in patterns)}


def _covered(root: Path, config: Path, roots: list[tuple[str, str]]) -> set[tuple[str, str]]:
    """The roots some configured block reaches."""
    configured = {
        eco: {_normalise(d) for d in dependabot_directories(eco, config)} for eco in ("npm", "docker", "uv", "pip")
    }
    npm_dirs = {d for kind, d in roots if kind == "npm"}
    for directory in sorted(configured["npm"]):
        configured["npm"] |= _workspace_members(root, directory, npm_dirs)
    return {
        (kind, d)
        for kind, d in roots
        if any(_glob_matches(d, pattern) for eco in _COVERED_BY[kind] for pattern in configured[eco])
    }


@functools.lru_cache(maxsize=1)
def _uncovered() -> tuple[tuple[str, str], ...]:
    """The live tree's roots that no configured block reaches."""
    roots = list(REACH.examined(_REPO_ROOT))
    covered = _covered(_REPO_ROOT, _REPO_ROOT / _CONFIG_REL, roots)
    REACH.completed(len(roots))
    return tuple(sorted(set(roots) - covered))


def _npm_pins(path: Path) -> bool:
    manifest = json.loads((path / "package.json").read_text(encoding="utf-8"))
    sections = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
    return any(manifest.get(s) for s in sections) or (path / "package-lock.json").is_file()


def _pyproject_pins(path: Path) -> bool:
    import tomllib  # local, as pip_ignore_scope_test does (#15177)

    document = tomllib.loads((path / "pyproject.toml").read_text(encoding="utf-8"))
    project = document.get("project", {})
    groups = document.get("dependency-groups", {})  # PEP 735
    return bool(project.get("dependencies") or project.get("optional-dependencies") or any(groups.values()))


def _docker_pins(path: Path) -> bool:
    files = [f for f in path.iterdir() if f.is_file() and _DOCKERFILE.search(f.name)]
    return any(re.search(r"^\s*FROM\s", f.read_text(encoding="utf-8"), re.M | re.I) for f in files)


_PINS: dict[str, Callable[[Path], bool]] = {
    "npm": _npm_pins,
    "pip": _pyproject_pins,
    "docker": _docker_pins,
    "uv": lambda _path: True,
}


def _pins_something(root: Path, kind: str, directory: str) -> bool:
    """Whether the root declares anything dependabot could update."""
    return _PINS[kind](root / directory)


def _label(key: tuple[str, str]) -> str:
    return f"{key[0]}: /{key[1]}"


def test_the_roots_were_actually_found() -> None:
    """Named roots of every kind, so a narrowed sweep says which kind it lost."""
    roots = set(REACH.examined(_REPO_ROOT))
    for expected in (
        ("npm", "autobot-frontend"),
        ("npm", ".mcp"),
        ("docker", "docker/backend"),
        ("docker", "autobot-infrastructure/shared/docker"),
        ("uv", "autobot-infrastructure/shared/mcp/tools/knowledge-base-mcp"),
        ("pip", ""),
    ):
        assert expected in roots, f"{_label(expected)} is not in the population — FIX THE SWEEP"


def _configured_directory_exists(root: Path, directory: str) -> bool:
    """A literal directory is a directory; a glob must match at least one tracked directory."""
    pattern = _normalise(directory)
    if not any(ch in pattern for ch in "*?["):
        return (root / pattern).is_dir()
    try:
        tracked = tracked_paths(root)
    except EmptyEnumeration:
        return False
    return any(_glob_matches(posixpath.dirname(rel), pattern) for rel in tracked)


def test_every_configured_directory_exists() -> None:
    """A block on a moved directory scans nothing, and dependabot reports no error."""
    for eco in ("npm", "docker", "uv"):
        directories = dependabot_directories(eco, _REPO_ROOT / _CONFIG_REL)
        assert directories, f"no {eco} blocks parsed from dependabot.yml — FIX THE SWEEP"
        for directory in directories:
            assert _configured_directory_exists(
                _REPO_ROOT, directory
            ), f"dependabot.yml configures {eco} directory {directory!r}, which does not exist"


def test_every_package_root_is_covered_or_excused() -> None:
    """The #19523 defect: a root that pins dependencies and that no block ever updates."""
    unexcused = [k for k in _uncovered() if k not in _KNOWN_UNCOVERED]
    assert not unexcused, (
        "these tracked package roots have no dependabot.yml entry for their ecosystem, so "
        "nothing ever updates what they pin, security fixes included. Add a block for the "
        "directory, or record the root in _KNOWN_UNCOVERED with its follow-up issue and "
        "the reason (#19523):\n  " + "\n  ".join(_label(k) for k in unexcused)
    )


@pytest.mark.parametrize("key", sorted(_KNOWN_UNCOVERED), ids=_label)
def test_each_exemption_is_still_needed(key: tuple[str, str]) -> None:
    """An exemption for a covered or deleted root excuses nothing, silently."""
    assert key in REACH.examined(_REPO_ROOT), f"{_label(key)} is no longer a tracked root — delete its exemption"
    assert key in _uncovered(), f"{_label(key)} is covered now — delete its exemption from _KNOWN_UNCOVERED"


@pytest.mark.parametrize("key", sorted(_KNOWN_UNCOVERED), ids=_label)
def test_each_exemption_names_a_follow_up_and_a_reason(key: tuple[str, str]) -> None:
    follow_up, reason = _KNOWN_UNCOVERED[key]
    assert reason.strip(), f"{_label(key)}: an exemption needs a reason"
    if follow_up == NO_DEPENDENCIES:
        assert not _pins_something(_REPO_ROOT, *key), f"{_label(key)} is excused as pinning nothing, but it pins"
        return
    assert re.fullmatch(r"#\d+", follow_up), f"{_label(key)}: follow-up must be an issue or NO_DEPENDENCIES"
    assert _pins_something(_REPO_ROOT, *key), f"{_label(key)} pins nothing; excuse it as NO_DEPENDENCIES"


def _plant(tmp_path: Path, config: str) -> Path:
    """A git tree with one npm root that has dependencies, and the given dependabot.yml."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "package.json").write_text('{"dependencies": {"zod": "^3.22.0"}}', encoding="utf-8")
    (tmp_path / ".github").mkdir()
    (tmp_path / _CONFIG_REL).write_text(config, encoding="utf-8")
    git(make_repo(tmp_path), "add", "-A")
    return tmp_path


_BLOCK = "version: 2\nupdates:\n  - package-ecosystem: npm\n    directory: {}\n    schedule: {{interval: weekly}}\n"


def test_an_uncovered_root_with_dependencies_is_reported(tmp_path: Path) -> None:
    """Positive control: with the real tree excused, "found nothing" proves nothing."""
    tree = _plant(tmp_path, _BLOCK.format('"/elsewhere"'))
    assert _roots(tree) == [("npm", "app")]
    assert _pins_something(tree, "npm", "app")
    assert _covered(tree, tree / _CONFIG_REL, _roots(tree)) == set()


def test_the_same_root_is_clear_once_configured(tmp_path: Path) -> None:
    tree = _plant(tmp_path, _BLOCK.format('"/app"'))
    assert _covered(tree, tree / _CONFIG_REL, _roots(tree)) == {("npm", "app")}


def test_a_workspace_member_is_covered_through_its_workspace_root(tmp_path: Path) -> None:
    """The #19477 shape: members reached through a covered root's ``workspaces``."""
    tree = _plant(tmp_path, _BLOCK.format('"/"'))
    (tree / "package.json").write_text('{"workspaces": ["app"]}', encoding="utf-8")
    assert _covered(tree, tree / _CONFIG_REL, [("npm", ""), ("npm", "app")]) == {("npm", ""), ("npm", "app")}


def test_a_workspace_glob_does_not_reach_a_nested_package(tmp_path: Path) -> None:
    """Negative control: ``packages/*`` is one level; ``packages/a/nested`` stays uncovered."""
    tree = _plant(tmp_path, _BLOCK.format('"/"'))
    (tree / "package.json").write_text('{"workspaces": ["packages/*"]}', encoding="utf-8")
    roots = [("npm", ""), ("npm", "packages/a"), ("npm", "packages/a/nested")]
    assert _covered(tree, tree / _CONFIG_REL, roots) == {("npm", ""), ("npm", "packages/a")}


def test_a_double_star_segment_spans_levels() -> None:
    assert _glob_matches("packages/a/nested", "packages/**")
    assert _glob_matches("packages", "packages/**")
    assert not _glob_matches("other/a", "packages/**")
    assert not _glob_matches("packages/a/nested", "packages/*")


_GLOB_BLOCK = (
    "version: 2\nupdates:\n  - package-ecosystem: npm\n    directories: [{}]\n    schedule: {{interval: weekly}}\n"
)


def test_a_directories_glob_covers_what_it_matches(tmp_path: Path) -> None:
    """A ``directories`` entry with ``*`` covers a one-level match and nothing deeper."""
    tree = _plant(tmp_path, _GLOB_BLOCK.format('"/*"'))
    roots = [("npm", "app"), ("npm", "app/deep")]
    assert _covered(tree, tree / _CONFIG_REL, roots) == {("npm", "app")}
    assert _configured_directory_exists(tree, "/*")
    assert not _configured_directory_exists(tree, "/nomatch*")


def test_every_dockerfile_name_dependabot_reads_is_a_docker_root() -> None:
    """Contrast: ``Dockerfile-ci`` and ``ci.containerfile`` are manifests; ``docker-compose.yml`` is not."""
    assert _kind("Dockerfile-ci") == _kind("Dockerfile_x") == _kind("ci.containerfile") == "docker"
    assert _kind("Dockerfile") == _kind("sandbox.Dockerfile") == "docker"
    assert _kind("docker-compose.yml") is None
    assert _kind("dockerize.py") is None


def test_a_pyproject_with_only_dependency_groups_pins(tmp_path: Path) -> None:
    """PEP 735: packages declared only under ``[dependency-groups]`` still count as pinned."""
    (tmp_path / "pyproject.toml").write_text('[dependency-groups]\ndev = ["pytest>=8"]\n', encoding="utf-8")
    assert _pins_something(tmp_path, "pip", "")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    assert not _pins_something(tmp_path, "pip", "")
