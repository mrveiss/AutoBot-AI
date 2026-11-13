# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The re-embed lease TTL default has one definition (#21102)."""

import pytest

from autobot_shared.env_registry import REGISTRY
from autobot_shared.env_registry_mesh_reembed import (
    REEMBED_INTERVAL_DEFAULT_S,
    REEMBED_LEASE_INTERVALS,
    reembed_lease_ttl_default_ms,
)
from services.mesh_brain import reembed_consumer as rc


def test_registry_interval_default_is_the_shared_constant():
    assert REGISTRY["AUTOBOT_MESH_REEMBED_INTERVAL_S"].default == REEMBED_INTERVAL_DEFAULT_S


def test_registry_ttl_default_is_derived_from_the_registry_interval_default():
    interval = REGISTRY["AUTOBOT_MESH_REEMBED_INTERVAL_S"].default
    assert REGISTRY["AUTOBOT_MESH_REEMBED_LEASE_TTL_MS"].default == reembed_lease_ttl_default_ms(interval)


_INTERVAL_VAR = "AUTOBOT_MESH_REEMBED_INTERVAL_S"
_TTL_VAR = "AUTOBOT_MESH_REEMBED_LEASE_TTL_MS"


@pytest.fixture
def clean_env(monkeypatch):
    """Neither variable set, whatever the process started with; monkeypatch restores both afterwards.

    The consumer's module constants are read once at import, so these tests call the functions that
    derive them instead of reloading the module (a reload would replace its classes under other tests).
    """
    monkeypatch.delenv(_INTERVAL_VAR, raising=False)
    monkeypatch.delenv(_TTL_VAR, raising=False)
    return monkeypatch


def test_consumer_default_with_nothing_set(clean_env):
    assert rc.lease_ttl_ms_from_env() == reembed_lease_ttl_default_ms(REEMBED_INTERVAL_DEFAULT_S)
    assert rc.lease_ttl_ms_from_env() == 120000


def test_a_changed_interval_moves_the_consumers_default(clean_env):
    clean_env.setenv(_INTERVAL_VAR, "60")
    assert rc.interval_s_from_env() == 60
    assert rc.lease_ttl_ms_from_env() == 240000


def test_an_explicit_ttl_wins_over_the_interval_derived_default(clean_env):
    clean_env.setenv(_INTERVAL_VAR, "60")
    clean_env.setenv(_TTL_VAR, "5000")
    assert rc.lease_ttl_ms_from_env() == 5000


@pytest.mark.parametrize(
    ("interval_s", "expected_ms"),
    [(30, 120000), (60, 240000), (1, 4000)],
)
def test_a_changed_interval_moves_the_default(interval_s, expected_ms):
    assert reembed_lease_ttl_default_ms(interval_s) == expected_ms


def test_the_ttl_spans_the_documented_number_of_intervals():
    assert REEMBED_LEASE_INTERVALS == 4
    assert reembed_lease_ttl_default_ms(10) == 10 * REEMBED_LEASE_INTERVALS * 1000
