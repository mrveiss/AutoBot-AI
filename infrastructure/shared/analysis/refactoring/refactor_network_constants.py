#!/usr/bin/env python3
"""
Script to refactor hardcoded IP addresses and URLs to use shared constants
"""

import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import unified_config_manager

logger = logging.getLogger(__name__)


def get_replacement_map() -> Dict[str, str]:
    """Generate replacement map dynamically from configuration"""
    # Get configuration values
    redis_config = unified_config_manager.get_redis_config()
    backend_config = unified_config_manager.get_backend_config()
    services_config = unified_config_manager.get_distributed_services_config()
    system_defaults = (
        unified_config_manager.get_config_section("service_discovery_defaults") or {}
    )

    # Get values from configuration without hardcoded fallbacks
    redis_host = redis_config.get("host") or system_defaults.get(
        "redis_host", "localhost"
    )
    redis_port = redis_config.get("port") or system_defaults.get("redis_port", 6379)
    backend_host = backend_config.get("host") or system_defaults.get(
        "backend_host", "localhost"
    )
    backend_port = backend_config.get("port") or system_defaults.get(
        "backend_port", 8001
    )
    backend_api_endpoint = f"http://{backend_host}:{backend_port}"

    # Get service-specific hosts from configuration
    frontend_host = services_config.get("frontend", {}).get(
        "host"
    ) or system_defaults.get("frontend_host", "localhost")
    frontend_port = services_config.get("frontend", {}).get(
        "port"
    ) or system_defaults.get("frontend_port", 5173)
    npu_worker_host = services_config.get("npu_worker", {}).get(
        "host"
    ) or system_defaults.get("npu_worker_host", "localhost")
    ai_stack_host = services_config.get("ai_stack", {}).get(
        "host"
    ) or system_defaults.get("ai_stack_host", "localhost")
    browser_host = services_config.get("browser_service", {}).get(
        "host"
    ) or system_defaults.get("browser_service_host", "localhost")
    ollama_config = services_config.get("ollama", {})
    ollama_port = ollama_config.get("port") or system_defaults.get("ollama_port", 11434)

    # Mapping of hardcoded values to constants (from configuration)
    replacement_map = {
        # IP addresses (from config)
        redis_host: "NetworkConstants.REDIS_VM_IP",
        backend_host: "NetworkConstants.MAIN_MACHINE_IP",
        frontend_host: "NetworkConstants.FRONTEND_VM_IP",
        npu_worker_host: "NetworkConstants.NPU_WORKER_VM_IP",
        ai_stack_host: "NetworkConstants.AI_STACK_VM_IP",
        browser_host: "NetworkConstants.BROWSER_VM_IP",
        "localhost": "NetworkConstants.LOCALHOST_IP",
        # URLs (from config)
        f"http://localhost:{backend_port}": "ServiceURLs.BACKEND_LOCAL",
        backend_api_endpoint: "ServiceURLs.BACKEND_API",
        f"http://localhost:{frontend_port}": "ServiceURLs.FRONTEND_LOCAL",
        f"http://{frontend_host}:{frontend_port}": "ServiceURLs.FRONTEND_VM",
        f"http://localhost:{ollama_port}": "ServiceURLs.OLLAMA_LOCAL",
        f"redis://{redis_host}:{redis_port}": "ServiceURLs.REDIS_VM",
        f"redis://localhost:{redis_port}": "ServiceURLs.REDIS_LOCAL",
    }

    return replacement_map


# Get replacement map from configuration
REPLACEMENT_MAP = get_replacement_map()


def should_refactor_file(file_path: Path) -> bool:
    """Check if file should be refactored"""
    # Skip certain directories and files
    skip_patterns = [
        "node_modules",
        ".venv",
        "__pycache__",
        ".git",
        "reports",
        "logs",
        "temp",
        "archives",
        "analysis/refactoring",  # Don't refactor our own analysis tools
    ]

    path_str = str(file_path)
    for pattern in skip_patterns:
        if pattern in path_str:
            return False

    # Only refactor code files
    return file_path.suffix in {".py", ".js", ".ts", ".vue", ".jsx", ".tsx"}


def add_import_if_needed(content: str, file_path: Path) -> str:
    """Add NetworkConstants import if replacements were made and not already imported"""

    # Check if we already have the import
    if (
        "from constants import NetworkConstants" in content
        or "from constants.network_constants import NetworkConstants" in content
    ):
        return content

    # Check if any of our constants are used
    uses_constants = any(
        const_name in content for const_name in REPLACEMENT_MAP.values()
    )
    if not uses_constants:
        return content

    # Find where to add the import
    lines = content.split("\n")
    import_line = "from constants import NetworkConstants, ServiceURLs"

    # Find the best place to add the import
    last_import_line = -1
    for i, line in enumerate(lines):
        if line.strip().startswith(
            ("import ", "from ")
        ) and not line.strip().startswith("from ."):
            last_import_line = i

    if last_import_line >= 0:
        # Add after the last import
        lines.insert(last_import_line + 1, import_line)
    else:
        # Add at the beginning after any docstring
        insert_pos = 0
        if (
            lines
            and lines[0].strip().startswith('"""')
            or lines[0].strip().startswith("'''")
        ):
            # Find end of docstring
            quote_char = '"""' if lines[0].strip().startswith('"""') else "'''"
            for i in range(1, len(lines)):
                if quote_char in lines[i]:
                    insert_pos = i + 1
                    break

        lines.insert(insert_pos, import_line)
        lines.insert(insert_pos + 1, "")  # Add blank line

    return "\n".join(lines)


def refactor_file_content(content: str, file_path: Path) -> Tuple[str, int]:
    """Refactor content to use constants. Returns (new_content, num_replacements)"""
    original_content = content
    replacements_made = 0

    # Sort replacements by length (longest first) to avoid partial replacements
    sorted_replacements = sorted(
        REPLACEMENT_MAP.items(), key=lambda x: len(x[0]), reverse=True
    )

    for hardcoded_value, constant_name in sorted_replacements:
        # Create patterns for different contexts
        patterns = [
            # In quotes
            f'"{re.escape(hardcoded_value)}"',
            f"'{re.escape(hardcoded_value)}'",
            # In f-strings and other contexts
            re.escape(hardcoded_value),
        ]

        for pattern in patterns:
            if pattern in content:
                # For quoted strings, replace with the constant
                if pattern.startswith(('"', "'")):
                    content = content.replace(pattern, constant_name)
                else:
                    # For unquoted occurrences, be more careful
                    # Use word boundaries to avoid partial matches
                    regex_pattern = r"\b" + re.escape(hardcoded_value) + r"\b"
                    if re.search(regex_pattern, content):
                        content = re.sub(regex_pattern, constant_name, content)

                if content != original_content:
                    replacements_made += 1
                    original_content = content

    # Add import if we made replacements
    if replacements_made > 0:
        content = add_import_if_needed(content, file_path)

    return content, replacements_made


def refactor_file(file_path: Path, content: str = None) -> bool:
    """Refactor a single file. Returns True if changes were made.

    Args:
        file_path: Path to the file to refactor
        content: Optional pre-read content (avoids repeated file open) (#623)
    """
    try:
        # Issue #623: Avoid repeated file opens - use pre-read content if provided
        if content is None:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

        new_content, replacements = refactor_file_content(content, file_path)

        if replacements > 0:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            logger.info(f"   ✅ {file_path.name}: {replacements} replacements")
            return True
        else:
            logger.info(f"   ⏭️  {file_path.name}: No changes needed")
            return False

    except Exception as e:
        logger.info(f"   ❌ Error refactoring {file_path}: {e}")
        return False


def find_core_files() -> List[Path]:
    """Find core AutoBot files that should be refactored"""
    # Use project-relative path instead of hardcoded absolute path
    root_path = Path(__file__).parent.parent.parent
    core_files = []

    # Focus on core directories
    core_dirs = ["src", "backend", "autobot-vue/src", "scripts"]

    for core_dir in core_dirs:
        dir_path = root_path / core_dir
        if dir_path.exists():
            for file_path in dir_path.rglob("*"):
                if file_path.is_file() and should_refactor_file(file_path):
                    core_files.append(file_path)

    return core_files


def main():
    """Main refactoring function"""
    logger.info("🚀 Starting network constants refactoring...")
    logger.info(f"📋 Will replace {len(REPLACEMENT_MAP)} hardcoded values with constants")

    # Use project-relative path
    root_path = Path(__file__).parent.parent.parent

    files = find_core_files()
    logger.info(f"📁 Found {len(files)} files to analyze")

    total_files_changed = 0

    # Issue #623: Read each file once, pass content to refactor_file()
    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Check if file contains any hardcoded values
            has_hardcoded = any(
                hardcoded in content for hardcoded in REPLACEMENT_MAP.keys()
            )
            if not has_hardcoded:
                continue

            logger.info(f"🔧 Refactoring {file_path.relative_to(root_path)}...")
            # Pass pre-read content to avoid second file open
            if refactor_file(file_path, content=content):
                total_files_changed += 1

        except Exception as e:
            logger.info(f"❌ Error processing {file_path}: {e}")

    logger.info("\n✅ Network constants refactoring complete!")
    logger.info(f"📊 Files modified: {total_files_changed}")
    logger.info(f"🔄 Total patterns available for replacement: {len(REPLACEMENT_MAP)}")

    logger.info("\n💡 Next steps:")
    logger.info("   1. Test the refactored code")
    logger.info("   2. Update any remaining hardcoded values manually")
    logger.info("   3. Add environment-specific configuration")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
