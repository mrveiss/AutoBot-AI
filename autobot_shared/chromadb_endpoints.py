# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ChromaDB server HTTP paths — the one home (#19413).

The pinned server is chromadb 1.x (``chromadb>=1.5.9,<2.0.0``; compose pins
``chromadb/chroma:1.5.9``). 1.x serves the heartbeat only under ``/api/v2``;
the v1 heartbeat answers 410 "The v1 API is deprecated" and ``/health`` is 404.

Python probes import :data:`CHROMADB_HEARTBEAT_PATH`. Files that cannot import Python
(shell, ansible, compose, manifests) keep a copy that
``repo_tests/chromadb_heartbeat_one_home_19413_test.py`` pins to this value.
"""

#: Liveness probe path on a ChromaDB 1.x server; the body carries ``"nanosecond heartbeat"``.
CHROMADB_HEARTBEAT_PATH = "/api/v2/heartbeat"
