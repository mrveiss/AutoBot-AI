# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SLM Backend Middleware Package

Contains reusable ASGI/Starlette middleware for the SLM backend.
"""

# Issue #10778: HTTP API request counter middleware
from middleware.api_request_counter import ApiRequestCounterMiddleware
from middleware.security_headers import SecurityHeadersMiddleware

__all__ = ["SecurityHeadersMiddleware", "ApiRequestCounterMiddleware"]
