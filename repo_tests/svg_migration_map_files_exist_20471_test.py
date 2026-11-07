# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20471: every ``file`` in ``svg-migration-map.json`` must name a component that exists.

The map records which Vue component each extracted inline SVG came from. Components get
deleted or renamed and nothing pruned their entries: 21 entries named 8 files that no
longer exist anywhere in the tree (``WebResearchSettings.vue`` alone had 13). This guard
lists every entry whose file is missing, so the next deletion has to drop its entries in
the same change (the way #14778 and #18929 did by hand).
"""

from __future__ import annotations

import json
from pathlib import Path

from repo_tests._paths import repo_root

_REPO_ROOT = repo_root()
_FRONTEND = Path("autobot-frontend")

#: The map's ``file`` values are relative to ``autobot-frontend/src``.
_SRC = _FRONTEND / "src"
_MAP = _FRONTEND / "svg-migration-map.json"

#: 125 entries when measured (2026-11-02); the floor is under the population so an
#: emptied or mis-parsed map cannot pass vacuously.
_MIN_ENTRIES = 100


def _load_entries(root: Path) -> dict[str, dict]:
    return json.loads((root / _MAP).read_text(encoding="utf-8"))


def _resolves_inside_src(root: Path, name: str) -> bool:
    """True when *name* is an existing file whose resolved path stays inside ``src`` (no ``../`` escape)."""
    src = (root / _SRC).resolve()
    target = (root / _SRC / name).resolve()
    return target.is_relative_to(src) and target.is_file()


def _entries_naming_missing_files(entries: dict[str, dict], root: Path) -> dict[str, str]:
    """Entry key -> file, for every entry whose component is not a file inside ``src`` (#20723)."""
    return {key: entry["file"] for key, entry in entries.items() if not _resolves_inside_src(root, entry["file"])}


def test_the_map_is_not_vacuous() -> None:
    found = len(_load_entries(_REPO_ROOT))
    assert found >= _MIN_ENTRIES, f"svg-migration-map.json has {found} entries (floor {_MIN_ENTRIES})"


def test_every_entry_names_an_existing_component() -> None:
    missing = _entries_naming_missing_files(_load_entries(_REPO_ROOT), _REPO_ROOT)
    by_file: dict[str, list[str]] = {}
    for key, name in missing.items():
        by_file.setdefault(name, []).append(key)
    assert not by_file, (
        "svg-migration-map.json entries name components that no longer exist (drop the entries "
        f"in the change that deletes or renames the file): {by_file}"
    )


def test_the_detector_discriminates(tmp_path: Path) -> None:
    """Control: an entry for a present file is kept, one for a missing file is listed."""
    present = tmp_path / _SRC / "components" / "Here.vue"
    present.parent.mkdir(parents=True)
    present.write_text("<template/>", encoding="utf-8")
    entries = {
        "aaaa0001": {"id": "icons-aaaa0001", "category": "icons", "file": "components/Here.vue"},
        "bbbb0002": {"id": "icons-bbbb0002", "category": "icons", "file": "components/Gone.vue"},
    }
    assert _entries_naming_missing_files(entries, tmp_path) == {"bbbb0002": "components/Gone.vue"}


def test_an_entry_escaping_src_is_listed(tmp_path: Path) -> None:
    """#20723 negative fixture: a ``../`` path to a file that exists outside ``src`` must not count as present."""
    (tmp_path / _SRC).mkdir(parents=True)
    (tmp_path / _FRONTEND / "outside.vue").write_text("<template/>", encoding="utf-8")
    entries = {"cccc0003": {"id": "icons-cccc0003", "category": "icons", "file": "../outside.vue"}}
    assert _entries_naming_missing_files(entries, tmp_path) == {"cccc0003": "../outside.vue"}
