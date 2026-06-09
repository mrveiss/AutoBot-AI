# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Security module for AutoBot
Provides service-to-service authentication and authorization
"""

from security.service_auth import ServiceAuthManager, validate_service_auth

__all__ = ["ServiceAuthManager", "validate_service_auth"]
