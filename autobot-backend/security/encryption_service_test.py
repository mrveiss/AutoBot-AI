#!/usr/bin/env python3
"""
Unit tests for the EncryptionService module.
"""

import os
import unittest
from unittest.mock import patch

from encryption_service import (
    EncryptionService,
    decrypt_data,
    encrypt_data,
    is_encryption_enabled,
)


class TestEncryptionService(unittest.TestCase):
    """Test cases for EncryptionService."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_key = "test_master_key_for_encryption_testing_12345678"
        self.service = EncryptionService(self.test_key)

    def test_initialization_with_key(self):
        """Test service initialization with provided key."""
        service = EncryptionService("test_key_123")
        self.assertIsNotNone(service.master_key)

    @patch.dict(os.environ, {}, clear=True)
    def test_initialization_without_key_fails(self):
        """Test service initialization fails without key."""
        with self.assertRaises(ValueError):
            EncryptionService()

    @patch.dict(os.environ, {"AUTOBOT_ENCRYPTION_KEY": "env_test_key"})
    def test_initialization_from_environment(self):
        """Test service initialization from environment variable."""
        service = EncryptionService()
        self.assertEqual(service.master_key, "env_test_key")

    def test_encrypt_decrypt_string(self):
        """Test basic string encryption and decryption."""
        original = "This is a test message for encryption"

        # Encrypt
        encrypted = self.service.encrypt(original)
        self.assertIsInstance(encrypted, str)
        self.assertNotEqual(encrypted, original)

        # Decrypt
        decrypted = self.service.decrypt(encrypted)
        self.assertEqual(decrypted, original)

    def test_encrypt_decrypt_bytes(self):
        """Test bytes encryption and decryption."""
        original = b"This is test binary data \x00\x01\x02"

        # Encrypt
        encrypted = self.service.encrypt(original)
        self.assertIsInstance(encrypted, str)

        # Decrypt
        decrypted = self.service.decrypt(encrypted)
        self.assertEqual(decrypted.encode("utf-8"), original)

    def test_encrypt_decrypt_json(self):
        """Test JSON encryption and decryption."""
        original = {
            "user": "test_user",
            "message": "Hello, world!",
            "metadata": {"timestamp": 1234567890, "encrypted": True},
        }

        # Encrypt
        encrypted = self.service.encrypt_json(original)
        self.assertIsInstance(encrypted, str)

        # Decrypt
        decrypted = self.service.decrypt_json(encrypted)
        self.assertEqual(decrypted, original)

    def test_encryption_randomness(self):
        """Test that encryption produces different outputs for same input."""
        original = "Same message encrypted multiple times"

        encrypted1 = self.service.encrypt(original)
        encrypted2 = self.service.encrypt(original)

        # Should be different due to random salt/nonce
        self.assertNotEqual(encrypted1, encrypted2)

        # But both should decrypt to same original
        self.assertEqual(self.service.decrypt(encrypted1), original)
        self.assertEqual(self.service.decrypt(encrypted2), original)

    def test_is_encrypted_detection(self):
        """Test detection of encrypted data."""
        original = "Test message"
        encrypted = self.service.encrypt(original)

        self.assertTrue(self.service.is_encrypted(encrypted))
        self.assertFalse(self.service.is_encrypted(original))
        self.assertFalse(self.service.is_encrypted("definitely not encrypted"))

    def test_invalid_decryption_data(self):
        """Test decryption with invalid data raises errors."""
        with self.assertRaises(ValueError):
            self.service.decrypt("invalid_base64_data")

        with self.assertRaises(ValueError):
            self.service.decrypt("dGVzdA==")  # Valid base64 but too short

    def test_wrong_key_decryption_fails(self):
        """Test decryption fails with wrong key."""
        original = "Secret message"
        encrypted = self.service.encrypt(original)

        # Try to decrypt with different key
        wrong_service = EncryptionService("different_key_123456")
        with self.assertRaises(ValueError):
            wrong_service.decrypt(encrypted)

    def test_generate_key(self):
        """Test secure key generation."""
        key1 = self.service.generate_key()
        key2 = self.service.generate_key()

        self.assertIsInstance(key1, str)
        self.assertIsInstance(key2, str)
        self.assertGreaterEqual(len(key1), 64)  # Should be at least 64 chars
        self.assertNotEqual(key1, key2)  # Should be different

    def test_key_info(self):
        """Test key information retrieval."""
        info = self.service.get_key_info()

        self.assertEqual(info["algorithm"], "AES-256-GCM")
        self.assertEqual(info["key_derivation"], "PBKDF2-SHA256")
        self.assertEqual(info["iterations"], 100000)
        self.assertEqual(info["key_length"], len(self.test_key))
        self.assertIn("key_hash_prefix", info)

    def test_empty_string_encryption(self):
        """Test encryption of empty string."""
        original = ""
        encrypted = self.service.encrypt(original)
        decrypted = self.service.decrypt(encrypted)
        self.assertEqual(decrypted, original)

    def test_unicode_encryption(self):
        """Test encryption of unicode characters."""
        original = "Testing unicode: 🔒🔑 héllo wørld 中文"
        encrypted = self.service.encrypt(original)
        decrypted = self.service.decrypt(encrypted)
        self.assertEqual(decrypted, original)

    def test_large_data_encryption(self):
        """Test encryption of large data."""
        original = "Large data test: " + "x" * 10000  # ~10KB
        encrypted = self.service.encrypt(original)
        decrypted = self.service.decrypt(encrypted)
        self.assertEqual(decrypted, original)


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions."""

    @patch.dict(os.environ, {"AUTOBOT_ENCRYPTION_KEY": "test_key_for_convenience"})
    def test_encrypt_decrypt_data_string(self):
        """Test convenience functions with string data."""
        original = "Test message for convenience functions"

        encrypted = encrypt_data(original)
        decrypted = decrypt_data(encrypted)

        self.assertEqual(decrypted, original)

    @patch.dict(os.environ, {"AUTOBOT_ENCRYPTION_KEY": "test_key_for_convenience"})
    def test_encrypt_decrypt_data_json(self):
        """Test convenience functions with JSON data."""
        original = {"message": "test", "value": 42}

        encrypted = encrypt_data(original)
        decrypted = decrypt_data(encrypted, as_json=True)

        self.assertEqual(decrypted, original)


class TestConfigurationIntegration(unittest.TestCase):
    """Test integration with configuration system."""

    @patch("src.config.config")
    def test_is_encryption_enabled_true(self, mock_config):
        """Test encryption enabled check returns True."""
        mock_config.get_nested.return_value = True
        self.assertTrue(is_encryption_enabled())
        mock_config.get_nested.assert_called_with("security.enable_encryption", False)

    @patch("src.config.config")
    def test_is_encryption_enabled_false(self, mock_config):
        """Test encryption enabled check returns False."""
        mock_config.get_nested.return_value = False
        self.assertFalse(is_encryption_enabled())
        mock_config.get_nested.assert_called_with("security.enable_encryption", False)


if __name__ == "__main__":
    unittest.main()
