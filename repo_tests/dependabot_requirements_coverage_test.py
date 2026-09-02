# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A tracked manifest dependabot cannot reach never gets a security bump (#14562).

``autobot-npu-worker/resources/windows-npu-worker/requirements.txt`` pinned
``tokenizers>=0.15.0`` for as long as it has existed. The tree above it carries a
dependabot entry (``directory: "/autobot-npu-worker"``), so the pin looked
covered — but dependabot's pip ecosystem resolves manifests relative to the
configured ``directory`` and recurses only through ``-r``/``-c`` includes. It
does not walk subdirectories. Two levels down with no include chain, that file
was scanned by nothing: no update of any kind reached it, security ones
included, and it carried none of the conflict caps its two scanned siblings do.

The reach model here is not inferred from documentation. It is what this
repository has been observed to do:

* the root ``/`` block's grouped PR #14951 edited ``autobot-backend/requirements.txt``
  and six ``requirements-ci/*.txt`` files — both sets are subdirectory files
  reachable ONLY through the ``-r`` lines in ``requirements-dev.txt`` and
  ``requirements-ci.txt``, and it touched no subdirectory manifest lacking one;
* #14722 bumped ``openai`` into ``autobot-backend``'s own manifest from the root
  block through that same ``-r`` chain, which is why the root block repeats the
  ``/autobot-backend`` exclusion (see the comment on it in ``dependabot.yml``).

So: reach = the manifests sitting directly in a configured ``directory``, plus
everything transitively included from them. That is exactly what
``pip_ignore_scope_test._files_reachable_from`` already models, and this guard
imports it rather than restating it — one definition of reach, not two.

The POPULATION is derived the same way, from ``git ls-files`` rather than a
hand-listed set: a guard that has to be told which manifests exist will not be
told about the next one. It is the include-closure of every tracked
``requirements*.txt``, which is what pulls in ``requirements-ci/*.txt`` (named
``agent.txt``, ``ai-ml.txt`` and so on — a plain ``requirements*.txt`` glob
misses every one of them) and ``constraints/shared.txt``.
"""

from __future__ import annotations

import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

import pytest
import yaml
from repo_tests.pip_ignore_scope_test import _files_reachable_from, _resolve_includes

from autobot_shared.paths import scrubbed_git_env

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONFIG = _REPO_ROOT / ".github" / "dependabot.yml"

# Relative to the repo root, never matched against the absolute path (#14484):
# this repo runs from `.worktrees/<branch>/` checkouts, where an absolute match
# would hit the root itself and empty the population.
_SKIP_PARTS = {".git", "node_modules", "__pycache__", ".worktrees", ".claude", "venv", ".venv"}

# Tracked manifests deliberately left outside dependabot's reach, each with the
# reason. THIS DICT ONLY SHRINKS: the parametrized test below asserts each entry
# is STILL unreached, so putting one inside a block's directory forces its
# exemption out rather than leaving this guard quietly covering one file less
# than it claims.
_KNOWN_UNSCANNED = {
    "docs/guides/requirements-local.txt": (
        "a worked example inside a guide, not an installed manifest. No workflow, "
        "Dockerfile or deploy role reads it; its floors are illustrative and "
        "deliberately loose so the guide keeps working on older hosts. Scanning it "
        "would produce weekly PRs against documentation prose (#14562)."
    ),
    "repo_tests/requirements_ci_drift_baseline.txt": (
        "an allowlist of PACKAGE NAMES, not a manifest — it records the production "
        "packages CI deliberately omits, for tools/lint/check_requirements_ci_drift.py. "
        "It carries no version specifiers at all and nothing installs from it; it is "
        "in this population only because its filename starts with `requirements` (#14562)."
    ),
}


def _tracked_manifests(root: Path = _REPO_ROOT) -> list[Path]:
    """Tracked ``*requirements*.txt``, from git rather than a walk.

    ``git ls-files`` and not ``rglob`` for the reason the sibling guards give:
    a walk under a worktree checkout picks up files belonging to other branches.
    """
    out = subprocess.run(  # nosec B603  # fixed argv
        ["git", "-C", str(root), "ls-files", "*requirements*.txt"],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    ).stdout
    paths = [root / line for line in out.splitlines() if line]
    return [p for p in paths if not any(part in _SKIP_PARTS for part in p.relative_to(root).parts)]


def _population(root: Path = _REPO_ROOT) -> set[Path]:
    """Every manifest in the repository, including ones reached only by ``-r``/``-c``."""
    files: set[Path] = set()
    for manifest in _tracked_manifests(root):
        _resolve_includes(manifest, files)
    return {p for p in files if not any(part in _SKIP_PARTS for part in p.relative_to(root).parts)}


def _pip_directories() -> list[str]:
    config = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))
    return [u["directory"] for u in config["updates"] if u.get("package-ecosystem") == "pip"]


def _reach(directories: list[str], root: Path = _REPO_ROOT) -> set[Path]:
    """Every manifest some configured pip block can edit."""
    files: set[Path] = set()
    for directory in directories:
        files |= _files_reachable_from(directory, root)
    return files


def _relative(paths: set[Path], root: Path = _REPO_ROOT) -> set[str]:
    return {str(p.relative_to(root)) for p in paths}


def test_the_population_was_actually_built() -> None:
    """Floor on the INPUT, before any rule reads it.

    A sweep that matches zero files still passes every set-difference below it,
    reporting a clean repository because it looked at nothing. This runs first
    and names the failure.
    """
    population = _relative(_population())

    assert len(population) >= 25, (
        f"only {len(population)} manifests in the population — FIX THE SWEEP. "
        "git ls-files is not returning the tree, or the include resolution "
        "stopped following `-r`. Every coverage rule below now passes over nothing."
    )
    for expected in (
        "autobot-backend/requirements.txt",
        "requirements-ci/ai-ml.txt",
        "constraints/shared.txt",
        "autobot-npu-worker/resources/windows-npu-worker/requirements.txt",
    ):
        assert expected in population, (
            f"{expected} is not in the population — FIX THE SWEEP. The first two "
            "are reached only through `-r`, `constraints/shared.txt` only through "
            "`-c`, and the fourth is the file #14562 was filed for."
        )


def test_the_reach_was_actually_computed() -> None:
    """Floor on the OTHER input. An empty reach set makes every file look uncovered.

    That direction fails loudly rather than silently, but it fails with a list of
    thirty filenames and no hint that the config was the problem — so it is named.
    """
    directories = _pip_directories()

    assert len(directories) >= 9, f"only {len(directories)} pip blocks parsed from dependabot.yml — FIX THE SWEEP"
    reachable = _relative(_reach(directories))
    assert (
        len(reachable) >= 25
    ), f"only {len(reachable)} manifests reachable from {len(directories)} pip blocks — FIX THE SWEEP"

    for directory in directories:
        assert (_REPO_ROOT / directory.lstrip("/")).is_dir(), (
            f"dependabot.yml configures pip directory {directory!r}, which does not "
            "exist in this checkout. Dependabot silently scans nothing for it."
        )


def test_every_tracked_manifest_is_inside_dependabots_reach() -> None:
    """The #14562 defect: a pinned manifest no configured block can ever edit."""
    uncovered = sorted(_relative(_population() - _reach(_pip_directories())) - set(_KNOWN_UNSCANNED))

    assert not uncovered, (
        "these tracked manifests pin dependencies that dependabot cannot reach. "
        "Its pip ecosystem resolves manifests relative to the configured "
        "`directory:` and follows `-r`/`-c` includes — it does NOT recurse into "
        "subdirectories, so a file nested below a configured directory is scanned "
        "by nothing and its pins never receive a security bump. Add a pip block "
        "for the directory, add an `-r` line from a manifest already in reach, or "
        "record the file in _KNOWN_UNSCANNED with the reason (#14562):\n  " + "\n  ".join(uncovered)
    )


def test_the_reach_model_matches_what_dependabot_was_observed_to_do() -> None:
    """Named sites, so a regression says WHICH chain broke rather than that a count moved.

    Each of these was edited by a real dependabot PR from the block named, which
    is the evidence the model is built on rather than a reading of the docs.
    """
    from_root = _relative(_files_reachable_from("/"))

    for expected in ("autobot-backend/requirements.txt", "requirements-ci/ai-ml.txt"):
        assert expected in from_root, (
            f"the root pip block no longer reaches {expected}, which PR #14951 "
            "edited from it. Either an `-r` line was dropped or include "
            "resolution regressed — and the openai exclusion repeated in the root "
            "block (#14722) is now guarding a file it cannot touch."
        )

    windows = "autobot-npu-worker/resources/windows-npu-worker/requirements.txt"
    assert windows in _relative(_reach(_pip_directories())), (
        f"{windows} has fallen back outside dependabot's reach — that is the " "exact regression #14562 was filed for."
    )


@pytest.mark.parametrize("relative", sorted(_KNOWN_UNSCANNED))
def test_each_exemption_is_still_outside_the_reach(relative: str) -> None:
    """An exemption that no longer applies exempts nothing, silently."""
    path = _REPO_ROOT / relative

    assert path.is_file(), f"{relative} moved or was deleted — update or drop this exemption (#14562)"
    assert path.resolve() not in _reach(_pip_directories()), (
        f"{relative} is now inside a configured pip block's reach, so its "
        "exemption is obsolete — remove it from _KNOWN_UNSCANNED so the file is "
        "covered by the rule instead of carved out of it (#14562)"
    )


def _plant(root: Path) -> Path:
    """A synthetic tree: a root manifest, and one nested two directories below it."""
    nested = root / "worker" / "resources" / "win"
    nested.mkdir(parents=True)
    (nested / "requirements.txt").write_text("tokenizers>=0.15.0\n", encoding="utf-8")
    (root / "worker").joinpath("requirements.txt").write_text("numpy>=2.0\n", encoding="utf-8")
    (root / "requirements.txt").write_text("requests>=2.0\n", encoding="utf-8")
    return nested / "requirements.txt"


def test_the_detector_reports_a_nested_manifest_as_unreachable(tmp_path) -> None:
    """Positive control. With the real repo clean, "found nothing" proves nothing.

    A block on ``/worker`` does not reach ``/worker/resources/win`` — the shape
    #14562 is about.
    """
    nested = _plant(tmp_path)

    assert nested.resolve() not in _reach(["/", "/worker"], tmp_path)


def test_the_detector_clears_a_nested_manifest_once_an_include_reaches_it(tmp_path) -> None:
    """Negative control, and the distinction the whole model rests on.

    Same tree, same blocks — the only difference is an ``-r`` line. If reach did
    not follow includes, ``requirements-ci/*.txt`` would read as uncovered and
    this guard would demand nine pointless pip blocks.
    """
    nested = _plant(tmp_path)
    (tmp_path / "worker" / "requirements.txt").write_text(
        "numpy>=2.0\n-r resources/win/requirements.txt\n", encoding="utf-8"
    )

    assert nested.resolve() in _reach(["/", "/worker"], tmp_path)
