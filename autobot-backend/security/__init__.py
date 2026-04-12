# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security module for AutoBot
Provides service-to-service authentication and authorization
"""

from security.service_auth import ServiceAuthManager, validate_service_auth

__all__ = ["ServiceAuthManager", "validate_service_auth"]
