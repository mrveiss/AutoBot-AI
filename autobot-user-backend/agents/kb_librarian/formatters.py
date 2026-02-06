# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Formatters for KB Librarian tool information and documentation.

Extracted from enhanced_kb_librarian.py as part of Issue #381 god class refactoring.
"""

from typing import Any, Dict, List


class ToolInfoFormatter:
    """Helper class for formatting tool information and documentation."""

    @classmethod
    def format_command_examples(cls, examples: List[Dict[str, str]]) -> str:
        """Format command examples for documentation."""
        if not examples:
            return "No examples available"

        formatted = []
        for i, example in enumerate(examples, 1):
            if isinstance(example, dict):
                cmd = example.get("command", "")
                desc = example.get("description", "")
                output = example.get("expected_output", "")

                formatted.append(f"{i}. {desc}")
                formatted.append(f"   Command: {cmd}")
                if output:
                    formatted.append(f"   Expected Output: {output}")
                formatted.append("")
            else:
                formatted.append(f"{i}. {example}")

        return "\n".join(formatted)

    @classmethod
    def _format_procedure_dict(cls, proc: Dict[str, str]) -> List[str]:
        """Format a single procedure dict to lines (Issue #315 - extracted helper)."""
        lines = []
        name = proc.get("name", "Unnamed Procedure")
        desc = proc.get("description", "")
        steps = proc.get("steps", [])

        lines.append(f"* {name}")
        if desc:
            lines.append(f"  Description: {desc}")
        for i, step in enumerate(steps, 1):
            lines.append(f"  {i}. {step}")
        lines.append("")
        return lines

    @classmethod
    def format_procedures(cls, procedures: List[Dict[str, str]]) -> str:
        """Format procedure documentation."""
        if not procedures:
            return "No procedures documented"

        formatted = []
        for proc in procedures:
            if isinstance(proc, dict):
                formatted.extend(cls._format_procedure_dict(proc))
            else:
                formatted.append(f"* {proc}")

        return "\n".join(formatted)

    @classmethod
    def format_steps(cls, steps: List[str]) -> str:
        """Format step-by-step instructions."""
        if not steps:
            return "No steps documented"

        return "\n".join([f"{i}. {step}" for i, step in enumerate(steps, 1)])

    @classmethod
    def format_troubleshooting(cls, issues: List[Dict[str, str]]) -> str:
        """Format troubleshooting information."""
        if not issues:
            return "No common issues documented"

        formatted = []
        for issue in issues:
            if isinstance(issue, dict):
                problem = issue.get("problem", "Unknown issue")
                solution = issue.get("solution", "No solution provided")
                formatted.append(f"Problem: {problem}")
                formatted.append(f"Solution: {solution}")
                formatted.append("")
            else:
                formatted.append(f"* {issue}")

        return "\n".join(formatted)

    @classmethod
    def format_best_practices(cls, practices: List[str]) -> str:
        """Format best practices."""
        if not practices:
            return "No best practices documented"

        return "\n".join([f"* {practice}" for practice in practices])

    @classmethod
    def _format_example_dict(cls, example: Dict[str, str], index: int) -> List[str]:
        """Format a single example dict to lines (Issue #315 - extracted helper)."""
        lines = []
        title = example.get("title", f"Example {index}")
        scenario = example.get("scenario", "")
        commands = example.get("commands", [])

        lines.append(f"{index}. {title}")
        if scenario:
            lines.append(f"   Scenario: {scenario}")
        if commands:
            lines.append("   Commands:")
            for cmd in commands:
                lines.append(f"     {cmd}")
        lines.append("")
        return lines

    @classmethod
    def format_documentation_examples(cls, examples: List[Dict[str, str]]) -> str:
        """Format documentation examples."""
        if not examples:
            return "No examples available"

        formatted = []
        for i, example in enumerate(examples, 1):
            if isinstance(example, dict):
                formatted.extend(cls._format_example_dict(example, i))

        return "\n".join(formatted)

    @classmethod
    def format_verification_steps(cls, steps: List[str]) -> str:
        """Format verification steps."""
        if not steps:
            return "No verification steps provided"

        return "\n".join([f"{i}. {step}" for i, step in enumerate(steps, 1)])

    @classmethod
    def format_prerequisites(cls, prereqs: List[str]) -> str:
        """Format prerequisites."""
        if not prereqs:
            return "None specified"
        return "\n".join([f"* {prereq}" for prereq in prereqs])

    @classmethod
    def format_tool_requirements(cls, tools: List[Dict[str, str]]) -> str:
        """Format tool requirements."""
        if not tools:
            return "Standard system tools"

        formatted = []
        for tool in tools:
            if isinstance(tool, dict):
                name = tool.get("name", "Unknown tool")
                purpose = tool.get("purpose", "")
                optional = tool.get("optional", False)
                prefix = "Optional: " if optional else "Required: "
                formatted.append(f"* {prefix}{name}")
                if purpose:
                    formatted.append(f"  Purpose: {purpose}")
            else:
                formatted.append(f"* {tool}")

        return "\n".join(formatted)

    @classmethod
    def _format_workflow_step_dict(cls, step: Dict[str, Any], index: int) -> List[str]:
        """Format a single workflow step dict to lines (Issue #315 - extracted helper)."""
        lines = []
        action = step.get("action", f"Step {index}")
        details = step.get("details", "")
        commands = step.get("commands", [])
        expected_output = step.get("expected_output", "")

        lines.append(f"{index}. {action}")
        if details:
            lines.append(f"   Details: {details}")
        if commands:
            lines.append("   Commands:")
            for cmd in commands:
                lines.append(f"     {cmd}")
        if expected_output:
            lines.append(f"   Expected Output: {expected_output}")
        lines.append("")
        return lines

    @classmethod
    def format_workflow_steps(cls, steps: List[Dict[str, Any]]) -> str:
        """Format detailed workflow steps."""
        if not steps:
            return "No steps documented"

        formatted = []
        for i, step in enumerate(steps, 1):
            if isinstance(step, dict):
                formatted.extend(cls._format_workflow_step_dict(step, i))
            else:
                formatted.append(f"{i}. {step}")

        return "\n".join(formatted)

    @classmethod
    def format_decision_points(cls, decisions: List[Dict[str, str]]) -> str:
        """Format decision points in workflow."""
        if not decisions:
            return "No decision points documented"

        formatted = []
        for decision in decisions:
            if isinstance(decision, dict):
                condition = decision.get("condition", "Unknown condition")
                if_true = decision.get("if_true", "Continue")
                if_false = decision.get("if_false", "Stop")
                formatted.append(f"* If {condition}:")
                formatted.append(f"  - True: {if_true}")
                formatted.append(f"  - False: {if_false}")
                formatted.append("")

        return "\n".join(formatted)

    @classmethod
    def format_quality_checks(cls, checks: List[str]) -> str:
        """Format quality check steps."""
        if not checks:
            return "No quality checks documented"

        return "\n".join([f"[x] {check}" for check in checks])

    @classmethod
    def format_pitfalls(cls, pitfalls: List[Dict[str, str]]) -> str:
        """Format common pitfalls and how to avoid them."""
        if not pitfalls:
            return "No common pitfalls documented"

        formatted = []
        for pitfall in pitfalls:
            if isinstance(pitfall, dict):
                issue = pitfall.get("issue", "Unknown issue")
                prevention = pitfall.get("prevention", "No prevention method")
                formatted.append(f"[!] {issue}")
                formatted.append(f"   Prevention: {prevention}")
                formatted.append("")

        return "\n".join(formatted)

    @classmethod
    def format_alternatives(cls, alternatives: List[Dict[str, str]]) -> str:
        """Format alternative approaches."""
        if not alternatives:
            return "No alternatives documented"

        formatted = []
        for alt in alternatives:
            if isinstance(alt, dict):
                approach = alt.get("approach", "Alternative approach")
                when_to_use = alt.get("when_to_use", "When standard method fails")
                formatted.append(f"* {approach}")
                formatted.append(f"  When to use: {when_to_use}")
                formatted.append("")

        return "\n".join(formatted)


__all__ = ["ToolInfoFormatter"]
