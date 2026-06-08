# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Minimal conftest for the llc.adapters subpackage tests.

This conftest lives here (not in llc/tests/) so pytest can collect adapter
tests without loading llc/__init__.py's full API router import chain.
The adapter package has no dependency on the FastAPI app or database layer.
"""
