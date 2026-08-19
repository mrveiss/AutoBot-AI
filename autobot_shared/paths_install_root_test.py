# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A deployed install must resolve its own project root (#14624).

Live outage: the SLM backend crash-looped on a deployed host, uvicorn exiting 1
during import, restart counter past 530, API unreachable — including the
code-sync and self-update endpoints that would normally deploy a fix.

`resolve_project_root` raises rather than guessing (#14544), which is right, but
every arm failed on the install layout:

* `/opt/autobot/.env` does not exist — per-component `.env` files live one level
  down (`autobot-backend/.env`, `autobot-ai-stack/.env`, ...), so the docstring's
  "an install has a .env" premise did not hold.
* `is_checkout_root` requires BOTH `.git` and `autobot_shared`; an install has
  only the latter.
* neither env override was set, because the host's systemd unit was two months
  stale and predated the template line that renders it.

The deployment does normally export `AUTOBOT_PROJECT_ROOT`. Depending on that
alone makes startup contingent on every host's unit being current, and this one
was not — so the layout is now recognisable on its own terms.

These build real directory trees and run the real resolver against them.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_paths_module():
    """Load `paths.py` directly: it is a bootstrap module that must not import config."""
    name = "_paths_under_test_14624"
    spec = importlib.util.spec_from_file_location(name, _REPO_ROOT / "autobot_shared" / "paths.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


paths = _load_paths_module()


@pytest.fixture(autouse=True)
def _no_env_overrides(monkeypatch):
    """The overrides short-circuit everything; these tests are about the walk."""
    monkeypatch.delenv(paths.PROJECT_ROOT_ENV, raising=False)
    monkeypatch.delenv(paths.BASE_DIR_ENV, raising=False)


def _deployed_install(root: Path) -> Path:
    """The real layout: autobot_shared beside components, no .git, no root .env."""
    (root / "autobot_shared").mkdir(parents=True)
    (root / "autobot-slm-backend").mkdir()
    (root / "autobot-backend").mkdir()
    (root / "autobot-backend" / ".env").write_text("X=1\n", encoding="utf-8")
    return root


def test_the_module_loaded_for_real():
    assert callable(paths.resolve_project_root)
    assert callable(paths.is_install_root)


def test_a_deployed_install_resolves_instead_of_raising(tmp_path):
    """The outage, reproduced as a rule."""
    install = _deployed_install(tmp_path / "autobot")

    resolved = paths.resolve_project_root(install / "autobot_shared" / "paths.py")

    assert resolved == install, "a deployed install still cannot resolve its own root (#14624)"


def test_the_pre_fix_arms_really_did_all_fail(tmp_path):
    """Pins WHY it raised, so a future change cannot quietly reintroduce it.

    If any of these three becomes true for an install layout, the reasoning in
    `is_install_root` needs revisiting rather than silently still working.
    """
    install = _deployed_install(tmp_path / "autobot")

    assert not (install / ".env").exists(), "the install layout grew a root .env — revisit is_install_root"
    assert not paths.is_checkout_root(install), "an install now looks like a checkout — markers changed"
    assert paths.is_install_root(install), "the install arm no longer recognises the deployed layout"


def test_a_source_checkout_still_wins_on_its_own_terms(tmp_path):
    """The checkout arm must keep matching where it always did."""
    checkout = tmp_path / "AutoBot-AI"
    (checkout / "autobot_shared").mkdir(parents=True)
    (checkout / "autobot-slm-backend").mkdir()
    (checkout / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")

    assert paths.is_checkout_root(checkout)
    assert paths.resolve_project_root(checkout / "autobot_shared" / "paths.py") == checkout


def test_a_worktree_does_not_escape_to_the_main_tree(tmp_path):
    """#13149: the failure the single-pass walk exists to prevent.

    A worktree has no `.env` of its own. If the walk climbed past it, every
    worktree's paths would point at the main checkout. The new arm must not
    reopen that: it matches at the worktree's own level, not above it.
    """
    main = tmp_path / "AutoBot-AI"
    (main / "autobot_shared").mkdir(parents=True)
    (main / "autobot-slm-backend").mkdir()
    (main / ".git").mkdir()
    (main / ".env").write_text("MAIN=1\n", encoding="utf-8")

    worktree = main / ".worktrees" / "issue-1"
    (worktree / "autobot_shared").mkdir(parents=True)
    (worktree / "autobot-slm-backend").mkdir()
    (worktree / ".git").write_text("gitdir: ../../.git/worktrees/issue-1\n", encoding="utf-8")

    resolved = paths.resolve_project_root(worktree / "autobot_shared" / "paths.py")

    assert resolved == worktree, f"worktree escaped to {resolved} — #13149 regression"


def test_a_bare_package_parent_is_not_an_install_root(tmp_path):
    """`autobot_shared` alone must not be enough.

    That is why CHECKOUT_MARKERS requires both markers, and the new arm must not
    become a backdoor around it: a directory holding only the package is not an
    install and resolving to it would be the silent-guess behaviour #14544
    removed.
    """
    lone = tmp_path / "somewhere"
    (lone / "autobot_shared").mkdir(parents=True)

    assert not paths.is_install_root(lone)

    with pytest.raises(paths.ProjectRootUndeterminable):
        paths.resolve_project_root(lone / "autobot_shared" / "paths.py")


def test_an_unresolvable_tree_still_raises(tmp_path):
    """The #14544 guarantee is preserved: no guessing when nothing identifies a root."""
    nothing = tmp_path / "empty" / "deep"
    nothing.mkdir(parents=True)

    with pytest.raises(paths.ProjectRootUndeterminable):
        paths.resolve_project_root(nothing / "paths.py")


@pytest.mark.parametrize(
    "component",
    ["autobot-npu-worker", "autobot-tts-worker", "autobot-ai-stack", "autobot-browser-worker", "autobot-slm-agent"],
)
def test_a_minimal_node_resolves_whatever_single_component_it_carries(tmp_path, component):
    """A fleet node deploys only the components its roles carry.

    The first version of this fix enumerated four component names and would
    have left a node carrying only npu-worker (or tts-worker, or ai-stack)
    raising exactly as before — and those minimal nodes are the ones most
    likely to be affected, because a fleet update unpacks the shared tree and
    restarts their services in the same pass.
    """
    node = tmp_path / "autobot"
    (node / "autobot_shared").mkdir(parents=True)
    (node / component).mkdir()

    assert paths.is_install_root(node), f"a node carrying only {component} cannot resolve its root"
    assert paths.resolve_project_root(node / "autobot_shared" / "paths.py") == node


def test_a_non_component_sibling_is_not_enough(tmp_path):
    """The prefix must still mean something.

    `autobot_shared` next to an unrelated directory is not an install; treating
    it as one would drift back toward the silent guess #14544 removed.
    """
    lone = tmp_path / "somewhere"
    (lone / "autobot_shared").mkdir(parents=True)
    (lone / "unrelated").mkdir()
    (lone / "autobot_docs").mkdir()  # underscore, not the component prefix

    assert not paths.is_install_root(lone)
