#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Model References Verification Script
Verifies that all model references use ModelConstants from src/constants/model_constants.py

Usage:
    python scripts/ai-ml/model_references_corrector.py

This script checks that the codebase properly uses centralized ModelConstants
instead of hardcoded model names.
"""

import logging
import os
import re
import sys

# Add project root to path
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger(__name__)


def check_hardcoded_models(directory: str, extensions: list[str]) -> list[dict]:
    """
    Check for hardcoded model references in files.

    Args:
        directory: Directory to scan
        extensions: List of file extensions to check

    Returns:
        List of findings with file, line number, and content
    """
    findings = []

    # Patterns that indicate hardcoded models (excluding constants file)
    hardcoded_patterns = [
        r'["\'](?:mistral|llama|gemma|qwen|deepseek)[^"\']*:[0-9]+b[^"\']*["\']',
        r'os\.getenv\(["\']AUTOBOT_OLLAMA_MODEL["\']',  # Deprecated env var
    ]

    # Issue #506: Precompile and combine patterns - O(1) instead of O(p) per line
    combined_pattern = re.compile(
        "|".join(f"({p})" for p in hardcoded_patterns), re.IGNORECASE
    )

    # Files/directories to skip
    skip_dirs = {"archives", "analysis", ".git", "__pycache__", "node_modules", ".venv"}
    skip_files = {"model_constants.py"}  # This file defines the constants
    # Issue #506: Convert extensions to set for O(1) lookup
    extensions_set = set(extensions)

    for root, dirs, files in os.walk(directory):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for filename in files:
            # Issue #506: O(1) extension check using set
            ext = os.path.splitext(filename)[1]
            if ext not in extensions_set:
                continue

            # Skip excluded files
            if filename in skip_files:
                continue

            filepath = os.path.join(root, filename)

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                # Issue #506: Single pattern search per line instead of loop
                for line_num, line in enumerate(lines, 1):
                    if combined_pattern.search(line):
                        findings.append(
                            {
                                "file": filepath,
                                "line": line_num,
                                "content": line.strip(),
                                "pattern": "combined_hardcoded_pattern",
                            }
                        )
            except (IOError, UnicodeDecodeError):
                continue

    return findings


def verify_model_constants_usage():
    """Verify that ModelConstants is being used correctly."""
    logger.info("Verifying ModelConstants usage...")

    try:
        from constants.model_constants import FALLBACK_MODEL, ModelConstants

        logger.info(f"  FALLBACK_MODEL: {FALLBACK_MODEL}")
        logger.info(f"  DEFAULT_OLLAMA_MODEL: {ModelConstants.DEFAULT_OLLAMA_MODEL}")
        logger.info(f"  DEFAULT_OPENAI_MODEL: {ModelConstants.DEFAULT_OPENAI_MODEL}")
        logger.info(f"  DEFAULT_ANTHROPIC_MODEL: {ModelConstants.DEFAULT_ANTHROPIC_MODEL}")
        logger.info("ModelConstants imported successfully")
        return True
    except ImportError as e:
        logger.info(f"Failed to import ModelConstants: {e}")
        return False


def verify_env_var_usage():
    """Verify correct environment variable is being used."""
    logger.info("\nVerifying environment variable usage...")

    correct_var = "AUTOBOT_DEFAULT_LLM_MODEL"
    deprecated_var = "AUTOBOT_OLLAMA_MODEL"

    # Check current environment
    correct_value = os.getenv(correct_var)
    deprecated_value = os.getenv(deprecated_var)

    if correct_value:
        logger.info(f"  {correct_var}={correct_value}")
    else:
        logger.info(f"  {correct_var} not set (will use FALLBACK_MODEL)")

    if deprecated_value:
        logger.info(f"  WARNING: Deprecated {deprecated_var}={deprecated_value}")
        logger.info(f"  Please migrate to {correct_var}")

    return True


def main():
    """Main verification function."""
    logger.info("=" * 60)
    logger.info("AutoBot Model References Verification")
    logger.info("=" * 60)

    os.chdir(PROJECT_ROOT)

    # Verify ModelConstants
    if not verify_model_constants_usage():
        logger.info("\nERROR: ModelConstants verification failed")
        sys.exit(1)

    # Verify env var usage
    verify_env_var_usage()

    # Check for hardcoded models in Python files
    logger.info("\nScanning for hardcoded model references...")

    findings = check_hardcoded_models(PROJECT_ROOT, extensions=[".py"])

    if findings:
        logger.info(f"\nFound {len(findings)} potential hardcoded model references:")
        for finding in findings:
            rel_path = os.path.relpath(finding["file"], PROJECT_ROOT)
            logger.info(f"  {rel_path}:{finding['line']}")
            logger.info(f"    {finding['content'][:80]}...")
    else:
        logger.info("No hardcoded model references found in active code")

    logger.info("\n" + "=" * 60)
    logger.info("Verification complete")
    logger.info("=" * 60)

    logger.info("\nCorrect usage pattern:")
    logger.info("  from constants.model_constants import ModelConstants")
    logger.info("  model = ModelConstants.DEFAULT_OLLAMA_MODEL")
    logger.info("\nEnvironment variable:")
    logger.info("  AUTOBOT_DEFAULT_LLM_MODEL=mistral:7b-instruct")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
