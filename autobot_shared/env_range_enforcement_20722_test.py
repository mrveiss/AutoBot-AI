# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""env() enforces each registered ``range`` once, for every variable (#20722)."""

import logging

import pytest

from autobot_shared import env_registry
from autobot_shared.env_registry import REGISTRY, EnvVarSpec, env

_NAME = "AUTOBOT_TEST_RANGE_20722"


@pytest.fixture
def spec(monkeypatch):
    monkeypatch.delenv(_NAME, raising=False)
    monkeypatch.setitem(REGISTRY, _NAME, EnvVarSpec(_NAME, int, 10, "range probe", "testing", range=(5, 20)))
    return REGISTRY[_NAME]


def test_in_range_passes_including_bounds(spec, monkeypatch):
    for raw, want in (("5", 5), ("12", 12), ("20", 20)):
        monkeypatch.setenv(_NAME, raw)
        assert env(_NAME) == want


@pytest.mark.parametrize("raw", ["4", "21", "-1"])
def test_out_of_range_falls_back_with_warning(spec, monkeypatch, caplog, raw):
    monkeypatch.setenv(_NAME, raw)
    with caplog.at_level(logging.WARNING):
        assert env(_NAME) == 10
    assert _NAME in caplog.text
    assert raw not in caplog.text.replace(_NAME, "")


def test_open_ended_range(monkeypatch):
    monkeypatch.setitem(REGISTRY, _NAME, EnvVarSpec(_NAME, int, 3, "probe", "testing", range=(1, None)))
    monkeypatch.setenv(_NAME, "1000000")
    assert env(_NAME) == 1000000
    monkeypatch.setenv(_NAME, "0")
    assert env(_NAME) == 3


def test_non_numeric_type_with_range_untouched(monkeypatch):
    monkeypatch.setitem(REGISTRY, _NAME, EnvVarSpec(_NAME, str, "a", "probe", "testing", range=(1, 2)))
    monkeypatch.setenv(_NAME, "zzz")
    assert env(_NAME) == "zzz"


def test_every_registered_default_lies_inside_its_range():
    assert env_registry.REGISTRY
    bad = []
    for name, s in REGISTRY.items():
        if s.range is None or isinstance(s.default, bool) or not isinstance(s.default, (int, float)):
            continue
        lo, hi = s.range
        if (lo is not None and s.default < lo) or (hi is not None and s.default > hi):
            bad.append((name, s.default, s.range))
    assert not bad, f"registry bug: default outside its own range: {bad}"
