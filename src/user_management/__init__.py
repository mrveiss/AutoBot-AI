# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
User Management System for AutoBot

This module provides enterprise-grade user management with:
- Multi-tenancy support (single_user, single_company, multi_company, provider modes)
- Team/collaboration management
- SSO/OAuth integration (LDAP, AD, OAuth2, SAML)
- 2FA/MFA support
- API key management
- PostgreSQL storage with SQLAlchemy async
"""

from src.user_management.config import DeploymentMode, get_deployment_config

__all__ = ["DeploymentMode", "get_deployment_config"]
