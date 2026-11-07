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


def _live(code_source: Path, base: Path) -> ManifestLoader:
    from services.manifest_loader import candidate_infra_roots

    return ManifestLoader(roots=lambda: candidate_infra_roots(override="", code_source=code_source, base_dir=base))


def test_an_incomplete_code_source_tree_does_not_hide_the_installs_manifest(tmp_path: Path) -> None:
    """code_source has the infra dir but not this role: the install's manifest (and its conflict checks) apply."""
    code_source, base = tmp_path / "code_source", tmp_path / "install"
    (code_source / "autobot-infrastructure" / "other").mkdir(parents=True)
    _write(base, "from the install")
    manifest = _live(code_source, base).load("example")
    assert manifest is not None and manifest.description == "from the install"


def test_a_code_source_populated_after_start_is_picked_up_and_the_cache_dropped(tmp_path: Path) -> None:
    code_source, base = tmp_path / "code_source", tmp_path / "install"
    _write(base, "from the install")
    loader = _live(code_source, base)
    assert loader.load("example").description == "from the install"
    _write(code_source, "from code_source")
    assert loader.load("example").description == "from code_source"  # no force_reload: the root changed


def test_load_all_unions_the_roots_with_the_first_winning(tmp_path: Path) -> None:
    code_source, base = tmp_path / "code_source", tmp_path / "install"
    _write(code_source, "from code_source")
    _write(base, "from the install")
    infra = base / "autobot-infrastructure"
    (infra / "autobot-extra").mkdir()
    (infra / "autobot-extra" / "manifest.yml").write_text(
        _MANIFEST.replace("autobot-example", "autobot-extra").format(description="extra"), encoding="utf-8"
    )
    assert set(_live(code_source, base).load_all()) == {"autobot-extra"}
