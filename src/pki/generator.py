# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Certificate Generator Module
============================

Generates TLS certificates for AutoBot infrastructure.
Uses OpenSSL via subprocess for certificate operations.

Inspired by oVirt's ovirt-engine-pki-ca-create and ovirt-engine-pki-enroll.
"""

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from src.pki.config import (
    CertificateStatus,
    CertificateType,
    TLSConfig,
    VMCertificateInfo,
    VM_DEFINITIONS,
)

logger = logging.getLogger(__name__)


class CertificateGenerator:
    """
    Generates TLS certificates for AutoBot VMs.

    Handles:
    - CA certificate creation
    - Service certificate generation
    - Certificate signing
    - Certificate validation
    """

    def __init__(self, config: Optional[TLSConfig] = None):
        """Initialize generator with configuration."""
        self.config = config or TLSConfig()

    def generate_all(self, force: bool = False) -> bool:
        """
        Generate all certificates (CA + all VMs).

        Args:
            force: If True, regenerate even if certificates exist

        Returns:
            True if all certificates generated successfully
        """
        logger.info("Starting certificate generation for all VMs")

        # Create CA first
        if not self._generate_ca(force):
            logger.error("Failed to generate CA certificate")
            return False

        # Generate certificates for each VM
        for vm_name, vm_ip in VM_DEFINITIONS.items():
            vm_info = self.config.get_vm_cert_info(vm_name, vm_ip)
            if not self._generate_service_cert(vm_info, force):
                logger.error(f"Failed to generate certificate for {vm_name}")
                return False

        logger.info("All certificates generated successfully")
        return True

    def _generate_ca(self, force: bool = False) -> bool:
        """Generate CA certificate and key."""
        ca_cert = self.config.ca_cert_path
        ca_key = self.config.ca_key_path

        if ca_cert.exists() and ca_key.exists() and not force:
            logger.info("CA certificate already exists, skipping generation")
            return True

        logger.info("Generating CA certificate")

        # Create directory
        ca_cert.parent.mkdir(parents=True, exist_ok=True)

        # Generate CA private key
        key_cmd = [
            "openssl", "genrsa",
            "-out", str(ca_key),
            str(self.config.key_size),
        ]

        try:
            subprocess.run(key_cmd, check=True, capture_output=True)
            os.chmod(ca_key, 0o600)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to generate CA key: {e.stderr.decode()}")
            return False

        # Generate CA certificate
        subject = f"/C={self.config.country}/O={self.config.organization}/CN=AutoBot CA"

        cert_cmd = [
            "openssl", "req",
            "-new", "-x509",
            "-key", str(ca_key),
            "-out", str(ca_cert),
            "-days", str(self.config.ca_validity_days),
            "-subj", subject,
            "-sha256",
        ]

        try:
            subprocess.run(cert_cmd, check=True, capture_output=True)
            os.chmod(ca_cert, 0o644)
            logger.info(f"CA certificate generated: {ca_cert}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to generate CA certificate: {e.stderr.decode()}")
            return False

    def _generate_service_cert(
        self, vm_info: VMCertificateInfo, force: bool = False
    ) -> bool:
        """Generate service certificate for a VM."""
        cert_path = vm_info.cert_path
        key_path = vm_info.key_path

        if cert_path.exists() and key_path.exists() and not force:
            logger.info(f"Certificate for {vm_info.name} already exists, skipping")
            return True

        logger.info(f"Generating certificate for {vm_info.name}")

        # Create directory
        cert_path.parent.mkdir(parents=True, exist_ok=True)

        # Create OpenSSL config for SAN
        conf_path = cert_path.parent / "server.conf"
        san_string = ",".join(vm_info.san_entries)

        conf_content = f"""[req]
default_bits = {self.config.key_size}
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = req_ext

[dn]
C = {self.config.country}
O = {self.config.organization}
CN = {vm_info.common_name}

[req_ext]
subjectAltName = {san_string}

[v3_ext]
authorityKeyIdentifier = keyid,issuer
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth, clientAuth
subjectAltName = {san_string}
"""
        conf_path.write_text(conf_content)

        # Generate private key
        key_cmd = [
            "openssl", "genrsa",
            "-out", str(key_path),
            str(self.config.key_size),
        ]

        try:
            subprocess.run(key_cmd, check=True, capture_output=True)
            os.chmod(key_path, 0o600)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to generate key for {vm_info.name}: {e.stderr.decode()}")
            return False

        # Generate CSR
        csr_path = cert_path.parent / "server.csr"
        csr_cmd = [
            "openssl", "req",
            "-new",
            "-key", str(key_path),
            "-out", str(csr_path),
            "-config", str(conf_path),
        ]

        try:
            subprocess.run(csr_cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to generate CSR for {vm_info.name}: {e.stderr.decode()}")
            return False

        # Sign with CA
        sign_cmd = [
            "openssl", "x509",
            "-req",
            "-in", str(csr_path),
            "-CA", str(self.config.ca_cert_path),
            "-CAkey", str(self.config.ca_key_path),
            "-CAcreateserial",
            "-out", str(cert_path),
            "-days", str(self.config.cert_validity_days),
            "-sha256",
            "-extfile", str(conf_path),
            "-extensions", "v3_ext",
        ]

        try:
            subprocess.run(sign_cmd, check=True, capture_output=True)
            os.chmod(cert_path, 0o644)
            # Clean up CSR
            csr_path.unlink()
            logger.info(f"Certificate generated for {vm_info.name}: {cert_path}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to sign certificate for {vm_info.name}: {e.stderr.decode()}")
            return False

    def get_certificate_status(self, cert_path: Path) -> CertificateStatus:
        """Get status of a certificate."""
        if not cert_path.exists():
            return CertificateStatus(exists=False, valid=False)

        try:
            # Get certificate info
            cmd = [
                "openssl", "x509",
                "-in", str(cert_path),
                "-noout",
                "-subject", "-issuer", "-dates",
            ]
            result = subprocess.run(cmd, capture_output=True, check=True)
            output = result.stdout.decode()

            # Parse output
            subject = None
            issuer = None
            expires_at = None

            for line in output.strip().split("\n"):
                if line.startswith("subject="):
                    subject = line.replace("subject=", "").strip()
                elif line.startswith("issuer="):
                    issuer = line.replace("issuer=", "").strip()
                elif line.startswith("notAfter="):
                    expires_at = line.replace("notAfter=", "").strip()

            # Calculate days until expiry
            days_until_expiry = None
            needs_renewal = False
            if expires_at:
                try:
                    # Parse OpenSSL date format
                    expiry_date = datetime.strptime(
                        expires_at, "%b %d %H:%M:%S %Y %Z"
                    )
                    days_until_expiry = (expiry_date - datetime.now()).days
                    needs_renewal = days_until_expiry <= self.config.renewal_threshold_days
                except ValueError:
                    pass

            # Verify certificate
            verify_cmd = [
                "openssl", "verify",
                "-CAfile", str(self.config.ca_cert_path),
                str(cert_path),
            ]
            verify_result = subprocess.run(verify_cmd, capture_output=True)
            valid = verify_result.returncode == 0

            return CertificateStatus(
                exists=True,
                valid=valid,
                expires_at=expires_at,
                days_until_expiry=days_until_expiry,
                subject=subject,
                issuer=issuer,
                needs_renewal=needs_renewal,
            )

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get certificate status: {e}")
            return CertificateStatus(exists=True, valid=False)

    def get_all_statuses(self) -> dict:
        """Get status of all certificates."""
        statuses = {}

        # CA status
        statuses["ca"] = self.get_certificate_status(self.config.ca_cert_path)

        # VM certificates
        for vm_name, vm_ip in VM_DEFINITIONS.items():
            vm_info = self.config.get_vm_cert_info(vm_name, vm_ip)
            statuses[vm_name] = self.get_certificate_status(vm_info.cert_path)

        return statuses

    def needs_renewal(self) -> List[str]:
        """Get list of certificates needing renewal."""
        needs_renewal = []
        statuses = self.get_all_statuses()

        for name, status in statuses.items():
            if status.needs_renewal:
                needs_renewal.append(name)

        return needs_renewal
