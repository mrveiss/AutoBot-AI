# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20567: role manifests come from code_source, then the install's copy; unavailable is loud, not silent."""

from __future__ import annotations

import logging
from pathlib import Path

from services.manifest_loader import ManifestLoader, resolve_infra_base

_MANIFEST = """\
role: autobot-example
description: {description}
deploy:
  source: autobot-example/
  destination: /srv/example/
"""


def _write(root: Path, description: str) -> Path:
    infra = root / "autobot-infrastructure"
    (infra / "example").mkdir(parents=True)
    (infra / "example" / "manifest.yml").write_text(_MANIFEST.format(description=description), encoding="utf-8")
    return infra


def _loader(code_source: Path, base_dir: Path) -> ManifestLoader:
    return ManifestLoader(infra_base=resolve_infra_base(override="", code_source=code_source, base_dir=base_dir))


def test_code_source_wins_over_the_installs_copy(tmp_path: Path) -> None:
    code_source, base = tmp_path / "code_source", tmp_path / "install"
    _write(code_source, "from code_source")
    _write(base, "from the install")
    manifest = _loader(code_source, base).load("example")
    assert manifest is not None and manifest.description == "from code_source"


def test_the_installs_copy_is_used_when_code_source_has_none(tmp_path: Path) -> None:
    code_source, base = tmp_path / "code_source", tmp_path / "install"
    code_source.mkdir()
    _write(base, "from the install")
    manifest = _loader(code_source, base).load("example")
    assert manifest is not None and manifest.description == "from the install"


def test_the_override_beats_both(tmp_path: Path) -> None:
    code_source, base, other = tmp_path / "code_source", tmp_path / "install", tmp_path / "other"
    _write(code_source, "from code_source")
    chosen = _write(other, "from the override")
    assert resolve_infra_base(override=str(chosen), code_source=code_source, base_dir=base) == chosen


def test_nothing_anywhere_warns_and_does_not_crash(tmp_path: Path, caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="services.manifest_loader"):
        loader = _loader(tmp_path / "code_source", tmp_path / "install")
    assert any("manifests are unavailable" in r.getMessage() for r in caplog.records)
    assert loader.load("example") is None
    assert loader.load_all() == {}
