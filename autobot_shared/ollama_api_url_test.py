# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pins the one base-URL -> Ollama API URL rule (#21750).

A configured endpoint may be a bare base or already end in ``/api/generate``;
both must yield exactly one path segment.
"""

import pytest

from autobot_shared.ollama_urls import (
    ollama_api_url,
    ollama_base_url,
    ollama_chat_url,
    ollama_embeddings_url,
    ollama_generate_url,
    ollama_pull_url,
    ollama_show_url,
    ollama_tags_url,
)
from autobot_shared.ssot_constants import PATH_OLLAMA_CHAT, PATH_OLLAMA_TAGS

_EXPECTED = "http://ollama.example:11434/api/generate"


@pytest.mark.parametrize(
    "base",
    [
        "http://ollama.example:11434",
        "http://ollama.example:11434/",
        "http://ollama.example:11434/api/generate",
        "http://ollama.example:11434/api/generate/",
        "http://ollama.example:11434/api/chat",
    ],
)
def test_generate_url_has_the_path_exactly_once(base):
    assert ollama_generate_url(base) == _EXPECTED


def test_generate_url_is_idempotent():
    assert ollama_generate_url(ollama_generate_url("http://ollama.example:11434")) == _EXPECTED


def test_other_paths_replace_a_carried_path():
    assert ollama_api_url(_EXPECTED, PATH_OLLAMA_TAGS) == "http://ollama.example:11434/api/tags"
    assert ollama_api_url("http://ollama.example:11434", PATH_OLLAMA_CHAT) == "http://ollama.example:11434/api/chat"


def test_path_prefixed_base_keeps_its_prefix():
    assert ollama_generate_url("http://gw.example/ollama/api/generate") == "http://gw.example/ollama/api/generate"
    assert ollama_generate_url("http://gw.example/ollama") == "http://gw.example/ollama/api/generate"


@pytest.mark.parametrize(
    "base",
    ["http://ollama.example:11434", _EXPECTED, "http://ollama.example:11434/api/tags/"],
)
def test_named_wrappers_each_yield_one_path(base):
    root = "http://ollama.example:11434"
    assert ollama_base_url(base) == root
    assert ollama_chat_url(base) == root + "/api/chat"
    assert ollama_tags_url(base) == root + "/api/tags"
    assert ollama_pull_url(base) == root + "/api/pull"
    assert ollama_embeddings_url(base) == root + "/api/embeddings"
    assert ollama_embeddings_url(root + "/api/embeddings") == root + "/api/embeddings"


@pytest.mark.parametrize(
    "base",
    [
        "http://ollama.example:11434/api",
        "http://ollama.example:11434/api/",
        "http://ollama.example:11434/v1",
        "http://ollama.example:11434/v1/",
    ],
)
def test_api_and_v1_roots_are_stripped(base):
    assert ollama_generate_url(base) == _EXPECTED
    assert ollama_base_url(base) == "http://ollama.example:11434"


def test_prefixed_api_root_keeps_its_prefix():
    assert ollama_generate_url("http://gw.example/ollama/api") == "http://gw.example/ollama/api/generate"
    assert ollama_generate_url("http://gw.example/ollama/v1") == "http://gw.example/ollama/api/generate"


def test_query_string_is_unsupported_and_pinned():
    # Not a supported form: the path is appended after the query, unchanged.
    assert ollama_generate_url("http://ollama.example:11434?x=1") == "http://ollama.example:11434?x=1/api/generate"


@pytest.mark.parametrize("host", ["api", "v1"])
def test_host_named_like_an_api_root_is_not_stripped(host):
    base = f"http://{host}"
    assert ollama_generate_url(base) == f"http://{host}/api/generate"
    assert ollama_base_url(base) == base
    assert ollama_generate_url(base + "/api") == f"http://{host}/api/generate"


@pytest.mark.parametrize(
    "base",
    [
        "http://ollama.example:11434",
        _EXPECTED,
        "http://ollama.example:11434/api/show/",
        "http://ollama.example:11434/api",
    ],
)
def test_show_url_has_the_path_exactly_once(base):
    assert ollama_show_url(base) == "http://ollama.example:11434/api/show"
    assert ollama_generate_url("http://ollama.example:11434/api/show") == _EXPECTED
