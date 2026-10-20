# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The backend image ships the same ``llm_models.yaml`` as a native install (#18884).

The Dockerfile does ``COPY autobot-backend/``, so the image carries the backend registry. Any later
``COPY`` that lands a file on ``config/llm_models.yaml`` from elsewhere would give Docker and native
installs different model registries, so only the canonical source (or the whole backend tree) may
write that destination.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

_DOCKERFILE = "docker/backend/Dockerfile"
_CANONICAL = "autobot-backend/config/llm_models.yaml"
_BACKEND_TREE = "autobot-backend/"


def _copies(text: str) -> list[tuple[list[str], str]]:
    """(sources, destination) for every plain ``COPY`` (flags dropped, line continuations joined)."""
    out = []
    for line in text.replace("\\\n", " ").splitlines():
        parts = line.split()
        if not parts or parts[0].upper() != "COPY":
            continue
        args = [a for a in parts[1:] if not a.startswith("--")]
        if len(args) >= 2:
            out.append((args[:-1], args[-1]))
    return out


def _offenders(text: str) -> list[str]:
    found = []
    for sources, dest in _copies(text):
        if not re.search(r"llm_models\.yaml$", dest) and not any(s.endswith("llm_models.yaml") for s in sources):
            continue
        if sources != [_CANONICAL] and sources != [_BACKEND_TREE]:
            found.append(f"COPY {' '.join(sources)} -> {dest}")
    return found


def test_no_copy_overwrites_the_backend_llm_registry() -> None:
    text = (repo_root() / _DOCKERFILE).read_text(encoding="utf-8")
    assert not _offenders(text), f"#18884: {_offenders(text)}"


def test_the_image_gets_the_canonical_registry_from_the_backend_tree() -> None:
    text = (repo_root() / _DOCKERFILE).read_text(encoding="utf-8")
    sources = [s for srcs, _ in _copies(text) for s in srcs]
    assert _BACKEND_TREE in sources
    assert (repo_root() / _CANONICAL).is_file()


def test_the_check_catches_an_overwrite() -> None:
    bad = "COPY autobot-backend/ /app/autobot-backend/\nCOPY other/llm_models.yaml /app/autobot-backend/config/llm_models.yaml\n"
    assert _offenders(bad)
    assert not _offenders("COPY autobot-backend/ /app/autobot-backend/\n")
