# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every ``AUTOBOT_*`` alias an SSOT settings model binds is registered, or is on a shrink-only baseline (#17419).

Static: reads ``autobot_shared/ssot*.py`` and ``autobot_shared/env_registry*.py`` as text through
``repo_tests/_env_alias_census.py``, so it neither imports the models nor depends on import order. The
population is what that census can see (string constants); the baseline module states what it cannot.
The runtime counterpart is ``env_planes_agree_on_defaults_17419_test.py``.
"""

from __future__ import annotations

from pathlib import Path

from repo_tests._env_alias_census import Census, aliases_in, registered_in
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.env_alias_registry_gap_baseline_17419 import (
    ALIAS_SIDE_DYNAMIC,
    REGISTRY_SIDE_DYNAMIC,
    UNREGISTERED_ALIASES,
)

from autobot_shared.testfile_names import is_test_filename
from tools.lint import _parse_cache as parse_cache

SSOT_GLOB = "ssot*.py"
REGISTRY_GLOB = "env_registry*.py"
#: AUTOBOT_* aliases the census extracts from ssot*.py (447, re-measured on the merged tree); pinned with no margin.
MIN_ALIASES_EXTRACTED = 447
#: Source files read (48 when measured); the floor is pinned to it, with no margin, by the reach-floor gate.
MIN_FILES_READ = 48


def _sources(root: Path, pattern: str) -> list[Path]:
    return [p for p in sorted((root / "autobot_shared").glob(pattern)) if not is_test_filename(p.name)]


def _population(root: Path) -> list[str]:
    return [str(p.relative_to(root)) for pattern in (SSOT_GLOB, REGISTRY_GLOB) for p in _sources(root, pattern)]


REACH = declare(
    "env-alias-registry-gap",
    discover=_population,
    floor=MIN_FILES_READ,
    roots=("autobot_shared",),
    what="ssot*.py and env_registry*.py read for AUTOBOT_* aliases and registrations",
)


def _census(paths: list[Path], extract) -> tuple[Census, dict[str, int]]:
    """The names found, and per file how many names the census could not read (counts, never line numbers)."""
    total = Census()
    dynamic: dict[str, int] = {}
    for path in paths:
        found = extract(parse_cache.parse(path.read_text(encoding="utf-8"), str(path)))
        total.names |= found.names
        total.dynamic += found.dynamic
        if found.dynamic:
            dynamic[path.name] = len(found.dynamic)
    return total, dynamic


def _alias_population(root: Path) -> list[str]:
    """Every AUTOBOT_* alias the census extracts from the ssot*.py sources."""
    return sorted(_census(_sources(root, SSOT_GLOB), aliases_in)[0].names)


ALIAS_REACH = declare(
    "env-alias-census",
    discover=_alias_population,
    floor=MIN_ALIASES_EXTRACTED,
    what="AUTOBOT_* aliases extracted from ssot*.py",
)


def unregistered(aliases: set[str], registered: set[str]) -> set[str]:
    return aliases - registered


def test_every_alias_is_registered_or_baselined() -> None:
    root = repo_root()
    REACH.verify_floor(root)
    aliases, _ = _census(_sources(root, SSOT_GLOB), aliases_in)
    registered, _ = _census(_sources(root, REGISTRY_GLOB), registered_in)
    ALIAS_REACH.verify_floor(root)
    gap = unregistered(aliases.names, registered.names)
    assert gap - UNREGISTERED_ALIASES == set(), "register these in an env_registry_<component>.py"
    assert UNREGISTERED_ALIASES - gap == set(), "stale baseline entries: delete them"


def test_the_names_the_census_cannot_read_are_pinned_per_file() -> None:
    """A new variable-built alias or registration is a blind spot appearing; it must be a reviewed decision."""
    root = repo_root()
    _, alias_side = _census(_sources(root, SSOT_GLOB), aliases_in)
    _, registry_side = _census(_sources(root, REGISTRY_GLOB), registered_in)
    assert alias_side == ALIAS_SIDE_DYNAMIC, "alias-side blind spots changed: see the baseline module"
    assert registry_side == REGISTRY_SIDE_DYNAMIC, "registry-side blind spots changed: see the baseline module"


def test_an_extra_dynamic_alias_changes_the_pinned_count(tmp_path: Path) -> None:
    one = tmp_path / "ssot_one.py"
    one.write_text('a = Field(alias="AUTOBOT_X")\nb = Field(alias=name)\n', encoding="utf-8")
    assert _census([one], aliases_in)[1] == {"ssot_one.py": 1}
    one.write_text('a = Field(alias="AUTOBOT_X")\nb = Field(alias=name)\nc = Field(alias=other)\n', encoding="utf-8")
    assert _census([one], aliases_in)[1] == {"ssot_one.py": 2}


def test_a_planted_unregistered_alias_is_caught_and_a_registered_one_is_not() -> None:
    settings = parse_cache.parse(
        'a = Field(default="", alias="AUTOBOT_PLANTED_X")\nb = Field(validation_alias=AliasChoices("AUTOBOT_PLANTED_Y", "LEGACY"))\n'
        'c = Field(alias="AUTOBOT_PLANTED_REGISTERED")\nd = Field(alias=some_variable)\n'
    )
    registry = parse_cache.parse('register_env_var(EnvVarSpec(name="AUTOBOT_PLANTED_REGISTERED", type=str))\n')
    aliases = aliases_in(settings)
    assert aliases.names == {"AUTOBOT_PLANTED_X", "AUTOBOT_PLANTED_Y", "AUTOBOT_PLANTED_REGISTERED"}
    assert aliases.dynamic == [(4, "alias")]
    assert unregistered(aliases.names, registered_in(registry).names) == {"AUTOBOT_PLANTED_X", "AUTOBOT_PLANTED_Y"}


def test_keyword_expansion_is_a_dynamic_site_and_a_literal_name_is_not() -> None:
    static = registered_in(parse_cache.parse('EnvVarSpec(name="AUTOBOT_X", type=str)\n'))
    expanded = registered_in(parse_cache.parse("EnvVarSpec(**spec)\n"))
    assert static.names == {"AUTOBOT_X"} and static.dynamic == []
    assert expanded.dynamic == [(1, "EnvVarSpec")]


def test_a_name_handed_to_a_registering_helper_counts_as_registered() -> None:
    helper = parse_cache.parse(
        "def _register(name):\n    register_env_var(EnvVarSpec(name=name))\n\n_register('AUTOBOT_VIA_HELPER')\n"
    )
    found = registered_in(helper)
    assert "AUTOBOT_VIA_HELPER" in found.names and found.dynamic == [(2, "EnvVarSpec")]
