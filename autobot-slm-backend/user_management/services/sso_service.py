# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SSO Service

Handles SSO provider configuration and authentication flows.
Supports OAuth2 (Google, GitHub, Facebook), LDAP/AD, and SAML.
"""

import base64
import hashlib
import json
import logging
import secrets
import uuid
from typing import Any

from sqlalchemy import select

from autobot_shared.redis_client import get_redis_client
from user_management.models.sso import SSOProvider, SSOProviderType, UserSSOLink
from user_management.models.user import User
from user_management.schemas.sso import SSOProviderCreate, SSOProviderUpdate
from user_management.services.base_service import BaseService
from user_management.services.sso_secrets import SSOSecretsManager

# Optional imports for SSO providers
try:
    from authlib.integrations.httpx_client import AsyncOAuth2Client
except ImportError:
    AsyncOAuth2Client = None  # type: ignore

try:
    from ldap3 import ALL, SUBTREE, Connection, Server
except ImportError:
    Server = Connection = ALL = SUBTREE = None  # type: ignore

try:
    from pysaml2.client import Saml2Client
    from pysaml2.config import Config as Saml2Config
except ImportError:
    Saml2Client = Saml2Config = None  # type: ignore

logger = logging.getLogger(__name__)

OAUTH_STATE_TTL_SECONDS = 600


def _pkce_challenge_s256(verifier: str) -> str:
    """Derive the RFC 7636 S256 code_challenge from a code_verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class SSOServiceError(Exception):
    """Base exception for SSO service errors."""


class SSOProviderNotFoundError(SSOServiceError):
    """SSO provider not found."""


class SSOAuthenticationError(SSOServiceError):
    """SSO authentication failed."""


class SSOService(BaseService):
    """SSO provider management and authentication service."""

    @staticmethod
    def get_provider_endpoint_template(provider_type: str, domain: str = "") -> dict[str, str]:
        """Return pre-filled OIDC endpoint config for known provider types."""
        templates = {
            SSOProviderType.OKTA.value: {
                "authorize_url": f"https://{domain}/oauth2/v1/authorize",
                "token_url": f"https://{domain}/oauth2/v1/token",
                "userinfo_url": f"https://{domain}/oauth2/v1/userinfo",
                "scope": "openid email profile groups",
                # OIDC RP-initiated logout (RFC 9207 / Okta docs)
                "end_session_endpoint": f"https://{domain}/oauth2/v1/logout",
            },
            SSOProviderType.MICROSOFT_ENTRA.value: {
                "authorize_url": f"https://login.microsoftonline.com/{domain}/oauth2/v2.0/authorize",
                "token_url": f"https://login.microsoftonline.com/{domain}/oauth2/v2.0/token",
                "userinfo_url": "https://graph.microsoft.com/oidc/userinfo",
                "scope": "openid email profile",
                # OIDC RP-initiated logout (Microsoft Identity Platform docs)
                "end_session_endpoint": f"https://login.microsoftonline.com/{domain}/oauth2/v2.0/logout",
            },
            SSOProviderType.GOOGLE_WORKSPACE.value: {
                "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_url": "https://oauth2.googleapis.com/token",  # nosec B105 - OAuth2 public token endpoint URL,
                "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
                "scope": "openid email profile",
                # Google does NOT support RP-initiated OIDC end_session (no end_session_endpoint
                # in their OIDC discovery doc).  The /o/oauth2/revoke endpoint revokes tokens
                # server-side but is not an OIDC logout redirect.  Callers should handle None.
                "end_session_endpoint": None,
            },
            SSOProviderType.GITHUB.value: {
                "authorize_url": "https://github.com/login/oauth/authorize",
                "token_url": "https://github.com/login/oauth/access_token",  # nosec B105 - OAuth2 public token endpoint
                "userinfo_url": "https://api.github.com/user",
                "scope": "user:email read:user",
                # GitHub OAuth2 (not OIDC) — no standard end_session_endpoint
                "end_session_endpoint": None,
            },
        }
        return templates.get(provider_type, {})

    async def create_provider(self, data: SSOProviderCreate) -> SSOProvider:
        """Create a new SSO provider with encrypted credential storage."""
        # Create provider with placeholder ID for secret key generation
        provider = SSOProvider(
            provider_type=data.provider_type,
            name=data.name,
            config={},  # Will be populated after secrets extraction
            org_id=data.org_id,
            is_active=data.is_active,
            is_social=data.is_social,
            allow_user_creation=data.allow_user_creation,
            default_role=data.default_role,
            group_mapping=data.group_mapping,
        )
        self.session.add(provider)
        await self.session.flush()

        # Store sensitive secrets separately and sanitize config
        secrets_mgr = SSOSecretsManager(self.session)
        provider.config = await secrets_mgr.store_secrets(provider.id, data.config)
        await self.session.flush()

        logger.info("Created SSO provider: %s (%s)", provider.name, provider.provider_type)
        return provider

    async def list_providers(
        self, org_id: uuid.UUID | None = None, active_only: bool = False
    ) -> tuple[list[SSOProvider], int]:
        """List SSO providers with optional filtering."""
        query = select(SSOProvider)
        if org_id is not None:
            query = query.where((SSOProvider.org_id == org_id) | (SSOProvider.org_id.is_(None)))
        if active_only:
            query = query.where(SSOProvider.is_active.is_(True))
        result = await self.session.execute(query)
        providers = list(result.scalars().all())
        return providers, len(providers)

    async def get_provider(self, provider_id: uuid.UUID) -> SSOProvider:
        """Get SSO provider by ID."""
        result = await self.session.execute(select(SSOProvider).where(SSOProvider.id == provider_id))
        provider = result.scalar_one_or_none()
        if not provider:
            raise SSOProviderNotFoundError(f"SSO provider {provider_id} not found")
        return provider

    async def update_provider(self, provider_id: uuid.UUID, data: SSOProviderUpdate) -> SSOProvider:
        """Update an existing SSO provider with secure credential handling."""
        provider = await self.get_provider(provider_id)
        update_data = data.model_dump(exclude_unset=True)

        # Handle config updates specially to extract/update secrets
        if "config" in update_data:
            secrets_mgr = SSOSecretsManager(self.session)
            # Update secrets and get sanitized config
            sanitized_config = await secrets_mgr.store_secrets(provider_id, update_data["config"])
            update_data["config"] = sanitized_config

        for field, value in update_data.items():
            setattr(provider, field, value)
        await self.session.flush()
        logger.info("Updated SSO provider: %s", provider_id)
        return provider

    async def delete_provider(self, provider_id: uuid.UUID) -> None:
        """Delete an SSO provider and its encrypted secrets."""
        provider = await self.get_provider(provider_id)

        # Delete associated secrets first
        secrets_mgr = SSOSecretsManager(self.session)
        await secrets_mgr.delete_secrets(provider_id)

        await self.session.delete(provider)
        await self.session.flush()
        logger.info("Deleted SSO provider: %s", provider_id)

    async def test_provider_connection(self, provider_id: uuid.UUID) -> dict[str, Any]:
        """Test SSO provider connection."""
        provider = await self.get_provider(provider_id)
        if provider.provider_type in (
            SSOProviderType.LDAP.value,
            SSOProviderType.ACTIVE_DIRECTORY.value,
        ):
            return await self._test_ldap_connection(provider)
        return {
            "success": True,
            "message": f"Test not implemented for {provider.provider_type}",
        }

    async def _test_ldap_connection(self, provider: SSOProvider) -> dict[str, Any]:
        """Test LDAP/AD connection with encrypted credentials."""
        if Server is None:
            return {"success": False, "message": "ldap3 library not installed"}
        try:
            server_uri = provider.config.get("server_uri")
            bind_dn = provider.config.get("bind_dn")

            # Retrieve bind_password from SystemSecret storage
            secrets_mgr = SSOSecretsManager(self.session)
            bind_password = await secrets_mgr.retrieve_secret(provider.id, "bind_password")

            if not bind_password:
                return {"success": False, "message": "LDAP bind_password not found"}

            server = Server(server_uri, get_info=ALL)
            conn = Connection(server, bind_dn, bind_password, auto_bind=True)
            conn.unbind()
            return {"success": True, "message": "LDAP connection successful"}
        except Exception as e:
            logger.error("LDAP connection test failed: %s", e)
            return {"success": False, "message": "LDAP connection test failed"}

    async def _generate_oauth_state(self, provider_id: uuid.UUID) -> tuple[str, str]:
        """Generate OAuth2 state + PKCE verifier; store both in Redis with TTL."""
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        redis = get_redis_client()
        if redis:
            payload = json.dumps({"provider_id": str(provider_id), "code_verifier": code_verifier})
            await redis.set(f"sso:state:{state}", payload, ex=OAUTH_STATE_TTL_SECONDS)
        return state, code_verifier

    async def _validate_oauth_state(self, state: str) -> tuple[uuid.UUID, str | None]:
        """Validate state via atomic GETDEL (single-use). Returns (provider_id, code_verifier)."""
        redis = get_redis_client()
        if not redis:
            raise SSOAuthenticationError("Redis unavailable for state validation")
        raw = await redis.getdel(f"sso:state:{state}")
        if not raw:
            raise SSOAuthenticationError("Invalid or expired OAuth state")
        try:
            data = json.loads(raw)
            return uuid.UUID(data["provider_id"]), data.get("code_verifier")
        except (json.JSONDecodeError, TypeError, KeyError):
            # Legacy plain-UUID state from a pre-PKCE in-flight login.
            try:
                return uuid.UUID(raw), None
            except ValueError as e:
                raise SSOAuthenticationError("Malformed OAuth state") from e

    async def _build_oauth_client(self, provider: SSOProvider) -> Any:
        """Build OAuth2 client from provider config with decrypted credentials."""
        if AsyncOAuth2Client is None:
            raise SSOServiceError("authlib library not installed")

        client_id = provider.config.get("client_id")

        # Retrieve client_secret from SystemSecret storage
        secrets_mgr = SSOSecretsManager(self.session)
        client_secret = await secrets_mgr.retrieve_secret(provider.id, "client_secret")

        if not client_secret:
            raise SSOServiceError(f"OAuth client_secret not found for provider {provider.id}")

        return AsyncOAuth2Client(
            client_id=client_id,
            client_secret=client_secret,
        )

    async def _get_oauth_authorize_url(self, provider: SSOProvider, callback_url: str) -> tuple[str, str]:
        """Generate OAuth2 authorization URL with PKCE (S256)."""
        client = await self._build_oauth_client(provider)
        state, code_verifier = await self._generate_oauth_state(provider.id)
        authorize_url = provider.config.get("authorize_url")
        scope = provider.config.get("scope", "openid email profile")
        url, _ = await client.create_authorization_url(
            authorize_url,
            redirect_uri=callback_url,
            scope=scope,
            state=state,
            code_challenge=_pkce_challenge_s256(code_verifier),
            code_challenge_method="S256",
        )
        return url, state

    async def _exchange_oauth_code(
        self, provider: SSOProvider, code: str, callback_url: str, code_verifier: str | None = None
    ) -> dict[str, Any]:
        """Exchange OAuth2 authorization code for access token (PKCE verifier when present)."""
        client = await self._build_oauth_client(provider)
        token_url = provider.config.get("token_url")
        kwargs: dict[str, Any] = {"code": code, "redirect_uri": callback_url}
        if code_verifier:
            kwargs["code_verifier"] = code_verifier
        return await client.fetch_token(token_url, **kwargs)

    async def _get_oauth_userinfo(self, provider: SSOProvider, token: dict[str, Any]) -> dict[str, Any]:
        """Fetch user info from OAuth2 provider."""
        client = await self._build_oauth_client(provider)
        userinfo_url = provider.config.get("userinfo_url")
        client.token = token
        response = await client.get(userinfo_url)
        response.raise_for_status()
        return response.json()

    async def initiate_oauth_login(self, provider_id: uuid.UUID, callback_url: str) -> tuple[str, str]:
        """Initiate OAuth2 login flow."""
        provider = await self.get_provider(provider_id)
        if not provider.is_active:
            raise SSOAuthenticationError(f"SSO provider {provider.name} is disabled")
        return await self._get_oauth_authorize_url(provider, callback_url)

    async def complete_oauth_login(
        self, code: str, state: str, callback_url: str, provider_id: uuid.UUID | None = None
    ) -> User:
        """Complete OAuth2 login flow and return authenticated user."""
        # Always validate state to prevent CSRF attacks
        state_provider_id, code_verifier = await self._validate_oauth_state(state)
        if provider_id is not None and provider_id != state_provider_id:
            raise SSOAuthenticationError("State/provider mismatch")
        provider_id = state_provider_id
        provider = await self.get_provider(provider_id)
        token = await self._exchange_oauth_code(provider, code, callback_url, code_verifier=code_verifier)
        userinfo = await self._get_oauth_userinfo(provider, token)
        external_id = userinfo.get("sub") or userinfo.get("id")
        user_data = self._extract_oauth_user_data(userinfo, provider)
        return await self._find_or_provision_user(provider, external_id, user_data)

    @staticmethod
    def _normalize_groups(raw: Any) -> list[str] | None:
        """Normalize an IdP groups claim to list[str] or None (absent).

        Returns None when the claim is absent so callers can distinguish
        "IdP did not assert groups" from "IdP asserted an empty group list".
        """
        if raw is None:
            return None
        if isinstance(raw, list):
            return [str(g) for g in raw]
        # Some IdPs return a single string when the user belongs to one group.
        return [str(raw)]

    def _extract_oauth_user_data(self, userinfo: dict[str, Any], provider: SSOProvider) -> dict[str, Any]:
        """Extract user data from OAuth2 userinfo."""
        email = userinfo.get("email")
        name = userinfo.get("name") or userinfo.get("display_name")
        username = userinfo.get("preferred_username") or email.split("@")[0] if email else None
        return {
            "email": email,
            "display_name": name,
            "username": username,
            "avatar_url": userinfo.get("picture"),
            "groups": self._normalize_groups(userinfo.get("groups")),
        }

    def _build_ldap_connection(self, provider: SSOProvider, username: str, password: str) -> Any:
        """Create LDAP connection."""
        from autobot_shared.security.input_sanitizer import sanitize_ldap_dn

        if Server is None:
            raise SSOServiceError("ldap3 library not installed")
        server_uri = provider.config.get("server_uri")
        use_ssl = provider.config.get("use_ssl", True)
        server = Server(server_uri, use_ssl=use_ssl, get_info=ALL)
        user_dn_template = provider.config.get("user_dn_template", "uid={},ou=users,dc=example,dc=com")
        safe_username = sanitize_ldap_dn(username)
        user_dn = user_dn_template.format(safe_username)
        return Connection(server, user_dn, password)

    def _search_ldap_user(self, conn: Any, provider: SSOProvider, username: str) -> dict[str, Any] | None:
        """Search for user in LDAP directory."""
        from autobot_shared.security.input_sanitizer import sanitize_ldap_filter

        base_dn = provider.config.get("base_dn", "dc=example,dc=com")
        safe_username = sanitize_ldap_filter(username)
        search_filter = provider.config.get("search_filter", "(uid={})").format(safe_username)
        conn.search(  # codeql[py/ldap-injection] safe_username is RFC-4515-escaped by sanitize_ldap_filter above
            base_dn, search_filter, search_scope=SUBTREE
        )
        if conn.entries:
            return conn.entries[0].entry_attributes_as_dict
        return None

    def _extract_ldap_user_data(self, entry: dict[str, Any], provider: SSOProvider) -> dict[str, Any]:
        """Extract user data from LDAP entry."""
        attr_map = provider.config.get("attribute_mapping", {})
        email = entry.get(attr_map.get("email", "mail"), [None])[0]
        display_name = entry.get(attr_map.get("display_name", "displayName"), [None])[0]
        groups_attr = attr_map.get("groups", "memberOf")
        raw_groups = entry.get(groups_attr)
        return {
            "email": email,
            "display_name": display_name,
            "username": entry.get(attr_map.get("username", "uid"), [None])[0],
            "groups": self._normalize_groups(raw_groups),
        }

    async def authenticate_ldap(self, provider_id: uuid.UUID, username: str, password: str) -> User:
        """Authenticate user via LDAP."""
        provider = await self.get_provider(provider_id)
        if not provider.is_active:
            raise SSOAuthenticationError(f"SSO provider {provider.name} is disabled")
        conn = self._build_ldap_connection(provider, username, password)
        if not conn.bind():
            raise SSOAuthenticationError("LDAP authentication failed")
        user_entry = self._search_ldap_user(conn, provider, username)
        conn.unbind()
        if not user_entry:
            raise SSOAuthenticationError("User not found in LDAP directory")
        user_data = self._extract_ldap_user_data(user_entry, provider)
        return await self._find_or_provision_user(provider, username, user_data)

    def _get_saml_config(self, provider: SSOProvider) -> dict[str, Any]:
        """Build pysaml2 config from provider settings.

        SAML SLO is not yet implemented — tracked in #10281.
        """
        _http_post = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        endpoints: dict[str, Any] = {
            "assertion_consumer_service": [
                (provider.config.get("acs_url"), _http_post),
            ],
        }
        return {
            "entityid": provider.config.get("sp_entity_id"),
            "service": {"sp": {"endpoints": endpoints}},
            "metadata": {"remote": [{"url": provider.config.get("idp_metadata_url")}]},
        }

    def _build_saml_client(self, provider: SSOProvider) -> Any:
        """Create SAML client."""
        if Saml2Client is None:
            raise SSOServiceError("pysaml2 library not installed")
        config_dict = self._get_saml_config(provider)
        saml_config = Saml2Config()
        saml_config.load(config_dict)
        return Saml2Client(config=saml_config)

    async def _generate_saml_authn_request(self, provider: SSOProvider) -> tuple[str, str]:
        """Generate SAML AuthnRequest; relay state stored in Redis with 10-min TTL."""
        client = self._build_saml_client(provider)
        relay_state = secrets.token_urlsafe(32)
        redis = get_redis_client()
        if redis:
            await redis.set(f"sso:state:{relay_state}", str(provider.id), ex=600)
        request_id, info = client.prepare_for_authenticate()
        redirect_url = dict(info["headers"])["Location"]
        return redirect_url, relay_state

    def _extract_saml_user_data(self, authn_response: Any, provider: SSOProvider) -> dict[str, Any]:
        """Extract user data from SAML assertion."""
        attrs = authn_response.ava
        attr_map = provider.config.get("attribute_mapping", {})
        email = attrs.get(attr_map.get("email", "email"), [None])[0]
        display_name = attrs.get(attr_map.get("display_name", "displayName"), [None])[0]
        username = attrs.get(attr_map.get("username", "uid"), [None])[0]
        raw_groups = attrs.get(attr_map.get("groups", "groups"))
        return {
            "email": email,
            "display_name": display_name,
            "username": username,
            "groups": self._normalize_groups(raw_groups),
        }

    async def complete_saml_login(self, provider_id: uuid.UUID, saml_response: str) -> User:
        """Complete SAML login flow."""
        provider = await self.get_provider(provider_id)
        if not provider.is_active:
            raise SSOAuthenticationError(f"SSO provider {provider.name} is disabled")
        client = self._build_saml_client(provider)
        authn_response = client.parse_authn_request_response(saml_response, "POST")
        external_id = authn_response.name_id
        user_data = self._extract_saml_user_data(authn_response, provider)
        return await self._find_or_provision_user(provider, external_id, user_data)

    async def _find_existing_sso_link(self, provider_id: uuid.UUID, external_id: str) -> UserSSOLink | None:
        """Find existing SSO link."""
        result = await self.session.execute(
            select(UserSSOLink).where(
                UserSSOLink.provider_id == provider_id,
                UserSSOLink.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def _find_user_by_email(self, email: str) -> User | None:
        """Find user by email address."""
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def _create_sso_user(self, provider: SSOProvider, user_data: dict[str, Any]) -> User:
        """Create new user from SSO authentication."""
        user = User(
            email=user_data["email"],
            username=user_data["username"],
            display_name=user_data.get("display_name"),
            avatar_url=user_data.get("avatar_url"),
            org_id=provider.org_id,
            is_active=True,
            is_verified=True,
            password_hash=None,
        )
        self.session.add(user)
        await self.session.flush()
        logger.info("Created SSO user: %s", user.email)
        return user

    async def _create_sso_link(
        self,
        user: User,
        provider: SSOProvider,
        external_id: str,
        metadata: dict[str, Any],
    ) -> UserSSOLink:
        """Create SSO link between user and provider."""
        link = UserSSOLink(
            user_id=user.id,
            provider_id=provider.id,
            external_id=external_id,
            external_email=metadata.get("email"),
            sso_metadata=metadata,
        )
        self.session.add(link)
        await self.session.flush()
        logger.info("Created SSO link for user %s with provider %s", user.id, provider.id)
        return link

    async def _find_or_provision_user(self, provider: SSOProvider, external_id: str, user_data: dict[str, Any]) -> User:
        """Find existing user or provision new one via JIT."""
        link = await self._find_existing_sso_link(provider.id, external_id)
        if link:
            link.record_login()
            await self.session.flush()
            result = await self.session.execute(select(User).where(User.id == link.user_id))
            return result.scalar_one()
        if not provider.allow_user_creation:
            raise SSOAuthenticationError("User not found and auto-provisioning is disabled")
        email = user_data.get("email")
        if not email:
            raise SSOAuthenticationError("Email not provided by SSO provider")
        user = await self._find_user_by_email(email)
        if not user:
            user = await self._create_sso_user(provider, user_data)
        await self._create_sso_link(user, provider, external_id, user_data)
        return user
