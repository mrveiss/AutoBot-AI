# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security module for AutoBot
Provides service-to-service authentication and authorization
"""

from backend.security.service_auth import ServiceAuthManager, validate_service_auth
from src.constants.network_constants import NetworkConstants

__all__ = ["ServiceAuthManager", "validate_service_auth"]
