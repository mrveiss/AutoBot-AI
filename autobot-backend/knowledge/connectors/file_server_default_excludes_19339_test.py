# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""FileServerConnector default excludes: canonical skip dirs and minified files (#19339)."""

from pathlib import Path

import pytest

from knowledge.connectors.file_server import FileServerConnector
from knowledge.connectors.models import ConnectorConfig


def _connector(base: Path, **extra) -> FileServerConnector:
    config = {"base_path": str(base), "include_patterns": ["*.py", "*.js"], **extra}
    return FileServerConnector(
        ConnectorConfig(connector_id="fs-19339", connector_type="file_server", name="fs", config=config)
    )


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    for rel in (
        "keep.py",
        "pkg/app.py",
        "node_modules/dep.js",
        "pkg/dist/bundle.js",
        ".worktrees/wt/copy.py",
        "web/app.min.js",
    ):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x = 1\n", encoding="utf-8")
    return tmp_path


def _scanned_rel(connector: FileServerConnector, base: Path) -> set[str]:
    """What the connector's own scan returns, relative to *base* -- not a re-implementation of it."""
    return {str(Path(source.path).relative_to(base)) for source in connector._scan_files_sync()}


def test_default_excludes_skip_canonical_dirs_and_minified_files(tree: Path) -> None:
    assert _scanned_rel(_connector(tree), tree) == {"keep.py", "pkg/app.py"}


def test_an_explicit_exclude_list_replaces_the_defaults(tree: Path) -> None:
    got = _scanned_rel(_connector(tree, exclude_patterns=["pkg/*"]), tree)
    assert "node_modules/dep.js" in got and "web/app.min.js" in got and "pkg/app.py" not in got


def test_default_discovery_covers_the_canonical_text_extensions(tmp_path: Path) -> None:
    """With no include_patterns, every TEXT_FILE_EXTENSIONS file is discovered, not a 6-suffix subset."""
    from utils.file_types import TEXT_FILE_EXTENSIONS

    for name in ("guide.rst", "conf.yaml", "view.tsx", "notes.md"):
        (tmp_path / name).write_text("x\n", encoding="utf-8")
    config = ConnectorConfig(
        connector_id="fs-19339", connector_type="file_server", name="fs", config={"base_path": str(tmp_path)}
    )
    got = _scanned_rel(FileServerConnector(config), tmp_path)
    assert {".rst", ".yaml", ".tsx"} <= TEXT_FILE_EXTENSIONS
    assert got == {"guide.rst", "conf.yaml", "view.tsx", "notes.md"}


def test_a_secret_named_file_is_never_discovered(tmp_path: Path) -> None:
    """Default discovery reads every text suffix, so secret-shaped names are excluded by name (#19339)."""
    planted = ("credentials.json", "secrets.toml", "conf/.env.local", "service-account-key.json", "key.json")
    for name in (*planted, "notes.md", "tokenizer.py", "key-concepts.md"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x\n", encoding="utf-8")
    config = ConnectorConfig(
        connector_id="fs-19339", connector_type="file_server", name="fs", config={"base_path": str(tmp_path)}
    )
    assert _scanned_rel(FileServerConnector(config), tmp_path) == {"notes.md", "tokenizer.py", "key-concepts.md"}
    explicit = _connector(tmp_path, include_patterns=["*"], exclude_patterns=[])
    assert "credentials.json" not in _scanned_rel(explicit, tmp_path)  # an explicit list does not lift it
