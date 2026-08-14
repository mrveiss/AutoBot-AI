# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Host-generated state must survive every delete-style sync (#14231).

These tests assert the *invariant* -- no path that exists only on the host ends
up in a deletion set -- rather than the five paths a refused resync happened to
name. Three previous fixes (#9970, #11440, #13851) each asserted their own
reported instance and the next instance still got through.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SLM_BACKEND = _REPO_ROOT / "autobot-slm-backend"


def _load_deploy_artifacts():
    """Load the module from its file, not through the `services` package.

    The api/ conftests stub package entries in sys.modules, and a MagicMock
    answers `iter()` with an empty sequence -- so `for pattern in
    HOST_STATE_EXCLUDES` would loop zero times and every assertion below would
    read as "nothing is protected" rather than "the module was not loaded".
    """
    path = _SLM_BACKEND / "services" / "deploy_artifacts.py"
    spec = importlib.util.spec_from_file_location("_deploy_artifacts_14231", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ARTIFACTS = _load_deploy_artifacts()
HOST_STATE_EXCLUDES = _ARTIFACTS.HOST_STATE_EXCLUDES
HOST_STATE_REINCLUDES = _ARTIFACTS.HOST_STATE_REINCLUDES
rsync_host_state_args = _ARTIFACTS.rsync_host_state_args


def test_the_vocabulary_actually_loaded():
    """Guard the guard: an empty tuple would make every test below pass."""
    assert isinstance(HOST_STATE_EXCLUDES, tuple)
    assert len(HOST_STATE_EXCLUDES) >= 7
    assert isinstance(HOST_STATE_REINCLUDES, tuple) and HOST_STATE_REINCLUDES

_ANSIBLE_SYNC_TASK = (
    _REPO_ROOT
    / "autobot-slm-backend"
    / "ansible"
    / "roles"
    / "slm_manager"
    / "tasks"
    / "main.yml"
)

# The paths a live node reported it would lose. Kept as data, not as the
# assertion -- they are the reproduction, and the invariant tests below are what
# must hold for the paths nobody has reported yet.
_REPORTED_ON_A_LIVE_NODE = (
    ".env.production",
    "config/",
    ".deployed_commit",
    "ansible/enroll.yml",
)

# Synced by the code-sync flow; must match _SLM_COMPONENTS in api/code_sync.py.
_SYNCED_COMPONENTS = ("autobot-slm-backend", "autobot-slm-frontend", "autobot_shared")


def _matches_any_exclude(relative_path: str) -> bool:
    """Approximate rsync pattern matching for the patterns this module uses.

    Anchored (`/`-prefixed) patterns match from the transfer root; bare patterns
    match any path component. A trailing slash marks a directory.
    """
    parts = relative_path.split("/")
    for pattern in HOST_STATE_EXCLUDES:
        if pattern.startswith("/"):
            anchored = pattern.strip("/")
            if relative_path == anchored or relative_path.startswith(anchored + "/"):
                return True
        elif any(fnmatch.fnmatch(part, pattern.rstrip("/")) for part in parts):
            return True
    return False


def _matches_any_reinclude(relative_path: str) -> bool:
    return any(
        relative_path == pattern.lstrip("/") for pattern in HOST_STATE_REINCLUDES
    )


def _tracked_files(component: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", component],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"git ls-files failed for {component}: {result.stderr}")
    files = [line for line in result.stdout.splitlines() if line.strip()]
    if not files:
        # An empty listing and a clean listing look identical; refuse to pass on it.
        pytest.fail(f"git ls-files returned nothing for {component}")
    return files


# --------------------------------------------------------------------------
# The invariant: nothing tracked is silently dropped
# --------------------------------------------------------------------------


@pytest.mark.parametrize("component", _SYNCED_COMPONENTS)
def test_no_tracked_source_file_is_excluded_without_a_reinclude(component):
    """A protected pattern that also catches tracked source stops that file
    being deployed, and the drift checker then reports it missing forever --
    #11440's failure mode arriving from the opposite direction.

    `.env.*` is exactly that shape: right for host state, wrong for the
    `.env.example` the backend tracks.
    """
    swallowed = []
    for tracked in _tracked_files(component):
        relative = tracked[len(component) + 1 :]
        if relative.rsplit("/", 1)[-1] == ".gitkeep":
            # A placeholder whose only job is to keep an empty directory in git.
            # The deployment creates the directory itself, so not shipping it
            # costs nothing -- unlike a real source file, which would read as
            # permanent drift. Expressed as a rule, not as an allowlist entry,
            # so a genuinely new file under data/ still fails this test.
            continue
        if _matches_any_exclude(relative) and not _matches_any_reinclude(relative):
            swallowed.append(relative)

    assert swallowed == [], (
        f"{component}: tracked source matched a host-state exclude with no "
        f"re-include, so it would never be deployed: {swallowed}"
    )


def test_every_reported_host_path_survives_a_sync():
    """The reproduction. Each of these was listed for deletion on a live node."""
    unprotected = [p for p in _REPORTED_ON_A_LIVE_NODE if not _matches_any_exclude(p.rstrip("/"))]

    assert unprotected == [], f"still deletable: {unprotected}"


def test_the_exact_env_pattern_does_not_cover_its_siblings():
    """Why `.env` alone was not enough -- the fact that made this a bug.

    If this ever passes with only `.env` present, the family pattern has been
    removed and `.env.production` is deletable again.
    """
    assert not fnmatch.fnmatch(".env.production", ".env")
    assert _matches_any_exclude(".env.production")


def test_config_is_anchored_so_nested_source_config_still_syncs():
    """A bare `config` would also exclude `autobot-slm-frontend/src/config/`,
    which is tracked source."""
    assert _matches_any_exclude("config/settings.yaml")
    assert not _matches_any_exclude("src/config/ssot-config.ts")


# --------------------------------------------------------------------------
# One source, two writers
# --------------------------------------------------------------------------


def test_the_ansible_sync_task_carries_every_host_state_exclude():
    """Both writers of the deployed tree must agree, or whichever runs last
    decides. The ansible task protected `.deployed_commit` and the code-sync API
    did not -- for the same file, in the same tree."""
    tasks = yaml.safe_load(_ANSIBLE_SYNC_TASK.read_text(encoding="utf-8"))
    sync_tasks = [
        task
        for task in tasks
        if isinstance(task, dict) and "ansible.posix.synchronize" in task
    ]
    assert sync_tasks, "no synchronize task found -- the guard cannot see what it checks"

    for task in sync_tasks:
        if not task["ansible.posix.synchronize"].get("delete"):
            continue  # a non-delete sync cannot remove host state
        opts = task["ansible.posix.synchronize"].get("rsync_opts", [])
        missing = [p for p in HOST_STATE_EXCLUDES if f"--exclude={p}" not in opts]
        assert missing == [], (
            f"{task.get('name')}: delete-style sync missing host-state excludes {missing}"
        )


def test_the_ansible_task_puts_reincludes_before_excludes():
    """rsync applies the first matching rule; order is the mechanism here."""
    tasks = yaml.safe_load(_ANSIBLE_SYNC_TASK.read_text(encoding="utf-8"))
    for task in tasks:
        if not isinstance(task, dict) or "ansible.posix.synchronize" not in task:
            continue
        opts = task["ansible.posix.synchronize"].get("rsync_opts", [])
        includes = [i for i, opt in enumerate(opts) if opt.startswith("--include=")]
        excludes = [i for i, opt in enumerate(opts) if opt.startswith("--exclude=")]
        if includes and excludes:
            assert max(includes) < min(excludes), (
                f"{task.get('name')}: --include must precede --exclude"
            )


def test_rsync_host_state_args_emits_reincludes_first():
    args = rsync_host_state_args()
    first_exclude = next(i for i, a in enumerate(args) if a.startswith("--exclude="))
    includes = [i for i, a in enumerate(args) if a.startswith("--include=")]

    assert includes, "no re-includes emitted"
    assert max(includes) < first_exclude


def test_the_chokepoint_passes_host_state_args_through():
    """The API-side wiring: a caller that forgets nothing still gets them."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _code_sync_import import import_code_sync  # #12572: real schema stand-ins

    _rsync_exclude_args = import_code_sync()._rsync_exclude_args

    args = _rsync_exclude_args([], component="autobot-slm-backend")

    for pattern in HOST_STATE_EXCLUDES:
        assert f"--exclude={pattern}" in args, f"{pattern} missing at the rsync chokepoint"
    assert args[0].startswith("--include=")
