#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Environment File Validator
Validates consistency between environment files and complete.yaml
"""

import re
from pathlib import Path
from typing import Any, Dict, List

import yaml


def load_config():
    """Load the complete.yaml configuration"""
    config_path = Path(__file__).parent.parent / "config" / "complete.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def parse_env_file(file_path: Path) -> Dict[str, str]:
    """Parse environment file and return variables as dict"""
    env_vars = {}

    if not file_path.exists():
        return env_vars

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()

    return env_vars


def validate_required_variables(env_vars: Dict[str, str], env_type: str) -> List[str]:
    """Validate that required variables are present"""
    errors = []

    # Common required variables for backend environments (skip for frontend)
    common_required = []
    if env_type != "frontend":
        common_required = [
            "AUTOBOT_BACKEND_HOST",
            "AUTOBOT_BACKEND_PORT",
            "AUTOBOT_REDIS_HOST",
            "AUTOBOT_REDIS_PORT",
            "AUTOBOT_OLLAMA_HOST",
            "AUTOBOT_OLLAMA_PORT",
        ]

    # Environment-specific required variables
    env_specific = {
        "main": ["AUTOBOT_DEPLOYMENT_MODE", "AUTOBOT_DEBUG", "AUTOBOT_LOG_LEVEL"],
        "localhost": ["AUTOBOT_DEPLOYMENT_MODE"],
        "native-vm": ["AUTOBOT_DEPLOYMENT_MODE", "AUTOBOT_VM_ARCHITECTURE"],
        "frontend": ["VITE_API_BASE_URL", "VITE_WS_BASE_URL", "VITE_BACKEND_HOST"],
        "docker-production": ["AUTOBOT_ENVIRONMENT"],
    }

    required_vars = common_required + env_specific.get(env_type, [])

    for var in required_vars:
        if var not in env_vars:
            errors.append(f"Missing required variable: {var}")
        elif not env_vars[var]:
            errors.append(f"Empty value for required variable: {var}")

    return errors


def validate_redis_databases(env_vars: Dict[str, str], env_type: str = "") -> List[str]:
    """Validate Redis database assignments"""
    errors = []

    # Skip Redis database validation for frontend files
    if env_type == "frontend":
        return errors

    # Expected Redis database variables
    expected_dbs = {
        "AUTOBOT_REDIS_DB_MAIN": "0",
        "AUTOBOT_REDIS_DB_KNOWLEDGE": "1",
        "AUTOBOT_REDIS_DB_PROMPTS": "2",
        "AUTOBOT_REDIS_DB_AGENTS": "3",
        "AUTOBOT_REDIS_DB_METRICS": "4",
        "AUTOBOT_REDIS_DB_CACHE": "5",
        "AUTOBOT_REDIS_DB_SESSIONS": "6",
        "AUTOBOT_REDIS_DB_TASKS": "7",
        "AUTOBOT_REDIS_DB_LOGS": "8",
        "AUTOBOT_REDIS_DB_TEMP": "9",
        "AUTOBOT_REDIS_DB_BACKUP": "10",
        "AUTOBOT_REDIS_DB_TESTING": "15",
    }

    # Check for missing database assignments
    for db_var, expected_value in expected_dbs.items():
        if db_var in env_vars:
            if env_vars[db_var] != expected_value:
                errors.append(
                    f"Redis database mismatch: {db_var} = {env_vars[db_var]}, expected {expected_value}"
                )
        else:
            errors.append(f"Missing Redis database assignment: {db_var}")

    # Check for duplicate database numbers
    db_values = []
    for db_var, value in env_vars.items():
        if (
            db_var.startswith("AUTOBOT_REDIS_DB_")
            and db_var != "AUTOBOT_REDIS_DB_TESTING"
        ):
            if value in db_values:
                errors.append(
                    f"Duplicate Redis database number: {value} used by {db_var}"
                )
            db_values.append(value)

    return errors


def validate_ip_consistency(env_vars: Dict[str, str], env_type: str) -> List[str]:
    """Validate IP address consistency"""
    errors = []

    # Expected IP patterns by environment type
    expected_patterns = {
        "main": r"^172\.16\.168\.",
        "native-vm": r"^172\.16\.168\.",
        "localhost": r"^127\.0\.0\.1$",
        "network": r"^172\.16\.168\.",
    }

    pattern = expected_patterns.get(env_type)
    if not pattern:
        return errors  # No IP validation for this environment type

    ip_vars = [var for var in env_vars if var.endswith("_HOST")]

    for var in ip_vars:
        value = env_vars[var]
        if not re.match(pattern, value):
            errors.append(
                f"IP address pattern mismatch in {var}: {value} (expected pattern: {pattern})"
            )

    return errors


def validate_url_consistency(env_vars: Dict[str, str]) -> List[str]:
    """Validate URL construction consistency"""
    errors = []

    # Check that URL variables match host/port combinations
    url_mappings = [
        ("AUTOBOT_BACKEND_URL", "AUTOBOT_BACKEND_HOST", "AUTOBOT_BACKEND_PORT"),
        ("AUTOBOT_REDIS_URL", "AUTOBOT_REDIS_HOST", "AUTOBOT_REDIS_PORT"),
        ("AUTOBOT_OLLAMA_URL", "AUTOBOT_OLLAMA_HOST", "AUTOBOT_OLLAMA_PORT"),
    ]

    for url_var, host_var, port_var in url_mappings:
        if all(var in env_vars for var in [url_var, host_var, port_var]):
            expected_url = f"http://{env_vars[host_var]}:{env_vars[port_var]}"
            actual_url = env_vars[url_var]

            if url_var == "AUTOBOT_REDIS_URL":
                expected_url = f"redis://{env_vars[host_var]}:{env_vars[port_var]}"

            if actual_url != expected_url:
                errors.append(
                    f"URL mismatch: {url_var} = {actual_url}, expected {expected_url}"
                )

    return errors


def validate_port_consistency(
    env_vars: Dict[str, str], config: Dict[str, Any]
) -> List[str]:
    """Validate port assignments match configuration"""
    errors = []

    expected_ports = config.get("infrastructure", {}).get("ports", {})

    port_mappings = {
        "AUTOBOT_BACKEND_PORT": "backend",
        "AUTOBOT_FRONTEND_PORT": "frontend",
        "AUTOBOT_REDIS_PORT": "redis",
        "AUTOBOT_OLLAMA_PORT": "ollama",
        "AUTOBOT_AI_STACK_PORT": "ai_stack",
        "AUTOBOT_NPU_WORKER_PORT": "npu_worker",
    }

    for env_var, config_key in port_mappings.items():
        if env_var in env_vars and config_key in expected_ports:
            actual_port = env_vars[env_var]
            expected_port = str(expected_ports[config_key])

            if actual_port != expected_port:
                errors.append(
                    f"Port mismatch: {env_var} = {actual_port}, expected {expected_port}"
                )

    return errors


def check_legacy_compatibility(env_vars: Dict[str, str]) -> List[str]:
    """Check legacy variable compatibility"""
    warnings = []

    # Legacy variables that should be present for backward compatibility
    legacy_mappings = [
        ("REDIS_HOST", "AUTOBOT_REDIS_HOST"),
        ("REDIS_PORT", "AUTOBOT_REDIS_PORT"),
        ("OLLAMA_HOST", "AUTOBOT_OLLAMA_HOST"),
        ("OLLAMA_PORT", "AUTOBOT_OLLAMA_PORT"),
    ]

    for legacy_var, modern_var in legacy_mappings:
        if modern_var in env_vars and legacy_var not in env_vars:
            warnings.append(
                f"Missing legacy compatibility variable: {legacy_var} (should match {modern_var})"
            )
        elif legacy_var in env_vars and modern_var in env_vars:
            if env_vars[legacy_var] != env_vars[modern_var]:
                warnings.append(
                    f"Legacy variable mismatch: {legacy_var} = {env_vars[legacy_var]}, {modern_var} = {env_vars[modern_var]}"
                )

    return warnings


def validate_environment_file(
    file_path: Path, env_type: str, config: Dict[str, Any]
) -> Dict[str, List[str]]:
    """Validate a single environment file"""
    results = {"errors": [], "warnings": []}

    if not file_path.exists():
        results["errors"].append(f"Environment file does not exist: {file_path}")
        return results

    env_vars = parse_env_file(file_path)

    # Run all validations
    results["errors"].extend(validate_required_variables(env_vars, env_type))
    results["errors"].extend(validate_redis_databases(env_vars, env_type))
    results["errors"].extend(validate_ip_consistency(env_vars, env_type))
    results["errors"].extend(validate_url_consistency(env_vars))
    results["errors"].extend(validate_port_consistency(env_vars, config))

    results["warnings"].extend(check_legacy_compatibility(env_vars))

    return results


def main():
    """Main validation function"""
    print("AutoBot Environment File Validator")
    print("=" * 40)

    # Load configuration
    try:
        config = load_config()
        print("✓ Loaded config/complete.yaml")
    except Exception as e:
        print(f"✗ Error loading configuration: {e}")
        return 1

    project_root = Path(__file__).parent.parent

    # Define environment files to validate
    env_files = {
        ".env": "main",
        ".env.localhost": "localhost",
        ".env.native-vm": "native-vm",
        ".env.network": "network",
        "autobot-vue/.env": "frontend",
        "docker/compose/.env.production": "docker-production",
    }

    total_errors = 0
    total_warnings = 0
    validated_files = 0

    # Validate each environment file
    for file_path, env_type in env_files.items():
        full_path = project_root / file_path
        print(f"\n🔍 Validating {file_path}...")

        results = validate_environment_file(full_path, env_type, config)

        if results["errors"]:
            print(f"  ✗ {len(results['errors'])} errors found:")
            for error in results["errors"]:
                print(f"    • {error}")
            total_errors += len(results["errors"])
        else:
            print("  ✓ No errors found")

        if results["warnings"]:
            print(f"  ⚠ {len(results['warnings'])} warnings:")
            for warning in results["warnings"]:
                print(f"    • {warning}")
            total_warnings += len(results["warnings"])

        validated_files += 1

    # Summary
    print("\n" + "=" * 40)
    print("Validation Summary:")
    print(f"Files validated: {validated_files}/{len(env_files)}")
    print(f"Total errors: {total_errors}")
    print(f"Total warnings: {total_warnings}")

    if total_errors == 0:
        print("🎉 All environment files are valid!")
        if total_warnings > 0:
            print(f"⚠ {total_warnings} warnings found - review recommended")
    else:
        print(f"❌ {total_errors} errors found - fix required")
        print("\nTo fix errors:")
        print("1. Edit config/complete.yaml if configuration changes needed")
        print("2. Run: python scripts/generate-env-files.py")
        print("3. Re-run validation: python scripts/validate-env-files.py")

    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    exit(main())
