# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
import os

from autobot_shared.env_utils import env_float, env_int, env_int_clamped

_VAR = "TEST_ENV_INT_CLAMPED_XYZ"
_FLOAT_VAR = "TEST_ENV_FLOAT_XYZ"
_INT_VAR = "TEST_ENV_INT_XYZ"


def _clean():
    os.environ.pop(_VAR, None)


# ---------------------------------------------------------------------------
# env_float tests
# ---------------------------------------------------------------------------


def test_env_float_default_when_missing():
    os.environ.pop(_FLOAT_VAR, None)
    assert env_float(_FLOAT_VAR, 3.14) == 3.14


def test_env_float_reads_valid_value():
    os.environ[_FLOAT_VAR] = "2.5"
    try:
        assert env_float(_FLOAT_VAR, 1.0) == 2.5
    finally:
        os.environ.pop(_FLOAT_VAR, None)


def test_env_float_reads_integer_string():
    os.environ[_FLOAT_VAR] = "10"
    try:
        assert env_float(_FLOAT_VAR, 1.0) == 10.0
    finally:
        os.environ.pop(_FLOAT_VAR, None)


def test_env_float_fallback_on_malformed(caplog):
    os.environ[_FLOAT_VAR] = "notafloat"
    try:
        import logging

        with caplog.at_level(logging.WARNING, logger="autobot_shared.env_utils"):
            result = env_float(_FLOAT_VAR, 7.0)
        assert result == 7.0
        assert "notafloat" in caplog.text
    finally:
        os.environ.pop(_FLOAT_VAR, None)


def test_env_float_negative_value():
    os.environ[_FLOAT_VAR] = "-1.5"
    try:
        assert env_float(_FLOAT_VAR, 0.0) == -1.5
    finally:
        os.environ.pop(_FLOAT_VAR, None)


# ---------------------------------------------------------------------------
# env_int tests
# ---------------------------------------------------------------------------


def test_env_int_default_when_missing():
    os.environ.pop(_INT_VAR, None)
    assert env_int(_INT_VAR, 42) == 42


def test_env_int_reads_valid_value():
    os.environ[_INT_VAR] = "99"
    try:
        assert env_int(_INT_VAR, 1) == 99
    finally:
        os.environ.pop(_INT_VAR, None)


def test_env_int_fallback_on_malformed(caplog):
    os.environ[_INT_VAR] = "bad"
    try:
        import logging

        with caplog.at_level(logging.WARNING, logger="autobot_shared.env_utils"):
            result = env_int(_INT_VAR, 5)
        assert result == 5
        assert "bad" in caplog.text
    finally:
        os.environ.pop(_INT_VAR, None)


def test_env_int_negative_value():
    os.environ[_INT_VAR] = "-7"
    try:
        assert env_int(_INT_VAR, 0) == -7
    finally:
        os.environ.pop(_INT_VAR, None)


def test_default_when_missing():
    _clean()
    assert env_int_clamped(_VAR, 5) == 5


def test_reads_env_var():
    os.environ[_VAR] = "10"
    try:
        assert env_int_clamped(_VAR, 5) == 10
    finally:
        _clean()


def test_clamps_min():
    os.environ[_VAR] = "0"
    try:
        assert env_int_clamped(_VAR, 5, min_v=1) == 1
    finally:
        _clean()


def test_clamps_max():
    os.environ[_VAR] = "100"
    try:
        assert env_int_clamped(_VAR, 5, max_v=10) == 10
    finally:
        _clean()


def test_invalid_falls_back_to_default():
    os.environ[_VAR] = "notanint"
    try:
        assert env_int_clamped(_VAR, 5) == 5
    finally:
        _clean()


def test_no_bounds():
    os.environ[_VAR] = "999"
    try:
        assert env_int_clamped(_VAR, 1) == 999
    finally:
        _clean()


def test_clamps_both_bounds():
    os.environ[_VAR] = "15"
    try:
        assert env_int_clamped(_VAR, 5, min_v=1, max_v=10) == 10
    finally:
        _clean()


def test_negative_value_allowed_without_bounds():
    os.environ[_VAR] = "-3"
    try:
        assert env_int_clamped(_VAR, 0) == -3
    finally:
        _clean()
