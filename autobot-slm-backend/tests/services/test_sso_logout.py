# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for provider end_session_endpoint templates (OIDC RP-initiated logout).

Covers:
- get_provider_endpoint_template includes end_session_endpoint for Okta
- get_provider_endpoint_template includes end_session_endpoint for Microsoft Entra
- get_provider_endpoint_template has no end_session_endpoint for Google
  (Google uses /o/oauth2/revoke which is token-revocation, not RP-initiated OIDC logout)

SAML SLO is not yet implemented — tracked in #10281.
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).parent.parent.parent
_ROOT = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# Stubs — mirror the pattern from test_sso_service.py, with a real
# SSOProviderType enum so dict lookups resolve correctly.
# ---------------------------------------------------------------------------
import enum  # noqa: E402

_MODELS_SSO = "user_management.models.sso"


class _SSOProviderType(str, enum.Enum):
    """Minimal replica matching the real SSOProviderType string values."""

    OKTA = "okta"
    MICROSOFT_ENTRA = "microsoft_entra"
    GOOGLE_WORKSPACE = "google_workspace"
    GITHUB = "github"
    SAML = "saml"


_sso_models_stub = MagicMock()
_sso_models_stub.SSOProviderType = _SSOProviderType
sys.modules[_MODELS_SSO] = _sso_models_stub

_SSO_SECRETS = "user_management.services.sso_secrets"
if _SSO_SECRETS not in sys.modules:
    sys.modules[_SSO_SECRETS] = MagicMock()

# sso_service.py imports Role from user_management.models.role; stub it.
if "user_management.models.role" not in sys.modules:
    sys.modules["user_management.models.role"] = MagicMock()

# sso_service.py lazy-imports UserService; pre-populate stub.
if "user_management.services.user_service" not in sys.modules:
    sys.modules["user_management.services.user_service"] = MagicMock()

_base_mod = types.ModuleType("user_management.services.base_service")


class _BaseService:
    def __init__(self, session):
        self.session = session


_base_mod.BaseService = _BaseService  # type: ignore[attr-defined]
sys.modules["user_management.services.base_service"] = _base_mod

# ---------------------------------------------------------------------------
# Load sso_service.py directly (same technique as test_sso_service.py)
# ---------------------------------------------------------------------------
_SSO_PY = _BACKEND / "user_management" / "services" / "sso_service.py"
_spec = importlib.util.spec_from_file_location("_sso_service_under_test", _SSO_PY)
_sso_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_sso_mod)  # type: ignore[union-attr]

SSOService = _sso_mod.SSOService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_template(provider_value: str, domain: str = "dev.okta.com") -> dict:
    return SSOService.get_provider_endpoint_template(provider_value, domain=domain)


# ---------------------------------------------------------------------------
# end_session_endpoint in OIDC templates
# ---------------------------------------------------------------------------


class TestOktaEndSessionEndpoint:
    def test_okta_template_has_end_session_endpoint(self):
        template = _get_template("okta", domain="example.okta.com")
        assert "end_session_endpoint" in template

    def test_okta_end_session_uses_domain(self):
        template = _get_template("okta", domain="example.okta.com")
        assert "example.okta.com" in template["end_session_endpoint"]
        assert "/oauth2/v1/logout" in template["end_session_endpoint"]


class TestMicrosoftEntraEndSessionEndpoint:
    def test_entra_template_has_end_session_endpoint(self):
        template = _get_template("microsoft_entra", domain="common")
        assert "end_session_endpoint" in template

    def test_entra_end_session_uses_common_tenant(self):
        template = _get_template("microsoft_entra", domain="common")
        url = template["end_session_endpoint"]
        assert "login.microsoftonline.com" in url
        assert "common" in url
        assert "oauth2/v2.0/logout" in url

    def test_entra_end_session_uses_custom_tenant(self):
        template = _get_template("microsoft_entra", domain="mytenant")
        url = template["end_session_endpoint"]
        assert "mytenant" in url


class TestGoogleWorkspaceEndSessionEndpoint:
    def test_google_end_session_endpoint_is_null(self):
        """Google does not support RP-initiated OIDC end_session; must be None or absent."""
        template = _get_template("google_workspace")
        # Acceptable: key absent OR value is None
        endpoint = template.get("end_session_endpoint")
        assert endpoint is None
