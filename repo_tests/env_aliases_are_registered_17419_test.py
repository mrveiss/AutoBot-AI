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
from repo_tests.env_alias_registry_gap_baseline_17419 import UNREGISTERED_ALIASES

from autobot_shared.testfile_names import is_test_filename
from tools.lint import _parse_cache as parse_cache

SSOT_GLOB = "ssot*.py"
REGISTRY_GLOB = "env_registry*.py"
#: Aliases extracted when this guard landed was 447; a census that finds fewer than this has narrowed.
MIN_ALIASES_EXTRACTED = 350
#: Source files read (47 when measured), less a margin for removals.
MIN_FILES_READ = 40


def _sources(root: Path, pattern: str) -> list[Path]:
    return [p for p in sorted((root / "autobot_shared").glob(pattern)) if not is_test_filename(p.name)]


def _population(root: Path) -> list[str]:
    return [str(p.relative_to(root)) for pattern in (SSOT_GLOB, REGISTRY_GLOB) for p in _sources(root, pattern)]


REACH = declare(
    "env-alias-registry-gap",
    discover=_population,
    floor=MIN_FILES_READ,
    what="ssot*.py and env_registry*.py read for AUTOBOT_* aliases and registrations",
)


def _census(paths: list[Path], extract) -> Census:
    total = Census()
    for path in paths:
        found = extract(parse_cache.parse(path.read_text(encoding="utf-8"), str(path)))
        total.names |= found.names
        total.dynamic += found.dynamic
    return total


def unregistered(aliases: set[str], registered: set[str]) -> set[str]:
    return aliases - registered


def test_every_alias_is_registered_or_baselined() -> None:
    root = repo_root()
    REACH.verify_floor(root)
    aliases = _census(_sources(root, SSOT_GLOB), aliases_in).names
    registered = _census(_sources(root, REGISTRY_GLOB), registered_in).names
    assert len(aliases) >= MIN_ALIASES_EXTRACTED, f"extracted only {len(aliases)} aliases"
    gap = unregistered(aliases, registered)
    assert gap - UNREGISTERED_ALIASES == set(), "register these in an env_registry_<component>.py"
    assert UNREGISTERED_ALIASES - gap == set(), "stale baseline entries: delete them"


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


def test_a_name_handed_to_a_registering_helper_counts_as_registered() -> None:
    helper = parse_cache.parse(
        "def _register(name):\n    register_env_var(EnvVarSpec(name=name))\n\n_register('AUTOBOT_VIA_HELPER')\n"
    )
    found = registered_in(helper)
    assert "AUTOBOT_VIA_HELPER" in found.names and found.dynamic == [(2, "EnvVarSpec")]
