# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
import os

from autobot_shared.env_utils import env_int_clamped

_VAR = "TEST_ENV_INT_CLAMPED_XYZ"


def _clean():
    os.environ.pop(_VAR, None)


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
