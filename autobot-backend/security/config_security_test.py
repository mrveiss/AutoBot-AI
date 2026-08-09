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
from config.loader import _convert_env_value, load_yaml_config
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
        """Environment overrides are allowlisted, and applied verbatim.

        #13162: this test used to assume ConfigManager derived config keys
        from arbitrary ``AUTOBOT_*`` variable names. It never did, and it
        must not: ``config.loader.apply_env_overrides()`` walks a fixed
        ``ENV_VAR_MAPPINGS`` allowlist (loader.py:27-71), which *is* the
        injection protection. Pin both halves — unmapped names are ignored
        entirely, and a mapped name carrying a shell payload is stored as an
        inert string.
        """
        with patch.dict(
            os.environ,
            {
                "AUTOBOT_DANGEROUS_COMMAND": "rm -rf /",
                "AUTOBOT_SCRIPT_INJECTION": "$(malicious_command)",
                "AB_XSS_ATTEMPT": '<script>alert("xss")</script>',
                "SHELL_INJECTION": "; malicious_command; echo",
                # Allowlisted name (ENV_VAR_MAPPINGS -> ["ui", "theme"]).
                "AUTOBOT_UI_THEME": "$(malicious_command)",
            },
        ):
            # Constructed inside the patch: overrides are applied on load.
            config_manager = ConfigManager()

            # Unmapped names never become config keys, under any spelling.
            assert config_manager.get_nested("dangerous.command") is None
            assert config_manager.get_nested("script.injection") is None
            assert config_manager.get_nested("xss.attempt") is None
            assert config_manager.get("shell.injection", "default") == "default"
            assert "AUTOBOT_DANGEROUS_COMMAND" not in config_manager.to_dict()

            # Mapped names land at their mapped path as raw, unevaluated text.
            assert config_manager.get_nested("ui.theme") == "$(malicious_command)"

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

        # #13162: set()/get() are the flat key pair and set_nested()/
        # get_nested() the dot-notation pair (config/sync_ops.py:36-76).
        # Nested assertions need the nested setters.
        config_manager.set_nested("database.password", "super_secret_password")
        config_manager.set_nested("api.keys.openai", "sk-very-secret-key")
        config_manager.set_nested("security.secrets_key", "encryption_key_123")

        # #13162: get_all_config() never existed; to_dict() (config/
        # sync_ops.py:133) is the whole-config accessor.
        all_config = config_manager.to_dict()

        # Sensitive data should be accessible via direct key access
        assert config_manager.get_nested("database.password") == "super_secret_password"
        assert config_manager.get_nested("api.keys.openai") == "sk-very-secret-key"

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
            config_manager.set_nested(key, value)

        # Validation should complete and report structurally, not raise.
        # #13162: validate_config() returns a status *dict* whose "issues"
        # key holds the list (config/validation.py:218-237) — the old
        # `isinstance(status, list)` assertion predates that shape.
        status = config_manager.validate_config()

        assert isinstance(status, dict)
        assert status["config_loaded"] is True
        assert isinstance(status["issues"], list)
        # Malicious values are stored verbatim, never executed or resolved.
        assert config_manager.get_nested("redis.host") == "attacker-redis.com"
        assert config_manager.get_nested("security.allowed_commands") == ["rm -rf /"]

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
        """Odd env var names cannot manufacture config keys.

        #13162: name matching is exact against ENV_VAR_MAPPINGS, so no
        name — however it is punctuated — is ever *derived* into a config
        path. Loading with these variables present must also not raise.
        """
        with patch.dict(
            os.environ,
            {
                "AUTOBOT_NORMAL_KEY": "normal_value",
                "AUTOBOT_KEY_WITH_DOTS": "dotted_value",
                "AUTOBOT_KEY-WITH-DASHES": "dashed_value",
                "AUTOBOT_KEY_WITH_123": "numbered_value",
            },
        ):
            config_manager = ConfigManager()

            for derived_key in (
                "normal.key",
                "key.with.dots",
                "key-with-dashes",
                "key.with.123",
            ):
                assert config_manager.get_nested(derived_key) is None
                assert config_manager.get(derived_key) is None

            # The load itself stays healthy — defaults are still in place.
            assert config_manager.get_nested("backend.llm.local.provider") == "ollama"

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
        """Env value coercion is total and never raises.

        #13162: the old body read unmapped ``AUTOBOT_FAKE_*`` names, which
        never enter config at all. The coercion that *does* run on every
        allowlisted override is ``config.loader._convert_env_value()``
        (loader.py:158-173): "true"/"false" -> bool, all-digits -> int,
        anything else -> the untouched string. Exercise that directly with
        the ambiguous payloads.
        """
        assert _convert_env_value("True") is True  # case-insensitive bool
        assert _convert_env_value("false") is False
        assert _convert_env_value("123") == 123  # pure digits -> int
        assert _convert_env_value("123abc") == "123abc"  # letters -> stays a string
        assert _convert_env_value("3.14.159") == "3.14.159"  # invalid float -> string
        assert _convert_env_value("item1,item2,") == "item1,item2,"  # never split
        assert _convert_env_value("") == ""  # empty is not an error

        # And the mapped path receives exactly that coerced value.
        with patch.dict(os.environ, {"AUTOBOT_REDIS_ENABLED": "false"}):
            config_manager = ConfigManager()
            assert config_manager.get_nested("memory.redis.enabled") is False

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
        config_manager.set_nested("public.setting", "public_value")
        config_manager.set_nested("secret.api_key", "secret_key_value")

        # #13162: to_dict() is the whole-config accessor; get_all_config()
        # never existed on ConfigManager.
        all_config = config_manager.to_dict()

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
