# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one rule that turns an Ollama endpoint into an API URL (#21750).

A configured Ollama endpoint may be a bare base URL or already carry an API
path such as ``/api/generate``. Every caller
builds its URL here, so the path appears exactly once whichever form is set.
"""

from autobot_shared.ssot_constants import (
    PATH_OLLAMA_CHAT,
    PATH_OLLAMA_GENERATE,
    PATH_OLLAMA_PULL,
    PATH_OLLAMA_TAGS,
)

PATH_OLLAMA_EMBEDDINGS = "/api/embeddings"

_OLLAMA_API_PATHS = (
    PATH_OLLAMA_GENERATE,
    PATH_OLLAMA_CHAT,
    PATH_OLLAMA_TAGS,
    PATH_OLLAMA_PULL,
    PATH_OLLAMA_EMBEDDINGS,
)


def ollama_api_url(base_url: str, path: str) -> str:
    """``base_url`` (with or without a known API path) -> URL ending in ``path`` once."""
    base = base_url.rstrip("/")
    for known in _OLLAMA_API_PATHS:
        if base.endswith(known):
            base = base[: -len(known)].rstrip("/")
            break
    return base + path


def ollama_generate_url(base_url: str) -> str:
    """``base_url`` -> its single ``/api/generate`` URL."""
    return ollama_api_url(base_url, PATH_OLLAMA_GENERATE)


def ollama_base_url(url: str) -> str:
    """``url`` (with or without a known API path) -> the bare base URL."""
    return ollama_api_url(url, "")


def ollama_chat_url(base_url: str) -> str:
    """``base_url`` -> its single ``/api/chat`` URL."""
    return ollama_api_url(base_url, PATH_OLLAMA_CHAT)


def ollama_tags_url(base_url: str) -> str:
    """``base_url`` -> its single ``/api/tags`` URL."""
    return ollama_api_url(base_url, PATH_OLLAMA_TAGS)


def ollama_pull_url(base_url: str) -> str:
    """``base_url`` -> its single ``/api/pull`` URL."""
    return ollama_api_url(base_url, PATH_OLLAMA_PULL)


def ollama_embeddings_url(base_url: str) -> str:
    """``base_url`` -> its single ``/api/embeddings`` URL."""
    return ollama_api_url(base_url, PATH_OLLAMA_EMBEDDINGS)
