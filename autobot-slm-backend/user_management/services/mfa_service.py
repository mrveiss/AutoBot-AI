# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
MFA Service

Handles Multi-Factor Authentication (TOTP) setup, verification, and management.
"""

import json
import logging
import secrets
import uuid
from typing import Optional

from passlib.context import CryptContext
from passlib.hash import bcrypt as bcrypt_hash
from services.encryption import decrypt_data, encrypt_data
from sqlalchemy import select
from user_management.models.mfa import UserMFA
from user_management.models.user import User
from user_management.services.base_service import BaseService

try:
    import pyotp

    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class MFAServiceError(Exception):
    """Base exception for MFA service errors."""


class MFANotEnabledError(MFAServiceError):
    """Raised when MFA operation requires MFA to be enabled."""


class InvalidTOTPError(MFAServiceError):
    """Raised when TOTP code is invalid."""


class MFAService(BaseService):
    """Service for managing Multi-Factor Authentication."""

    async def setup_totp(self, user_id: uuid.UUID) -> dict:
        """Set up TOTP-based MFA for a user."""
        if not PYOTP_AVAILABLE:
            raise MFAServiceError("pyotp library not installed")

        user = await self._get_user_by_id(user_id)
        if not user:
            raise MFAServiceError("User not found")

        await self._check_no_existing_mfa(user_id)

        secret = pyotp.random_base32()
        otpauth_uri = self._build_otpauth_uri(secret, user.username)
        backup_codes = self._generate_backup_codes()

        encrypted_secret = encrypt_data(secret)
        encrypted_codes = self._encrypt_backup_codes(backup_codes)

        mfa_record = self._create_mfa_record(user_id, encrypted_secret, encrypted_codes)
        self.session.add(mfa_record)
        await self.session.flush()

        return {
            "secret": secret,
            "otpauth_uri": otpauth_uri,
            "backup_codes": backup_codes,
        }

    async def verify_setup(self, user_id: uuid.UUID, code: str) -> bool:
        """Verify MFA setup with initial TOTP code."""
        mfa = await self._get_unverified_mfa(user_id)
        if not mfa:
            raise MFAServiceError("No pending MFA setup found")

        secret = decrypt_data(mfa.secret_encrypted)
        if not self._verify_totp_code(secret, code):
            raise InvalidTOTPError("Invalid TOTP code")

        await self._mark_mfa_verified(mfa, user_id)
        return True

    async def verify_login(self, user_id: uuid.UUID, code: str) -> bool:
        """Verify MFA code during login (TOTP or backup code)."""
        mfa = await self._get_verified_mfa(user_id)
        if not mfa:
            raise MFANotEnabledError("MFA not enabled for this user")

        if self._verify_totp(mfa, code):
            mfa.record_verification()
            await self.session.flush()
            return True

        if self._verify_backup_code(mfa, code):
            mfa.record_verification()
            await self.session.flush()
            return True

        return False

    async def disable(self, user_id: uuid.UUID, password: str) -> bool:
        """Disable MFA for a user (requires password verification)."""
        user = await self._get_user_by_id(user_id)
        if not user:
            raise MFAServiceError("User not found")

        if not pwd_context.verify(password, user.password_hash):
            raise MFAServiceError("Invalid password")

        await self._delete_mfa_record(user_id)
        user.mfa_enabled = False
        await self.session.flush()
        return True

    async def get_status(self, user_id: uuid.UUID) -> dict:
        """Get MFA status for a user."""
        query = select(UserMFA).where(UserMFA.user_id == user_id)
        result = await self.session.execute(query)
        mfa = result.scalar_one_or_none()

        if not mfa or not mfa.is_verified:
            return self._default_status()

        return self._build_status(mfa)

    async def regenerate_backup_codes(self, user_id: uuid.UUID, password: str) -> list:
        """Regenerate backup codes (requires password)."""
        user = await self._get_user_by_id(user_id)
        if not user or not pwd_context.verify(password, user.password_hash):
            raise MFAServiceError("Invalid password")

        mfa = await self._get_verified_mfa(user_id)
        if not mfa:
            raise MFANotEnabledError("MFA not enabled")

        new_codes = self._generate_backup_codes()
        mfa.backup_codes_encrypted = self._encrypt_backup_codes(new_codes)
        mfa.backup_codes_remaining = len(new_codes)
        await self.session.flush()

        return new_codes

    def _verify_totp(self, mfa: UserMFA, code: str) -> bool:
        """Verify TOTP code against stored secret."""
        try:
            secret = decrypt_data(mfa.secret_encrypted)
            return self._verify_totp_code(secret, code)
        except Exception as e:
            logger.warning("TOTP verification error: %s", e)
            return False

    def _verify_backup_code(self, mfa: UserMFA, code: str) -> bool:
        """Verify backup code and mark as used."""
        if not mfa.backup_codes_encrypted or mfa.backup_codes_remaining == 0:
            return False

        try:
            codes = self._decrypt_backup_codes(mfa.backup_codes_encrypted)
            if self._check_backup_code(code, codes):
                self._remove_backup_code(mfa, code, codes)
                return True
        except Exception as e:
            logger.warning("Backup code verification error: %s", e)

        return False

    @staticmethod
    def _generate_backup_codes() -> list:
        """Generate 10 backup codes."""
        return [secrets.token_hex(6) for _ in range(10)]

    @staticmethod
    def _encrypt_backup_codes(codes: list) -> str:
        """Encrypt backup codes after hashing."""
        hashed = [bcrypt_hash.hash(code) for code in codes]
        return encrypt_data(json.dumps(hashed))

    @staticmethod
    def _decrypt_backup_codes(encrypted: str) -> list:
        """Decrypt backup codes."""
        decrypted = decrypt_data(encrypted)
        return json.loads(decrypted)

    async def _get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """Get user by ID."""
        query = select(User).where(User.id == user_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def _check_no_existing_mfa(self, user_id: uuid.UUID) -> None:
        """Ensure no verified MFA exists."""
        query = select(UserMFA).where(
            UserMFA.user_id == user_id, UserMFA.is_verified.is_(True)
        )
        result = await self.session.execute(query)
        if result.scalar_one_or_none():
            raise MFAServiceError("MFA already enabled for this user")

    @staticmethod
    def _build_otpauth_uri(secret: str, username: str) -> str:
        """Build otpauth URI for QR code."""
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(username, issuer_name="AutoBot SLM")

    @staticmethod
    def _create_mfa_record(
        user_id: uuid.UUID, encrypted_secret: str, encrypted_codes: str
    ) -> UserMFA:
        """Create new MFA record."""
        return UserMFA(
            user_id=user_id,
            secret_encrypted=encrypted_secret,
            backup_codes_encrypted=encrypted_codes,
            backup_codes_remaining=10,
            is_verified=False,
        )

    async def _get_unverified_mfa(self, user_id: uuid.UUID) -> Optional[UserMFA]:
        """Get unverified MFA record."""
        query = select(UserMFA).where(
            UserMFA.user_id == user_id, UserMFA.is_verified.is_(False)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    def _verify_totp_code(secret: str, code: str) -> bool:
        """Verify TOTP code."""
        totp = pyotp.TOTP(secret)
        return totp.verify(code)

    async def _mark_mfa_verified(self, mfa: UserMFA, user_id: uuid.UUID) -> None:
        """Mark MFA as verified and enable for user."""
        mfa.is_verified = True
        mfa.record_verification()

        user = await self._get_user_by_id(user_id)
        if user:
            user.mfa_enabled = True

        await self.session.flush()

    async def _get_verified_mfa(self, user_id: uuid.UUID) -> Optional[UserMFA]:
        """Get verified MFA record."""
        query = select(UserMFA).where(
            UserMFA.user_id == user_id, UserMFA.is_verified.is_(True)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def _delete_mfa_record(self, user_id: uuid.UUID) -> None:
        """Delete MFA record."""
        query = select(UserMFA).where(UserMFA.user_id == user_id)
        result = await self.session.execute(query)
        mfa = result.scalar_one_or_none()
        if mfa:
            await self.session.delete(mfa)

    @staticmethod
    def _default_status() -> dict:
        """Return default MFA status (disabled)."""
        return {
            "enabled": False,
            "method": "totp",
            "backup_codes_remaining": 0,
            "last_verified_at": None,
        }

    @staticmethod
    def _build_status(mfa: UserMFA) -> dict:
        """Build MFA status dict."""
        return {
            "enabled": True,
            "method": mfa.method,
            "backup_codes_remaining": mfa.backup_codes_remaining,
            "last_verified_at": mfa.last_verified_at,
        }

    @staticmethod
    def _check_backup_code(code: str, hashed_codes: list) -> bool:
        """Check if code matches any hashed backup code."""
        return any(bcrypt_hash.verify(code, hashed) for hashed in hashed_codes)

    def _remove_backup_code(self, mfa: UserMFA, code: str, hashed_codes: list) -> None:
        """Remove used backup code."""
        new_codes = [h for h in hashed_codes if not bcrypt_hash.verify(code, h)]
        mfa.backup_codes_encrypted = encrypt_data(json.dumps(new_codes))
        mfa.use_backup_code()
