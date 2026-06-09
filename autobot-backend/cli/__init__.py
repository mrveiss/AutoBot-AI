# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AutoBot CLI sub-package.

Issue #7371: repair actions extracted from the boot path live here so they
run explicitly (``autobot doctor``) rather than on every uvicorn worker fork.
"""
