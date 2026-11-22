# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20683: an unparseable CODEBASE_INDEX batch size falls back to its default at config load.

Loaded through ``CodebaseIndexSettings`` (the real settings class ``MiscConfig`` inherits),
with ``_env_file=None`` so no ``.env`` on disk interferes. Pre-fix, every ``abc`` case below
raised ``ValidationError`` and the unset ``batch_size`` default was 0, not 5000.
"""

import logging
import os
from unittest.mock import patch

import pytest

from autobot_shared.ssot_codebase_index import (
    DEFAULT_CODEBASE_INDEX_BATCH_SIZE,
    DEFAULT_CODEBASE_INDEX_EMBED_BATCH_SIZE,
    CodebaseIndexSettings,
)


def _load(env: dict) -> CodebaseIndexSettings:
    with patch.dict(os.environ, env, clear=True):
        return CodebaseIndexSettings(_env_file=None)  # type: ignore[call-arg]


def test_unset_batch_size_is_the_declared_default_not_zero() -> None:
    assert _load({}).codebase_index_batch_size == DEFAULT_CODEBASE_INDEX_BATCH_SIZE == 5000


@pytest.mark.parametrize(
    ("var", "attr", "default"),
    [
        ("CODEBASE_INDEX_BATCH_SIZE", "codebase_index_batch_size", DEFAULT_CODEBASE_INDEX_BATCH_SIZE),
        ("CODEBASE_INDEX_EMBED_BATCH_SIZE", "codebase_index_embed_batch_size", DEFAULT_CODEBASE_INDEX_EMBED_BATCH_SIZE),
    ],
)
def test_unparseable_value_falls_back_to_default_and_logs(var, attr, default, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        settings = _load({var: "abc"})
    assert getattr(settings, attr) == default
    assert var in caplog.text


@pytest.mark.parametrize("var", ["CODEBASE_INDEX_BATCH_SIZE", "CODEBASE_INDEX_EMBED_BATCH_SIZE"])
def test_blank_value_falls_back_to_default(var) -> None:
    settings = _load({var: ""})
    assert settings.codebase_index_batch_size == DEFAULT_CODEBASE_INDEX_BATCH_SIZE
    assert settings.codebase_index_embed_batch_size == DEFAULT_CODEBASE_INDEX_EMBED_BATCH_SIZE


def test_valid_values_still_parse() -> None:
    settings = _load({"CODEBASE_INDEX_BATCH_SIZE": "2500", "CODEBASE_INDEX_EMBED_BATCH_SIZE": "250"})
    assert (settings.codebase_index_batch_size, settings.codebase_index_embed_batch_size) == (2500, 250)


def test_programmatic_ints_and_integral_floats_are_kept_not_replaced() -> None:
    """Pre-fix of the parse helper, ``str(5.0)`` -> ``int("5.0")`` failed and 5.0 became the default."""
    with patch.dict(os.environ, {}, clear=True):
        built = CodebaseIndexSettings(  # type: ignore[call-arg]
            _env_file=None, CODEBASE_INDEX_BATCH_SIZE=2500, CODEBASE_INDEX_EMBED_BATCH_SIZE=250.0
        )
    assert (built.codebase_index_batch_size, built.codebase_index_embed_batch_size) == (2500, 250)


def test_a_fractional_float_or_bool_falls_back() -> None:
    with patch.dict(os.environ, {}, clear=True):
        built = CodebaseIndexSettings(  # type: ignore[call-arg]
            _env_file=None, CODEBASE_INDEX_BATCH_SIZE=2.5, CODEBASE_INDEX_EMBED_BATCH_SIZE=True
        )
    assert built.codebase_index_batch_size == DEFAULT_CODEBASE_INDEX_BATCH_SIZE
    assert built.codebase_index_embed_batch_size == DEFAULT_CODEBASE_INDEX_EMBED_BATCH_SIZE
