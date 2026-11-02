# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Readers of ``autobot-infrastructure`` follow code_source, not the stale copy beside the install (#20578).

A deployed host has two copies: ``<code_source>/autobot-infrastructure`` (kept current by the SLM) and
``<base_dir>/autobot-infrastructure`` (never updated after first install). Each test builds both on real
directories and checks which one a reader returns.
"""

from __future__ import annotations

from pathlib import Path

from autobot_shared import paths
from autobot_shared.redis_management import types as redis_types


def _tree(root: Path, marker: str) -> Path:
    config = root / paths.INFRASTRUCTURE_DIR_NAME / "shared" / "config"
    config.mkdir(parents=True)
    (config / "redis-databases.yaml").write_text(f"# {marker}\n", encoding="utf-8")
    return config


def _host(tmp_path: Path) -> tuple[Path, Path]:
    install = tmp_path / "opt-autobot"
    code_source = install / "code_source"
    _tree(install, "stale")
    _tree(code_source, "current")
    return install, code_source


def test_code_source_copy_wins_over_the_install_copy(tmp_path) -> None:
    install, code_source = _host(tmp_path)
    assert paths.infrastructure_dir(code_source, install) == code_source / paths.INFRASTRUCTURE_DIR_NAME


def test_install_copy_is_used_only_when_code_source_has_none(tmp_path) -> None:
    install = tmp_path / "opt-autobot"
    _tree(install, "only")
    code_source = install / "code_source"
    assert paths.infrastructure_dir(code_source, install) == install / paths.INFRASTRUCTURE_DIR_NAME


def test_neither_present_names_the_code_source_path(tmp_path) -> None:
    assert (
        paths.infrastructure_dir(tmp_path / "cs", tmp_path / "base") == tmp_path / "cs" / paths.INFRASTRUCTURE_DIR_NAME
    )


def test_env_names_code_source_when_unset_by_argument(tmp_path, monkeypatch) -> None:
    install, code_source = _host(tmp_path)
    monkeypatch.setenv(paths.CODE_SOURCE_ENV, str(code_source))
    monkeypatch.setenv(paths.BASE_DIR_ENV, str(install))
    assert paths.infrastructure_dir() == code_source / paths.INFRASTRUCTURE_DIR_NAME


def test_redis_databases_yaml_is_read_from_code_source(tmp_path, monkeypatch) -> None:
    install, code_source = _host(tmp_path)
    monkeypatch.setenv(paths.CODE_SOURCE_ENV, str(code_source))
    monkeypatch.setenv(paths.BASE_DIR_ENV, str(install))
    first = Path(redis_types._yaml_candidates()[0])
    assert first.read_text(encoding="utf-8") == "# current\n"
    assert (
        first.resolve()
        != (install / paths.INFRASTRUCTURE_DIR_NAME / "shared" / "config" / "redis-databases.yaml").resolve()
    )


def test_contrast_stale_copy_is_what_the_old_anchor_would_have_read(tmp_path) -> None:
    install, _ = _host(tmp_path)
    old_anchor = install / paths.INFRASTRUCTURE_DIR_NAME / "shared" / "config" / "redis-databases.yaml"
    assert old_anchor.read_text(encoding="utf-8") == "# stale\n"


def test_path_config_dir_follows_code_source(tmp_path) -> None:
    """``PATH.CONFIG_DIR`` is fixed at import, so it is read in a fresh interpreter (the event manager and service config use it)."""
    import os
    import subprocess
    import sys

    install, code_source = _host(tmp_path)
    env = {**os.environ, paths.CODE_SOURCE_ENV: str(code_source), paths.BASE_DIR_ENV: str(install)}
    out = (
        subprocess.run(
            [sys.executable, "-c", "from autobot_shared.ssot_constants import PATH; print(PATH.CONFIG_DIR)"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        .stdout.strip()
        .splitlines()[-1]
    )
    assert Path(out) == code_source / paths.INFRASTRUCTURE_DIR_NAME / "shared" / "config"


def test_undeterminable_root_raises_unless_a_fallback_is_named(tmp_path, monkeypatch) -> None:
    import pytest

    def _undeterminable() -> Path:
        raise paths.ProjectRootUndeterminable("no root here")

    monkeypatch.delenv(paths.CODE_SOURCE_ENV, raising=False)
    monkeypatch.delenv(paths.BASE_DIR_ENV, raising=False)
    monkeypatch.setattr(paths, "project_root", _undeterminable)
    with pytest.raises(paths.ProjectRootUndeterminable):
        paths.infrastructure_dir()
    assert paths.infrastructure_dir(fallback_root=tmp_path) == tmp_path / paths.INFRASTRUCTURE_DIR_NAME
