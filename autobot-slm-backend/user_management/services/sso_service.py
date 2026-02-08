# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SSO Service

Handles SSO provider configuration and authentication flows.
Supports OAuth2 (Google, GitHub, Facebook), LDAP/AD, and SAML.
"""

import logging
import secrets
import uuid
from typing import Any, Optional

from sqlalchemy import select
from user_management.models.sso import SSOProvider, SSOProviderType, UserSSOLink
from user_management.models.user import User
from user_management.schemas.sso import SSOProviderCreate, SSOProviderUpdate
from user_management.services.base_service import BaseService

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

# Module-level OAuth2 state storage
_oauth_states: dict[str, uuid.UUID] = {}


class SSOServiceError(Exception):
    """Base exception for SSO service errors."""


class SSOProviderNotFoundError(SSOServiceError):
    """SSO provider not found."""


class SSOAuthenticationError(SSOServiceError):
    """SSO authentication failed."""


class SSOService(BaseService):
    """SSO provider management and authentication service."""

    async def create_provider(self, data: SSOProviderCreate) -> SSOProvider:
        """Create a new SSO provider."""
        provider = SSOProvider(
            provider_type=data.provider_type,
            name=data.name,
            config=data.config,
            org_id=data.org_id,
            is_active=data.is_active,
            is_social=data.is_social,
            allow_user_creation=data.allow_user_creation,
            default_role=data.default_role,
            group_mapping=data.group_mapping,
        )
        self.session.add(provider)
        await self.session.flush()
        logger.info(
            "Created SSO provider: %s (%s)", provider.name, provider.provider_type
        )
        return provider

    async def list_providers(
        self, org_id: Optional[uuid.UUID] = None, active_only: bool = False
    ) -> tuple[list[SSOProvider], int]:
        """List SSO providers with optional filtering."""
        query = select(SSOProvider)
        if org_id is not None:
            query = query.where(
                (SSOProvider.org_id == org_id) | (SSOProvider.org_id.is_(None))
            )
        if active_only:
            query = query.where(SSOProvider.is_active.is_(True))
        result = await self.session.execute(query)
        providers = list(result.scalars().all())
        return providers, len(providers)

    async def get_provider(self, provider_id: uuid.UUID) -> SSOProvider:
        """Get SSO provider by ID."""
        result = await self.session.execute(
            select(SSOProvider).where(SSOProvider.id == provider_id)
        )
        provider = result.scalar_one_or_none()
        if not provider:
            raise SSOProviderNotFoundError(f"SSO provider {provider_id} not found")
        return provider

    async def update_provider(
        self, provider_id: uuid.UUID, data: SSOProviderUpdate
    ) -> SSOProvider:
        """Update an existing SSO provider."""
        provider = await self.get_provider(provider_id)
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(provider, field, value)
        await self.session.flush()
        logger.info("Updated SSO provider: %s", provider_id)
        return provider

    async def delete_provider(self, provider_id: uuid.UUID) -> None:
        """Delete an SSO provider."""
        provider = await self.get_provider(provider_id)
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
        """Test LDAP/AD connection."""
        if Server is None:
            return {"success": False, "message": "ldap3 library not installed"}
        try:
            server_uri = provider.config.get("server_uri")
            bind_dn = provider.config.get("bind_dn")
            bind_password = provider.config.get("bind_password")
            server = Server(server_uri, get_info=ALL)
            conn = Connection(server, bind_dn, bind_password, auto_bind=True)
            conn.unbind()
            return {"success": True, "message": "LDAP connection successful"}
        except Exception as e:
            logger.error("LDAP connection test failed: %s", e)
            return {"success": False, "message": str(e)}

    def _generate_oauth_state(self, provider_id: uuid.UUID) -> str:
        """Generate OAuth2 state token and store provider mapping."""
        state = secrets.token_urlsafe(32)
        _oauth_states[state] = provider_id
        return state

    def _validate_oauth_state(self, state: str) -> uuid.UUID:
        """Validate OAuth2 state token and return provider ID."""
        provider_id = _oauth_states.pop(state, None)
        if not provider_id:
            raise SSOAuthenticationError("Invalid or expired OAuth state")
        return provider_id

    def _build_oauth_client(self, provider: SSOProvider) -> Any:
        """Build OAuth2 client from provider config."""
        if AsyncOAuth2Client is None:
            raise SSOServiceError("authlib library not installed")
        client_id = provider.config.get("client_id")
        client_secret = provider.config.get("client_secret")
        return AsyncOAuth2Client(
            client_id=client_id,
            client_secret=client_secret,
        )

    async def _get_oauth_authorize_url(
        self, provider: SSOProvider, callback_url: str
    ) -> tuple[str, str]:
        """Generate OAuth2 authorization URL."""
        client = self._build_oauth_client(provider)
        state = self._generate_oauth_state(provider.id)
        authorize_url = provider.config.get("authorize_url")
        scope = provider.config.get("scope", "openid email profile")
        url, _ = await client.create_authorization_url(
            authorize_url,
            redirect_uri=callback_url,
            scope=scope,
            state=state,
        )
        return url, state

    async def _exchange_oauth_code(
        self, provider: SSOProvider, code: str, callback_url: str
    ) -> dict[str, Any]:
        """Exchange OAuth2 authorization code for access token."""
        client = self._build_oauth_client(provider)
        token_url = provider.config.get("token_url")
        token = await client.fetch_token(
            token_url,
            code=code,
            redirect_uri=callback_url,
        )
        return token

    async def _get_oauth_userinfo(
        self, provider: SSOProvider, token: dict[str, Any]
    ) -> dict[str, Any]:
        """Fetch user info from OAuth2 provider."""
        client = self._build_oauth_client(provider)
        userinfo_url = provider.config.get("userinfo_url")
        client.token = token
        response = await client.get(userinfo_url)
        response.raise_for_status()
        return response.json()

    async def initiate_oauth_login(
        self, provider_id: uuid.UUID, callback_url: str
    ) -> tuple[str, str]:
        """Initiate OAuth2 login flow."""
        provider = await self.get_provider(provider_id)
        if not provider.is_active:
            raise SSOAuthenticationError(f"SSO provider {provider.name} is disabled")
        return await self._get_oauth_authorize_url(provider, callback_url)

    async def complete_oauth_login(
        self, provider_id: uuid.UUID, code: str, state: str, callback_url: str
    ) -> User:
        """Complete OAuth2 login flow and return authenticated user."""
        validated_provider_id = self._validate_oauth_state(state)
        if validated_provider_id != provider_id:
            raise SSOAuthenticationError("OAuth state mismatch")
        provider = await self.get_provider(provider_id)
        token = await self._exchange_oauth_code(provider, code, callback_url)
        userinfo = await self._get_oauth_userinfo(provider, token)
        external_id = userinfo.get("sub") or userinfo.get("id")
        user_data = self._extract_oauth_user_data(userinfo, provider)
        return await self._find_or_provision_user(provider, external_id, user_data)

    def _extract_oauth_user_data(
        self, userinfo: dict[str, Any], provider: SSOProvider
    ) -> dict[str, Any]:
        """Extract user data from OAuth2 userinfo."""
        email = userinfo.get("email")
        name = userinfo.get("name") or userinfo.get("display_name")
        username = (
            userinfo.get("preferred_username") or email.split("@")[0] if email else None
        )
        return {
            "email": email,
            "display_name": name,
            "username": username,
            "avatar_url": userinfo.get("picture"),
        }

    def _build_ldap_connection(
        self, provider: SSOProvider, username: str, password: str
    ) -> Any:
        """Create LDAP connection."""
        if Server is None:
            raise SSOServiceError("ldap3 library not installed")
        server_uri = provider.config.get("server_uri")
        use_ssl = provider.config.get("use_ssl", True)
        server = Server(server_uri, use_ssl=use_ssl, get_info=ALL)
        user_dn_template = provider.config.get(
            "user_dn_template", "uid={},ou=users,dc=example,dc=com"
        )
        user_dn = user_dn_template.format(username)
        return Connection(server, user_dn, password)

    def _search_ldap_user(
        self, conn: Any, provider: SSOProvider, username: str
    ) -> Optional[dict[str, Any]]:
        """Search for user in LDAP directory."""
        base_dn = provider.config.get("base_dn", "dc=example,dc=com")
        search_filter = provider.config.get("search_filter", "(uid={})").format(
            username
        )
        conn.search(base_dn, search_filter, search_scope=SUBTREE)
        if conn.entries:
            return conn.entries[0].entry_attributes_as_dict
        return None

    def _extract_ldap_user_data(
        self, entry: dict[str, Any], provider: SSOProvider
    ) -> dict[str, Any]:
        """Extract user data from LDAP entry."""
        attr_map = provider.config.get("attribute_mapping", {})
        email = entry.get(attr_map.get("email", "mail"), [None])[0]
        display_name = entry.get(attr_map.get("display_name", "displayName"), [None])[0]
        return {
            "email": email,
            "display_name": display_name,
            "username": entry.get(attr_map.get("username", "uid"), [None])[0],
        }

    async def authenticate_ldap(
        self, provider_id: uuid.UUID, username: str, password: str
    ) -> User:
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
        """Build pysaml2 config from provider settings."""
        return {
            "entityid": provider.config.get("sp_entity_id"),
            "service": {
                "sp": {
                    "endpoints": {
                        "assertion_consumer_service": [
                            (
                                provider.config.get("acs_url"),
                                "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
                            ),
                        ],
                    },
                },
            },
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

    def _generate_saml_authn_request(self, provider: SSOProvider) -> tuple[str, str]:
        """Generate SAML AuthnRequest."""
        client = self._build_saml_client(provider)
        relay_state = secrets.token_urlsafe(32)
        _oauth_states[relay_state] = provider.id
        request_id, info = client.prepare_for_authenticate()
        redirect_url = dict(info["headers"])["Location"]
        return redirect_url, relay_state

    def _extract_saml_user_data(
        self, authn_response: Any, provider: SSOProvider
    ) -> dict[str, Any]:
        """Extract user data from SAML assertion."""
        attrs = authn_response.ava
        attr_map = provider.config.get("attribute_mapping", {})
        email = attrs.get(attr_map.get("email", "email"), [None])[0]
        display_name = attrs.get(attr_map.get("display_name", "displayName"), [None])[0]
        username = attrs.get(attr_map.get("username", "uid"), [None])[0]
        return {"email": email, "display_name": display_name, "username": username}

    async def complete_saml_login(
        self, provider_id: uuid.UUID, saml_response: str
    ) -> User:
        """Complete SAML login flow."""
        provider = await self.get_provider(provider_id)
        if not provider.is_active:
            raise SSOAuthenticationError(f"SSO provider {provider.name} is disabled")
        client = self._build_saml_client(provider)
        authn_response = client.parse_authn_request_response(saml_response, "POST")
        external_id = authn_response.name_id
        user_data = self._extract_saml_user_data(authn_response, provider)
        return await self._find_or_provision_user(provider, external_id, user_data)

    async def _find_existing_sso_link(
        self, provider_id: uuid.UUID, external_id: str
    ) -> Optional[UserSSOLink]:
        """Find existing SSO link."""
        result = await self.session.execute(
            select(UserSSOLink).where(
                UserSSOLink.provider_id == provider_id,
                UserSSOLink.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def _find_user_by_email(self, email: str) -> Optional[User]:
        """Find user by email address."""
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def _create_sso_user(
        self, provider: SSOProvider, user_data: dict[str, Any]
    ) -> User:
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
        logger.info(
            "Created SSO link for user %s with provider %s", user.id, provider.id
        )
        return link

    async def _find_or_provision_user(
        self, provider: SSOProvider, external_id: str, user_data: dict[str, Any]
    ) -> User:
        """Find existing user or provision new one via JIT."""
        link = await self._find_existing_sso_link(provider.id, external_id)
        if link:
            link.record_login()
            await self.session.flush()
            result = await self.session.execute(
                select(User).where(User.id == link.user_id)
            )
            return result.scalar_one()
        if not provider.allow_user_creation:
            raise SSOAuthenticationError(
                "User not found and auto-provisioning is disabled"
            )
        email = user_data.get("email")
        if not email:
            raise SSOAuthenticationError("Email not provided by SSO provider")
        user = await self._find_user_by_email(email)
        if not user:
            user = await self._create_sso_user(provider, user_data)
        await self._create_sso_link(user, provider, external_id, user_data)
        return user
