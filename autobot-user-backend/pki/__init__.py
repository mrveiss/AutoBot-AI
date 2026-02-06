# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
PKI Module - oVirt-style Automated Certificate Management
=========================================================

This module provides automated TLS certificate management for the AutoBot
distributed VM infrastructure. Inspired by oVirt's engine-setup PKI system.

Features:
- Automatic certificate generation during setup
- SSH-based certificate distribution to VMs
- Service configuration updates (Redis TLS, etc.)
- Certificate expiration monitoring
- Seamless integration with setup.py flow

Architecture:
- PKIManager: Main orchestrator (like oVirt's CAPlugin)
- CertificateGenerator: Creates CA and service certificates
- CertificateDistributor: Distributes certs to VMs via SSH
- ServiceConfigurator: Updates service configs for TLS

Usage:
    from pki import PKIManager

    # During setup - automatically handles everything
    pki = PKIManager()
    await pki.setup()  # Generates, distributes, configures

    # Check certificate status
    status = pki.get_status()

    # Renew certificates (if expiring)
    if pki.needs_renewal():
        await pki.renew()
"""

from pki.manager import PKIManager
from pki.generator import CertificateGenerator
from pki.distributor import CertificateDistributor
from pki.configurator import ServiceConfigurator

__all__ = [
    "PKIManager",
    "CertificateGenerator",
    "CertificateDistributor",
    "ServiceConfigurator",
]
