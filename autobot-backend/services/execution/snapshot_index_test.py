# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for _DEFAULT_SNAPSHOT_PATH's canonical project-root default (#13149).

Before this fix ``_DEFAULT_SNAPSHOT_PATH`` was a module-level literal
hardcoding ``/opt/autobot/snapshots`` — a dev run with
``AUTOBOT_SNAPSHOT_STORAGE_PATH`` unset would index (and attempt to write)
container snapshots under the live install. It now derives from
``autobot_shared.paths.project_root()``.
"""

from __future__ import annotations

import importlib

import pytest

import services.execution.snapshot_index as snapshot_index
from autobot_shared.paths import project_root


def test_default_snapshot_path_is_not_the_live_install():
    """The property that matters: a dev run must not resolve under /opt/autobot."""
    assert not snapshot_index._DEFAULT_SNAPSHOT_PATH.startswith("/opt/autobot")


def test_default_snapshot_path_is_wired_to_the_canonical_resolver():
    assert snapshot_index._DEFAULT_SNAPSHOT_PATH == str(project_root() / "snapshots")


def test_default_snapshot_path_tracks_project_root_env_override(monkeypatch, tmp_path):
    fake_root = tmp_path / "fake-checkout"
    fake_root.mkdir()
    monkeypatch.setenv("AUTOBOT_PROJECT_ROOT", str(fake_root))

    reloaded = importlib.reload(snapshot_index)
    try:
        assert reloaded._DEFAULT_SNAPSHOT_PATH == str(fake_root / "snapshots")
    finally:
        monkeypatch.delenv("AUTOBOT_PROJECT_ROOT", raising=False)
        importlib.reload(snapshot_index)


def test_deployed_install_still_resolves_to_the_original_default(monkeypatch):
    """Compositional check for the deployed case — see the equivalent test in
    ``source_paths_test.py`` for why AUTOBOT_PROJECT_ROOT stands in for the
    real ``.env``-walk here, and why full host verification is out of scope
    for a hermetic test.
    """
    monkeypatch.setenv("AUTOBOT_PROJECT_ROOT", "/opt/autobot")

    reloaded = importlib.reload(snapshot_index)
    try:
        assert reloaded._DEFAULT_SNAPSHOT_PATH == "/opt/autobot/snapshots"
    finally:
        monkeypatch.delenv("AUTOBOT_PROJECT_ROOT", raising=False)
        importlib.reload(snapshot_index)


@pytest.mark.parametrize(
    "payload",
    ["[" * 200_000, '{"n": ' + "9" * 5000 + "}"],
    ids=["deeply-nested", "over-long-integer"],
)
def test_unparseable_index_is_a_bad_record_not_an_exception(tmp_path, payload):
    (tmp_path / snapshot_index._INDEX_FILENAME).write_text(payload, encoding="utf-8")
    index = snapshot_index.SnapshotIndex(storage_path=tmp_path)
    assert index.get("any") is None
    assert index.list_by_session("any") == []
