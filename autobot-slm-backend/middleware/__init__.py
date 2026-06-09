# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SLM Backend Middleware Package

Contains reusable ASGI/Starlette middleware for the SLM backend.
"""

from middleware.security_headers import SecurityHeadersMiddleware

__all__ = ["SecurityHeadersMiddleware"]
