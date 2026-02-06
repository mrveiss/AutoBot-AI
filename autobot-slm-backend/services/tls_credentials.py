# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
TLS Credential Service (Issue #725)

Manages encrypted TLS certificate storage for mTLS authentication.
Certificates are stored encrypted in the database and served via API
for Ansible role deployments.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import CredentialType, Node, NodeCredential
from models.schemas import (
    TLSCertificateInfo,
    TLSCredentialCreate,
    TLSCredentialUpdate,
    TLSEndpointResponse,
)
from services.encryption import get_encryption_service

logger = logging.getLogger(__name__)


class TLSCredentialService:
    """Service for managing TLS certificate credentials."""

    def __init__(self):
        self.encryption = get_encryption_service()

    def _parse_certificate(self, cert_pem: str) -> TLSCertificateInfo:
        """Parse a PEM certificate and extract metadata."""
        try:
            cert = x509.load_pem_x509_certificate(cert_pem.encode())

            # Extract common name
            cn = ""
            for attr in cert.subject:
                if attr.oid == x509.oid.NameOID.COMMON_NAME:
                    cn = attr.value
                    break

            # Extract SANs
            san_list = []
            try:
                san_ext = cert.extensions.get_extension_for_oid(
                    x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                )
                for name in san_ext.value:
                    if isinstance(name, x509.DNSName):
                        san_list.append(f"DNS:{name.value}")
                    elif isinstance(name, x509.IPAddress):
                        san_list.append(f"IP:{name.value}")
            except x509.ExtensionNotFound:
                pass

            # Calculate fingerprint
            fingerprint = cert.fingerprint(
                cert.signature_hash_algorithm or hashlib.sha256()
            ).hex()

            return TLSCertificateInfo(
                common_name=cn,
                subject=cert.subject.rfc4514_string(),
                issuer=cert.issuer.rfc4514_string(),
                serial_number=format(cert.serial_number, "x"),
                not_before=cert.not_valid_before_utc,
                not_after=cert.not_valid_after_utc,
                fingerprint=fingerprint,
                san=san_list,
            )
        except Exception as e:
            logger.error("Failed to parse certificate: %s", e)
            raise ValueError(f"Invalid certificate: {e}")

    def _calculate_fingerprint(self, cert_pem: str) -> str:
        """Calculate SHA256 fingerprint of a certificate."""
        try:
            cert = x509.load_pem_x509_certificate(cert_pem.encode())
            return cert.fingerprint(hashlib.sha256()).hex()
        except Exception:
            # Fallback to hashing the PEM itself
            return hashlib.sha256(cert_pem.encode()).hexdigest()

    async def create_credential(
        self,
        db: AsyncSession,
        node_id: str,
        data: TLSCredentialCreate,
    ) -> NodeCredential:
        """Create a new TLS credential for a node."""
        # Verify node exists
        result = await db.execute(select(Node).where(Node.node_id == node_id))
        node = result.scalar_one_or_none()
        if not node:
            raise ValueError(f"Node not found: {node_id}")

        # Parse certificate to extract metadata
        cert_info = self._parse_certificate(data.server_cert)

        # Store certificates as encrypted JSON blob
        cert_data = {
            "ca_cert": data.ca_cert,
            "server_cert": data.server_cert,
            "server_key": data.server_key,
        }
        encrypted_data = self.encryption.encrypt(json.dumps(cert_data))

        # Create credential
        credential = NodeCredential(
            credential_id=str(uuid.uuid4()),
            node_id=node_id,
            credential_type=CredentialType.TLS.value,
            name=data.name,
            encrypted_data=encrypted_data,
            tls_common_name=data.common_name or cert_info.common_name,
            tls_expires_at=data.expires_at or cert_info.not_after,
            tls_fingerprint=cert_info.fingerprint,
            is_active=True,
        )

        db.add(credential)
        await db.commit()
        await db.refresh(credential)

        logger.info(
            "Created TLS credential %s for node %s (CN: %s)",
            credential.credential_id,
            node_id,
            credential.tls_common_name,
        )
        return credential

    async def get_credential(
        self, db: AsyncSession, credential_id: str
    ) -> Optional[NodeCredential]:
        """Get a TLS credential by ID."""
        result = await db.execute(
            select(NodeCredential).where(
                NodeCredential.credential_id == credential_id,
                NodeCredential.credential_type == CredentialType.TLS.value,
            )
        )
        return result.scalar_one_or_none()

    async def get_node_credentials(
        self, db: AsyncSession, node_id: str
    ) -> List[NodeCredential]:
        """Get all TLS credentials for a node."""
        result = await db.execute(
            select(NodeCredential).where(
                NodeCredential.node_id == node_id,
                NodeCredential.credential_type == CredentialType.TLS.value,
            )
        )
        return list(result.scalars().all())

    async def update_credential(
        self,
        db: AsyncSession,
        credential_id: str,
        data: TLSCredentialUpdate,
    ) -> Optional[NodeCredential]:
        """Update a TLS credential."""
        credential = await self.get_credential(db, credential_id)
        if not credential:
            return None

        # If certificates are being updated, re-encrypt the blob
        if data.ca_cert or data.server_cert or data.server_key:
            # Decrypt existing data
            existing = {}
            if credential.encrypted_data:
                existing = json.loads(
                    self.encryption.decrypt(credential.encrypted_data)
                )

            # Update with new values
            if data.ca_cert:
                existing["ca_cert"] = data.ca_cert
            if data.server_cert:
                existing["server_cert"] = data.server_cert
                # Re-parse certificate for metadata
                cert_info = self._parse_certificate(data.server_cert)
                credential.tls_common_name = cert_info.common_name
                credential.tls_expires_at = cert_info.not_after
                credential.tls_fingerprint = cert_info.fingerprint
            if data.server_key:
                existing["server_key"] = data.server_key

            # Re-encrypt
            credential.encrypted_data = self.encryption.encrypt(json.dumps(existing))

        if data.is_active is not None:
            credential.is_active = data.is_active

        if data.extra_data is not None:
            # Store extra data in a separate field or merge
            pass

        await db.commit()
        await db.refresh(credential)

        logger.info("Updated TLS credential %s", credential_id)
        return credential

    async def delete_credential(self, db: AsyncSession, credential_id: str) -> bool:
        """Delete a TLS credential."""
        credential = await self.get_credential(db, credential_id)
        if not credential:
            return False

        await db.delete(credential)
        await db.commit()

        logger.info("Deleted TLS credential %s", credential_id)
        return True

    async def get_certificates(
        self, db: AsyncSession, credential_id: str
    ) -> Optional[Dict[str, str]]:
        """Get decrypted certificates for deployment.

        Returns dict with ca_cert, server_cert, server_key.
        """
        credential = await self.get_credential(db, credential_id)
        if not credential or not credential.encrypted_data:
            return None

        # Update last used timestamp
        credential.last_used = datetime.utcnow()
        await db.commit()

        # Decrypt and return
        decrypted = self.encryption.decrypt(credential.encrypted_data)
        return json.loads(decrypted)

    async def get_all_tls_endpoints(
        self, db: AsyncSession, active_only: bool = True
    ) -> List[TLSEndpointResponse]:
        """Get all TLS endpoints across the fleet."""
        query = (
            select(NodeCredential, Node)
            .join(Node, NodeCredential.node_id == Node.node_id)
            .where(NodeCredential.credential_type == CredentialType.TLS.value)
        )

        if active_only:
            query = query.where(NodeCredential.is_active.is_(True))

        result = await db.execute(query)
        endpoints = []

        now = datetime.utcnow()
        for cred, node in result.all():
            days_until_expiry = None
            if cred.tls_expires_at:
                delta = cred.tls_expires_at - now
                days_until_expiry = delta.days

            endpoints.append(
                TLSEndpointResponse(
                    credential_id=cred.credential_id,
                    node_id=cred.node_id,
                    hostname=node.hostname,
                    ip_address=node.ip_address,
                    name=cred.name,
                    common_name=cred.tls_common_name,
                    expires_at=cred.tls_expires_at,
                    is_active=cred.is_active,
                    days_until_expiry=days_until_expiry,
                )
            )

        return endpoints

    async def get_expiring_certificates(
        self, db: AsyncSession, days: int = 30
    ) -> List[NodeCredential]:
        """Get certificates expiring within the specified days."""
        threshold = datetime.utcnow() + timedelta(days=days)
        result = await db.execute(
            select(NodeCredential).where(
                NodeCredential.credential_type == CredentialType.TLS.value,
                NodeCredential.is_active.is_(True),
                NodeCredential.tls_expires_at <= threshold,
            )
        )
        return list(result.scalars().all())

    def _generate_certificate_key_pair(self, common_name: str) -> tuple[str, str]:
        """Generate RSA key pair and self-signed X.509 certificate.

        Helper for renew_certificate (Issue #665).

        Args:
            common_name: Common name for the certificate subject

        Returns:
            Tuple of (cert_pem, key_pem) as PEM-encoded strings
        """
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        # Generate new RSA key pair
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Build certificate with 1 year validity
        now = datetime.utcnow()
        cert_builder = x509.CertificateBuilder()
        cert_builder = cert_builder.subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, common_name),
                ]
            )
        )
        cert_builder = cert_builder.issuer_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, "SLM-CA"),
                ]
            )
        )
        cert_builder = cert_builder.not_valid_before(now)
        cert_builder = cert_builder.not_valid_after(now + timedelta(days=365))
        cert_builder = cert_builder.serial_number(x509.random_serial_number())
        cert_builder = cert_builder.public_key(key.public_key())

        # Sign with SHA256
        new_cert = cert_builder.sign(key, hashes.SHA256())

        # Serialize to PEM format
        cert_pem = new_cert.public_bytes(serialization.Encoding.PEM).decode()
        key_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        return cert_pem, key_pem

    async def _create_renewed_credential(
        self,
        db: AsyncSession,
        credential: NodeCredential,
        cert_pem: str,
        key_pem: str,
        ca_cert: str,
    ) -> NodeCredential:
        """Create and save a new renewed credential to database.

        Helper for renew_certificate (Issue #665).

        Args:
            db: Database session
            credential: Original credential being renewed
            cert_pem: New certificate PEM string
            key_pem: New private key PEM string
            ca_cert: CA certificate to include

        Returns:
            The newly created NodeCredential
        """
        # Prepare encrypted data blob
        cert_data = {
            "ca_cert": ca_cert,
            "server_cert": cert_pem,
            "server_key": key_pem,
        }
        encrypted_data = self.encryption.encrypt(json.dumps(cert_data))

        # Parse certificate for metadata
        cert_info = self._parse_certificate(cert_pem)

        # Create new credential record
        new_credential = NodeCredential(
            credential_id=str(uuid.uuid4()),
            node_id=credential.node_id,
            credential_type=CredentialType.TLS.value,
            name=f"{credential.name} (renewed)",
            encrypted_data=encrypted_data,
            tls_common_name=cert_info.common_name,
            tls_expires_at=cert_info.not_after,
            tls_fingerprint=cert_info.fingerprint,
            is_active=True,
        )

        db.add(new_credential)
        await db.commit()
        await db.refresh(new_credential)

        return new_credential

    async def renew_certificate(
        self, db: AsyncSession, credential_id: str
    ) -> Optional[NodeCredential]:
        """
        Renew a TLS certificate.

        Generates a new certificate with extended validity period,
        keeping the same CN and other metadata. The old certificate
        is kept but can be deactivated.
        """
        credential = await self.get_credential(db, credential_id)
        if not credential or not credential.encrypted_data:
            return None

        # Get existing certificates
        existing = json.loads(self.encryption.decrypt(credential.encrypted_data))

        # Generate new key pair and certificate
        common_name = credential.tls_common_name or "renewed-cert"
        cert_pem, key_pem = self._generate_certificate_key_pair(common_name)

        # Create and save new credential
        new_credential = await self._create_renewed_credential(
            db=db,
            credential=credential,
            cert_pem=cert_pem,
            key_pem=key_pem,
            ca_cert=existing.get("ca_cert", ""),
        )

        logger.info(
            "Renewed TLS credential %s -> %s (CN: %s)",
            credential_id,
            new_credential.credential_id,
            new_credential.tls_common_name,
        )
        return new_credential

    async def rotate_certificate(
        self, db: AsyncSession, credential_id: str
    ) -> Optional[NodeCredential]:
        """
        Rotate a TLS certificate with full key rotation.

        Generates completely new cryptographic material (new keys).
        This is more secure than renewal as it uses fresh keys.
        """
        # Rotation is essentially the same as renewal with new keys
        # which is what renew_certificate already does
        return await self.renew_certificate(db, credential_id)

    async def deactivate_credential(self, db: AsyncSession, credential_id: str) -> bool:
        """Deactivate a TLS credential (mark as inactive)."""
        credential = await self.get_credential(db, credential_id)
        if not credential:
            return False

        credential.is_active = False
        await db.commit()

        logger.info("Deactivated TLS credential %s", credential_id)
        return True


# Singleton instance
_tls_credential_service: Optional[TLSCredentialService] = None


def get_tls_credential_service() -> TLSCredentialService:
    """Get the TLS credential service singleton."""
    global _tls_credential_service
    if _tls_credential_service is None:
        _tls_credential_service = TLSCredentialService()
    return _tls_credential_service
