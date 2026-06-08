# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for PKIManager.renew() — key preservation and key rotation paths.

These tests mock all subprocess/SSH calls so they run without OpenSSL or
a live CA on the test machine.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pki.config import TLSConfig, VMCertificateInfo
from pki.generator import CertificateGenerator
from pki.manager import PKIManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vm_info(tmp_path: Path, name: str = "redis") -> VMCertificateInfo:
    """Create a minimal VMCertificateInfo rooted under tmp_path."""
    vm_dir = tmp_path / name
    vm_dir.mkdir(parents=True, exist_ok=True)
    return VMCertificateInfo(
        name=name,
        ip="192.168.1.10",
        cert_path=vm_dir / "server-cert.pem",
        key_path=vm_dir / "server-key.pem",
        common_name=f"autobot-{name}",
        san_entries=[f"DNS:autobot-{name}", "IP:192.168.1.10"],
    )


def _make_manager(tmp_path: Path) -> PKIManager:
    """Build a PKIManager whose generator and distributor are fully mocked."""
    config = MagicMock(spec=TLSConfig)
    config.cert_dir_path = tmp_path / "certs"
    config.ca_cert_path = tmp_path / "certs" / "ca" / "ca-cert.pem"
    config.ca_key_path = tmp_path / "certs" / "ca" / "ca-key.pem"
    config.cert_validity_days = 365
    config.key_size = 2048
    config.country = "US"
    config.organization = "AutoBot"

    manager = PKIManager.__new__(PKIManager)
    manager.config = config
    manager.generator = MagicMock(spec=CertificateGenerator)
    manager.distributor = MagicMock()
    manager.distributor._distribute_to_vm = AsyncMock(return_value=None)
    manager.configurator = MagicMock()
    manager._stage = MagicMock()
    manager._errors = []
    manager._warnings = []
    return manager


# ---------------------------------------------------------------------------
# renew() — no-op when nothing needs renewal
# ---------------------------------------------------------------------------


def test_renew_no_certs_returns_true(tmp_path):
    manager = _make_manager(tmp_path)
    manager.generator.needs_renewal.return_value = []

    result = asyncio.get_event_loop().run_until_complete(manager.renew())

    assert result is True
    manager.generator._renew_service_cert.assert_not_called()
    manager.generator._generate_service_cert.assert_not_called()


# ---------------------------------------------------------------------------
# renew() — CA in list raises ValueError
# ---------------------------------------------------------------------------


def test_renew_ca_raises_value_error(tmp_path):
    manager = _make_manager(tmp_path)

    with pytest.raises(ValueError, match="CA certificate renewal requires manual steps"):
        asyncio.get_event_loop().run_until_complete(manager.renew(certificates=["ca"]))

    manager.generator._renew_service_cert.assert_not_called()
    manager.generator._generate_service_cert.assert_not_called()


def test_renew_ca_mixed_list_raises_before_any_cert(tmp_path):
    """CA in a mixed list must raise before touching any service cert."""
    manager = _make_manager(tmp_path)

    with pytest.raises(ValueError):
        asyncio.get_event_loop().run_until_complete(manager.renew(certificates=["redis", "ca"]))

    manager.generator._renew_service_cert.assert_not_called()
    manager.generator._generate_service_cert.assert_not_called()


# ---------------------------------------------------------------------------
# renew() — preserve_keys=True (default) path
# ---------------------------------------------------------------------------


def test_renew_preserve_keys_calls_renew_service_cert(tmp_path):
    manager = _make_manager(tmp_path)
    manager.generator._renew_service_cert.return_value = True

    vm_info = _make_vm_info(tmp_path, "redis")
    manager.config.get_vm_cert_info.return_value = vm_info

    with patch("pki.manager.VM_DEFINITIONS", {"redis": "192.168.1.10"}):
        result = asyncio.get_event_loop().run_until_complete(manager.renew(certificates=["redis"], preserve_keys=True))

    assert result is True
    manager.generator._renew_service_cert.assert_called_once_with(vm_info)
    manager.generator._generate_service_cert.assert_not_called()
    manager.distributor._distribute_to_vm.assert_awaited_once_with(vm_info)


def test_renew_default_preserve_keys_true(tmp_path):
    """preserve_keys defaults to True — ensure _renew_service_cert is used."""
    manager = _make_manager(tmp_path)
    manager.generator._renew_service_cert.return_value = True

    vm_info = _make_vm_info(tmp_path, "redis")
    manager.config.get_vm_cert_info.return_value = vm_info

    with patch("pki.manager.VM_DEFINITIONS", {"redis": "192.168.1.10"}):
        result = asyncio.get_event_loop().run_until_complete(manager.renew(certificates=["redis"]))

    assert result is True
    manager.generator._renew_service_cert.assert_called_once()
    manager.generator._generate_service_cert.assert_not_called()


# ---------------------------------------------------------------------------
# renew() — preserve_keys=False (key rotation) path
# ---------------------------------------------------------------------------


def test_renew_rotate_keys_calls_generate_service_cert(tmp_path):
    manager = _make_manager(tmp_path)
    manager.generator._generate_service_cert.return_value = True

    vm_info = _make_vm_info(tmp_path, "redis")
    manager.config.get_vm_cert_info.return_value = vm_info

    with patch("pki.manager.VM_DEFINITIONS", {"redis": "192.168.1.10"}):
        result = asyncio.get_event_loop().run_until_complete(manager.renew(certificates=["redis"], preserve_keys=False))

    assert result is True
    manager.generator._generate_service_cert.assert_called_once_with(vm_info, force=True)
    manager.generator._renew_service_cert.assert_not_called()
    manager.distributor._distribute_to_vm.assert_awaited_once_with(vm_info)


# ---------------------------------------------------------------------------
# renew() — failure propagation
# ---------------------------------------------------------------------------


def test_renew_preserve_keys_failure_returns_false(tmp_path):
    manager = _make_manager(tmp_path)
    manager.generator._renew_service_cert.return_value = False

    vm_info = _make_vm_info(tmp_path, "redis")
    manager.config.get_vm_cert_info.return_value = vm_info

    with patch("pki.manager.VM_DEFINITIONS", {"redis": "192.168.1.10"}):
        result = asyncio.get_event_loop().run_until_complete(manager.renew(certificates=["redis"], preserve_keys=True))

    assert result is False
    # Distribution must NOT be called when cert generation failed
    manager.distributor._distribute_to_vm.assert_not_awaited()


def test_renew_rotate_keys_failure_returns_false(tmp_path):
    manager = _make_manager(tmp_path)
    manager.generator._generate_service_cert.return_value = False

    vm_info = _make_vm_info(tmp_path, "redis")
    manager.config.get_vm_cert_info.return_value = vm_info

    with patch("pki.manager.VM_DEFINITIONS", {"redis": "192.168.1.10"}):
        result = asyncio.get_event_loop().run_until_complete(manager.renew(certificates=["redis"], preserve_keys=False))

    assert result is False
    manager.distributor._distribute_to_vm.assert_not_awaited()


# ---------------------------------------------------------------------------
# renew() — unknown cert name is skipped, not a hard failure
# ---------------------------------------------------------------------------


def test_renew_unknown_cert_name_skipped(tmp_path):
    manager = _make_manager(tmp_path)

    with patch("pki.manager.VM_DEFINITIONS", {}):
        result = asyncio.get_event_loop().run_until_complete(manager.renew(certificates=["unknown-vm"]))

    assert result is True
    manager.generator._renew_service_cert.assert_not_called()
    manager.generator._generate_service_cert.assert_not_called()


# ---------------------------------------------------------------------------
# CertificateGenerator._renew_service_cert — unit tests
# ---------------------------------------------------------------------------


def test_renew_service_cert_missing_key_returns_false(tmp_path):
    config = MagicMock(spec=TLSConfig)
    config.ca_cert_path = tmp_path / "ca-cert.pem"
    config.ca_key_path = tmp_path / "ca-key.pem"
    config.cert_validity_days = 365
    config.key_size = 2048
    config.country = "US"
    config.organization = "AutoBot"

    gen = CertificateGenerator(config=config)
    vm_info = _make_vm_info(tmp_path, "redis")
    # key_path does NOT exist

    result = gen._renew_service_cert(vm_info)

    assert result is False


def test_renew_service_cert_preserves_key_file(tmp_path):
    """_renew_service_cert must NOT overwrite the existing key file."""
    config = MagicMock(spec=TLSConfig)
    config.ca_cert_path = tmp_path / "ca-cert.pem"
    config.ca_key_path = tmp_path / "ca-key.pem"
    config.cert_validity_days = 365
    config.key_size = 2048
    config.country = "US"
    config.organization = "AutoBot"

    gen = CertificateGenerator(config=config)
    vm_info = _make_vm_info(tmp_path, "redis")

    # Plant a sentinel key file
    sentinel = b"EXISTING_KEY_CONTENT"
    vm_info.key_path.write_bytes(sentinel)

    # Stub out OpenSSL calls: CSR succeeds, signing succeeds, cert file created
    def fake_generate_csr(key_path, csr_path, conf_path, vm_name):
        csr_path.write_text("CSR", encoding="utf-8")
        return True

    def fake_sign_certificate(csr_path, cert_path, *args, **kwargs):
        cert_path.write_text("CERT", encoding="utf-8")
        import os

        os.chmod(cert_path, 0o644)
        return True

    with (
        patch("pki.generator._write_openssl_config"),
        patch("pki.generator._generate_csr", side_effect=fake_generate_csr),
        patch("pki.generator._sign_certificate", side_effect=fake_sign_certificate),
    ):
        result = gen._renew_service_cert(vm_info)

    assert result is True
    # The key file must be untouched
    assert vm_info.key_path.read_bytes() == sentinel
    # The cert file must have been written
    assert vm_info.cert_path.read_text(encoding="utf-8") == "CERT"
