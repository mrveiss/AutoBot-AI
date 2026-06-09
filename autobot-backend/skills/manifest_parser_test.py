# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for skills/manifest_parser.py (Issue #5063)."""

import pytest

from skills.manifest_parser import parse_manifest, validate_manifest

_VALID_MD = """\
---
name: my-skill
version: 1.0.0
description: A test skill
entrypoint: skill.py
category: testing
capabilities:
  - read
  - write
dependencies:
  - base-skill
tags:
  - test
author: mrveiss
license: MIT
homepage: https://example.com
trust_level_requested: sandboxed
---

# My Skill

Some documentation here.
"""

_MINIMAL_MD = """\
---
name: minimal
version: 0.1.0
description: Minimal skill
entrypoint: main.py
---
"""


class TestParseManifest:
    def test_valid_full_manifest(self) -> None:
        result = parse_manifest(_VALID_MD)
        assert result["name"] == "my-skill"
        assert result["version"] == "1.0.0"
        assert result["description"] == "A test skill"
        assert result["entrypoint"] == "skill.py"
        assert result["capabilities"] == ["read", "write"]
        assert result["trust_level_requested"] == "sandboxed"

    def test_valid_minimal_manifest(self) -> None:
        result = parse_manifest(_MINIMAL_MD)
        assert result["name"] == "minimal"
        assert result["version"] == "0.1.0"
        assert "capabilities" not in result

    def test_missing_front_matter_block(self) -> None:
        with pytest.raises(ValueError, match="front-matter block"):
            parse_manifest("# No front matter here\n\nJust text.")

    def test_invalid_yaml_raises_value_error(self) -> None:
        bad_yaml = "---\nname: [unclosed bracket\n---\n"
        with pytest.raises(ValueError, match="Invalid YAML"):
            parse_manifest(bad_yaml)

    def test_missing_required_field_name(self) -> None:
        md = "---\nversion: 1.0.0\ndescription: x\nentrypoint: skill.py\n---\n"
        with pytest.raises(ValueError, match="name"):
            parse_manifest(md)

    def test_missing_required_field_version(self) -> None:
        md = "---\nname: x\ndescription: x\nentrypoint: skill.py\n---\n"
        with pytest.raises(ValueError, match="version"):
            parse_manifest(md)

    def test_missing_required_field_description(self) -> None:
        md = "---\nname: x\nversion: 1.0.0\nentrypoint: skill.py\n---\n"
        with pytest.raises(ValueError, match="description"):
            parse_manifest(md)

    def test_missing_required_field_entrypoint(self) -> None:
        md = "---\nname: x\nversion: 1.0.0\ndescription: x\n---\n"
        with pytest.raises(ValueError, match="entrypoint"):
            parse_manifest(md)

    def test_non_mapping_yaml_raises(self) -> None:
        md = "---\n- item1\n- item2\n---\n"
        with pytest.raises(ValueError, match="mapping"):
            parse_manifest(md)

    def test_front_matter_not_at_start(self) -> None:
        md = "Some text\n---\nname: x\nversion: 1.0.0\n---\n"
        with pytest.raises(ValueError, match="front-matter block"):
            parse_manifest(md)


class TestValidateManifest:
    def test_valid_manifest_returns_empty_list(self) -> None:
        data = {
            "name": "x",
            "version": "1.0.0",
            "description": "desc",
            "entrypoint": "skill.py",
        }
        assert validate_manifest(data) == []

    def test_missing_required_returns_errors(self) -> None:
        errors = validate_manifest({})
        assert any("name" in e for e in errors)
        assert any("version" in e for e in errors)
        assert any("description" in e for e in errors)
        assert any("entrypoint" in e for e in errors)

    def test_invalid_trust_level(self) -> None:
        data = {
            "name": "x",
            "version": "1.0.0",
            "description": "d",
            "entrypoint": "skill.py",
            "trust_level_requested": "superadmin",
        }
        errors = validate_manifest(data)
        assert any("trust_level_requested" in e for e in errors)

    def test_valid_trust_levels_accepted(self) -> None:
        for level in ("trusted", "monitored", "sandboxed", "restricted"):
            data = {
                "name": "x",
                "version": "1.0.0",
                "description": "d",
                "entrypoint": "skill.py",
                "trust_level_requested": level,
            }
            assert validate_manifest(data) == [], f"Level '{level}' should be valid"

    def test_capabilities_must_be_list(self) -> None:
        data = {
            "name": "x",
            "version": "1.0.0",
            "description": "d",
            "entrypoint": "skill.py",
            "capabilities": "read",
        }
        errors = validate_manifest(data)
        assert any("capabilities" in e for e in errors)

    def test_unknown_field_flagged(self) -> None:
        data = {
            "name": "x",
            "version": "1.0.0",
            "description": "d",
            "entrypoint": "skill.py",
            "totally_unknown_key": "value",
        }
        errors = validate_manifest(data)
        assert any("totally_unknown_key" in e for e in errors)

    def test_list_with_non_string_items(self) -> None:
        data = {
            "name": "x",
            "version": "1.0.0",
            "description": "d",
            "entrypoint": "skill.py",
            "tags": ["valid", 42],
        }
        errors = validate_manifest(data)
        assert any("tags" in e for e in errors)
