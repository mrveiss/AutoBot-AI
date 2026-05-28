# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
"""
Unit tests for ConfigFileExtractor (MVA-1433).

Covers:
  - YAML top-level scalar extraction
  - TOML top-level scalar extraction
  - JSON top-level scalar extraction
  - Non-config path → no output
  - Malformed content → empty list (no exception)
  - Error field set → empty list
  - Nested values are skipped (only top-level scalars)
  - Integration: config contradiction detectable vs run_command port
"""

from __future__ import annotations

import pytest

from agent_loop.extractors.config_file import ConfigFileExtractor


@pytest.fixture
def extractor() -> ConfigFileExtractor:
    return ConfigFileExtractor()


# ---------------------------------------------------------------------------
# YAML
# ---------------------------------------------------------------------------


def test_yaml_extracts_top_level_scalars(extractor: ConfigFileExtractor) -> None:
    output = {
        "path": "/app/config.yaml",
        "content": "port: 8080\nhost: localhost\ndebug: true\n",
    }
    results = extractor.extract(output)
    keys = {k for k, _, _ in results}
    assert "config:/app/config.yaml/port" in keys
    assert "config:/app/config.yaml/host" in keys
    assert "config:/app/config.yaml/debug" in keys


def test_yaml_values_and_confidence(extractor: ConfigFileExtractor) -> None:
    output = {
        "path": "/app/config.yml",
        "content": "port: 3000\n",
    }
    results = extractor.extract(output)
    assert len(results) == 1
    key, value, confidence = results[0]
    assert key == "config:/app/config.yml/port"
    assert value == 3000
    assert confidence == pytest.approx(0.9)


def test_yaml_skips_nested_values(extractor: ConfigFileExtractor) -> None:
    output = {
        "path": "/srv/app.yaml",
        "content": "port: 8080\ndatabase:\n  host: db\n  port: 5432\n",
    }
    results = extractor.extract(output)
    keys = {k for k, _, _ in results}
    assert "config:/srv/app.yaml/port" in keys
    # nested keys must not be extracted
    assert not any("database" in k for k in keys)


def test_yaml_malformed_returns_empty(extractor: ConfigFileExtractor) -> None:
    output = {
        "path": "/app/config.yaml",
        "content": "port: [unclosed",
    }
    results = extractor.extract(output)
    assert results == []


def test_yaml_non_dict_root_returns_empty(extractor: ConfigFileExtractor) -> None:
    output = {
        "path": "/app/config.yaml",
        "content": "- item1\n- item2\n",
    }
    results = extractor.extract(output)
    assert results == []


# ---------------------------------------------------------------------------
# TOML
# ---------------------------------------------------------------------------


def test_toml_extracts_top_level_scalars(extractor: ConfigFileExtractor) -> None:
    output = {
        "path": "/app/config.toml",
        "content": 'port = 9000\nhost = "0.0.0.0"\nenabled = true\n',
    }
    results = extractor.extract(output)
    keys = {k for k, _, _ in results}
    assert "config:/app/config.toml/port" in keys
    assert "config:/app/config.toml/host" in keys
    assert "config:/app/config.toml/enabled" in keys


def test_toml_skips_table_sections(extractor: ConfigFileExtractor) -> None:
    output = {
        "path": "/app/settings.toml",
        "content": 'port = 8080\n\n[database]\nhost = "db"\n',
    }
    results = extractor.extract(output)
    keys = {k for k, _, _ in results}
    assert "config:/app/settings.toml/port" in keys
    assert not any("database" in k for k in keys)


def test_toml_malformed_returns_empty(extractor: ConfigFileExtractor) -> None:
    output = {
        "path": "/app/bad.toml",
        "content": "port = [[[",
    }
    results = extractor.extract(output)
    assert results == []


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def test_json_extracts_top_level_scalars(extractor: ConfigFileExtractor) -> None:
    output = {
        "path": "/etc/app/config.json",
        "content": '{"port": 8080, "host": "localhost", "debug": false}',
    }
    results = extractor.extract(output)
    keys = {k for k, _, _ in results}
    assert "config:/etc/app/config.json/port" in keys
    assert "config:/etc/app/config.json/host" in keys
    assert "config:/etc/app/config.json/debug" in keys


def test_json_skips_nested_objects(extractor: ConfigFileExtractor) -> None:
    output = {
        "path": "/etc/config.json",
        "content": '{"port": 8080, "db": {"host": "localhost"}}',
    }
    results = extractor.extract(output)
    keys = {k for k, _, _ in results}
    assert "config:/etc/config.json/port" in keys
    assert not any("db" in k for k in keys)


def test_json_array_root_returns_empty(extractor: ConfigFileExtractor) -> None:
    output = {
        "path": "/etc/config.json",
        "content": '[{"port": 8080}]',
    }
    results = extractor.extract(output)
    assert results == []


def test_json_malformed_returns_empty(extractor: ConfigFileExtractor) -> None:
    output = {
        "path": "/etc/config.json",
        "content": '{"port": 8080',
    }
    results = extractor.extract(output)
    assert results == []


# ---------------------------------------------------------------------------
# Guard conditions
# ---------------------------------------------------------------------------


def test_non_config_extension_returns_empty(extractor: ConfigFileExtractor) -> None:
    output = {
        "path": "/app/server.py",
        "content": "port = 8080\n",
    }
    results = extractor.extract(output)
    assert results == []


def test_non_dict_tool_output_returns_empty(extractor: ConfigFileExtractor) -> None:
    assert extractor.extract("not a dict") == []
    assert extractor.extract(None) == []
    assert extractor.extract(42) == []


def test_missing_path_returns_empty(extractor: ConfigFileExtractor) -> None:
    output = {"content": "port: 8080\n"}
    results = extractor.extract(output)
    assert results == []


def test_error_field_set_returns_empty(extractor: ConfigFileExtractor) -> None:
    output = {
        "path": "/app/config.yaml",
        "error": "file not found",
        "content": "port: 8080\n",
    }
    results = extractor.extract(output)
    assert results == []


def test_empty_content_returns_empty(extractor: ConfigFileExtractor) -> None:
    output = {
        "path": "/app/config.yaml",
        "content": "   ",
    }
    results = extractor.extract(output)
    assert results == []


def test_alternative_path_fields(extractor: ConfigFileExtractor) -> None:
    """file_path and filename fields should also trigger extraction."""
    output_file_path = {
        "file_path": "/tmp/settings.yaml",
        "content": "timeout: 30\n",
    }
    results = extractor.extract(output_file_path)
    assert any(k == "config:/tmp/settings.yaml/timeout" for k, _, _ in results)

    output_filename = {
        "filename": "/tmp/settings.json",
        "content": '{"timeout": 30}',
    }
    results = extractor.extract(output_filename)
    assert any(k == "config:/tmp/settings.json/timeout" for k, _, _ in results)


# ---------------------------------------------------------------------------
# Contradiction scenario (Task 5 benchmark)
# ---------------------------------------------------------------------------


def test_config_port_contradicts_process_port() -> None:
    """Config file port 8080 vs run_command port 3000 → values differ.

    This test verifies the raw key produced by ConfigFileExtractor so that
    BeliefStateUpdater can detect the contradiction when run_command reports
    a different port via the run_command:port/* key family.
    """
    extractor = ConfigFileExtractor()
    output = {
        "path": "/app/config.yaml",
        "content": "port: 8080\n",
    }
    results = extractor.extract(output)
    assert len(results) == 1
    key, value, confidence = results[0]
    assert key == "config:/app/config.yaml/port"
    assert value == 8080
    assert confidence == pytest.approx(0.9)
