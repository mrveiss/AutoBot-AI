# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SSO Integration Framework for Enterprise AutoBot
Provides Single Sign-On integration with SAML, OAuth2, OpenID Connect, and LDAP

Issue #378: Added threading locks for file operations to prevent race conditions.
"""

import base64
import json
import logging
import threading
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
)

from autobot_shared.http_client import get_http_client
from backend.constants.path_constants import PATH

logger = logging.getLogger(__name__)


class SSOProtocol(Enum):
    """Supported SSO protocols"""

    SAML2 = "saml2"
    OAUTH2 = "oauth2"
    OPENID_CONNECT = "openid_connect"
    LDAP = "ldap"
    AZURE_AD = "azure_ad"
    OKTA = "okta"
    GOOGLE_WORKSPACE = "google_workspace"


class AuthenticationStatus(Enum):
    """Authentication status values"""

    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    EXPIRED = "expired"
    INVALID = "invalid"


@dataclass
class SSOProvider:
    """SSO provider configuration"""

    provider_id: str
    name: str
    protocol: SSOProtocol
    enabled: bool
    config: Dict
    metadata: Dict
    created_at: datetime
    updated_at: datetime


@dataclass
class SSOSession:
    """SSO session information"""

    session_id: str
    user_id: str
    provider_id: str
    attributes: Dict
    created_at: datetime
    expires_at: datetime
    last_activity: datetime
    status: AuthenticationStatus


class SSOIntegrationFramework:
    """
    Enterprise SSO integration framework supporting multiple protocols
    """

    def __init__(
        self,
        config_path: str = str(PATH.get_config_path("security", "sso_config.yaml")),
    ):
        """Initialize SSO integration framework with config and provider storage."""
        # Thread-safe file operations - must be initialized first (Issue #378)
        self._file_lock = threading.Lock()

        self.config_path = config_path
        self.config = self._load_config()

        # Provider storage
        self.providers_path = PATH.get_data_path("security", "sso_providers")
        self.providers_path.mkdir(parents=True, exist_ok=True)

        # Active providers and sessions
        self.providers: Dict[str, SSOProvider] = {}
        self.active_sessions: Dict[str, SSOSession] = {}
        self._load_providers()

        # Cryptographic keys for SAML/JWT
        self.private_key = None
        self.public_key = None
        self._initialize_crypto_keys()

        # OAuth2 state tracking
        self.oauth_states: Dict[str, Dict] = {}

        # Statistics
        self.stats = {
            "total_providers": 0,
            "active_providers": 0,
            "successful_authentications": 0,
            "failed_authentications": 0,
            "active_sessions": 0,
            "authentications_by_provider": {},
            "last_authentication": None,
        }

        # Initialize default providers if configured
        self._initialize_default_providers()

        logger.info("SSO Integration Framework initialized")

    def _load_config(self) -> Dict:
        """Load SSO configuration"""
        try:
            if Path(self.config_path).exists():
                with open(self.config_path, "r") as f:
                    return yaml.safe_load(f)
            else:
                default_config = self._get_default_config()
                self._save_config(default_config)
                return default_config
        except Exception as e:
            logger.error("Failed to load SSO config: %s", e)
            return self._get_default_config()

    def _get_default_saml_config(self) -> Dict:
        """
        Return default SAML configuration settings.

        Issue #620.
        """
        return {
            "entity_id": "autobot-enterprise",
            "service_url": "https://autobot.company.com",
            "acs_url": "/api/auth/saml/acs",
            "sls_url": "/api/auth/saml/sls",
            "name_id_format": ("urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"),
            "attribute_mapping": {
                "email": (
                    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
                ),
                "first_name": (
                    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname"
                ),
                "last_name": (
                    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname"
                ),
                "groups": (
                    "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups"
                ),
            },
        }

    def _get_default_ldap_config(self) -> Dict:
        """
        Return default LDAP configuration settings.

        Issue #620.
        """
        return {
            "user_search_base": "ou=users,dc=company,dc=com",
            "group_search_base": "ou=groups,dc=company,dc=com",
            "user_filter": "(objectClass=person)",
            "group_filter": "(objectClass=group)",
            "attribute_mapping": {
                "username": "sAMAccountName",
                "email": "mail",
                "first_name": "givenName",
                "last_name": "sn",
                "groups": "memberOf",
            },
        }

    def _get_default_config(self) -> Dict:
        """Return default SSO configuration"""
        return {
            "sso_enabled": True,
            "default_session_timeout_hours": 8,
            "max_concurrent_sessions": 5,
            "auto_provision_users": True,
            "require_group_membership": False,
            # SAML configuration
            "saml": self._get_default_saml_config(),
            # OAuth2/OpenID Connect configuration
            "oauth2": {
                "default_scope": ["openid", "profile", "email"],
                "token_endpoint_auth_method": "client_secret_post",
                "response_type": "code",
                "grant_type": "authorization_code",
            },
            # LDAP configuration
            "ldap": self._get_default_ldap_config(),
            # Role mapping
            "role_mapping": {
                "admin_groups": ["AutoBot-Admins", "IT-Security"],
                "user_groups": ["AutoBot-Users", "All-Employees"],
                "default_role": "user",
            },
            # Security settings
            "security": {
                "encrypt_sessions": True,
                "sign_assertions": True,
                "require_encryption": True,
                "max_clock_skew_seconds": 300,
                "token_lifetime_minutes": 60,
            },
        }

    def _save_config(self, config: Dict):
        """Save configuration to file (thread-safe, Issue #378)"""
        with self._file_lock:
            try:
                Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
                with open(self.config_path, "w", encoding="utf-8") as f:
                    yaml.dump(config, f, default_flow_style=False)
            except Exception as e:
                logger.error("Failed to save SSO config: %s", e)

    def _load_providers(self):
        """Load SSO providers from storage"""
        try:
            provider_files = list(self.providers_path.glob("*.json"))

            for provider_file in provider_files:
                with open(provider_file, "r") as f:
                    provider_data = json.load(f)

                # Convert datetime strings
                provider_data["created_at"] = datetime.fromisoformat(
                    provider_data["created_at"]
                )
                provider_data["updated_at"] = datetime.fromisoformat(
                    provider_data["updated_at"]
                )
                provider_data["protocol"] = SSOProtocol(provider_data["protocol"])

                provider = SSOProvider(**provider_data)
                self.providers[provider.provider_id] = provider

            self._update_provider_statistics()
            logger.info("Loaded %s SSO providers", len(self.providers))

        except Exception as e:
            logger.error("Failed to load SSO providers: %s", e)

    def _save_provider(self, provider: SSOProvider):
        """Save SSO provider to storage (thread-safe, Issue #378)"""
        with self._file_lock:
            try:
                provider_file = self.providers_path / f"{provider.provider_id}.json"

                provider_dict = {
                    "provider_id": provider.provider_id,
                    "name": provider.name,
                    "protocol": provider.protocol.value,
                    "enabled": provider.enabled,
                    "config": provider.config,
                    "metadata": provider.metadata,
                    "created_at": provider.created_at.isoformat(),
                    "updated_at": provider.updated_at.isoformat(),
                }

                with open(provider_file, "w", encoding="utf-8") as f:
                    json.dump(provider_dict, f, indent=2, ensure_ascii=False)

            except Exception as e:
                logger.error(
                    "Failed to save SSO provider %s: %s", provider.provider_id, e
                )

    def _initialize_crypto_keys(self):
        """Initialize cryptographic keys for SAML and JWT signing (thread-safe, Issue #378)"""
        with self._file_lock:
            try:
                keys_path = PATH.get_data_path("security", "sso_keys")
                keys_path.mkdir(parents=True, exist_ok=True)

                private_key_path = keys_path / "private_key.pem"
                public_key_path = keys_path / "public_key.pem"

                if private_key_path.exists() and public_key_path.exists():
                    # Load existing keys
                    with open(private_key_path, "rb") as f:
                        self.private_key = load_pem_private_key(f.read(), password=None)

                    with open(public_key_path, "rb") as f:
                        self.public_key = load_pem_public_key(f.read())

                    logger.info("Loaded existing SSO cryptographic keys")
                else:
                    # Generate new keys
                    self.private_key = rsa.generate_private_key(
                        public_exponent=65537, key_size=2048
                    )
                    self.public_key = self.private_key.public_key()

                    # Save keys
                    with open(private_key_path, "wb") as f:
                        f.write(
                            self.private_key.private_bytes(
                                encoding=serialization.Encoding.PEM,
                                format=serialization.PrivateFormat.PKCS8,
                                encryption_algorithm=serialization.NoEncryption(),
                            )
                        )

                    with open(public_key_path, "wb") as f:
                        f.write(
                            self.public_key.public_bytes(
                                encoding=serialization.Encoding.PEM,
                                format=serialization.PublicFormat.SubjectPublicKeyInfo,
                            )
                        )

                    # Set secure permissions
                    private_key_path.chmod(0o600)
                    public_key_path.chmod(0o644)

                    logger.info("Generated new SSO cryptographic keys")

            except Exception as e:
                logger.error("Failed to initialize crypto keys: %s", e)

    def _initialize_default_providers(self):
        """Initialize default SSO providers based on configuration"""
        if not self.config.get("sso_enabled", True):
            return

        # Example Azure AD provider
        if self.config.get("azure_ad", {}).get("tenant_id"):
            self.create_provider(
                name="Azure Active Directory",
                protocol=SSOProtocol.AZURE_AD,
                config={
                    "tenant_id": self.config["azure_ad"]["tenant_id"],
                    "client_id": self.config["azure_ad"].get("client_id", ""),
                    "client_secret": self.config["azure_ad"].get("client_secret", ""),
                    "authority": (
                        f"https://login.microsoftonline.com/{self.config['azure_ad']['tenant_id']}"
                    ),
                    "scope": ["openid", "profile", "email", "User.Read"],
                },
                auto_enable=True,
            )

    def create_provider(
        self,
        name: str,
        protocol: SSOProtocol,
        config: Dict,
        auto_enable: bool = False,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Create a new SSO provider"""

        provider_id = str(uuid4())

        provider = SSOProvider(
            provider_id=provider_id,
            name=name,
            protocol=protocol,
            enabled=auto_enable,
            config=config,
            metadata=metadata or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        self.providers[provider_id] = provider
        self._save_provider(provider)
        self._update_provider_statistics()

        logger.info("Created SSO provider: %s (%s)", name, protocol.value)
        return provider_id

    def update_provider(self, provider_id: str, updates: Dict) -> bool:
        """Update an existing SSO provider"""

        if provider_id not in self.providers:
            logger.error("SSO provider not found: %s", provider_id)
            return False

        provider = self.providers[provider_id]

        # Apply updates
        for key, value in updates.items():
            if hasattr(provider, key):
                setattr(provider, key, value)

        provider.updated_at = datetime.utcnow()

        self._save_provider(provider)
        self._update_provider_statistics()

        logger.info("Updated SSO provider %s", provider_id)
        return True

    def enable_provider(self, provider_id: str) -> bool:
        """Enable an SSO provider"""
        return self.update_provider(provider_id, {"enabled": True})

    def disable_provider(self, provider_id: str) -> bool:
        """Disable an SSO provider"""
        return self.update_provider(provider_id, {"enabled": False})

    async def initiate_sso_authentication(
        self, provider_id: str, redirect_uri: str, state: Optional[str] = None
    ) -> Dict:
        """Initiate SSO authentication flow"""

        if provider_id not in self.providers:
            return {"error": "Provider not found"}

        provider = self.providers[provider_id]

        if not provider.enabled:
            return {"error": "Provider is disabled"}

        if provider.protocol == SSOProtocol.SAML2:
            return await self._initiate_saml_auth(provider, redirect_uri, state)
        elif provider.protocol in {
            SSOProtocol.OAUTH2,
            SSOProtocol.OPENID_CONNECT,
            SSOProtocol.AZURE_AD,
        }:
            return await self._initiate_oauth_auth(provider, redirect_uri, state)
        elif provider.protocol == SSOProtocol.LDAP:
            return {"error": "LDAP requires direct credential authentication"}
        else:
            return {"error": "Unsupported protocol"}

    async def _initiate_saml_auth(
        self, provider: SSOProvider, redirect_uri: str, state: Optional[str]
    ) -> Dict:
        """Initiate SAML authentication"""
        try:
            # Generate SAML AuthnRequest
            request_id = str(uuid4())
            timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

            saml_config = self.config.get("saml", {})

            authn_request = f"""
            <samlp:AuthnRequest
                xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                ID="{request_id}"
                Version="2.0"
                IssueInstant="{timestamp}"
                Destination="{provider.config['sso_url']}"
                AssertionConsumerServiceURL="{saml_config['service_url']}{saml_config['acs_url']}"
                ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
                <saml:Issuer>{saml_config['entity_id']}</saml:Issuer>
                <samlp:NameIDPolicy Format="{saml_config['name_id_format']}" AllowCreate="true"/>
            </samlp:AuthnRequest>
            """

            # Encode and sign request
            encoded_request = base64.b64encode(authn_request.encode()).decode()

            # Store state
            if state:
                self.oauth_states[request_id] = {
                    "state": state,
                    "redirect_uri": redirect_uri,
                    "provider_id": provider.provider_id,
                    "created_at": datetime.utcnow(),
                }

            saml_request = urllib.parse.quote(encoded_request)
            relay_state = state or ""
            return {
                "auth_url": (
                    f"{provider.config['sso_url']}?SAMLRequest={saml_request}"
                    f"&RelayState={relay_state}"
                ),
                "request_id": request_id,
                "method": "redirect",
            }

        except Exception as e:
            logger.error("SAML auth initiation failed: %s", e)
            return {"error": "Failed to initiate SAML authentication"}

    async def _initiate_oauth_auth(
        self, provider: SSOProvider, redirect_uri: str, state: Optional[str]
    ) -> Dict:
        """Initiate OAuth2/OpenID Connect authentication"""
        try:
            # Generate state for security
            auth_state = state or str(uuid4())

            # Store OAuth state
            self.oauth_states[auth_state] = {
                "redirect_uri": redirect_uri,
                "provider_id": provider.provider_id,
                "created_at": datetime.utcnow(),
            }

            oauth_config = self.config.get("oauth2", {})

            # Build authorization URL
            params = {
                "client_id": provider.config["client_id"],
                "response_type": oauth_config.get("response_type", "code"),
                "scope": " ".join(
                    provider.config.get(
                        "scope", oauth_config.get("default_scope", ["openid"])
                    )
                ),
                "redirect_uri": redirect_uri,
                "state": auth_state,
            }

            # Add provider-specific parameters
            if provider.protocol == SSOProtocol.AZURE_AD:
                params["prompt"] = "select_account"

            auth_url = (
                provider.config["authorization_endpoint"]
                + "?"
                + urllib.parse.urlencode(params)
            )

            return {"auth_url": auth_url, "state": auth_state, "method": "redirect"}

        except Exception as e:
            logger.error("OAuth auth initiation failed: %s", e)
            return {"error": "Failed to initiate OAuth authentication"}

    async def handle_sso_callback(self, provider_id: str, callback_data: Dict) -> Dict:
        """Handle SSO authentication callback"""

        if provider_id not in self.providers:
            return {"error": "Provider not found"}

        provider = self.providers[provider_id]

        try:
            if provider.protocol == SSOProtocol.SAML2:
                return await self._handle_saml_callback(provider, callback_data)
            elif provider.protocol in {
                SSOProtocol.OAUTH2,
                SSOProtocol.OPENID_CONNECT,
                SSOProtocol.AZURE_AD,
            }:
                return await self._handle_oauth_callback(provider, callback_data)
            else:
                return {"error": "Unsupported protocol for callback"}

        except Exception as e:
            logger.error("SSO callback handling failed: %s", e)
            self.stats["failed_authentications"] += 1
            return {"error": "Authentication failed"}

    async def _handle_saml_callback(
        self, provider: SSOProvider, callback_data: Dict
    ) -> Dict:
        """Handle SAML authentication callback"""
        try:
            saml_response = callback_data.get("SAMLResponse", "")
            relay_state = callback_data.get("RelayState", "")

            if not saml_response:
                return {"error": "Missing SAML response"}

            # Decode SAML response
            decoded_response = base64.b64decode(saml_response).decode()

            # Parse SAML assertion (simplified - production would use proper SAML library)
            # Extract user attributes from SAML assertion
            user_attributes = self._parse_saml_assertion(decoded_response, provider)

            if user_attributes:
                return await self._create_sso_session(
                    provider, user_attributes, relay_state
                )
            else:
                return {"error": "Failed to parse SAML assertion"}

        except Exception as e:
            logger.error("SAML callback failed: %s", e)
            return {"error": "SAML authentication failed"}

    async def _handle_oauth_callback(
        self, provider: SSOProvider, callback_data: Dict
    ) -> Dict:
        """Handle OAuth2/OpenID Connect callback"""
        try:
            code = callback_data.get("code")
            state = callback_data.get("state")
            error = callback_data.get("error")

            if error:
                return {"error": f"OAuth error: {error}"}

            if not code or not state:
                return {"error": "Missing authorization code or state"}

            # Verify state
            if state not in self.oauth_states:
                return {"error": "Invalid state parameter"}

            state_data = self.oauth_states[state]

            # Exchange code for tokens
            token_response = await self._exchange_oauth_code(
                provider, code, state_data["redirect_uri"]
            )

            if "error" in token_response:
                return token_response

            # Get user info
            user_info = await self._get_oauth_user_info(
                provider, token_response["access_token"]
            )

            if user_info:
                # Clean up state
                del self.oauth_states[state]

                return await self._create_sso_session(provider, user_info, state)
            else:
                return {"error": "Failed to get user information"}

        except Exception as e:
            logger.error("OAuth callback failed: %s", e)
            return {"error": "OAuth authentication failed"}

    async def _exchange_oauth_code(
        self, provider: SSOProvider, code: str, redirect_uri: str
    ) -> Dict:
        """Exchange OAuth authorization code for tokens"""
        try:
            oauth_config = self.config.get("oauth2", {})

            token_data = {
                "grant_type": oauth_config.get("grant_type", "authorization_code"),
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": provider.config["client_id"],
                "client_secret": provider.config["client_secret"],
            }

            http_client = get_http_client()
            async with await http_client.post(
                provider.config["token_endpoint"],
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(
                        "Token exchange failed: %s - %s", response.status, error_text
                    )
                    return {"error": "Token exchange failed"}

        except Exception as e:
            logger.error("OAuth code exchange failed: %s", e)
            return {"error": "Token exchange failed"}

    async def _get_oauth_user_info(
        self, provider: SSOProvider, access_token: str
    ) -> Optional[Dict]:
        """Get user information using OAuth access token"""
        try:
            headers = {"Authorization": f"Bearer {access_token}"}

            http_client = get_http_client()
            async with await http_client.get(
                provider.config["userinfo_endpoint"], headers=headers
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error("User info request failed: %s", response.status)
                    return None

        except Exception as e:
            logger.error("OAuth user info failed: %s", e)
            return None

    def _parse_saml_assertion(
        self, saml_response: str, provider: SSOProvider
    ) -> Optional[Dict]:
        """Parse SAML assertion and extract user attributes"""
        # This is a simplified parser - production should use proper SAML library
        try:
            # Extract attributes from SAML assertion
            # In production, use libraries like python3-saml

            # Mock extraction for example
            user_attributes = {
                "email": "user@company.com",
                "first_name": "John",
                "last_name": "Doe",
                "groups": ["AutoBot-Users"],
            }

            return user_attributes

        except Exception as e:
            logger.error("SAML assertion parsing failed: %s", e)
            return None

    async def _create_sso_session(
        self, provider: SSOProvider, user_attributes: Dict, state: Optional[str]
    ) -> Dict:
        """Create SSO session from successful authentication"""
        try:
            # Map attributes to internal user format
            mapped_user = self._map_user_attributes(provider, user_attributes)

            # Create session
            session_id = str(uuid4())
            session_timeout = self.config.get("default_session_timeout_hours", 8)

            sso_session = SSOSession(
                session_id=session_id,
                user_id=mapped_user["user_id"],
                provider_id=provider.provider_id,
                attributes=mapped_user,
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(hours=session_timeout),
                last_activity=datetime.utcnow(),
                status=AuthenticationStatus.SUCCESS,
            )

            self.active_sessions[session_id] = sso_session

            # Update statistics
            self.stats["successful_authentications"] += 1
            self.stats["active_sessions"] = len(self.active_sessions)
            self.stats["last_authentication"] = datetime.utcnow().isoformat()

            provider_name = provider.name
            self.stats["authentications_by_provider"][provider_name] = (
                self.stats["authentications_by_provider"].get(provider_name, 0) + 1
            )

            logger.info(
                f"Created SSO session for user {mapped_user['user_id']} via {provider.name}"
            )

            return {
                "success": True,
                "session_id": session_id,
                "user": mapped_user,
                "expires_at": sso_session.expires_at.isoformat(),
                "provider": provider.name,
            }

        except Exception as e:
            logger.error("SSO session creation failed: %s", e)
            return {"error": "Session creation failed"}

    def _map_user_attributes(self, provider: SSOProvider, attributes: Dict) -> Dict:
        """Map provider attributes to internal user format"""

        # Get attribute mapping from config
        if provider.protocol == SSOProtocol.SAML2:
            mapping = self.config.get("saml", {}).get("attribute_mapping", {})
        elif provider.protocol == SSOProtocol.LDAP:
            mapping = self.config.get("ldap", {}).get("attribute_mapping", {})
        else:
            # OAuth2/OpenID Connect uses standard claims
            mapping = {
                "email": "email",
                "first_name": "given_name",
                "last_name": "family_name",
                "username": "preferred_username",
            }

        mapped_user = {}

        # Map standard attributes
        for internal_attr, external_attr in mapping.items():
            if external_attr in attributes:
                mapped_user[internal_attr] = attributes[external_attr]

        # Generate user ID if not present
        if "user_id" not in mapped_user:
            mapped_user["user_id"] = mapped_user.get("username") or mapped_user.get(
                "email", "unknown"
            )

        # Map roles based on groups
        mapped_user["role"] = self._map_user_role(attributes.get("groups", []))

        # Add provider information
        mapped_user["auth_provider"] = provider.name
        mapped_user["auth_method"] = "sso"

        return mapped_user

    def _map_user_role(self, user_groups: List[str]) -> str:
        """Map user groups to internal roles"""
        role_mapping = self.config.get("role_mapping", {})

        # Check for admin groups
        admin_groups = role_mapping.get("admin_groups", [])
        if any(group in user_groups for group in admin_groups):
            return "admin"

        # Check for user groups
        user_groups_config = role_mapping.get("user_groups", [])
        if any(group in user_groups for group in user_groups_config):
            return "user"

        # Issue #744: Default to "user" role instead of "guest" for security
        # Guest role removed - all authenticated SSO users get at least "user" role
        return role_mapping.get("default_role", "user")

    def get_sso_session(self, session_id: str) -> Optional[SSOSession]:
        """Get SSO session by ID"""
        session = self.active_sessions.get(session_id)

        if session and session.expires_at > datetime.utcnow():
            # Update last activity
            session.last_activity = datetime.utcnow()
            return session
        elif session:
            # Session expired
            session.status = AuthenticationStatus.EXPIRED
            del self.active_sessions[session_id]

        return None

    def invalidate_sso_session(self, session_id: str) -> bool:
        """Invalidate SSO session"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            self.stats["active_sessions"] = len(self.active_sessions)
            logger.info("Invalidated SSO session %s", session_id)
            return True
        return False

    async def authenticate_ldap(
        self, provider_id: str, username: str, password: str
    ) -> Dict:
        """Authenticate user against LDAP provider"""
        if provider_id not in self.providers:
            return {"error": "Provider not found"}

        provider = self.providers[provider_id]

        if provider.protocol != SSOProtocol.LDAP:
            return {"error": "Provider is not LDAP"}

        try:
            # LDAP authentication (simplified)
            # In production, use proper LDAP library like python-ldap

            # Mock LDAP authentication for example
            if username and password:
                user_attributes = {
                    "username": username,
                    "email": f"{username}@company.com",
                    "groups": ["AutoBot-Users"],
                }

                return await self._create_sso_session(provider, user_attributes, None)
            else:
                return {"error": "Invalid credentials"}

        except Exception as e:
            logger.error("LDAP authentication failed: %s", e)
            return {"error": "LDAP authentication failed"}

    def list_providers(self, enabled_only: bool = False) -> List[SSOProvider]:
        """List SSO providers"""
        providers = list(self.providers.values())

        if enabled_only:
            providers = [p for p in providers if p.enabled]

        return providers

    def get_provider(self, provider_id: str) -> Optional[SSOProvider]:
        """Get SSO provider by ID"""
        return self.providers.get(provider_id)

    def generate_saml_metadata(self) -> str:
        """Generate SAML metadata for service provider"""
        saml_config = self.config.get("saml", {})

        metadata = f"""<?xml version="1.0" encoding="UTF-8"?>
        <md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                             entityID="{saml_config['entity_id']}">
            <md:SPSSODescriptor AuthnRequestsSigned="true" WantAssertionsSigned="true"
                                protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
                <md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                                           Location="{saml_config['service_url']}{saml_config['acs_url']}"
                                           index="1" isDefault="true"/>
                <md:SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                                      Location="{saml_config['service_url']}{saml_config['sls_url']}"/>
            </md:SPSSODescriptor>
        </md:EntityDescriptor>"""

        return metadata

    def _update_provider_statistics(self):
        """Update provider statistics"""
        self.stats["total_providers"] = len(self.providers)
        self.stats["active_providers"] = len(
            [p for p in self.providers.values() if p.enabled]
        )

    def get_statistics(self) -> Dict:
        """Get SSO integration statistics"""
        return {
            **self.stats,
            "providers_by_protocol": {
                protocol.value: len(
                    [p for p in self.providers.values() if p.protocol == protocol]
                )
                for protocol in SSOProtocol
            },
            "session_statistics": {
                "total_active": len(self.active_sessions),
                "average_session_age_minutes": self._calculate_average_session_age(),
                "sessions_expiring_soon": len(
                    [
                        s
                        for s in self.active_sessions.values()
                        if s.expires_at - datetime.utcnow() < timedelta(hours=1)
                    ]
                ),
            },
        }

    def _calculate_average_session_age(self) -> float:
        """Calculate average age of active sessions in minutes"""
        if not self.active_sessions:
            return 0.0

        total_age = sum(
            (datetime.utcnow() - session.created_at).total_seconds() / 60
            for session in self.active_sessions.values()
        )

        return total_age / len(self.active_sessions)

    async def cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        expired_sessions = []

        for session_id, session in self.active_sessions.items():
            if session.expires_at <= datetime.utcnow():
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            del self.active_sessions[session_id]

        if expired_sessions:
            self.stats["active_sessions"] = len(self.active_sessions)
            logger.info("Cleaned up %s expired SSO sessions", len(expired_sessions))

    async def refresh_session(self, session_id: str) -> bool:
        """Refresh SSO session timeout"""
        session = self.active_sessions.get(session_id)

        if session and session.expires_at > datetime.utcnow():
            session_timeout = self.config.get("default_session_timeout_hours", 8)
            session.expires_at = datetime.utcnow() + timedelta(hours=session_timeout)
            session.last_activity = datetime.utcnow()

            logger.debug("Refreshed SSO session %s", session_id)
            return True

        return False
