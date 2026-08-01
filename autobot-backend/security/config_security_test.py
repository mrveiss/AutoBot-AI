# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Security tests for configuration management
Tests security aspects of configuration loading, environment variables, and sensitive data handling
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from autobot_shared.logging_manager import get_logger
from config.loader import load_yaml_config
from config.manager import ConfigManager as ConfigManager


class TestConfigurationSecurity:
    """Test security aspects of configuration management"""

    def test_config_file_path_traversal_protection(self):
        """Test protection against path traversal attacks in config files"""
        # #13087: ConfigManager no longer accepts config_file=<path> — its
        # constructor only takes config_dir (config/manager.py:72-76) and
        # always loads the fixed filename "config.yaml" from it, so an
        # attacker-controlled *file* path can no longer even reach the
        # constructor. The layer that actually handles arbitrary/malicious
        # file paths safely today is config.loader.load_yaml_config(): it
        # never executes anything and falls back to defaults for a
        # missing/unreadable/invalid path (loader.py:75-95). No production
        # caller ever passes a variable config_dir either (git grep confirms
        # only the "config" default is used) so this is the real
        # attack-relevant unit to exercise.
        malicious_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "/etc/shadow",
            "../../secret_config.yaml",
            "file:///etc/passwd",
        ]

        for malicious_path in malicious_paths:
            # Should handle malicious paths gracefully
            result = load_yaml_config(Path(malicious_path))

            # Should fall back to default config, not load/execute the
            # malicious path. LLM defaults live under backend.llm.local
            # since the #763 SSOT migration (config/defaults.py:36-48) —
            # there is no top-level "llm" key.
            assert result["backend"]["llm"]["local"]["provider"] == "ollama"

    def test_environment_variable_injection_protection(self):
        """Test protection against environment variable injection"""
        config_manager = ConfigManager()

        # Test with potentially malicious environment variables
        with patch.dict(
            os.environ,
            {
                "AUTOBOT_DANGEROUS_COMMAND": "rm -rf /",
                "AUTOBOT_SCRIPT_INJECTION": "$(malicious_command)",
                "AB_XSS_ATTEMPT": '<script>alert("xss")</script>',
                "SHELL_INJECTION": "; malicious_command; echo",
            },
        ):
            # Environment variables should be returned as-is but not executed
            dangerous_cmd = config_manager.get("dangerous.command")
            script_injection = config_manager.get("script.injection")
            xss_attempt = config_manager.get("xss.attempt")
            shell_injection = config_manager.get("shell.injection", "default")

            # Values should be retrieved but not interpreted as commands
            assert dangerous_cmd == "rm -rf /"  # Raw value, not executed
            assert script_injection == "$(malicious_command)"  # Not evaluated
            assert xss_attempt == '<script>alert("xss")</script>'  # Not sanitized at config level
            assert shell_injection == "default"  # Should use default if not found

    def test_yaml_deserialization_safety(self):
        """Test YAML deserialization safety against malicious payloads"""
        # Create malicious YAML payloads
        malicious_yamls = [
            # Python object instantiation attempt
            """
!!python/object/apply:os.system
args: ["echo 'malicious command executed'"]
""",
            # Module import attempt
            """
!!python/module:subprocess
""",
            # Function execution attempt
            """
!!python/object/apply:subprocess.call
args: [["echo", "exploit"]]
""",
        ]

        for malicious_yaml in malicious_yamls:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                f.write(malicious_yaml)
                malicious_file = f.name

            try:
                # #13087: exercise the actual safety layer directly.
                # ConfigManager no longer accepts config_file=<path> nor
                # exposes get_all_config(); config.loader.load_yaml_config()
                # uses yaml.safe_load() (refuses !!python/object tags) and
                # catches every exception, falling back to defaults.
                result = load_yaml_config(Path(malicious_file))

                # Should fall back to defaults, not execute malicious code
                assert "backend" in result  # Should have default config
                assert result["backend"]["llm"]["local"]["provider"] == "ollama"

            finally:
                os.unlink(malicious_file)

    def test_sensitive_data_exposure_prevention(self):
        """Test that sensitive data is not accidentally exposed"""
        config_manager = ConfigManager()

        # Set some sensitive data
        config_manager.set("database.password", "super_secret_password")
        config_manager.set("api.keys.openai", "sk-very-secret-key")
        config_manager.set("security.secrets_key", "encryption_key_123")

        # Test that get_all_config doesn't expose everything by default in logs
        all_config = config_manager.get_all_config()

        # Sensitive data should be accessible via direct key access
        assert config_manager.get("database.password") == "super_secret_password"
        assert config_manager.get("api.keys.openai") == "sk-very-secret-key"

        # But should be present in all_config (caller responsible for handling)
        assert "database" in all_config
        assert all_config["database"]["password"] == "super_secret_password"

    def test_config_validation_against_malicious_values(self):
        """Test config validation prevents malicious configuration values"""
        config_manager = ConfigManager()

        # Test setting potentially malicious values
        malicious_configs = {
            "deployment.host": "evil.malicious.com",
            "redis.host": "attacker-redis.com",
            "llm.ollama.base_url": "http://malicious-llm.evil.com",
            "security.blocked_commands": [
                "rm -rf",
                "format",
                "delete",
            ],  # This should be OK
            "security.allowed_commands": ["rm -rf /"],  # This should be flagged
        }

        for key, value in malicious_configs.items():
            config_manager.set(key, value)

        # Validation should identify potential issues
        issues = config_manager.validate_config()

        # Should validate without throwing errors
        assert isinstance(issues, list)
        # Note: The current validation doesn't check for malicious hosts,
        # but it should at least complete without errors

    def test_config_file_permissions_handling(self):
        """Test handling of config files with various permissions"""
        import stat

        # #13087: ConfigManager only takes config_dir + a fixed "config.yaml"
        # filename (config/manager.py:72-76); write the file under that
        # exact name inside an isolated temp directory. LLM defaults live
        # under backend.llm.local since the #763 SSOT migration.
        tmp_dir = tempfile.mkdtemp()
        restricted_file = os.path.join(tmp_dir, "config.yaml")
        with open(restricted_file, "w", encoding="utf-8") as f:
            f.write("""
backend:
  llm:
    local:
      provider: "test_provider"
""")

        try:
            # Make file readable only by owner
            os.chmod(restricted_file, stat.S_IRUSR)

            # Should handle restricted permissions gracefully
            config_manager = ConfigManager(config_dir=tmp_dir)

            # Should either load the file or fall back to defaults
            provider = config_manager.get_nested("backend.llm.local.provider")
            assert provider in [
                "test_provider",
                "ollama",
            ]  # Either loaded or default

        finally:
            # Clean up - need to restore permissions to delete
            os.chmod(restricted_file, stat.S_IRUSR | stat.S_IWUSR)
            os.unlink(restricted_file)
            os.rmdir(tmp_dir)

    def test_environment_variable_name_sanitization(self):
        """Test that environment variable names are properly sanitized"""
        config_manager = ConfigManager()

        # Test with various potentially problematic env var names
        with patch.dict(
            os.environ,
            {
                "AUTOBOT_NORMAL_KEY": "normal_value",
                "AUTOBOT_KEY_WITH_DOTS": "dotted_value",
                "AUTOBOT_KEY-WITH-DASHES": "dashed_value",
                "AUTOBOT_KEY_WITH_123": "numbered_value",
            },
        ):
            # Normal key should work
            assert config_manager.get("normal.key") == "normal_value"

            # Keys with special characters should be handled
            # The _get_env_var method should handle conversion properly
            dotted_value = config_manager.get("key.with.dots")
            assert dotted_value in ["dotted_value", None]  # Depends on conversion logic

    def test_config_injection_via_yaml_anchors(self):
        """Test protection against YAML anchor-based injection"""
        yaml_with_anchors = """
defaults: &defaults
  dangerous_command: "rm -rf /"

production:
  <<: *defaults
  safe_setting: "production_value"
"""

        # #13087: ConfigManager only takes config_dir + fixed "config.yaml".
        tmp_dir = tempfile.mkdtemp()
        anchor_file = os.path.join(tmp_dir, "config.yaml")
        with open(anchor_file, "w", encoding="utf-8") as f:
            f.write(yaml_with_anchors)

        try:
            config_manager = ConfigManager(config_dir=tmp_dir)

            # Should handle YAML anchors without security issues.
            # get_config_section() (config/service_config.py:189, a plain
            # get_nested(section, {}) delegate) is the current equivalent of
            # the removed get_section().
            production_config = config_manager.get_config_section("production")

            # Values should be loaded but not cause security issues
            if production_config:
                dangerous_cmd = production_config.get("dangerous_command")
                if dangerous_cmd:
                    # Should be a string value, not executed
                    assert isinstance(dangerous_cmd, str)
                    assert dangerous_cmd == "rm -rf /"

        finally:
            os.unlink(anchor_file)
            os.rmdir(tmp_dir)

    def test_config_size_limits(self):
        """Test handling of excessively large configuration files"""
        # Create a very large config file
        large_config = "large_section:\n"
        for i in range(10000):
            large_config += f"  key_{i}: 'value_{i}'\n"

        # #13087: ConfigManager only takes config_dir + fixed "config.yaml".
        tmp_dir = tempfile.mkdtemp()
        large_file = os.path.join(tmp_dir, "config.yaml")
        with open(large_file, "w", encoding="utf-8") as f:
            f.write(large_config)

        try:
            # Should handle large files without crashing
            config_manager = ConfigManager(config_dir=tmp_dir)

            # Should load successfully or fall back to defaults. LLM
            # defaults live under backend.llm.local (#763 SSOT migration).
            provider = config_manager.get_nested("backend.llm.local.provider")
            assert isinstance(provider, str)

        finally:
            os.unlink(large_file)
            os.rmdir(tmp_dir)

    def test_config_circular_reference_protection(self):
        """Test protection against circular references in config"""
        circular_yaml = """
section_a:
  reference: &ref_a
    circular_ref: *ref_b

section_b:
  reference: &ref_b
    circular_ref: *ref_a
"""

        # #13087: ConfigManager only takes config_dir + fixed "config.yaml".
        # This YAML is actually invalid (an alias referencing an anchor not
        # yet defined at that point), so yaml.safe_load() raises inside
        # load_yaml_config(), which catches it and falls back to defaults
        # rather than propagating or recursing.
        tmp_dir = tempfile.mkdtemp()
        circular_file = os.path.join(tmp_dir, "config.yaml")
        with open(circular_file, "w", encoding="utf-8") as f:
            f.write(circular_yaml)

        try:
            # Should handle circular/forward-referencing anchors gracefully
            config_manager = ConfigManager(config_dir=tmp_dir)

            # Should not cause infinite recursion
            config_manager.get_config_section("section_a")

            # Should fall back to sane defaults, not get stuck/corrupted
            assert config_manager.get_nested("backend.llm.local.provider") == "ollama"

        finally:
            os.unlink(circular_file)
            os.rmdir(tmp_dir)

    def test_environment_variable_type_confusion(self):
        """Test protection against type confusion in environment variables"""
        config_manager = ConfigManager()

        # Test with environment variables that might cause type confusion
        with patch.dict(
            os.environ,
            {
                "AUTOBOT_FAKE_BOOL": "True",  # Capital T, might be confused with bool
                "AUTOBOT_FAKE_INT": "123abc",  # Starts with number but has letters
                "AUTOBOT_FAKE_FLOAT": "3.14.159",  # Invalid float format
                "AUTOBOT_FAKE_LIST": "item1,item2,",  # Trailing comma
            },
        ):
            # Should handle type parsing errors gracefully
            fake_bool = config_manager.get("fake.bool")
            fake_int = config_manager.get("fake.int")
            fake_float = config_manager.get("fake.float")
            fake_list = config_manager.get("fake.list")

            # Should return parsed values or original strings without errors
            assert fake_bool in [
                True,
                "True",
            ]  # Might be parsed as bool or kept as string
            assert fake_int == "123abc"  # Should remain string due to letters
            assert fake_float == "3.14.159"  # Should remain string due to invalid format
            assert isinstance(fake_list, (list, str))  # Should handle trailing comma

    def test_config_backup_and_recovery_security(self):
        """Test security of config backup and recovery operations"""
        # #13087: ConfigManager exposes no save(path)/get_section(); the
        # current persistence primitive is save_settings(), which always
        # writes <config_dir>/settings.json (config/sync_ops.py:77-92).
        # Round-trip through an isolated config_dir instead of an arbitrary
        # backup file path.
        tmp_dir = tempfile.mkdtemp()
        settings_file = os.path.join(tmp_dir, "settings.json")

        try:
            config_manager = ConfigManager(config_dir=tmp_dir)

            # Set some sensitive configuration
            config_manager.set("sensitive.api_key", "very_secret_key")
            config_manager.set("sensitive.database_password", "super_secret_db_pass")

            # Persist it
            config_manager.save_settings()

            # Verify file was created
            assert os.path.exists(settings_file)
            assert os.path.isfile(settings_file)

            # Create a fresh config manager reading the same directory —
            # simulates "recovery" from the persisted state
            backup_config_manager = ConfigManager(config_dir=tmp_dir)

            # Verify sensitive data was preserved
            assert backup_config_manager.get("sensitive.api_key") == "very_secret_key"
            assert backup_config_manager.get("sensitive.database_password") == "super_secret_db_pass"

        finally:
            if os.path.exists(settings_file):
                os.unlink(settings_file)
            os.rmdir(tmp_dir)


class TestSecretsHandlingInConfig:
    """Test secure handling of secrets in configuration"""

    def test_secrets_not_logged(self):
        """Test that secrets are not accidentally logged"""
        import logging
        from io import StringIO

        # Create a string buffer to capture log output
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)

        # Get the config logger and add our handler
        config_logger = get_logger("src.utils.config_manager")
        config_logger.addHandler(handler)
        config_logger.setLevel(logging.DEBUG)

        try:
            config_manager = ConfigManager()
            config_manager.set("secret.api_key", "sk-very-secret-key-12345")
            config_manager.set("secret.password", "super_secret_password")

            # Get the log output
            log_output = log_capture.getvalue()

            # Secrets should not appear in logs
            assert "sk-very-secret-key-12345" not in log_output
            assert "super_secret_password" not in log_output

        finally:
            config_logger.removeHandler(handler)

    def test_config_serialization_safety(self):
        """Test that config serialization doesn't expose secrets inadvertently"""
        import json

        import yaml

        config_manager = ConfigManager()
        config_manager.set("public.setting", "public_value")
        config_manager.set("secret.api_key", "secret_key_value")

        # Get all config
        all_config = config_manager.get_all_config()

        # Verify secrets are in the config (as expected)
        assert all_config["secret"]["api_key"] == "secret_key_value"

        # Test JSON serialization
        json_str = json.dumps(all_config)
        assert "secret_key_value" in json_str  # Should be there (caller's responsibility to handle)

        # Test YAML serialization
        yaml_str = yaml.dump(all_config)
        assert "secret_key_value" in yaml_str  # Should be there (caller's responsibility to handle)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
