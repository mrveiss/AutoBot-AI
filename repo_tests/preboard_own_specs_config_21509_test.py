# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Config discovery and object-spread refusal for the pre-board own-specs selection (#21509).

Split from ``preboard_own_specs_21509_test.py`` (its file-size ceiling): which config file names make a directory a
frontend package, and the shapes of a ``test`` object the rule reader refuses instead of guessing.
"""

from __future__ import annotations

import pytest
from repo_tests import _preboard_guard_lane_support as support


@pytest.fixture(scope="module")
def lane():
    yield from support.load_lane()


def test_the_config_file_names_are_vitests_own_list_in_its_order(lane) -> None:
    extensions = (".ts", ".mts", ".cts", ".js", ".mjs", ".cjs")
    expected = tuple(f"{stem}{e}" for stem in ("vitest.config", "vite.config") for e in extensions)
    assert lane.specs.CONFIG_NAMES == expected


@pytest.mark.parametrize("name", ["vitest.config.cts", "vitest.config.cjs", "vite.config.mts", "vite.config.cjs"])
def test_a_package_is_found_through_every_config_name_vitest_looks_for(lane, tmp_path, name) -> None:
    (tmp_path / "web" / "src").mkdir(parents=True)
    (tmp_path / "web" / name).write_text("module.exports = { test: { include: ['src/**/*.spec.ts'] } }\n", "utf-8")
    (tmp_path / "web" / "src" / "new.spec.ts").write_text("", encoding="utf-8")
    assert lane.specs.select_specs(tmp_path, ["web/src/new.spec.ts"]) == ({"web": ["src/new.spec.ts"]}, [], [])


def test_the_vitest_config_wins_over_a_vite_config_in_the_same_directory(lane, tmp_path) -> None:
    (tmp_path / "web").mkdir()
    for name in ("vite.config.ts", "vitest.config.cjs"):
        (tmp_path / "web" / name).write_text("", encoding="utf-8")
    assert lane.specs._config_file(tmp_path, "web").name == "vitest.config.cjs"


@pytest.mark.parametrize(
    "test_body",
    [
        "include: ['src/**/*.spec.ts'], exclude: ['src/new.spec.ts'], ...overrides",
        "...mergeConfig(a, b), include: ['src/**/*.spec.ts']",
        "include: ['src/**/*.spec.ts'],\n    ...(flag ? { exclude: [] } : {})",
    ],
)
def test_an_object_spread_in_the_test_object_is_refused(lane, tmp_path, test_body) -> None:
    config = tmp_path / "vitest.config.ts"
    config.write_text(f"export default {{ test: {{ {test_body} }} }}\n", encoding="utf-8")
    with pytest.raises(lane.specs.UnreadableConfig):
        lane.specs.package_rules(config)


def test_a_spread_inside_the_exclude_array_or_a_nested_object_is_not_an_object_spread(lane, tmp_path) -> None:
    config = tmp_path / "vitest.config.ts"
    config.write_text(
        "export default { test: { include: ['src/**/*.spec.ts'], exclude: [...configDefaults.exclude, 'a/**'],\n"
        "  coverage: { ...base, exclude: [...x] } } }\n",
        encoding="utf-8",
    )
    assert lane.specs.package_rules(config) == (["src/**/*.spec.ts"], ["a/**", *lane.specs.DEFAULT_EXCLUDE])
