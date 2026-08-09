# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared ChromaDB guard for the knowledge-backend contract suites (#13239).

``test_base.py`` and ``test_async_base.py`` both parametrize their contract over
an in-memory adapter and a ChromaDB adapter. Both need the same guard against
running the ChromaDB half against a stub, so it lives here rather than being
duplicated in each file.
"""

from __future__ import annotations

import pytest


def require_real_chromadb():
    """Return the real ``chromadb`` module, or skip if only the stub is present.

    ``autobot-backend/conftest.py`` installs a MagicMock package stub for
    ``chromadb`` before collection (MVA-1119 — the real import hangs on hosts
    without a local Chroma server). Because the stub is already in
    ``sys.modules``, ``pytest.importorskip`` finds it and does NOT skip, so the
    whole ChromaDB parametrization used to run against a MagicMock: every
    attribute access returns a mock, ``count()`` answers 1, ``len()`` answers 0,
    ``set()`` answers empty and nothing ever raises — exactly the failure
    signature reported in #13239.

    Detection probes ``__file__`` through ``vars()`` rather than ``getattr()``.
    ``_make_pkg_stub`` builds a bare ``ModuleType`` and installs a PEP 562
    module-level ``__getattr__`` that answers *any* attribute with a MagicMock,
    dunders included — so ``getattr(stub, "__file__", None)`` is a MagicMock,
    never ``None``. ``__dict__`` is a getset descriptor resolved before
    ``__getattr__`` is consulted, so ``vars()`` is the one lookup the stub
    cannot intercept. Every real installed package carries a ``__file__``.

    Testing for the presence of ``__getattr__`` instead would be fragile: PEP 562
    module ``__getattr__`` is an ordinary feature (stdlib ``unittest`` defines
    one), so a future ChromaDB that adopts lazy imports would be skipped
    permanently and silently. Same discriminator as
    ``code_intelligence/conftest.py`` uses for #13233.
    """
    chromadb = pytest.importorskip("chromadb")
    if vars(chromadb).get("__file__") is None:
        pytest.skip(
            "chromadb is stubbed by autobot-backend/conftest.py (MVA-1119); "
            "restoring real ChromaDB contract coverage is tracked in #13242"
        )
    return chromadb
