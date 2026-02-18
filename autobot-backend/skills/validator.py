# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Validator (Phase 5)

Validates a generated skill package before storing as a draft.
Checks: SKILL.md frontmatter, Python syntax, MCP server starts.
"""
import ast
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

_TEST_TIMEOUT = 15.0


@dataclass
class ValidationResult:
    """Result of validating a skill package."""

    valid: bool
    errors: List[str] = field(default_factory=list)
    tools_found: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


class SkillValidator:
    """Validates skill packages by checking syntax and optionally running the MCP server."""

    async def validate(
        self, skill_md: str, skill_py: Optional[str] = None
    ) -> ValidationResult:
        """Run all validation checks and return a ValidationResult.

        Checks manifest, Python syntax, and MCP server startup (if skill_py provided).
        """
        errors: List[str] = []
        tools_found: List[str] = []

        errors.extend(_check_manifest(skill_md))
        if skill_py:
            errors.extend(_check_python_syntax(skill_py))
            if not errors:
                mcp_errors, tools_found = await self._check_mcp_server(skill_py)
                errors.extend(mcp_errors)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            tools_found=tools_found,
        )

    @staticmethod
    async def _check_mcp_server(skill_py: str) -> Tuple[List[str], List[str]]:
        """Start MCP server in isolation, list tools, return (errors, tool_names)."""
        from skills.mcp_process import MCPProcessManager

        mgr = MCPProcessManager()
        errors: List[str] = []
        tools: List[str] = []
        try:
            await mgr.start("_validation_tmp", skill_py)
            tool_list = await mgr.list_tools("_validation_tmp")
            tools = [t["name"] for t in tool_list]
            if not tools:
                errors.append("MCP server started but no tools declared")
        except RuntimeError as exc:
            errors.append(f"MCP server failed to start: {exc}")
        finally:
            await mgr.stop("_validation_tmp")
        return errors, tools


def _check_manifest(skill_md: str) -> List[str]:
    """Validate SKILL.md has required YAML frontmatter with name, description, tools."""
    errors: List[str] = []
    match = re.match(r"^---\n(.*?)\n---", skill_md, re.DOTALL)
    if not match:
        errors.append("SKILL.md missing YAML frontmatter (--- block)")
        return errors
    try:
        manifest = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        errors.append(f"Invalid YAML frontmatter: {exc}")
        return errors
    for required_field in ("name", "description", "tools"):
        if not manifest.get(required_field):
            errors.append(f"Manifest missing required field: {required_field}")
    return errors


def _check_python_syntax(skill_py: str) -> List[str]:
    """Check skill.py content for Python syntax errors using ast.parse."""
    try:
        ast.parse(skill_py)
        return []
    except SyntaxError as exc:
        return [f"syntax error in skill.py at line {exc.lineno}: {exc.msg}"]
