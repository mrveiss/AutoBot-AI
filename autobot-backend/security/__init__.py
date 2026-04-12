# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security module for AutoBot
Provides service-to-service authentication and authorization
"""

from middleware.service_auth_enforcement import (
    get_endpoint_categories,
    get_enforcement_mode,
    log_enforcement_status,
)
from security.service_auth import ServiceAuthManager, validate_service_auth

__all__ = [
    "ServiceAuthManager",
    "validate_service_auth",
    "get_enforcement_mode",
    "log_enforcement_status",
    "get_endpoint_categories",
]
