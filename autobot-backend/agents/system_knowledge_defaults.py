# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Built-in default system-knowledge definitions (steganography tools, image-forensics workflow).

Moved verbatim out of ``system_knowledge_manager.py`` (#18577) to keep that module under its size
ceiling; ``SystemKnowledgeManager`` inherits them, so every ``self._get_*`` call is unchanged.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class DefaultKnowledgeMixin:
    """Pure-data default definitions used when no template tree is present."""

    def _get_steghide_tool_definition(self) -> Dict[str, Any]:
        """Get steghide tool definition."""
        return {
            "name": "steghide",
            "type": "steganography",
            "purpose": "Extract and embed hidden data in image and audio files",
            "installation": {
                "apt": "sudo apt-get install steghide",
                "yum": "sudo yum install steghide",
                "pacman": "sudo pacman -S steghide",
            },
            "usage": {
                "extract": "steghide extract -sf {image_file}",
                "info": "steghide info {image_file}",
                "embed": "steghide embed -cf {cover_file} -ef {data_file}",
            },
            "common_examples": [
                {
                    "description": "Extract hidden data from image",
                    "command": "steghide extract -sf suspicious.jpg",
                    "expected_output": "Enter passphrase: (if password protected)",
                },
                {
                    "description": "Check image capacity for hidden data",
                    "command": "steghide info suspicious.jpg",
                    "expected_output": "capacity: 57.8% (can hide data)",
                },
            ],
            "troubleshooting": [
                {
                    "problem": "could not extract any data with that passphrase",
                    "solution": "Try empty passphrase or common passwords",
                },
                {
                    "problem": "file format is not supported",
                    "solution": "Convert to JPEG or BMP format first",
                },
            ],
            "security_notes": [
                "Use strong passphrases for embedding",
                "Steganography can be detected by analysis tools",
                "Consider using multiple tools to avoid detection",
            ],
            "related_tools": ["binwalk", "outguess", "jsteg", "zsteg"],
            "output_formats": ["original file format", "text output for info"],
            "limitations": [
                "Only supports JPEG, BMP, WAV, AU formats",
                "Cannot process encrypted or corrupted images",
            ],
        }

    def _get_binwalk_tool_definition(self) -> Dict[str, Any]:
        """Get binwalk tool definition."""
        return {
            "name": "binwalk",
            "type": "file_analysis",
            "purpose": "Analyze and extract files from binary images",
            "installation": {
                "apt": "sudo apt-get install binwalk",
                "yum": "sudo yum install binwalk",
                "pacman": "sudo pacman -S binwalk",
            },
            "usage": {
                "analyze": "binwalk {file}",
                "extract": "binwalk -e {file}",
                "signature": "binwalk --signature {file}",
            },
            "common_examples": [
                {
                    "description": "Scan for embedded files",
                    "command": "binwalk suspicious.jpg",
                    "expected_output": "List of detected file signatures and offsets",
                },
                {
                    "description": "Extract all found files",
                    "command": "binwalk -e suspicious.jpg",
                    "expected_output": "Creates _suspicious.jpg.extracted/ directory",
                },
            ],
            "related_tools": ["foremost", "scalpel", "photorec"],
            "output_formats": ["extracted files", "signature analysis text"],
        }

    def _get_steganography_tools_data(self) -> Dict[str, Any]:
        """Get steganography tools knowledge data."""
        return {
            "metadata": {
                "category": "steganography",
                "description": "Tools for steganography analysis and detection",
                "last_updated": datetime.now(tz=timezone.utc).isoformat(),
                "version": "1.0.0",
            },
            "tools": [
                self._get_steghide_tool_definition(),
                self._get_binwalk_tool_definition(),
            ],
        }

    def _get_workflow_metadata(self) -> Dict[str, Any]:
        """Get metadata for image forensics workflow. Issue #620."""
        return {
            "name": "Image Steganography Analysis",
            "category": "forensics",
            "complexity": "medium",
            "estimated_time": "10-30 minutes",
            "version": "1.0.0",
        }

    def _get_workflow_required_tools(self) -> List[Dict[str, Any]]:
        """Get required tools for image forensics workflow. Issue #620."""
        return [
            {
                "name": "steghide",
                "purpose": "Extract hidden data from images",
                "optional": False,
            },
            {
                "name": "binwalk",
                "purpose": "Detect and extract embedded files",
                "optional": False,
            },
            {
                "name": "exiftool",
                "purpose": "Analyze image metadata",
                "optional": True,
            },
        ]

    def _get_workflow_steps(self) -> List[Dict[str, Any]]:
        """Get workflow steps for image forensics analysis. Issue #620."""
        return [
            {
                "step": 1,
                "action": "Initial image analysis",
                "details": "Gather basic information about the target image",
                "commands": [
                    "file {image_file}",
                    "ls -la {image_file}",
                    "identify {image_file}",
                ],
                "expected_output": "Image format, size, and basic properties",
            },
            {
                "step": 2,
                "action": "Metadata examination",
                "details": "Check for hidden information in image metadata",
                "commands": [
                    "exiftool {image_file}",
                    "strings {image_file} | head -20",
                ],
                "expected_output": "EXIF data, embedded comments, text strings",
            },
            {
                "step": 3,
                "action": "Steganography detection",
                "details": "Check for steganographic content using steghide",
                "commands": ["steghide info {image_file}"],
                "expected_output": "Capacity information or error if no hidden data",
            },
            {
                "step": 4,
                "action": "File signature analysis",
                "details": "Look for embedded files using binwalk",
                "commands": ["binwalk {image_file}", "binwalk -e {image_file}"],
                "expected_output": "List of detected files and extraction results",
            },
        ]

    def _get_workflow_decision_points(self) -> List[Dict[str, str]]:
        """Get decision points for image forensics workflow. Issue #620."""
        return [
            {
                "condition": "steghide reports capacity > 0",
                "if_true": "Attempt extraction with common passwords",
                "if_false": "Move to alternative steganography tools",
            },
            {
                "condition": "binwalk finds embedded files",
                "if_true": "Extract and analyze each file",
                "if_false": "Check for other steganography methods",
            },
        ]

    def _get_workflow_quality_and_pitfalls(self) -> Dict[str, Any]:
        """Get quality checks and common pitfalls for workflow. Issue #620."""
        return {
            "quality_checks": [
                "Verify extracted files are not corrupted",
                "Check that original image wasn't modified during analysis",
                "Confirm all potential hiding methods were tested",
            ],
            "common_pitfalls": [
                {
                    "issue": "Assuming empty passphrase when extraction fails",
                    "prevention": "Try common passwords and dictionary attacks",
                },
                {
                    "issue": "Missing hidden data due to format limitations",
                    "prevention": "Test with multiple steganography tools",
                },
            ],
        }

    def _get_image_forensics_workflow_data(self) -> Dict[str, Any]:
        """Get image forensics workflow data. Issue #620."""
        quality_and_pitfalls = self._get_workflow_quality_and_pitfalls()
        return {
            "metadata": self._get_workflow_metadata(),
            "objective": ("Analyze images for hidden files, steganographic content, " "and embedded data"),
            "prerequisites": [
                "Target image file(s)",
                "Basic understanding of steganography techniques",
                "Sufficient disk space for extracted files",
            ],
            "required_tools": self._get_workflow_required_tools(),
            "workflow_steps": self._get_workflow_steps(),
            "decision_points": self._get_workflow_decision_points(),
            "quality_checks": quality_and_pitfalls["quality_checks"],
            "common_pitfalls": quality_and_pitfalls["common_pitfalls"],
        }

    def _format_installation(self, install_data: Dict[str, str]) -> str:
        """Format installation commands from YAML"""
        if not install_data:
            return "Installation information not available"

        formatted = []
        for package_manager, command in install_data.items():
            formatted.append(f"{package_manager}: {command}")

        return "\n".join(formatted)

    def _format_usage(self, usage_data: Dict[str, str]) -> str:
        """Format usage information from YAML"""
        if not usage_data:
            return "Usage information not available"

        formatted = []
        for action, command in usage_data.items():
            formatted.append(f"{action}: {command}")

        return "\n".join(formatted)

    def _format_troubleshooting(self, trouble_data: List[Dict[str, str]]) -> str:
        """Format troubleshooting information from YAML"""
        if not trouble_data:
            return "No troubleshooting information available"

        formatted = []
        for item in trouble_data:
            problem = item.get("problem", "Unknown problem")
            solution = item.get("solution", "No solution provided")
            formatted.append(f"Problem: {problem}")
            formatted.append(f"Solution: {solution}")
            formatted.append("")

        return "\n".join(formatted)

    def _format_pitfalls(self, pitfalls_data: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Format pitfalls data for librarian"""
        formatted = []
        for pitfall in pitfalls_data:
            formatted.append(
                {
                    "issue": pitfall.get("issue", "Unknown issue"),
                    "prevention": pitfall.get("prevention", "No prevention method"),
                }
            )
        return formatted

    def _format_procedure_issues(self, issues_data: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Format procedure issues for librarian"""
        formatted = []
        for issue in issues_data:
            formatted.append(
                {
                    "problem": issue.get("problem", "Unknown problem"),
                    "solution": issue.get("solution", "No solution provided"),
                }
            )
        return formatted

    def _log_imported(self, kind: str, name: str, result: Any) -> None:
        """Log what the import actually did: nothing (already current), an unresolved match, or a write."""
        action = result.get("action") if isinstance(result, dict) else None
        if action == "skipped":
            logger.info("Unchanged %s (skipped): %s", kind, name)
        elif action == "unresolved":
            self._import_unresolved.append(f"{kind}:{name}")
        else:
            logger.info("Imported %s: %s", kind, name)

    @property
    def import_failures(self) -> List[str]:
        """Items the last import failed to store; they are retried on the next start (#19347)."""
        return list(self._import_failures)

    def _record_import_failure(self, kind: str, name: str, error: Exception) -> None:
        """Count a failed item; it is retried on the next import because nothing marks it done."""
        logger.error("Failed to import %s %s: %s", kind, name, error)
        self._import_failures.append(f"{kind}:{name}")

    def _report_unresolved(self) -> None:
        """Items whose near-duplicate is already linked to another item: reported, never retried."""
        if self._import_unresolved:
            logger.warning(
                "%d item(s) matched a fact linked to another item and were left unlinked: %s",
                len(self._import_unresolved),
                ", ".join(self._import_unresolved),
            )
