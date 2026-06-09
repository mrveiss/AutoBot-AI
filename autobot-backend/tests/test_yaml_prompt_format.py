# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for YAML-sectioned system prompt format.

Issue #4519: YAML-sectioned prompt format has no unit tests.
Tests cover: valid YAML sections, missing sections, malformed YAML,
section extraction, section assembly order, and section overrides.
"""

from pathlib import Path

import pytest
import yaml

from prompt_manager import _YAML_SECTION_ORDER, PromptManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pm(tmp_path: Path) -> PromptManager:
    """Return a PromptManager pointed at a temp prompts directory."""
    return PromptManager(prompts_dir=str(tmp_path))


def _write_yaml(tmp_path: Path, name: str, content: dict) -> Path:
    """Write a YAML prompt file and return its path."""
    p = tmp_path / name
    p.write_text(yaml.dump(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# TestAssembleYamlSections — unit tests for the assembly helper
# ---------------------------------------------------------------------------


class TestAssembleYamlSections:
    """Tests for PromptManager._assemble_yaml_sections."""

    def _pm(self, tmp_path):
        return _make_pm(tmp_path)

    def test_known_order_is_respected(self, tmp_path):
        """role -> objective -> tools -> examples -> instructions order."""
        pm = _make_pm(tmp_path)
        sections = {
            "instructions": "do stuff",
            "role": "you are",
            "examples": "eg",
            "objective": "help user",
            "tools": "use tool",
        }
        result = pm._assemble_yaml_sections(sections)
        parts = result.split("\n\n")
        assert parts[0] == "you are"
        assert parts[1] == "help user"
        assert parts[2] == "use tool"
        assert parts[3] == "eg"
        assert parts[4] == "do stuff"

    def test_unknown_sections_appended_sorted(self, tmp_path):
        """Unknown sections come after standard ones, sorted alphabetically."""
        pm = _make_pm(tmp_path)
        sections = {
            "role": "agent role",
            "zeta": "last",
            "alpha": "first extra",
        }
        result = pm._assemble_yaml_sections(sections)
        parts = result.split("\n\n")
        assert parts[0] == "agent role"
        assert parts[1] == "first extra"  # alpha before zeta
        assert parts[2] == "last"

    def test_empty_sections_dict(self, tmp_path):
        """Empty sections mapping produces empty string."""
        pm = _make_pm(tmp_path)
        result = pm._assemble_yaml_sections({})
        assert result == ""

    def test_sections_stripped(self, tmp_path):
        """Leading/trailing whitespace inside section values is stripped."""
        pm = _make_pm(tmp_path)
        sections = {"role": "  spaced role  "}
        result = pm._assemble_yaml_sections(sections)
        assert result == "spaced role"

    def test_partial_known_sections(self, tmp_path):
        """Only present known sections appear; absent known sections are skipped."""
        pm = _make_pm(tmp_path)
        sections = {"objective": "task", "instructions": "steps"}
        result = pm._assemble_yaml_sections(sections)
        parts = result.split("\n\n")
        assert len(parts) == 2
        assert "task" in parts[0]
        assert "steps" in parts[1]

    def test_all_whitespace_value_excluded(self, tmp_path):
        """A section whose stripped value is empty is excluded from output."""
        pm = _make_pm(tmp_path)
        sections = {"role": "agent", "objective": "   "}
        result = pm._assemble_yaml_sections(sections)
        assert result == "agent"


# ---------------------------------------------------------------------------
# TestLoadYamlPromptFile — unit tests for file loading
# ---------------------------------------------------------------------------


class TestLoadYamlPromptFile:
    """Tests for PromptManager._load_yaml_prompt_file."""

    def test_valid_yaml_loads_sections(self, tmp_path):
        """A valid YAML file populates yaml_sections and prompts."""
        _write_yaml(
            tmp_path,
            "agent.yml",
            {
                "role": "you are a helpful assistant",
                "objective": "answer questions",
            },
        )
        pm = _make_pm(tmp_path)

        assert "agent" in pm.yaml_sections
        assert pm.yaml_sections["agent"]["role"] == "you are a helpful assistant"
        assert pm.yaml_sections["agent"]["objective"] == "answer questions"

    def test_valid_yaml_assembles_prompt(self, tmp_path):
        """A valid YAML file produces assembled prompt stored in pm.prompts."""
        _write_yaml(
            tmp_path,
            "agent.yml",
            {
                "role": "you are",
                "instructions": "be concise",
            },
        )
        pm = _make_pm(tmp_path)

        assert "agent" in pm.prompts
        text = pm.prompts["agent"]
        assert "you are" in text
        assert "be concise" in text

    def test_valid_yaml_registers_template(self, tmp_path):
        """A valid YAML file produces a Jinja2 template in pm.templates."""
        _write_yaml(tmp_path, "agent.yml", {"role": "hello {{ name }}"})
        pm = _make_pm(tmp_path)

        assert "agent" in pm.templates

    def test_all_standard_sections(self, tmp_path):
        """All five standard sections are loaded and assembled in order."""
        _write_yaml(
            tmp_path,
            "full.yaml",
            {
                "role": "R",
                "objective": "O",
                "tools": "T",
                "examples": "E",
                "instructions": "I",
            },
        )
        pm = _make_pm(tmp_path)

        assert "full" in pm.yaml_sections
        result = pm.prompts["full"]
        # Verify all sections present
        for marker in ("R", "O", "T", "E", "I"):
            assert marker in result

    def test_non_dict_yaml_skipped(self, tmp_path):
        """A YAML file whose top-level value is not a mapping is skipped."""
        bad = tmp_path / "list_prompt.yml"
        bad.write_text("- item1\n- item2\n", encoding="utf-8")
        pm = _make_pm(tmp_path)

        assert "list_prompt" not in pm.yaml_sections
        assert "list_prompt" not in pm.prompts

    def test_malformed_yaml_skipped(self, tmp_path):
        """A file with invalid YAML syntax is skipped without raising."""
        bad = tmp_path / "broken.yml"
        bad.write_text(": bad: yaml: {unclosed\n", encoding="utf-8")
        # Should not raise
        pm = _make_pm(tmp_path)
        assert "broken" not in pm.prompts

    def test_non_string_values_excluded(self, tmp_path):
        """Non-string YAML values (lists, dicts) are excluded from sections."""
        _write_yaml(
            tmp_path,
            "mixed.yml",
            {
                "role": "text role",
                "tools": ["tool1", "tool2"],  # list — not a str
                "meta": {"version": 1},  # dict — not a str
            },
        )
        pm = _make_pm(tmp_path)

        assert "mixed" in pm.yaml_sections
        sections = pm.yaml_sections["mixed"]
        assert "role" in sections
        assert "tools" not in sections
        assert "meta" not in sections

    def test_yaml_extension_yml(self, tmp_path):
        """Files with .yml extension are loaded as YAML prompts."""
        _write_yaml(tmp_path, "prompt.yml", {"role": "yml role"})
        pm = _make_pm(tmp_path)
        assert "prompt" in pm.yaml_sections

    def test_yaml_extension_yaml(self, tmp_path):
        """Files with .yaml extension are loaded as YAML prompts."""
        _write_yaml(tmp_path, "prompt.yaml", {"role": "yaml role"})
        pm = _make_pm(tmp_path)
        assert "prompt" in pm.yaml_sections

    def test_key_uses_dot_notation(self, tmp_path):
        """A nested YAML file produces a dot-notation key."""
        subdir = tmp_path / "orchestrator"
        subdir.mkdir()
        _write_yaml(subdir, "system.yml", {"role": "orchestrator"})
        pm = _make_pm(tmp_path)

        assert "orchestrator.system" in pm.yaml_sections

    def test_empty_file_skipped(self, tmp_path):
        """An empty YAML file (null document) does not crash and is skipped."""
        empty = tmp_path / "empty.yml"
        empty.write_text("", encoding="utf-8")
        pm = _make_pm(tmp_path)
        assert "empty" not in pm.yaml_sections


# ---------------------------------------------------------------------------
# TestGetWithYamlOverrides — section override via pm.get()
# ---------------------------------------------------------------------------


class TestGetWithYamlOverrides:
    """Tests for per-section overrides through PromptManager.get()."""

    def _pm_with_agent(self, tmp_path) -> PromptManager:
        _write_yaml(
            tmp_path,
            "agent.yml",
            {
                "role": "default role",
                "objective": "default objective",
                "instructions": "default instructions",
            },
        )
        return _make_pm(tmp_path)

    def test_override_single_section(self, tmp_path):
        """Overriding one section replaces only that section."""
        pm = self._pm_with_agent(tmp_path)
        result = pm.get("agent", overrides={"role": "custom role"})

        assert "custom role" in result
        assert "default objective" in result
        assert "default instructions" in result

    def test_override_multiple_sections(self, tmp_path):
        """Overriding multiple sections replaces each."""
        pm = self._pm_with_agent(tmp_path)
        result = pm.get(
            "agent",
            overrides={"role": "new role", "instructions": "new steps"},
        )

        assert "new role" in result
        assert "default objective" in result
        assert "new steps" in result

    def test_override_adds_new_section(self, tmp_path):
        """An override key not in the original YAML is appended."""
        pm = self._pm_with_agent(tmp_path)
        result = pm.get("agent", overrides={"extra": "extra text"})

        assert "extra text" in result

    def test_no_overrides_returns_base(self, tmp_path):
        """Calling get() without overrides returns the base assembled prompt."""
        pm = self._pm_with_agent(tmp_path)
        base = pm.get("agent")
        result = pm.get("agent", overrides=None)

        assert base == result

    def test_empty_overrides_ignored(self, tmp_path):
        """An empty overrides dict falls through to the base prompt path."""
        pm = self._pm_with_agent(tmp_path)
        base = pm.get("agent")
        result = pm.get("agent", overrides={})

        assert base == result

    def test_override_caches_separately(self, tmp_path):
        """Two different overrides cache under distinct keys."""
        pm = self._pm_with_agent(tmp_path)
        r1 = pm.get("agent", overrides={"role": "role A"})
        r2 = pm.get("agent", overrides={"role": "role B"})

        assert "role A" in r1
        assert "role B" in r2
        assert r1 != r2

    def test_override_nonexistent_prompt_raises(self, tmp_path):
        """get() on a non-existent key raises KeyError regardless of overrides."""
        pm = _make_pm(tmp_path)
        with pytest.raises(KeyError):
            pm.get("nonexistent.key", overrides={"role": "x"})


# ---------------------------------------------------------------------------
# TestYamlSectionConstants — module-level constants
# ---------------------------------------------------------------------------


class TestYamlSectionConstants:
    """Tests for _YAML_SECTION_ORDER constant."""

    def test_section_order_is_tuple(self):
        assert isinstance(_YAML_SECTION_ORDER, tuple)

    def test_section_order_contains_expected_keys(self):
        expected = {"role", "objective", "tools", "examples", "instructions"}
        assert expected == set(_YAML_SECTION_ORDER)

    def test_section_order_starts_with_role(self):
        assert _YAML_SECTION_ORDER[0] == "role"

    def test_section_order_ends_with_instructions(self):
        assert _YAML_SECTION_ORDER[-1] == "instructions"


# ---------------------------------------------------------------------------
# TestYamlJinja2Integration — Jinja2 template rendering inside YAML prompts
# ---------------------------------------------------------------------------


class TestYamlJinja2Integration:
    """Tests that Jinja2 templates work inside YAML-sectioned prompts."""

    def test_jinja2_variable_renders(self, tmp_path):
        """Template variables in section text are rendered by get()."""
        _write_yaml(
            tmp_path,
            "greeting.yml",
            {
                "role": "you are {{ name }}",
            },
        )
        pm = _make_pm(tmp_path)
        result = pm.get("greeting", name="Alice")
        assert "Alice" in result

    def test_jinja2_variable_in_overridden_section(self, tmp_path):
        """Template variables also work inside overridden sections."""
        _write_yaml(
            tmp_path,
            "greeting.yml",
            {
                "role": "default role",
                "objective": "help {{ user }}",
            },
        )
        pm = _make_pm(tmp_path)
        result = pm.get(
            "greeting",
            overrides={"role": "custom role for {{ user }}"},
            user="Bob",
        )
        assert "Bob" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
