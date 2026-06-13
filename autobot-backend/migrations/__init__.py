# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Alembic migration scripts and the baseline-adoption entrypoint (#10001).

This package marker exists so ``python -m migrations.baseline`` is runnable
from the backend root. Alembic itself loads env.py by path
(``script_location = migrations``) and is unaffected.
"""
