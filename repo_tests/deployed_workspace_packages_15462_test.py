# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every `file:` workspace dependency is actually deployed (#15462).

The outage this comes from: `/slm/` served 403 for hours while every service
reported healthy. The SLM frontend's build was failing with
``[MISSING_EXPORT] "provideToast" is not exported by "@autobot/ui"`` for a
symbol that existed in the repository and did not exist on the host.

`autobot-slm-frontend/package.json` declares ``"@autobot/ui": "file:../libs/
autobot-ui"``. npm resolves that to a **symlink inside the deployed tree** --
``/opt/autobot/autobot-slm-frontend/node_modules/@autobot/ui ->
../../../libs/autobot-ui`` -- so the build reads ``/opt/autobot/libs/...``,
never the synced source. `update-all-nodes.yml` archived seven components and
`libs/` was not one of them, so that directory had not been updated since July
while the repo moved on. `autobot-plugins/` had the same gap, since June.

It stayed invisible for as long as nothing NEW was exported from those
packages: an app building against a stale copy of a package whose surface has
not changed builds fine. #14907 consolidated the shared composables into
``@autobot/ui``, the exported surface grew, and every app depending on the new
symbols broke at once -- on the host only, so nothing in CI saw it.

The invariant, stated so the next workspace package cannot repeat it: if an app
declares a `file:` dependency, the deploy must ship the directory it points at.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Set

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = REPO_ROOT / "autobot-slm-backend/ansible/playbooks/update-all-nodes.yml"

# `- { name: x, path: some/dir/ }` rows of the component-archive loop.
_COMPONENT = re.compile(r"^\s*-\s*\{\s*name:\s*([\w-]+)\s*,\s*path:\s*([^\s},]+)\s*\}", re.MULTILINE)


def _app_manifests() -> List[Path]:
    """Every deployed app's package.json (not libraries, not node_modules)."""
    return [
        p
        for p in REPO_ROOT.glob("autobot-*frontend/package.json")
        if "node_modules" not in p.parts
    ]


def _file_dependencies() -> Dict[str, Set[str]]:
    """Map each app to the repo-relative directories its `file:` deps point at."""
    found: Dict[str, Set[str]] = {}
    for manifest in _app_manifests():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        targets: Set[str] = set()
        for section in ("dependencies", "devDependencies"):
            for spec in (data.get(section) or {}).values():
                if not isinstance(spec, str) or not spec.startswith("file:"):
                    continue
                # Resolve relative to the app directory, then back to repo-relative.
                resolved = (manifest.parent / spec[len("file:") :]).resolve()
                try:
                    targets.add(resolved.relative_to(REPO_ROOT).parts[0])
                except ValueError:  # pragma: no cover - a dep outside the repo
                    pytest.fail(f"{manifest.name}: `file:` dependency escapes the repo: {spec}")
        if targets:
            found[manifest.parent.name] = targets
    return found


def _deployed_roots() -> Set[str]:
    """Top-level directories the playbook archives and ships."""
    text = PLAYBOOK.read_text(encoding="utf-8")
    return {path.strip("/").split("/")[0] for _name, path in _COMPONENT.findall(text)}


_FILE_DEPS = _file_dependencies()
_DEPLOYED = _deployed_roots()


def test_the_guard_can_see_both_sides() -> None:
    """Guard the guard.

    If either parser silently finds nothing -- a renamed playbook, a changed
    loop shape, a moved package.json -- the assertion below passes vacuously,
    which is precisely the shape of the failure it exists to catch.
    """
    assert PLAYBOOK.exists(), f"{PLAYBOOK} moved; this guard needs its new path"
    assert _FILE_DEPS, "no app declares a `file:` dependency -- parser is broken or apps moved"
    assert len(_DEPLOYED) >= 5, (
        f"only {len(_DEPLOYED)} deployed components parsed from the playbook: {sorted(_DEPLOYED)}. "
        "The component-archive loop probably changed shape."
    )


@pytest.mark.parametrize("app", sorted(_FILE_DEPS), ids=lambda v: str(v))
def test_every_workspace_dependency_of_an_app_is_deployed(app: str) -> None:
    missing = sorted(_FILE_DEPS[app] - _DEPLOYED)
    assert not missing, (
        f"{app} declares `file:` dependencies on {missing}, which "
        f"update-all-nodes.yml never ships. npm links those into the deployed "
        f"tree, so the build resolves them from /opt/autobot/ and reads whatever "
        f"stale copy is there. Deployed components: {sorted(_DEPLOYED)}."
    )


def test_the_workspace_packages_land_before_the_frontend_build() -> None:
    """Ordering, not just presence.

    Shipping the packages after `npm ci` would still build against the old copy,
    and the failure would look identical -- so the invariant is that every
    workspace-package deploy task appears before the first npm task.
    """
    text = PLAYBOOK.read_text(encoding="utf-8")
    # `cmd:`-anchored: the playbook's prose mentions `npm ci` in a comment 300
    # lines above the first real task, and matching that made this pass for the
    # wrong reason on the first run.
    npm_task = re.compile(r"^\s*cmd:\s*npm\s+(ci|run)\b", re.MULTILINE)
    first = npm_task.search(text)
    assert first, "no npm task found in the playbook; this guard needs updating"
    first_npm = first.start()

    for component in ("libs.tar.gz", "plugins.tar.gz"):
        position = text.find(component)
        assert position != -1, f"{component} is never deployed"
        assert position < first_npm, (
            f"{component} is deployed after the first npm task, so the build still "
            "resolves the previous copy from the host."
        )
