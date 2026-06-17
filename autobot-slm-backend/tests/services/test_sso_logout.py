# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
TDD tests for Task 3: provider end_session_endpoint templates + SAML SLO config.

Covers:
- get_provider_endpoint_template includes end_session_endpoint for Okta
- get_provider_endpoint_template includes end_session_endpoint for Microsoft Entra
- get_provider_endpoint_template has no end_session_endpoint for Google
  (Google uses /o/oauth2/revoke which is token-revocation, not RP-initiated OIDC logout)
- _get_saml_config includes single_logout_service in the SP endpoints
- initiate_saml_logout generates a redirect URL and stores relay state in Redis
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
SSOServiceError = _sso_mod.SSOServiceError

# Provider type constants (access via the MagicMock stub module)
_provider_types = sys.modules[_MODELS_SSO].SSOProviderType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_template(provider_value: str, domain: str = "dev.okta.com") -> dict:
    return SSOService.get_provider_endpoint_template(provider_value, domain=domain)


# ---------------------------------------------------------------------------
# Task 3a: end_session_endpoint in OIDC templates
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


# ---------------------------------------------------------------------------
# Task 3b: SAML SLO in _get_saml_config
# ---------------------------------------------------------------------------


class TestSamlSloConfig:
    def _make_provider(self, **config_overrides) -> MagicMock:
        provider = MagicMock()
        base_cfg = {
            "sp_entity_id": "https://slm.example.com/saml/metadata",
            "acs_url": "https://slm.example.com/api/auth/sso/saml/acs",
            "slo_url": "https://slm.example.com/api/auth/sso/saml/slo",
            "idp_metadata_url": "https://idp.example.com/metadata.xml",
        }
        base_cfg.update(config_overrides)
        provider.config = base_cfg
        return provider

    def test_saml_config_includes_single_logout_service(self):
        service = SSOService(session=MagicMock())
        provider = self._make_provider()
        config = service._get_saml_config(provider)
        sp_section = config["service"]["sp"]
        assert "single_logout_service" in sp_section["endpoints"]

    def test_saml_slo_endpoint_uses_provider_slo_url(self):
        service = SSOService(session=MagicMock())
        provider = self._make_provider(slo_url="https://slm.example.com/api/auth/sso/saml/slo")
        config = service._get_saml_config(provider)
        slo_entries = config["service"]["sp"]["endpoints"]["single_logout_service"]
        slo_urls = [entry[0] for entry in slo_entries]
        assert any("saml/slo" in url for url in slo_urls)


# ---------------------------------------------------------------------------
# Task 3c: initiate_saml_logout method exists and returns (url, relay_state)
# ---------------------------------------------------------------------------


class TestInitiateSamlLogout:
    def test_method_exists_on_sso_service(self):
        assert hasattr(SSOService, "initiate_saml_logout")

    @pytest.mark.asyncio
    async def test_returns_tuple_of_url_and_relay_state(self):
        """initiate_saml_logout must return a (redirect_url, relay_state) tuple."""
        service = SSOService(session=MagicMock())
        provider = MagicMock()
        provider.id = "test-provider-id"
        provider.config = {
            "sp_entity_id": "https://slm.example.com/saml",
            "acs_url": "https://slm.example.com/api/auth/sso/saml/acs",
            "slo_url": "https://slm.example.com/api/auth/sso/saml/slo",
            "idp_metadata_url": "https://idp.example.com/metadata.xml",
        }

        # Mock the Saml2Client so we don't need a real IdP
        mock_client = MagicMock()
        mock_client.global_logout.return_value = (
            "test-logout-request-id",
            {"headers": [("Location", "https://idp.example.com/slo")]},
        )

        redis_mock = AsyncMock()
        redis_mock.set = AsyncMock(return_value=True)

        with patch.object(_sso_mod, "get_redis_client", return_value=redis_mock):
            with patch.object(service, "_build_saml_client", return_value=mock_client):
                result = await service.initiate_saml_logout(provider)

        assert isinstance(result, tuple)
        assert len(result) == 2
        redirect_url, relay_state = result
        assert isinstance(redirect_url, str)
        assert isinstance(relay_state, str)
        assert len(relay_state) > 0
