# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for verify_knowledge_consistency's FT.INFO walk (#13290).

This script builds its Redis client via ``get_redis_client()``, which resolves
``decode_responses=True``, so ``FT.INFO`` returns ``str`` elements. The walk
previously compared against ``bytes`` literals, which never matched — so
``_find_vector_dimension_in_index`` always returned ``None`` and the mismatch
branch in ``_verify_redis_vector_dimension`` could never fire. Unlike the two
copies fixed alongside it, this one failed *silently*: a consistency verifier
that always reports consistent.
"""

import importlib.util
import pathlib
import sys
from unittest.mock import MagicMock

import pytest

_MODULE_PATH = pathlib.Path(__file__).with_name("verify_knowledge_consistency.py")

# What a decode_responses=True client returns for FT.INFO on the vector index.
_DECODED_FT_INFO = [
    "index_name",
    "llama_index",
    "attributes",
    [
        [
            "identifier",
            "vector",
            "attribute",
            "vector",
            "type",
            "VECTOR",
            "DIM",
            "768",
        ]
    ],
]


def _load_module():
    """Import verify_knowledge_consistency by path — its directory is not a package."""
    spec = importlib.util.spec_from_file_location("verify_knowledge_consistency", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - dependency-driven skip
        pytest.skip(f"verify_knowledge_consistency is not importable here: {exc}")
    return module


@pytest.fixture(scope="module")
def mod():
    return _load_module()


def test_find_vector_dimension_reads_a_decoded_ft_info_reply(mod):
    """The walk must find the dimension in a str-keyed FT.INFO reply."""
    assert mod._find_vector_dimension_in_index(_DECODED_FT_INFO) == 768


def test_extract_vector_dim_reads_a_decoded_attribute(mod):
    """The per-attribute helper must match 'VECTOR'/'DIM' as str, not bytes."""
    assert mod._extract_vector_dim_from_attr(_DECODED_FT_INFO[3][0]) == 768


def test_non_vector_attribute_yields_no_dimension(mod):
    """A non-vector attribute must not be mistaken for one."""
    assert mod._extract_vector_dim_from_attr(["identifier", "title", "attribute", "title", "type", "TEXT"]) is None


def test_lowercase_dim_key_is_accepted(mod):
    """RediSearch key casing varies by version — both must resolve."""
    attr = ["identifier", "vector", "attribute", "vector", "type", "VECTOR", "dim", "768"]
    assert mod._extract_vector_dim_from_attr(attr) == 768


def test_mismatched_dimension_is_reported(mod):
    """The mismatch branch must actually fire — it never could before #13290."""
    client = MagicMock()
    client.execute_command.return_value = _DECODED_FT_INFO

    ok, message = mod._verify_redis_vector_dimension(client, expected_dimension=1024)

    assert ok is False
    assert "768" in message and "1024" in message


def test_matching_dimension_passes(mod):
    """A correct index reports consistent, with no message."""
    client = MagicMock()
    client.execute_command.return_value = _DECODED_FT_INFO

    assert mod._verify_redis_vector_dimension(client, expected_dimension=768) == (True, None)
