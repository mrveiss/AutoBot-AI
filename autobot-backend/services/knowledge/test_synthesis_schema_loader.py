# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for synthesis_schema_loader.

Covers:
- Successful load from a valid YAML file
- Graceful fallback (empty schema) when the file is absent
- ValueError raised on unknown top-level collection keys
"""

import textwrap
from pathlib import Path

import pytest

from services.knowledge.synthesis_schema_loader import (
    CollectionConfig,
    SynthesisSchema,
    load_synthesis_schema,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(tmp_path: Path, content: str) -> Path:
    """Write YAML content to a temp file and return its path."""
    schema_file = tmp_path / "synthesis_schema.yaml"
    schema_file.write_text(textwrap.dedent(content), encoding="utf-8")
    return schema_file


VALID_YAML = """\
    collections:
      - name: architecture_adrs
        paths:
          - docs/architecture
          - docs/adr
        synthesis_target: autobot_synthesis_architecture
        prompt_template: |
          Summarise architecture docs.
          Documents: {documents}

      - name: api_reference
        paths:
          - docs/api
        synthesis_target: autobot_synthesis_api
        prompt_template: |
          Summarise API docs.
          Documents: {documents}

      - name: runbooks_operations
        paths:
          - docs/operations
        synthesis_target: autobot_synthesis_runbooks
        prompt_template: |
          Summarise runbooks.
          Documents: {documents}
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLoadSuccess:
    def test_returns_synthesis_schema(self, tmp_path):
        path = _write_yaml(tmp_path, VALID_YAML)
        schema = load_synthesis_schema(path)
        assert isinstance(schema, SynthesisSchema)

    def test_collection_count(self, tmp_path):
        path = _write_yaml(tmp_path, VALID_YAML)
        schema = load_synthesis_schema(path)
        assert len(schema.collections) == 3

    def test_first_collection_fields(self, tmp_path):
        path = _write_yaml(tmp_path, VALID_YAML)
        schema = load_synthesis_schema(path)
        col: CollectionConfig = schema.collections[0]
        assert col.name == "architecture_adrs"
        assert "docs/architecture" in col.paths
        assert col.synthesis_target == "autobot_synthesis_architecture"
        assert "{documents}" in col.prompt_template

    def test_all_collections_have_required_fields(self, tmp_path):
        path = _write_yaml(tmp_path, VALID_YAML)
        schema = load_synthesis_schema(path)
        for col in schema.collections:
            assert col.name
            assert col.paths
            assert col.synthesis_target
            assert col.prompt_template


class TestFallbackOnMissingFile:
    def test_returns_empty_schema(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        schema = load_synthesis_schema(missing)
        assert isinstance(schema, SynthesisSchema)
        assert schema.collections == []

    def test_no_exception_raised(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        # Should not raise
        load_synthesis_schema(missing)


class TestValidationError:
    def test_unknown_key_raises_value_error(self, tmp_path):
        bad_yaml = """\
            collections:
              - name: test_col
                paths:
                  - docs/test
                synthesis_target: autobot_test
                prompt_template: "test {documents}"
                unknown_key: should_fail
        """
        path = _write_yaml(tmp_path, bad_yaml)
        with pytest.raises(ValueError, match="unknown keys"):
            load_synthesis_schema(path)

    def test_missing_required_key_raises_value_error(self, tmp_path):
        incomplete_yaml = """\
            collections:
              - name: test_col
                paths:
                  - docs/test
                synthesis_target: autobot_test
        """
        path = _write_yaml(tmp_path, incomplete_yaml)
        with pytest.raises(ValueError, match="missing required keys"):
            load_synthesis_schema(path)

    def test_missing_collections_key_raises_value_error(self, tmp_path):
        bad_yaml = """\
            not_collections:
              - name: something
        """
        path = _write_yaml(tmp_path, bad_yaml)
        with pytest.raises(ValueError, match="collections"):
            load_synthesis_schema(path)


class TestPathExistenceWarnings:
    """load_synthesis_schema warns on missing paths but does not raise."""

    def _yaml_with_paths(self, *paths: str) -> str:
        paths_block = "\n".join(f"          - {p}" for p in paths)
        return (
            "collections:\n"
            "  - name: test_col\n"
            "    paths:\n"
            f"{paths_block}\n"
            "    synthesis_target: autobot_test\n"
            '    prompt_template: "test {documents}"\n'
        )

    def test_no_warning_for_existing_path(self, tmp_path, caplog):
        real_dir = tmp_path / "existing_docs"
        real_dir.mkdir()
        schema_path = _write_yaml(tmp_path, self._yaml_with_paths("existing_docs"))
        import logging
        with caplog.at_level(logging.WARNING):
            load_synthesis_schema(schema_path, repo_root=tmp_path)
        warnings = [r for r in caplog.records if r.levelname == "WARNING" and "does not exist" in r.message]
        assert warnings == [], f"Unexpected warnings: {[r.message for r in warnings]}"

    def test_warning_for_missing_path(self, tmp_path, caplog):
        schema_path = _write_yaml(tmp_path, self._yaml_with_paths("nonexistent_dir"))
        import logging
        with caplog.at_level(logging.WARNING):
            schema = load_synthesis_schema(schema_path, repo_root=tmp_path)
        # Schema still loads — no exception
        assert len(schema.collections) == 1
        warnings = [r for r in caplog.records if r.levelname == "WARNING" and "does not exist" in r.message]
        assert len(warnings) == 1
        assert "nonexistent_dir" in warnings[0].message

    def test_warning_per_missing_path_in_mixed_list(self, tmp_path, caplog):
        real_dir = tmp_path / "real_docs"
        real_dir.mkdir()
        schema_path = _write_yaml(
            tmp_path,
            self._yaml_with_paths("real_docs", "missing_one", "missing_two"),
        )
        import logging
        with caplog.at_level(logging.WARNING):
            schema = load_synthesis_schema(schema_path, repo_root=tmp_path)
        assert len(schema.collections) == 1
        warnings = [r for r in caplog.records if r.levelname == "WARNING" and "does not exist" in r.message]
        assert len(warnings) == 2
        missing_paths_warned = {w.message for w in warnings}
        assert any("missing_one" in m for m in missing_paths_warned)
        assert any("missing_two" in m for m in missing_paths_warned)
