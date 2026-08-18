# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every runtime that imports `autobot_shared` from a marker-free tree must
declare `AUTOBOT_PROJECT_ROOT` (#14544, #14575).

`autobot_shared.paths.project_root()` now raises `ProjectRootUndeterminable`
instead of silently guessing `/opt/autobot` when it cannot find `.env` or a
checkout (`.git` + `autobot_shared`) by walking up from its own install
location. That is correct — the silent guess was the defect #14544 fixed —
but it makes every deployed runtime a contract: the resolver raises unless
something tells it where it is.

Both Docker images fail this contract out of the box: `COPY autobot_shared/
/app/autobot_shared/` ships the package with no `.git` and no `.env`, so
`smoke-test`/`hardened-smoke-test` failed at import with exactly this raise
(#14575 review). Three native systemd/env deployments have the identical gap
for the identical reason:

- `autobot-slm-backend.service.j2` -- sets `PYTHONPATH` for `autobot_shared`
  but never `AUTOBOT_PROJECT_ROOT`/`AUTOBOT_BASE_DIR`.
- `slm-agent.service.j2` -- `agent.py` imports `autobot_shared.ssot_config
  .get_config` directly; same gap.
- `ai-stack.env.j2` -- `ai_api_server.py` imports `agents.base_agent`, which
  imports `autobot_shared.ssot_config.config` directly; same gap, and
  *topology-dependent* on top of it: whether `project_root()`'s walk finds a
  `.env` for this unit depends on which `backend_install_dir` a given deploy
  playbook sets, so it silently worked on one topology and would have
  silently failed on another (#14575 review, round 2).

Before #14544 this was invisible because the guess happened to be
`/opt/autobot`, which is where all three actually run (or, for the ai-stack
case, ran by accident on only one of two shipped topologies) — a
wrong-but-plausible default working by coincidence is exactly the failure
mode #14544 exists to close.

`npu-worker.env.j2` was considered and deliberately **not** touched:
`npu-worker.py.j2`, the script this unit actually runs, imports no
first-party code at all -- not `autobot_shared`, not anything that imports
it. `core/npu_integration.py` (which does import `autobot_shared
.ssot_constants`, transitively pulling in `ssot_config`) belongs to a
different, unwired module under `autobot-npu-worker/core/` that this unit
never executes -- confirmed by grepping every importer of it, which is only
its own test file. An earlier version of this fix declared the variable here
anyway, citing that file; the citation was wrong, so the declaration was
reverted rather than kept on a false premise (#14575 review, round 2).

This is a static text check against the deployment sources themselves, not a
container build or a live systemd unit — sufficient to catch a future edit
that quietly drops the variable, which is the point: the next person editing
one of these files cannot remove the line without failing here first. It
runs under `python-suite`, which `.github/filters/python-paths.yml` gates on
`**/*.py` by default; the five files this test names are added to that
filter explicitly, or a PR touching only one of them (no `.py` change) would
report `python-suite` green without ever running this test (#14575 review,
round 2).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autobot_shared.paths import PROJECT_ROOT_ENV, ProjectRootUndeterminable, resolve_project_root

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: (file, must contain) -- every deployment source that has to declare
#: AUTOBOT_PROJECT_ROOT for a process importing autobot_shared to start.
_DECLARATIONS: tuple[tuple[str, str], ...] = (
    ("docker/backend/Dockerfile", "ENV AUTOBOT_PROJECT_ROOT=/app"),
    ("docker/slm/Dockerfile", "ENV AUTOBOT_PROJECT_ROOT=/app"),
    (
        "autobot-slm-backend/ansible/roles/slm_manager/templates/autobot-slm-backend.service.j2",
        "AUTOBOT_PROJECT_ROOT={{ slm_base_dir }}",
    ),
    (
        "autobot-slm-backend/ansible/roles/slm_agent/templates/slm-agent.service.j2",
        "AUTOBOT_PROJECT_ROOT={{ slm_agent_dir | dirname }}",
    ),
    (
        "autobot-slm-backend/ansible/roles/ai-stack/templates/ai-stack.env.j2",
        "AUTOBOT_PROJECT_ROOT={{ ai_install_dir | dirname }}",
    ),
)


@pytest.mark.parametrize("rel_path, needle", _DECLARATIONS)
def test_deployment_source_declares_autobot_project_root(rel_path: str, needle: str) -> None:
    path = _REPO_ROOT / rel_path
    assert path.is_file(), f"{rel_path} moved or was deleted -- update this test's path"

    source = path.read_text(encoding="utf-8")
    assert needle in source, (
        f"{rel_path} no longer declares `{needle}`. Without it, any process there that "
        "imports autobot_shared (directly or via ssot_config/ssot_constants) raises "
        "ProjectRootUndeterminable at import time and the service never starts (#14544, #14575)."
    )


def test_project_root_succeeds_under_a_marker_free_tree_once_the_env_is_set(tmp_path, monkeypatch) -> None:
    """The exact shape a container/systemd unit is in: no .git, no .env, no markers."""
    monkeypatch.delenv("AUTOBOT_BASE_DIR", raising=False)
    bare = tmp_path / "app"
    bare.mkdir()
    monkeypatch.setenv(PROJECT_ROOT_ENV, str(bare))

    assert resolve_project_root(bare / "autobot_shared" / "paths.py") == bare


def test_project_root_raises_under_the_same_tree_without_the_env(tmp_path, monkeypatch) -> None:
    """The failure this whole contract exists to make loud, not silent."""
    monkeypatch.delenv(PROJECT_ROOT_ENV, raising=False)
    monkeypatch.delenv("AUTOBOT_BASE_DIR", raising=False)
    bare = tmp_path / "app"
    bare.mkdir()

    with pytest.raises(ProjectRootUndeterminable):
        resolve_project_root(bare / "autobot_shared" / "paths.py")
