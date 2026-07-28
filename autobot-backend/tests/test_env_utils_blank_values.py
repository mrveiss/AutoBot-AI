# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A blank env var must behave as absent, not as a value (#12782).

A deployment template that renders an undefined variable exports ``NAME=``
instead of omitting the line. That blank is worse than absence: it looks "set"
to any presence check, and ``os.environ.get(name, default)`` returns ``""`` —
not the default — so every default-argument fallback is silently defeated.

Observed on a live node as six settings collapsing to defaults with confusing
"Invalid X=''" warnings every boot, and previously as #12778, where a blank
REDIS_HOST defeated its fallback and the backend refused to connect.
"""

import pytest

from autobot_shared.env_utils import (
    env_flag,
    env_float,
    env_int,
    env_int_clamped,
    env_raw,
    env_str,
)

_BLANKS = ["", "   ", "\t", "\n"]


@pytest.mark.parametrize("blank", _BLANKS)
def test_env_raw_treats_blank_as_absent(monkeypatch, blank):
    monkeypatch.setenv("PROBE_VAR", blank)
    assert env_raw("PROBE_VAR") is None


def test_env_raw_preserves_a_real_value(monkeypatch):
    monkeypatch.setenv("PROBE_VAR", " actual ")
    assert env_raw("PROBE_VAR") == " actual "


@pytest.mark.parametrize("blank", _BLANKS)
def test_env_str_falls_back_on_blank(monkeypatch, blank):
    """The os.environ.get(k, default) trap: a blank returns "" instead of the default."""
    monkeypatch.setenv("PROBE_VAR", blank)

    import os

    assert os.environ.get("PROBE_VAR", "fallback") != "fallback"  # the trap, pinned
    assert env_str("PROBE_VAR", "fallback") == "fallback"  # the fix


@pytest.mark.parametrize("blank", _BLANKS)
def test_env_int_falls_back_on_blank_without_a_warning(monkeypatch, caplog, blank):
    """A blank is a deployment artefact, not an invalid integer.

    It previously reached int("") and was reported as
    "AUTOBOT_CHAT_SESSION_CACHE_TTL='' is not an integer" on every boot — noise
    that trains operators to ignore the warning stream.
    """
    monkeypatch.setenv("PROBE_VAR", blank)

    with caplog.at_level("WARNING"):
        assert env_int("PROBE_VAR", 86400) == 86400

    assert not [r for r in caplog.records if "PROBE_VAR" in r.getMessage()]


def test_env_int_still_warns_on_a_genuinely_invalid_value(monkeypatch, caplog):
    """Blank-tolerance must not silence real misconfiguration."""
    monkeypatch.setenv("PROBE_VAR", "not-a-number")

    with caplog.at_level("WARNING"):
        assert env_int("PROBE_VAR", 7) == 7

    assert any("PROBE_VAR" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("blank", _BLANKS)
def test_env_float_falls_back_on_blank(monkeypatch, blank):
    monkeypatch.setenv("PROBE_VAR", blank)
    assert env_float("PROBE_VAR", 1.5) == 1.5


@pytest.mark.parametrize("blank", _BLANKS)
def test_env_int_clamped_falls_back_on_blank(monkeypatch, blank):
    monkeypatch.setenv("PROBE_VAR", blank)
    assert env_int_clamped("PROBE_VAR", 50, min_v=1, max_v=100) == 50


@pytest.mark.parametrize("blank", _BLANKS)
def test_blank_does_not_silently_disable_a_default_on_flag(monkeypatch, blank):
    """The sharpest case: truthy("") is False, so a blank would flip a default-True flag OFF."""
    monkeypatch.setenv("PROBE_VAR", blank)

    assert env_flag("PROBE_VAR", default=True) is True
    assert env_flag("PROBE_VAR", default=False) is False


def test_flag_still_honours_an_explicit_false(monkeypatch):
    monkeypatch.setenv("PROBE_VAR", "false")
    assert env_flag("PROBE_VAR", default=True) is False


def test_absent_var_behaves_the_same_as_blank(monkeypatch):
    """The whole point: absent and blank must be indistinguishable to callers."""
    monkeypatch.delenv("PROBE_VAR", raising=False)
    absent = (env_raw("PROBE_VAR"), env_str("PROBE_VAR", "d"), env_int("PROBE_VAR", 3), env_flag("PROBE_VAR", True))

    monkeypatch.setenv("PROBE_VAR", "")
    blank = (env_raw("PROBE_VAR"), env_str("PROBE_VAR", "d"), env_int("PROBE_VAR", 3), env_flag("PROBE_VAR", True))

    assert absent == blank
