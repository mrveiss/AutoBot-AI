# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one rule that turns an Ollama endpoint into an API URL (#21750).

A configured Ollama endpoint may be a bare base URL or already carry an API
path such as ``/api/generate``. Every caller
builds its URL here, so the path appears exactly once whichever form is set.

Supported forms: a bare base, a base ending in a known API path, a base ending
in ``/api`` (the Ollama API root) or ``/v1`` (the OpenAI-compatible root; both
are stripped, since every URL built here is a native ``/api/...`` one), and a
path-prefixed gateway base. A query string or fragment is NOT supported.
"""

from urllib.parse import urlsplit, urlunsplit

from autobot_shared.ssot_constants import (
    PATH_OLLAMA_CHAT,
    PATH_OLLAMA_EMBEDDINGS,
    PATH_OLLAMA_GENERATE,
    PATH_OLLAMA_PULL,
    PATH_OLLAMA_TAGS,
)

_API_ROOT_SUFFIXES = ("/api", "/v1")

# Model-details endpoint; lives here because ssot_constants.py is size-frozen (859 lines).
PATH_OLLAMA_SHOW = "/api/show"
PATH_OLLAMA_PS = "/api/ps"

_OLLAMA_API_PATHS = (
    PATH_OLLAMA_GENERATE,
    PATH_OLLAMA_CHAT,
    PATH_OLLAMA_TAGS,
    PATH_OLLAMA_PULL,
    PATH_OLLAMA_EMBEDDINGS,
    PATH_OLLAMA_SHOW,
    PATH_OLLAMA_PS,
)


def _strip_suffix(path: str) -> str:
    """Drop one known API path, else one API-root suffix, from a URL path."""
    for suffix in _OLLAMA_API_PATHS + _API_ROOT_SUFFIXES:
        if path.endswith(suffix):
            return path[: -len(suffix)].rstrip("/")
    return path


def ollama_api_url(base_url: str, path: str) -> str:
    """``base_url`` (with or without a known API path) -> URL ending in ``path`` once.

    Suffixes are stripped from the URL path only, never from the authority.
    """
    parts = urlsplit(base_url.rstrip("/"))
    stripped = _strip_suffix(parts.path)
    return urlunsplit((parts.scheme, parts.netloc, stripped, parts.query, parts.fragment)) + path


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


def ollama_show_url(base_url: str) -> str:
    """``base_url`` -> its single ``/api/show`` URL."""
    return ollama_api_url(base_url, PATH_OLLAMA_SHOW)


def ollama_ps_url(base_url: str) -> str:
    """``base_url`` -> its single ``/api/ps`` URL (the models currently loaded)."""
    return ollama_api_url(base_url, PATH_OLLAMA_PS)
