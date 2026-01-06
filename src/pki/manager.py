# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
PKI Manager - Main Orchestrator
===============================

Main orchestrator for PKI operations, inspired by oVirt's CAPlugin.
Provides a unified interface for certificate lifecycle management.

This is the primary entry point for all PKI operations in AutoBot.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from src.pki.config import TLSConfig, TLSMode, VM_DEFINITIONS
from src.pki.generator import CertificateGenerator
from src.pki.distributor import CertificateDistributor, DistributionResult
from src.pki.configurator import ServiceConfigurator, ConfigurationResult

logger = logging.getLogger(__name__)


class PKIStage(str, Enum):
    """PKI setup stages (like oVirt's setup stages)."""

    INIT = "init"
    VALIDATION = "validation"
    GENERATION = "generation"
    DISTRIBUTION = "distribution"
    CONFIGURATION = "configuration"
    VERIFICATION = "verification"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class PKIStatus:
    """Overall PKI status."""

    stage: PKIStage
    tls_mode: TLSMode
    ca_exists: bool
    ca_valid: bool
    certificates_generated: int
    certificates_distributed: int
    services_configured: int
    last_updated: datetime = field(default_factory=datetime.now)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class PKIManager:
    """
    Main PKI orchestrator for AutoBot.

    Provides unified interface for:
    - Certificate generation
    - Certificate distribution
    - Service configuration
    - Status monitoring
    - Certificate renewal

    Usage:
        pki = PKIManager()

        # Full setup (generate + distribute + configure)
        await pki.setup()

        # Check status
        status = pki.get_status()

        # Renew if needed
        if pki.needs_renewal():
            await pki.renew()
    """

    def __init__(self, config: Optional[TLSConfig] = None):
        """Initialize PKI manager."""
        self.config = config or TLSConfig()
        self.generator = CertificateGenerator(self.config)
        self.distributor = CertificateDistributor(self.config)
        self.configurator = ServiceConfigurator(self.config)

        self._stage = PKIStage.INIT
        self._errors: List[str] = []
        self._warnings: List[str] = []

    async def setup(
        self,
        force_regenerate: bool = False,
        skip_distribution: bool = False,
        skip_configuration: bool = False,
    ) -> bool:
        """
        Run complete PKI setup.

        This is the main entry point for setting up TLS across the infrastructure.
        Equivalent to oVirt's engine-setup PKI plugin stages.

        Args:
            force_regenerate: Regenerate certificates even if they exist
            skip_distribution: Skip distributing to VMs (for local-only setup)
            skip_configuration: Skip service configuration

        Returns:
            True if setup completed successfully
        """
        logger.info("Starting PKI setup")
        self._errors = []
        self._warnings = []

        # Stage 1: Validation
        self._stage = PKIStage.VALIDATION
        logger.info("PKI Stage: Validation")

        if not self._validate_prerequisites():
            self._stage = PKIStage.FAILED
            return False

        # Stage 2: Generation
        self._stage = PKIStage.GENERATION
        logger.info("PKI Stage: Certificate Generation")

        if not self.generator.generate_all(force=force_regenerate):
            self._errors.append("Certificate generation failed")
            self._stage = PKIStage.FAILED
            return False

        # Stage 3: Distribution
        if not skip_distribution:
            self._stage = PKIStage.DISTRIBUTION
            logger.info("PKI Stage: Certificate Distribution")

            results = await self.distributor.distribute_all()
            failed = [name for name, r in results.items() if not r.success]

            if failed:
                self._warnings.append(
                    f"Distribution failed for: {', '.join(failed)}"
                )
                # Don't fail completely - some VMs might be offline
                logger.warning(f"Some distributions failed: {failed}")

        # Stage 4: Configuration
        if not skip_configuration:
            self._stage = PKIStage.CONFIGURATION
            logger.info("PKI Stage: Service Configuration")

            config_results = await self.configurator.configure_all()
            for service, result in config_results.items():
                if not result.success:
                    self._warnings.append(
                        f"Configuration failed for {service}: {result.message}"
                    )

        # Stage 5: Verification
        self._stage = PKIStage.VERIFICATION
        logger.info("PKI Stage: Verification")

        if not skip_distribution:
            verification = await self.distributor.verify_distribution()
            failed_verify = [name for name, ok in verification.items() if not ok]
            if failed_verify:
                self._warnings.append(
                    f"Verification failed for: {', '.join(failed_verify)}"
                )

        # Complete
        self._stage = PKIStage.COMPLETE
        logger.info("PKI setup complete")

        return len(self._errors) == 0

    def _validate_prerequisites(self) -> bool:
        """Validate prerequisites for PKI setup."""
        errors = []

        # Check SSH key exists
        if not self.config.ssh_key_path.exists():
            errors.append(f"SSH key not found: {self.config.ssh_key_path}")

        # Check OpenSSL is available
        import shutil
        if not shutil.which("openssl"):
            errors.append("OpenSSL not found in PATH")

        # Check cert directory is writable
        cert_dir = self.config.cert_dir_path
        try:
            cert_dir.mkdir(parents=True, exist_ok=True)
            test_file = cert_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
        except PermissionError:
            errors.append(f"Cannot write to certificate directory: {cert_dir}")

        if errors:
            self._errors.extend(errors)
            for error in errors:
                logger.error(f"Prerequisite check failed: {error}")
            return False

        return True

    def get_status(self) -> PKIStatus:
        """Get current PKI status."""
        statuses = self.generator.get_all_statuses()
        ca_status = statuses.get("ca")

        # Count certificates
        cert_count = sum(
            1 for name, s in statuses.items()
            if name != "ca" and s.exists and s.valid
        )

        return PKIStatus(
            stage=self._stage,
            tls_mode=self.config.mode,
            ca_exists=ca_status.exists if ca_status else False,
            ca_valid=ca_status.valid if ca_status else False,
            certificates_generated=cert_count,
            certificates_distributed=0,  # Would need to check remote
            services_configured=0,  # Would need to check services
            errors=self._errors.copy(),
            warnings=self._warnings.copy(),
        )

    def needs_renewal(self) -> bool:
        """Check if any certificates need renewal."""
        return len(self.generator.needs_renewal()) > 0

    def get_renewal_list(self) -> List[str]:
        """Get list of certificates needing renewal."""
        return self.generator.needs_renewal()

    async def renew(self, certificates: Optional[List[str]] = None) -> bool:
        """
        Renew certificates.

        Args:
            certificates: List of certificate names to renew.
                         If None, renews all that need renewal.

        Returns:
            True if renewal successful
        """
        if certificates is None:
            certificates = self.generator.needs_renewal()

        if not certificates:
            logger.info("No certificates need renewal")
            return True

        logger.info(f"Renewing certificates: {certificates}")

        # For now, regenerate and redistribute
        # TODO: Implement proper renewal that preserves keys if desired

        for cert_name in certificates:
            if cert_name == "ca":
                # CA renewal is more complex - would need to re-sign all certs
                logger.warning("CA renewal not yet implemented")
                continue

            vm_ip = VM_DEFINITIONS.get(cert_name)
            if vm_ip:
                vm_info = self.config.get_vm_cert_info(cert_name, vm_ip)
                # Regenerate
                self.generator._generate_service_cert(vm_info, force=True)
                # Redistribute
                await self.distributor._distribute_to_vm(vm_info)

        return True

    def get_certificate_details(self) -> Dict[str, dict]:
        """Get detailed certificate information."""
        statuses = self.generator.get_all_statuses()
        details = {}

        for name, status in statuses.items():
            details[name] = {
                "exists": status.exists,
                "valid": status.valid,
                "expires_at": status.expires_at,
                "days_until_expiry": status.days_until_expiry,
                "subject": status.subject,
                "issuer": status.issuer,
                "needs_renewal": status.needs_renewal,
            }

        return details

    def print_status(self):
        """Print formatted status to console."""
        status = self.get_status()
        details = self.get_certificate_details()

        logger.info("\n" + "=" * 60)
        logger.info("AutoBot PKI Status")
        logger.info("=" * 60)
        logger.info("Stage: %s", status.stage.value)
        logger.info("TLS Mode: %s", status.tls_mode.value)
        logger.info("CA Valid: %s", "Yes" if status.ca_valid else "No")
        logger.info("Certificates Generated: %s", status.certificates_generated)
        logger.info("")

        logger.info("Certificate Details:")
        logger.info("-" * 60)
        for name, detail in details.items():
            status_str = "✓" if detail["valid"] else "✗"
            expiry_str = (
                f"{detail['days_until_expiry']} days"
                if detail["days_until_expiry"]
                else "N/A"
            )
            renewal_str = " (RENEWAL NEEDED)" if detail["needs_renewal"] else ""
            logger.info("  %s %s: expires in %s%s", status_str, name, expiry_str, renewal_str)

        if status.errors:
            logger.info("")
            logger.error("Errors:")
            for error in status.errors:
                logger.error("  ✗ %s", error)

        if status.warnings:
            logger.info("")
            logger.warning("Warnings:")
            for warning in status.warnings:
                logger.warning("  ⚠ %s", warning)

        logger.info("=" * 60 + "\n")


# Convenience function for CLI/setup integration
async def setup_pki(
    force: bool = False,
    distribute: bool = True,
    configure: bool = True,
) -> bool:
    """
    Convenience function for PKI setup.

    Can be called from setup.py or CLI.

    Args:
        force: Force regeneration of certificates
        distribute: Distribute certificates to VMs
        configure: Configure services for TLS

    Returns:
        True if setup successful
    """
    manager = PKIManager()
    success = await manager.setup(
        force_regenerate=force,
        skip_distribution=not distribute,
        skip_configuration=not configure,
    )
    manager.print_status()
    return success
