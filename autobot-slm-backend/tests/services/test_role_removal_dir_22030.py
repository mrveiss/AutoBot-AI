# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Removing one role never deletes the install root, a dot path, a path outside it or a shared directory (#22030)."""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from autobot_shared.install_paths import overlaps, safe_relative_dir
from models.manifest import ManifestDeploy, RoleManifest
from services.manifest_loader import ManifestLoader
from services.role_removal_dir import detected_roles_if_fresh, removal_path

ROOT = "/opt/autobot"


@pytest.fixture(scope="module")
def manifests():
    from repo_tests._paths import repo_root

    return ManifestLoader(infra_base=repo_root() / "autobot-infrastructure").load_all()


def _registry():
    """(role names, literal target paths, required roles) read from role_registry.py without importing it."""
    from repo_tests._paths import repo_root

    tree = ast.parse(
        (repo_root() / "autobot-slm-backend" / "services" / "role_registry.py").read_text(encoding="utf-8")
    )
    names, paths, required = [], {}, set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        fields = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
        name = fields.get("name")
        if not isinstance(name, ast.Constant) or "display_name" not in fields:
            continue
        names.append(name.value)
        target = fields.get("target_path")
        if isinstance(target, ast.Constant):
            paths[name.value] = target.value
        if isinstance(fields.get("required"), ast.Constant) and fields["required"].value is True:
            required.add(name.value)
    return names, paths, frozenset(required)


def _evil(destination: str, **kwargs) -> dict:
    deploy = ManifestDeploy.model_construct(source="x/", destination=destination, sync=False, sync_target="")
    return {"autobot-evil": RoleManifest.model_construct(role="autobot-evil", deploy=deploy, services=[], **kwargs)}


def test_the_owner_of_a_manifest_removes_its_destination_relative_to_the_root(manifests):
    assert removal_path("backend", [], manifests, {}) == "autobot-backend"
    assert removal_path("frontend", [], manifests, {}) == "autobot-frontend"


def test_the_agent_and_the_shared_package_are_never_removed_with_their_directory(manifests):
    """deploy_to_all manifests are imported or managed by every other role on the node."""
    for role in ("slm-agent", "autobot_shared"):
        assert removal_path(role, [], manifests, {}) is None, role


def test_a_required_role_is_never_removed_with_its_directory(manifests):
    assert removal_path("backend", [], manifests, {}, frozenset({"backend"})) is None


def test_celery_and_scheduler_own_no_directory(manifests):
    for role in ("celery", "scheduler", "redis", "postgres", "chromadb"):
        assert removal_path(role, ["backend"], manifests, {}) is None, role
        assert removal_path(role, [], manifests, {}) is None, role


def test_the_backend_keeps_its_directory_while_another_role_of_the_node_uses_it(manifests):
    assert removal_path("backend", ["celery"], manifests, {}) is None
    assert removal_path("backend", ["scheduler", "frontend"], manifests, {}) is None
    assert removal_path("backend", ["frontend"], manifests, {}) == "autobot-backend"


def test_a_directory_containing_or_inside_another_roles_directory_is_kept():
    assert overlaps("a/b", "a") and overlaps("a", "a/b") and overlaps("a", "a") and not overlaps("a", "ab")
    assert removal_path("x", ["y"], {}, {"x": f"{ROOT}/tts", "y": f"{ROOT}/tts/sub"}) is None
    assert removal_path("x", ["y"], {}, {"x": f"{ROOT}/tts/sub", "y": f"{ROOT}/tts"}) is None


def test_a_role_with_no_manifest_keeps_its_target_path_only_inside_the_root(manifests):
    assert (
        removal_path("tts-worker", [], manifests, {"tts-worker": f"{ROOT}/autobot-tts-worker"}) == "autobot-tts-worker"
    )
    for outside in ("/usr/bin/Xtigervnc", ROOT, ROOT + "/", "/opt/autobotx/y", f"{ROOT}/../etc", f"{ROOT}/.", "", None):
        assert removal_path("vnc", [], manifests, {"vnc": outside}) is None, outside


@pytest.mark.parametrize(
    "destination",
    [ROOT, ROOT + "/", "/", "/etc", f"{ROOT}/..", f"{ROOT}/.", f"{ROOT}/a/../..", f"{ROOT}//x", "relative/x", "."],
)
def test_a_crafted_destination_never_reaches_the_root_or_outside_it(destination):
    assert removal_path("evil", [], _evil(destination), {}) is None


@pytest.mark.parametrize(
    "destination", [".", "..", f"{ROOT}/..", f"{ROOT}/./x", f"{ROOT}/a/../b", "/", "", f"{ROOT}//x"]
)
def test_the_manifest_model_rejects_a_dot_destination(destination):
    with pytest.raises(ValueError):
        ManifestDeploy(source="x/", destination=destination, sync=False)


def test_the_manifest_model_accepts_the_real_destinations(manifests):
    assert all(m.deploy.destination.startswith(ROOT + "/") for m in manifests.values())


@pytest.mark.parametrize(
    "value", [None, "", ".", "..", "/", "/etc", "a/..", "../a", "a/./b", "a//b", "a b", "a;b", "a\\b", "~", 7]
)
def test_safe_relative_dir_refuses_anything_that_is_not_plain_and_relative(value):
    assert safe_relative_dir(value) is None


def test_safe_relative_dir_keeps_a_multi_segment_path():
    assert safe_relative_dir("autobot-slm-agent/slm/agent") == "autobot-slm-agent/slm/agent"
    assert safe_relative_dir("autobot-backend/") == "autobot-backend"


def test_every_registry_role_alone_or_with_every_other_role_removes_nothing_unsafe(manifests):
    """The property: for each DEFAULT_ROLES role, on a bare node and on a node running every other role."""
    names, paths, required = _registry()
    assert len(names) >= 15
    for role in names:
        everyone_else = [n for n in names if n != role]
        for others in ([], everyone_else):
            got = removal_path(role, others, manifests, paths, required)
            if got is None:
                continue
            assert safe_relative_dir(got) == got, (role, got)
            assert role not in required, role
            assert not any(
                overlaps(got, other_dir)
                for other in others
                if (other_dir := removal_path(other, [], manifests, paths)) is not None
            ), (role, got)


def _node(detected, beat):
    return SimpleNamespace(detected_roles=detected, last_heartbeat=beat)


def test_detected_roles_are_trusted_only_when_a_fresh_report_names_the_removed_role():
    now = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
    fresh = now - timedelta(seconds=30)
    assert detected_roles_if_fresh(_node(["backend", "celery"], fresh), now, 90, "backend") == {"backend", "celery"}
    assert detected_roles_if_fresh(_node(["backend"], None), now, 90, "backend") is None
    assert detected_roles_if_fresh(_node(["backend"], now - timedelta(seconds=91)), now, 90, "backend") is None
    assert detected_roles_if_fresh(None, now, 90, "backend") is None


def test_a_node_whose_agent_never_sent_a_role_report_is_not_known_to_run_nothing():
    """An empty ``Node.detected_roles`` (the column default, or an agent with no definitions) is "never reported"."""
    now = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
    fresh = now - timedelta(seconds=5)
    assert detected_roles_if_fresh(_node([], fresh), now, 90, "backend") is None
    assert detected_roles_if_fresh(_node(None, fresh), now, 90, "backend") is None
    assert detected_roles_if_fresh(_node({}, fresh), now, 90, "backend") is None
    assert detected_roles_if_fresh(_node(["celery"], fresh), now, 90, "backend") is None, "the removed role is absent"


def test_a_role_nothing_is_known_about_blocks_the_removal(manifests):
    known = frozenset({"npu-worker", "tts-worker"})
    paths = {"tts-worker": f"{ROOT}/autobot-tts-worker"}
    assert removal_path("tts-worker", [], manifests, paths, frozenset(), known) == "autobot-tts-worker"
    assert removal_path("tts-worker", ["mystery"], manifests, paths, frozenset(), known) is None
    assert removal_path("mystery", [], manifests, paths, frozenset(), known) is None
    assert removal_path("tts-worker", ["backend"], manifests, paths, frozenset(), known) == "autobot-tts-worker"


def test_a_node_running_every_other_role_keeps_the_backend_directory(manifests):
    names, paths, required = _registry()
    assert removal_path("backend", [n for n in names if n != "backend"], manifests, paths, required) is None
