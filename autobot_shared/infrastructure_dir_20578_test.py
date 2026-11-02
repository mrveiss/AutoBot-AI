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

import shutil
from pathlib import Path

import pytest

from autobot_shared import paths
from autobot_shared.redis_management import types as redis_types

_INVENTORY = "autobot-slm-backend/ansible/inventory/dynamic/generate_inventory.py"


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


def test_contrast_with_no_code_source_the_install_copy_is_what_is_read(tmp_path, monkeypatch) -> None:
    """The same reader as above, so the difference between them is code_source and nothing else."""
    install, code_source = _host(tmp_path)
    shutil.rmtree(code_source / paths.INFRASTRUCTURE_DIR_NAME)
    monkeypatch.setenv(paths.CODE_SOURCE_ENV, str(code_source))
    monkeypatch.setenv(paths.BASE_DIR_ENV, str(install))
    first = redis_types._yaml_candidates()[0]
    assert Path(first).read_text(encoding="utf-8") == "# stale\n"


def _inventory_infra(root: Path) -> Path:
    """generate_inventory.py's own lines, run as if the script sat under *root*: it can't import the helper."""
    source = (Path(__file__).resolve().parent.parent / _INVENTORY).read_text(encoding="utf-8")
    block = source[source.index("_ROOT = Path(__file__)") : source.index("_DATABASES_YAML = _INFRA")]
    scope = {"Path": Path, "__file__": str(root / _INVENTORY)}
    exec(block, scope)  # noqa: S102  # nosec B102  # a slice of this repo's own script
    return scope["_INFRA"]


@pytest.mark.parametrize("present", [("code_source", "install"), ("code_source",), ("install",), ()])
def test_the_inventory_scripts_copy_of_the_order_matches_the_helper(tmp_path, present) -> None:
    """Twice-defined because the script runs without autobot_shared (#1086), so the two are pinned equal."""
    if "code_source" in present:
        (tmp_path / "code_source" / paths.INFRASTRUCTURE_DIR_NAME).mkdir(parents=True)
    if "install" in present:
        (tmp_path / paths.INFRASTRUCTURE_DIR_NAME).mkdir(parents=True)
    helper = paths.infrastructure_dir(code_source=tmp_path / "code_source", base_dir=tmp_path)
    assert _inventory_infra(tmp_path) == helper


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
