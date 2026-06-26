# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for SAML Single Logout (SLO) — issue #10281.

Covers:
- _get_saml_config includes single_logout_service endpoint when slo_url is set
- _get_saml_config omits single_logout_service when slo_url is absent
- complete_saml_login stores saml_name_id + saml_name_id_format in sso_metadata
- initiate_saml_logout returns None when no slo_url configured
- initiate_saml_logout delegates to Saml2Client.global_logout and returns redirect URL
- handle_saml_slo_callback raises SSOAuthenticationError on bad XML
- handle_saml_slo_callback validates issuer mismatch
- _validate_saml_issuer passes when issuer matches idp_entity_id
- _validate_saml_issuer raises when issuer differs
- _extract_redirect_url handles tuple (HTTP-Redirect) shape
- _extract_redirect_url handles dict (HTTP-POST / SOAP) shape
- _extract_redirect_url returns None for None input
- _build_sso_logout_url delegates to SAML SLO for SAML-linked users
- _build_sso_logout_url falls through to OIDC for non-SAML providers
"""

import importlib.util
import sys
import types
import uuid
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
# SSO model stubs (must be set before sso_service.py is loaded)
# ---------------------------------------------------------------------------
import enum  # noqa: E402

_MODELS_SSO = "user_management.models.sso"


class _SSOProviderType(str, enum.Enum):
    OKTA = "okta"
    MICROSOFT_ENTRA = "microsoft_entra"
    GOOGLE_WORKSPACE = "google_workspace"
    GITHUB = "github"
    SAML = "saml"


if _MODELS_SSO not in sys.modules:
    _sso_stub = MagicMock()
    _sso_stub.SSOProviderType = _SSOProviderType
    sys.modules[_MODELS_SSO] = _sso_stub

for _mod in [
    "user_management.services.sso_secrets",
    "user_management.models.role",
    "user_management.services.user_service",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_base_mod = types.ModuleType("user_management.services.base_service")


class _BaseService:
    def __init__(self, session):
        self.session = session


_base_mod.BaseService = _BaseService  # type: ignore[attr-defined]
sys.modules["user_management.services.base_service"] = _base_mod

# ---------------------------------------------------------------------------
# Load sso_service.py directly (bypass conftest stubs)
# ---------------------------------------------------------------------------
_SSO_PY = _BACKEND / "user_management" / "services" / "sso_service.py"
_spec = importlib.util.spec_from_file_location("_sso_slo_under_test", _SSO_PY)
_sso_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_sso_mod)  # type: ignore[union-attr]

SSOService = _sso_mod.SSOService
SSOAuthenticationError = _sso_mod.SSOAuthenticationError
SSOServiceError = _sso_mod.SSOServiceError
_extract_redirect_url = _sso_mod._extract_redirect_url
_validate_saml_issuer = _sso_mod._validate_saml_issuer

# ---------------------------------------------------------------------------
# Load api/auth.py helpers via exec (same pattern as test_auth_logout.py)
# ---------------------------------------------------------------------------
_AUTH_ROUTER_PY = _BACKEND / "api" / "auth.py"

# Ensure config stub is in place before exec
if "config" not in sys.modules:
    _cfg_stub = MagicMock()
    _cfg_stub.settings = MagicMock()
    _cfg_stub.settings.secret_key = "test-slo-secret-key-32characters"
    _cfg_stub.settings.trusted_proxies = []
    sys.modules["config"] = _cfg_stub

for _amod in [
    "models.schemas",
    "user_management",
    "user_management.models",
    "user_management.models.user",
    "user_management.services",
    "user_management.database",
    "services.jwks_verifier",
    "services.database",
    "autobot_shared.proxy_utils",
    "fastapi",
    "fastapi.security",
    "sqlalchemy",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.orm",
    "models",
    "models.database",
    "api.security",
]:
    if _amod not in sys.modules:
        sys.modules[_amod] = MagicMock()

# Provide real token_denylist
_DENYLIST_PY = _BACKEND / "services" / "token_denylist.py"
_dl_spec = importlib.util.spec_from_file_location("services.token_denylist", _DENYLIST_PY)
_dl_mod = importlib.util.module_from_spec(_dl_spec)  # type: ignore[arg-type]
_dl_spec.loader.exec_module(_dl_mod)  # type: ignore[union-attr]
sys.modules["services.token_denylist"] = _dl_mod  # type: ignore[assignment]

_AUTH_PY = _BACKEND / "services" / "auth.py"
_auth_spec = importlib.util.spec_from_file_location("services.auth", _AUTH_PY)
_auth_mod = importlib.util.module_from_spec(_auth_spec)  # type: ignore[arg-type]
_auth_spec.loader.exec_module(_auth_mod)  # type: ignore[union-attr]
sys.modules["services.auth"] = _auth_mod  # type: ignore[assignment]

_router_ns: dict = {
    "__name__": "api.auth_slo_test",
    "__file__": str(_AUTH_ROUTER_PY),
    "revoke_jti": _dl_mod.revoke_jti,
    "is_jti_revoked": _dl_mod.is_jti_revoked,
}
_router_src = _AUTH_ROUTER_PY.read_text(encoding="utf-8")
exec(compile(_router_src, str(_AUTH_ROUTER_PY), "exec"), _router_ns)  # nosec B102

_build_sso_logout_url = _router_ns["_build_sso_logout_url"]
_build_end_session_url = _router_ns["_build_end_session_url"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(session=None) -> SSOService:  # type: ignore[valid-type]
    return SSOService(session=session or MagicMock())


def _mock_saml_provider(
    *,
    slo_url: str | None = "https://idp.example.com/slo",
    acs_url: str = "https://sp.example.com/acs",
    sp_entity_id: str = "https://sp.example.com",
    idp_entity_id: str = "https://idp.example.com",
    idp_metadata_url: str = "https://idp.example.com/metadata",
) -> MagicMock:
    provider = MagicMock()
    provider.id = uuid.uuid4()
    provider.provider_type = "saml"
    provider.is_active = True
    provider.config = {
        "slo_url": slo_url,
        "acs_url": acs_url,
        "sp_entity_id": sp_entity_id,
        "idp_entity_id": idp_entity_id,
        "idp_metadata_url": idp_metadata_url,
    }
    return provider


# ---------------------------------------------------------------------------
# _extract_redirect_url — module-level helper
# ---------------------------------------------------------------------------


class TestExtractRedirectUrl:
    def test_returns_none_for_none_input(self):
        assert _extract_redirect_url(None) is None

    def test_tuple_http_redirect_binding(self):
        """pysaml2 HTTP-Redirect binding returns (status, reason, headers, body)."""
        result = ("302 Found", "Found", [("Location", "https://idp.example.com/slo?SAMLRequest=abc")], "")
        assert _extract_redirect_url(result) == "https://idp.example.com/slo?SAMLRequest=abc"

    def test_tuple_case_insensitive_location(self):
        result = ("200 OK", "OK", [("location", "https://idp.example.com/slo")], "")
        assert _extract_redirect_url(result) == "https://idp.example.com/slo"

    def test_dict_url_key(self):
        assert _extract_redirect_url({"url": "https://idp.example.com/slo"}) == "https://idp.example.com/slo"

    def test_dict_location_key(self):
        assert _extract_redirect_url({"Location": "https://idp.example.com/slo"}) == "https://idp.example.com/slo"

    def test_dict_no_url_returns_none(self):
        assert _extract_redirect_url({"data": "some-saml-xml"}) is None

    def test_short_tuple_returns_none(self):
        # Tuple with less than 3 elements should not crash
        assert _extract_redirect_url(("200 OK", "OK")) is None


# ---------------------------------------------------------------------------
# _validate_saml_issuer
# ---------------------------------------------------------------------------


class TestValidateSamlIssuer:
    def _make_parsed(self, issuer_text: str | None):
        parsed = MagicMock()
        if issuer_text is None:
            del parsed.message.issuer.text  # make attribute access raise AttributeError
            parsed.message.issuer.text = MagicMock(side_effect=AttributeError)
        else:
            parsed.message.issuer.text = issuer_text
        return parsed

    def test_matching_issuer_passes(self):
        provider = _mock_saml_provider(idp_entity_id="https://idp.example.com")
        parsed = MagicMock()
        parsed.message.issuer.text = "https://idp.example.com"
        # Should not raise
        _validate_saml_issuer(parsed, provider)

    def test_mismatched_issuer_raises(self):
        provider = _mock_saml_provider(idp_entity_id="https://trusted.idp.com")
        parsed = MagicMock()
        parsed.message.issuer.text = "https://evil.idp.com"
        with pytest.raises(SSOAuthenticationError, match="issuer mismatch"):
            _validate_saml_issuer(parsed, provider)

    def test_no_idp_entity_id_configured_skips_check(self):
        """If provider has no idp_entity_id configured, validation is skipped (not enforced)."""
        provider = _mock_saml_provider()
        provider.config.pop("idp_entity_id")
        parsed = MagicMock()
        parsed.message.issuer.text = "https://any.idp.com"
        # Should not raise
        _validate_saml_issuer(parsed, provider)


# ---------------------------------------------------------------------------
# _get_saml_config — SLO endpoint inclusion
# ---------------------------------------------------------------------------


class TestGetSamlConfigSlo:
    def test_includes_slo_endpoint_when_slo_url_set(self):
        provider = _mock_saml_provider(slo_url="https://idp.example.com/slo")
        svc = _make_service()
        config = svc._get_saml_config(provider)
        endpoints = config["service"]["sp"]["endpoints"]
        assert "single_logout_service" in endpoints
        slo_entries = endpoints["single_logout_service"]
        # Should include at least one entry with the slo_url
        urls = [entry[0] for entry in slo_entries]
        assert "https://idp.example.com/slo" in urls

    def test_omits_slo_endpoint_when_slo_url_absent(self):
        provider = _mock_saml_provider(slo_url=None)
        svc = _make_service()
        config = svc._get_saml_config(provider)
        endpoints = config["service"]["sp"]["endpoints"]
        assert "single_logout_service" not in endpoints

    def test_acs_endpoint_always_present(self):
        provider = _mock_saml_provider(acs_url="https://sp.example.com/acs")
        svc = _make_service()
        config = svc._get_saml_config(provider)
        endpoints = config["service"]["sp"]["endpoints"]
        assert "assertion_consumer_service" in endpoints


# ---------------------------------------------------------------------------
# initiate_saml_logout
# ---------------------------------------------------------------------------


class TestInitiateSamlLogout:
    def test_returns_none_when_no_slo_url(self):
        provider = _mock_saml_provider(slo_url=None)
        svc = _make_service()
        result = svc.initiate_saml_logout(provider, MagicMock())
        assert result is None

    def test_returns_none_when_pysaml2_unavailable(self):
        provider = _mock_saml_provider()
        svc = _make_service()
        with patch.object(_sso_mod, "Saml2Client", None):
            result = svc.initiate_saml_logout(provider, MagicMock())
        assert result is None

    def test_delegates_to_global_logout_and_extracts_url(self):
        """global_logout returns a tuple; initiate_saml_logout must extract the Location header."""
        provider = _mock_saml_provider()
        svc = _make_service()
        fake_name_id = MagicMock()
        fake_result = (
            "302 Found",
            "Found",
            [("Location", "https://idp.example.com/slo?SAMLRequest=encodedrequest")],
            "",
        )
        mock_client = MagicMock()
        mock_client.global_logout.return_value = fake_result

        # Patch Saml2Client to a non-None sentinel so the availability guard passes.
        with (
            patch.object(_sso_mod, "Saml2Client", MagicMock()),
            patch.object(svc, "_build_saml_client", return_value=mock_client),
        ):
            result = svc.initiate_saml_logout(provider, fake_name_id)

        mock_client.global_logout.assert_called_once_with(fake_name_id)
        assert result == "https://idp.example.com/slo?SAMLRequest=encodedrequest"

    def test_returns_none_when_global_logout_raises(self):
        """If pysaml2 raises (e.g. no metadata), we log and return None gracefully."""
        provider = _mock_saml_provider()
        svc = _make_service()
        mock_client = MagicMock()
        mock_client.global_logout.side_effect = Exception("metadata unavailable")

        with patch.object(svc, "_build_saml_client", return_value=mock_client):
            result = svc.initiate_saml_logout(provider, MagicMock())

        assert result is None


# ---------------------------------------------------------------------------
# handle_saml_slo_callback
# ---------------------------------------------------------------------------


class TestHandleSamlSloCallback:
    def test_raises_when_pysaml2_unavailable(self):
        provider = _mock_saml_provider()
        svc = _make_service()
        with patch.object(_sso_mod, "Saml2Client", None):
            with pytest.raises(SSOServiceError, match="pysaml2"):
                svc.handle_saml_slo_callback(provider, "<saml/>", "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST")

    def test_raises_sso_auth_error_on_bad_xml(self):
        """Unparseable XML must raise SSOAuthenticationError (not a raw exception)."""
        provider = _mock_saml_provider()
        svc = _make_service()
        mock_client = MagicMock()
        mock_client.parse_logout_request.side_effect = Exception("bad xml")

        with (
            patch.object(_sso_mod, "Saml2Client", MagicMock()),
            patch.object(svc, "_build_saml_client", return_value=mock_client),
        ):
            with pytest.raises(SSOAuthenticationError, match="Invalid SAML LogoutRequest"):
                svc.handle_saml_slo_callback(provider, "<bad/>", "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST")

    def test_validates_issuer_and_raises_on_mismatch(self):
        provider = _mock_saml_provider(idp_entity_id="https://trusted.idp.com")
        svc = _make_service()
        mock_client = MagicMock()
        parsed = MagicMock()
        parsed.message.issuer.text = "https://evil.idp.com"
        mock_client.parse_logout_request.return_value = parsed

        with (
            patch.object(_sso_mod, "Saml2Client", MagicMock()),
            patch.object(svc, "_build_saml_client", return_value=mock_client),
        ):
            with pytest.raises(SSOAuthenticationError, match="issuer mismatch"):
                svc.handle_saml_slo_callback(provider, "<xml/>", "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST")

    def test_success_returns_redirect_url(self):
        """Valid LogoutRequest → success=True + redirect URL from handle_logout_request."""
        provider = _mock_saml_provider(idp_entity_id="https://idp.example.com")
        svc = _make_service()
        mock_client = MagicMock()
        parsed = MagicMock()
        parsed.message.issuer.text = "https://idp.example.com"
        parsed.message.name_id = MagicMock()
        mock_client.parse_logout_request.return_value = parsed
        mock_client.handle_logout_request.return_value = (
            "302 Found",
            "Found",
            [("Location", "https://idp.example.com/slo?SAMLResponse=encoded")],
            "",
        )

        with (
            patch.object(_sso_mod, "Saml2Client", MagicMock()),
            patch.object(svc, "_build_saml_client", return_value=mock_client),
        ):
            success, url = svc.handle_saml_slo_callback(
                provider, "<xml/>", "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
            )

        assert success is True
        assert url == "https://idp.example.com/slo?SAMLResponse=encoded"

    def test_success_true_even_when_handle_logout_raises(self):
        """handle_logout_request failure is non-fatal: SLO succeeds locally, no redirect URL."""
        provider = _mock_saml_provider(idp_entity_id="https://idp.example.com")
        svc = _make_service()
        mock_client = MagicMock()
        parsed = MagicMock()
        parsed.message.issuer.text = "https://idp.example.com"
        parsed.message.name_id = MagicMock()
        mock_client.parse_logout_request.return_value = parsed
        mock_client.handle_logout_request.side_effect = Exception("response build failed")

        with (
            patch.object(_sso_mod, "Saml2Client", MagicMock()),
            patch.object(svc, "_build_saml_client", return_value=mock_client),
        ):
            success, url = svc.handle_saml_slo_callback(
                provider, "<xml/>", "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
            )

        assert success is True
        assert url is None


# ---------------------------------------------------------------------------
# complete_saml_login — NameID persistence in sso_metadata (#10281)
# ---------------------------------------------------------------------------


class TestCompleteSamlLoginNameIdPersistence:
    @pytest.mark.asyncio
    async def test_name_id_stored_in_metadata(self):
        """complete_saml_login must write saml_name_id to user_data passed to _find_or_provision_user."""
        provider = _mock_saml_provider()
        provider.is_active = True
        svc = _make_service()

        # Build a realistic mock authn_response.
        # NOTE: MagicMock.assertion is a reserved attribute for assert helpers;
        # use a plain object to carry .assertion without triggering the guard.
        name_id_obj = MagicMock()
        name_id_obj.text = "uid=alice,dc=example,dc=com"
        name_id_obj.format = "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"

        class _FakeAuthnResponse:
            name_id = "uid=alice,dc=example,dc=com"
            ava = {
                "email": ["alice@example.com"],
                "displayName": ["Alice Example"],
                "uid": ["alice"],
            }

            class assertion:  # noqa: N801 — plain namespace
                class subject:
                    name_id = name_id_obj  # type: ignore[assignment]

        authn_response = _FakeAuthnResponse()
        mock_client = MagicMock()
        mock_client.parse_authn_request_response.return_value = authn_response
        fake_user = MagicMock()

        captured_user_data: dict = {}

        async def _fake_provision(p, ext_id, user_data):
            captured_user_data.update(user_data)
            return fake_user

        with (
            patch.object(svc, "get_provider", new=AsyncMock(return_value=provider)),
            patch.object(svc, "_build_saml_client", return_value=mock_client),
            patch.object(svc, "_find_or_provision_user", side_effect=_fake_provision),
        ):
            user, pid = await svc.complete_saml_login(provider.id, "base64encodedSAMLResponse")

        assert user is fake_user
        assert "saml_name_id" in captured_user_data, "saml_name_id must be in user_data for SLO"
        assert captured_user_data["saml_name_id"] == "uid=alice,dc=example,dc=com"
        assert "saml_name_id_format" in captured_user_data


# ---------------------------------------------------------------------------
# _build_sso_logout_url — branching in auth.py
# ---------------------------------------------------------------------------


class TestBuildSsoLogoutUrl:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_link(self):
        result = await _build_sso_logout_url(None, MagicMock(), "testuser")
        assert result is None

    @pytest.mark.asyncio
    async def test_oidc_link_returns_end_session_url(self):
        """For OIDC providers (okta, entra, etc.) the existing OIDC logout path is used."""
        link = MagicMock()
        link.provider.provider_type = "okta"
        link.provider.config = {"end_session_endpoint": "https://okta.example.com/logout"}
        link.sso_metadata = {}
        result = await _build_sso_logout_url(link, MagicMock(), "testuser")
        assert result == "https://okta.example.com/logout"

    @pytest.mark.asyncio
    async def test_saml_link_calls_initiate_saml_slo(self):
        """For SAML providers the SLO path is taken, delegating to _initiate_saml_slo."""
        link = MagicMock()
        link.provider.provider_type = "saml"
        expected_url = "https://idp.example.com/slo?SAMLRequest=abc"

        with patch.dict(_router_ns, {"_initiate_saml_slo": AsyncMock(return_value=expected_url)}):
            result = await _build_sso_logout_url(link, MagicMock(), "saml_user")

        assert result == expected_url
