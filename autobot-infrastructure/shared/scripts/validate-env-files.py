#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot Environment File Validator
Validates consistency between environment files and complete.yaml
"""

import re
import sys
from pathlib import Path
from typing import Any, Dict, List

# Sibling helper module: the importing script may have been loaded by file path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
# Runs from any directory with no PYTHONPATH: the repository root provides `autobot_shared` (#18289).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from env_files_config import load_config  # noqa: E402

# #19232: the one .env reader -- this file kept its own copy (no quote or inline-comment handling).
from autobot_shared.env_file import parse_env_file  # noqa: E402


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
    """Refuse AUTOBOT_REDIS_DB_* overrides the runtime would refuse (#19232).

    The numbers live in redis-databases.yaml; an env file only overrides one when a
    deployment differs. So this checks what the runtime checks -- a non-numeric value,
    or two declared databases on one number -- against that one table, instead of a
    hand-kept copy of it (which had drifted: TESTING=15 is celery_results' DB).
    """
    if env_type == "frontend":
        return []
    from autobot_shared.redis_management.database_overrides import override_problems
    from autobot_shared.redis_management.types import DECLARED_DATABASES

    return [f"Redis database override: {problem}" for problem in override_problems(DECLARED_DATABASES, env_vars)]


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
            errors.append(f"IP address pattern mismatch in {var}: {value} (expected pattern: {pattern})")

    return errors


def _expected_redis_url(host: str, port: str) -> str:
    """The credential-free Redis URL for *host*/*port*, from the one URL builder (#19232)."""
    from autobot_shared.redis_management.endpoint import RedisEndpoint

    if not port.strip().isdigit():
        return f"<AUTOBOT_REDIS_PORT {port!r} is not a port>"
    return RedisEndpoint(host=host, port=int(port)).url(with_auth=False)


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
                expected_url = _expected_redis_url(env_vars[host_var], env_vars[port_var])

            if actual_url != expected_url:
                errors.append(f"URL mismatch: {url_var} = {actual_url}, expected {expected_url}")

    return errors


def validate_port_consistency(env_vars: Dict[str, str], config: Dict[str, Any]) -> List[str]:
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
                errors.append(f"Port mismatch: {env_var} = {actual_port}, expected {expected_port}")

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
            warnings.append(f"Missing legacy compatibility variable: {legacy_var} (should match {modern_var})")
        elif legacy_var in env_vars and modern_var in env_vars:
            if env_vars[legacy_var] != env_vars[modern_var]:
                warnings.append(
                    f"Legacy variable mismatch: {legacy_var} = {env_vars[legacy_var]}, "
                    f"{modern_var} = {env_vars[modern_var]}"
                )

    return warnings


#: Native overlays on .env.base (#18555): each holds only what differs from the base.
NATIVE_OVERLAYS = {".env.localhost", ".env.native-vm", ".env.network", ".env.network-template"}


def effective_env_vars(file_path: Path) -> Dict[str, str]:
    """What a loader actually sees: .env.base first, then the overlay on top (#18555).

    A native overlay validated alone would report every shared key as missing.
    """
    env_vars: Dict[str, str] = {}
    base = file_path.parent / ".env.base"
    if file_path.name in NATIVE_OVERLAYS and base.exists():
        env_vars.update(parse_env_file(base))
    if file_path.exists():
        env_vars.update(parse_env_file(file_path))
    return env_vars


def validate_environment_file(file_path: Path, env_type: str, config: Dict[str, Any]) -> Dict[str, List[str]]:
    """Validate a single environment file"""
    results = {"errors": [], "warnings": []}

    if not file_path.exists():
        results["errors"].append(f"Environment file does not exist: {file_path}")
        return results

    env_vars = effective_env_vars(file_path)

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
