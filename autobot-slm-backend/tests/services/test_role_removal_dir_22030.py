# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Removing a role deletes only the install directory it owns (#22030, after #21974 moved the sync targets)."""

from __future__ import annotations

import pytest

from services.manifest_loader import ManifestLoader
from services.role_removal_dir import removal_path


@pytest.fixture(scope="module")
def manifests():
    from repo_tests._paths import repo_root

    return ManifestLoader(infra_base=repo_root() / "autobot-infrastructure").load_all()


def test_the_owner_of_a_manifest_removes_its_destination_not_its_sync_target(manifests):
    assert removal_path("backend", [], manifests, {}) == "/opt/autobot/autobot-backend"
    assert removal_path("slm-agent", [], manifests, {}) == "/opt/autobot/autobot-slm-agent/slm/agent"


def test_celery_and_scheduler_own_no_directory_so_removing_them_deletes_none(manifests):
    for role in ("celery", "scheduler"):
        assert removal_path(role, ["backend"], manifests, {}) is None
        assert removal_path(role, [], manifests, {}) is None


def test_the_backend_keeps_its_directory_while_another_role_of_the_node_uses_it(manifests):
    assert removal_path("backend", ["celery"], manifests, {}) is None
    assert removal_path("backend", ["scheduler", "frontend"], manifests, {}) is None
    assert removal_path("backend", ["frontend"], manifests, {}) == "/opt/autobot/autobot-backend"


def test_a_role_with_no_manifest_keeps_its_own_target_path(manifests):
    paths = {"tts-worker": "/opt/autobot/autobot-tts-worker"}
    assert removal_path("tts-worker", [], manifests, paths) == "/opt/autobot/autobot-tts-worker"
    assert (
        removal_path(
            "tts-worker",
            ["x"],
            manifests,
            {"tts-worker": "/opt/autobot/autobot-tts-worker", "x": "/opt/autobot/autobot-tts-worker/"},
        )
        is None
    )
    assert removal_path("tts-worker", [], manifests, {}) is None


def test_a_shared_manifest_role_such_as_redis_removes_no_directory(manifests):
    assert removal_path("redis", [], manifests, {"redis": ""}) is None
