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

from autobot_shared.paths import scrubbed_git_env

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


_ANSIBLE_ROOT = _REPO_ROOT / "autobot-slm-backend" / "ansible"


def _delete_style_syncs():
    """Every `synchronize` task in the ansible tree that can remove files.

    Scoped to the whole tree, not to one role. The first version of this test
    read `roles/slm_manager/tasks/main.yml` alone -- and three more delete-style
    syncs with the identical gap sat in the frontend and backend roles, invisible
    to a guard whose reach was narrower than its own subject.
    """
    found = []
    for path in sorted(_ANSIBLE_ROOT.rglob("*.yml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:  # pragma: no cover - a malformed file fails elsewhere
            continue

        def walk(node):
            if isinstance(node, list):
                for item in node:
                    walk(item)
            elif isinstance(node, dict):
                sync = node.get("ansible.posix.synchronize") or node.get("synchronize")
                if isinstance(sync, dict) and sync.get("delete"):
                    found.append((path.relative_to(_ANSIBLE_ROOT).as_posix(), node.get("name"), sync))
                for value in node.values():
                    walk(value)

        walk(document)
    return found


# The paths a live node reported it would lose. Kept as data, not as the
# assertion -- they are the reproduction, and the invariant tests below are what
# must hold for the paths nobody has reported yet.
_REPORTED_ON_A_LIVE_NODE = (
    ".env.production",
    "config/",
    ".deployed_commit",
    "ansible/enroll.yml",
)

# Every source root a delete-style sync copies from: the three code-sync
# components (matching _SLM_COMPONENTS in api/code_sync.py) AND the shared trees
# the ansible roles sync separately. The excludes apply to all of them, so the
# "no tracked file is swallowed" invariant has to cover all of them -- checking
# only the code-sync three would leave three roots where a new `.env.*` or
# root-level `config/` could silently stop deploying.
_SYNCED_COMPONENTS = (
    "autobot-slm-backend",
    "autobot-slm-frontend",
    "autobot_shared",
    "autobot-plugins",
    "libs",
    "docs",
)


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
    return any(relative_path == pattern.lstrip("/") for pattern in HOST_STATE_REINCLUDES)


def _tracked_files(component: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", component],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=scrubbed_git_env(),
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


def test_every_delete_style_ansible_sync_carries_the_host_state_excludes():
    """Both writers of the deployed tree must agree, or whichever runs last
    decides. The ansible role protected `.deployed_commit` and the code-sync API
    did not -- for the same file, in the same tree."""
    syncs = _delete_style_syncs()
    assert len(syncs) >= 6, f"only {len(syncs)} delete-style syncs found — the scan did not reach the ansible tree"

    gaps = []
    for source, name, sync in syncs:
        opts = sync.get("rsync_opts", [])
        missing = [p for p in HOST_STATE_EXCLUDES if f"--exclude={p}" not in opts]
        if missing:
            gaps.append(f"{source}: {name}: missing {missing}")

    assert gaps == [], "\n".join(gaps)


def test_no_delete_style_sync_uses_delete_excluded():
    """`--delete-excluded` would remove the very paths the excludes protect,
    turning every guarantee above into its opposite."""
    offenders = [
        f"{source}: {name}"
        for source, name, sync in _delete_style_syncs()
        if any("--delete-excluded" in str(opt) for opt in sync.get("rsync_opts", [])) or sync.get("delete_excluded")
    ]

    assert offenders == [], offenders


def test_every_ansible_task_puts_reincludes_before_excludes():
    """rsync applies the first matching rule; order is the mechanism here."""
    for source, name, sync in _delete_style_syncs():
        opts = sync.get("rsync_opts", [])
        includes = [i for i, opt in enumerate(opts) if str(opt).startswith("--include=")]
        excludes = [i for i, opt in enumerate(opts) if str(opt).startswith("--exclude=")]
        if includes and excludes:
            assert max(includes) < min(excludes), f"{source}: {name}: --include must precede --exclude"


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
