# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Waiver fixture: explicitly waived ad-hoc engine construction."""

from sqlalchemy import create_engine

engine = create_engine("sqlite://")  # canonical: ignore py-adhoc-db-engine
