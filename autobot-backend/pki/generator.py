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
import subprocess  # nosec B404 - Required for PKI certificate generation
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from pki.config import VM_DEFINITIONS, CertificateStatus, TLSConfig, VMCertificateInfo

logger = logging.getLogger(__name__)


def _run_openssl_command(
    cmd: List[str], operation: str, context: str = ""
) -> Tuple[bool, Optional[str]]:
    """
    Execute an OpenSSL command with error handling.

    Issue #665: Extracted helper to reduce code duplication in certificate
    generation methods.

    Args:
        cmd: OpenSSL command as list of strings
        operation: Human-readable operation name for logging
        context: Additional context (e.g., VM name)

    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True, None
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        log_ctx = f" for {context}" if context else ""
        logger.error(f"Failed to {operation}{log_ctx}: {error_msg}")
        return False, error_msg


def _write_openssl_config(
    conf_path: Path, config: TLSConfig, vm_info: VMCertificateInfo
) -> None:
    """
    Write OpenSSL configuration file for certificate generation.

    Issue #665: Extracted from _generate_service_cert to improve readability.

    Args:
        conf_path: Path to write the config file
        config: TLS configuration with key size, country, org
        vm_info: VM certificate info with common name and SAN entries
    """
    san_string = ",".join(vm_info.san_entries)

    conf_content = f"""[req]
default_bits = {config.key_size}
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = req_ext

[dn]
C = {config.country}
O = {config.organization}
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
    conf_path.write_text(conf_content, encoding="utf-8")


def _generate_service_key(key_path: Path, key_size: int, vm_name: str) -> bool:
    """
    Generate private key for a service certificate.

    Extracted from _generate_service_cert to reduce function complexity. Issue #620.

    Args:
        key_path: Path to write the private key
        key_size: RSA key size in bits
        vm_name: VM name for logging context

    Returns:
        True if key generation succeeded
    """
    key_cmd = [
        "openssl",
        "genrsa",
        "-out",
        str(key_path),
        str(key_size),
    ]
    success, _ = _run_openssl_command(key_cmd, "generate key", vm_name)
    if success:
        os.chmod(key_path, 0o600)
    return success


def _generate_csr(
    key_path: Path, csr_path: Path, conf_path: Path, vm_name: str
) -> bool:
    """
    Generate Certificate Signing Request for a service.

    Extracted from _generate_service_cert to reduce function complexity. Issue #620.

    Args:
        key_path: Path to the private key
        csr_path: Path to write the CSR
        conf_path: Path to the OpenSSL config file
        vm_name: VM name for logging context

    Returns:
        True if CSR generation succeeded
    """
    csr_cmd = [
        "openssl",
        "req",
        "-new",
        "-key",
        str(key_path),
        "-out",
        str(csr_path),
        "-config",
        str(conf_path),
    ]
    success, _ = _run_openssl_command(csr_cmd, "generate CSR", vm_name)
    return success


def _sign_certificate(
    csr_path: Path,
    cert_path: Path,
    ca_cert_path: Path,
    ca_key_path: Path,
    conf_path: Path,
    validity_days: int,
    vm_name: str,
) -> bool:
    """
    Sign a certificate with the CA.

    Extracted from _generate_service_cert to reduce function complexity. Issue #620.

    Args:
        csr_path: Path to the CSR file
        cert_path: Path to write the signed certificate
        ca_cert_path: Path to the CA certificate
        ca_key_path: Path to the CA private key
        conf_path: Path to the OpenSSL config file
        validity_days: Certificate validity in days
        vm_name: VM name for logging context

    Returns:
        True if signing succeeded
    """
    sign_cmd = [
        "openssl",
        "x509",
        "-req",
        "-in",
        str(csr_path),
        "-CA",
        str(ca_cert_path),
        "-CAkey",
        str(ca_key_path),
        "-CAcreateserial",
        "-out",
        str(cert_path),
        "-days",
        str(validity_days),
        "-sha256",
        "-extfile",
        str(conf_path),
        "-extensions",
        "v3_ext",
    ]
    success, _ = _run_openssl_command(sign_cmd, "sign certificate", vm_name)
    if success:
        os.chmod(cert_path, 0o644)
    return success


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

    def _generate_ca_private_key(self, ca_key: Path) -> bool:
        """
        Generate CA private key using OpenSSL.

        Args:
            ca_key: Path to write the CA private key

        Returns:
            True if key generation succeeded

        Issue #620.
        """
        key_cmd = [
            "openssl",
            "genrsa",
            "-out",
            str(ca_key),
            str(self.config.key_size),
        ]

        try:
            subprocess.run(key_cmd, check=True, capture_output=True)
            os.chmod(ca_key, 0o600)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to generate CA key: {e.stderr.decode()}")
            return False

    def _generate_ca_certificate(self, ca_key: Path, ca_cert: Path) -> bool:
        """
        Generate self-signed CA certificate using OpenSSL.

        Args:
            ca_key: Path to the CA private key
            ca_cert: Path to write the CA certificate

        Returns:
            True if certificate generation succeeded

        Issue #620.
        """
        subject = f"/C={self.config.country}/O={self.config.organization}/CN=AutoBot CA"

        cert_cmd = [
            "openssl",
            "req",
            "-new",
            "-x509",
            "-key",
            str(ca_key),
            "-out",
            str(ca_cert),
            "-days",
            str(self.config.ca_validity_days),
            "-subj",
            subject,
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

    def _generate_ca(self, force: bool = False) -> bool:
        """
        Generate CA certificate and key.

        Issue #620: Refactored using Extract Method pattern to use
        _generate_ca_private_key() and _generate_ca_certificate() helpers.
        """
        ca_cert = self.config.ca_cert_path
        ca_key = self.config.ca_key_path

        if ca_cert.exists() and ca_key.exists() and not force:
            logger.info("CA certificate already exists, skipping generation")
            return True

        logger.info("Generating CA certificate")
        ca_cert.parent.mkdir(parents=True, exist_ok=True)

        if not self._generate_ca_private_key(ca_key):
            return False

        return self._generate_ca_certificate(ca_key, ca_cert)

    def _generate_service_cert(
        self, vm_info: VMCertificateInfo, force: bool = False
    ) -> bool:
        """
        Generate service certificate for a VM.

        Issue #620: Refactored using Extract Method pattern to use helper
        functions for key generation, CSR creation, and certificate signing.
        """
        cert_path = vm_info.cert_path
        key_path = vm_info.key_path

        if cert_path.exists() and key_path.exists() and not force:
            logger.info(f"Certificate for {vm_info.name} already exists, skipping")
            return True

        logger.info(f"Generating certificate for {vm_info.name}")

        # Create directory and write OpenSSL config
        cert_path.parent.mkdir(parents=True, exist_ok=True)
        conf_path = cert_path.parent / "server.conf"
        _write_openssl_config(conf_path, self.config, vm_info)

        # Generate private key (Issue #620: extracted to helper)
        if not _generate_service_key(key_path, self.config.key_size, vm_info.name):
            return False

        # Generate CSR (Issue #620: extracted to helper)
        csr_path = cert_path.parent / "server.csr"
        if not _generate_csr(key_path, csr_path, conf_path, vm_info.name):
            return False

        # Sign with CA (Issue #620: extracted to helper)
        if not _sign_certificate(
            csr_path,
            cert_path,
            self.config.ca_cert_path,
            self.config.ca_key_path,
            conf_path,
            self.config.cert_validity_days,
            vm_info.name,
        ):
            return False

        csr_path.unlink()  # Clean up CSR
        logger.info(f"Certificate generated for {vm_info.name}: {cert_path}")
        return True

    def _parse_certificate_output(
        self, output: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Parse OpenSSL x509 output for subject, issuer, and expiry date.

        Issue #620.

        Args:
            output: Raw output from openssl x509 command

        Returns:
            Tuple of (subject, issuer, expires_at)
        """
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

        return subject, issuer, expires_at

    def _calculate_expiry_info(
        self, expires_at: Optional[str]
    ) -> Tuple[Optional[int], bool]:
        """
        Calculate days until expiry and renewal status from expiry date string.

        Issue #620.

        Args:
            expires_at: Expiry date string in OpenSSL format

        Returns:
            Tuple of (days_until_expiry, needs_renewal)
        """
        if not expires_at:
            return None, False

        try:
            expiry_date = datetime.strptime(expires_at, "%b %d %H:%M:%S %Y %Z")
            days_until_expiry = (expiry_date - datetime.now()).days
            needs_renewal = days_until_expiry <= self.config.renewal_threshold_days
            return days_until_expiry, needs_renewal
        except ValueError:
            return None, False

    def _verify_certificate(self, cert_path: Path) -> bool:
        """
        Verify certificate against CA.

        Issue #620.

        Args:
            cert_path: Path to certificate file

        Returns:
            True if certificate is valid
        """
        verify_cmd = [
            "openssl",
            "verify",
            "-CAfile",
            str(self.config.ca_cert_path),
            str(cert_path),
        ]
        verify_result = subprocess.run(verify_cmd, capture_output=True)
        return verify_result.returncode == 0

    def get_certificate_status(self, cert_path: Path) -> CertificateStatus:
        """Get status of a certificate."""
        if not cert_path.exists():
            return CertificateStatus(exists=False, valid=False)

        try:
            cmd = [
                "openssl",
                "x509",
                "-in",
                str(cert_path),
                "-noout",
                "-subject",
                "-issuer",
                "-dates",
            ]
            result = subprocess.run(cmd, capture_output=True, check=True)
            output = result.stdout.decode()

            subject, issuer, expires_at = self._parse_certificate_output(output)
            days_until_expiry, needs_renewal = self._calculate_expiry_info(expires_at)
            valid = self._verify_certificate(cert_path)

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
