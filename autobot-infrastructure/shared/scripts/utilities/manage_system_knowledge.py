#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System Knowledge Management CLI Tool
Provides command-line interface for managing system knowledge templates
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


async def init_knowledge(force: bool = False):
    """Initialize system knowledge"""
    logger.info("🔄 Initializing system knowledge...")

    try:
        kb = KnowledgeBase()
        await kb.ainit()

        manager = SystemKnowledgeManager(kb)
        await manager.initialize_system_knowledge(force_reinstall=force)

        logger.info("✅ System knowledge initialized successfully!")

    except Exception as e:
        logger.error(f"❌ Failed to initialize system knowledge: {e}")
        import traceback

        traceback.print_exc()
        return False

    return True


async def reload_knowledge():
    """Reload system knowledge from runtime files"""
    logger.info("🔄 Reloading system knowledge...")

    try:
        kb = KnowledgeBase()
        await kb.ainit()

        manager = SystemKnowledgeManager(kb)
        await manager.reload_system_knowledge()

        logger.info("✅ System knowledge reloaded successfully!")

    except Exception as e:
        logger.error(f"❌ Failed to reload system knowledge: {e}")
        import traceback

        traceback.print_exc()
        return False

    return True


def list_knowledge():
    """List available system knowledge files"""
    logger.info("📚 System Knowledge Structure:")
    logger.info("=" * 50)

    # List original templates
    system_dir = Path("system_knowledge")
    if system_dir.exists():
        logger.info("\n🔒 ORIGINAL TEMPLATES (Immutable):")
        for category_dir in system_dir.iterdir():
            if category_dir.is_dir():
                logger.info(f"  📁 {category_dir.name}/")
                for yaml_file in category_dir.glob("*.yaml"):
                    logger.info(f"    📄 {yaml_file.name}")
    else:
        logger.warning("\n⚠️ Original templates directory not found")

    # List runtime copies
    runtime_dir = Path("data/system_knowledge")
    if runtime_dir.exists():
        logger.info("\n✏️ RUNTIME COPIES (Editable):")
        for category_dir in runtime_dir.iterdir():
            if category_dir.is_dir() and category_dir.name != "__pycache__":
                logger.info(f"  📁 {category_dir.name}/")
                for yaml_file in category_dir.glob("*.yaml"):
                    logger.info(f"    📄 {yaml_file.name}")
    else:
        logger.warning("\n⚠️ Runtime knowledge directory not found")

    # List backups
    backup_dir = Path("data/system_knowledge_backups")
    if backup_dir.exists() and any(backup_dir.iterdir()):
        logger.info("\n🗄️ BACKUPS:")
        for backup in sorted(backup_dir.iterdir()):
            if backup.is_dir():
                logger.info(f"  📦 {backup.name}")
    else:
        logger.info("\n📦 No backups found")


def edit_knowledge(category: str, filename: str):
    """Open knowledge file for editing"""
    runtime_file = Path("data/system_knowledge") / category / f"{filename}.yaml"

    if not runtime_file.exists():
        logger.error(f"❌ File not found: {runtime_file}")
        logger.info("💡 Available files:")
        list_knowledge()
        return False

    logger.info(f"📝 Opening {runtime_file} for editing...")
    logger.info(
        "💡 After editing, run 'python manage_system_knowledge.py reload' "
        "to apply changes"
    )

    # Try to open with system editor
    import os

    editor = os.environ.get("EDITOR", "nano")

    try:
        os.system(f"{editor} {runtime_file}")
        logger.info("✅ File editing completed")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to open editor: {e}")
        logger.info(f"💡 You can manually edit: {runtime_file}")
        return False


def _validate_tools_category(yaml_file: Path, data: dict, errors: list) -> None:
    """Validate tools category YAML (Issue #315: extracted helper)."""
    if "tools" not in data:
        errors.append(f"{yaml_file}: Missing 'tools' key")
        return
    if not isinstance(data["tools"], list):
        errors.append(f"{yaml_file}: 'tools' must be a list")
        return
    for i, tool in enumerate(data["tools"]):
        if not isinstance(tool, dict):
            errors.append(f"{yaml_file}: Tool {i} must be a dictionary")
        elif "name" not in tool:
            errors.append(f"{yaml_file}: Tool {i} missing 'name'")


def _validate_yaml_file(
    yaml_file: Path, category_name: str, runtime_dir: Path, errors: list, warnings: list
) -> bool:
    """Validate single YAML file (Issue #315: extracted helper)."""
    try:
        with open(yaml_file, "r") as f:
            data = yaml.safe_load(f)

        if not data:
            errors.append(f"{yaml_file}: Empty file")
            return False

        # Validate based on category
        if category_name == "tools":
            _validate_tools_category(yaml_file, data, errors)
        elif category_name == "workflows":
            if "metadata" not in data:
                warnings.append(f"{yaml_file}: Missing 'metadata' section")
            if "workflow_steps" not in data:
                errors.append(f"{yaml_file}: Missing 'workflow_steps'")
        elif category_name == "procedures":
            if "title" not in data:
                errors.append(f"{yaml_file}: Missing 'title'")

        logger.info(f"✅ {yaml_file.relative_to(runtime_dir)}")
        return True

    except yaml.YAMLError as e:
        errors.append(f"{yaml_file}: YAML syntax error - {e}")
        return False
    except Exception as e:
        errors.append(f"{yaml_file}: Validation error - {e}")
        return False


def validate_knowledge():
    """Validate system knowledge YAML files"""
    logger.info("🔍 Validating system knowledge files...")

    errors = []
    warnings = []

    runtime_dir = Path("data/system_knowledge")
    if not runtime_dir.exists():
        logger.error("❌ Runtime knowledge directory not found")
        return False

    # Validate each category directory (Issue #315: reduced nesting)
    for category_dir in runtime_dir.iterdir():
        if not category_dir.is_dir() or category_dir.name == "__pycache__":
            continue
        for yaml_file in category_dir.glob("*.yaml"):
            _validate_yaml_file(
                yaml_file, category_dir.name, runtime_dir, errors, warnings
            )

    # Report results
    if errors:
        logger.error(f"\n❌ Found {len(errors)} errors:")
        for error in errors:
            logger.error(f"  • {error}")

    if warnings:
        logger.warning(f"\n⚠️ Found {len(warnings)} warnings:")
        for warning in warnings:
            logger.warning(f"  • {warning}")

    if not errors and not warnings:
        logger.info("✅ All system knowledge files are valid!")

    return len(errors) == 0


def _build_tools_template(name: str) -> dict:
    """Build a tools category template.

    Helper for create_template (#825).
    """
    return {
        "metadata": {
            "category": name,
            "description": f"{name} tools",
            "last_updated": "2024-01-01T00:00:00",
            "version": "1.0.0",
        },
        "tools": [
            {
                "name": "example_tool",
                "type": "command-line tool",
                "purpose": "Description of what this tool does",
                "installation": {"apt": "sudo apt-get install example_tool"},
                "usage": {"basic": "example_tool [options] [file]"},
                "common_examples": [
                    {
                        "description": "Basic usage example",
                        "command": "example_tool --help",
                        "expected_output": "Help information",
                    }
                ],
                "troubleshooting": [
                    {
                        "problem": "Common error message",
                        "solution": "How to fix it",
                    }
                ],
            }
        ],
    }


def _build_workflows_template(name: str) -> dict:
    """Build a workflows category template.

    Helper for create_template (#825).
    """
    return {
        "metadata": {
            "name": f"{name} Workflow",
            "category": "general",
            "complexity": "medium",
            "estimated_time": "10-30 minutes",
            "version": "1.0.0",
        },
        "objective": f"Perform {name} analysis",
        "prerequisites": [
            "Required tools installed",
            "Target files available",
        ],
        "required_tools": [
            {
                "name": "example_tool",
                "purpose": "Primary analysis tool",
                "optional": False,
            }
        ],
        "workflow_steps": [
            {
                "step": 1,
                "action": "Initial analysis",
                "details": "Gather basic information",
                "commands": ["example_tool --info {target}"],
                "expected_output": "Basic file information",
            }
        ],
    }


def _build_procedures_template(name: str) -> dict:
    """Build a procedures category template.

    Helper for create_template (#825).
    """
    return {
        "title": f"{name} Procedure",
        "type": "procedure",
        "category": "system",
        "overview": f"Procedure for {name}",
        "procedures": [
            {
                "name": f"{name} Setup",
                "description": f"How to set up {name}",
                "steps": [
                    "Step 1: Preparation",
                    "Step 2: Configuration",
                    "Step 3: Verification",
                ],
            }
        ],
    }


def create_template(category: str, name: str):
    """Create a new knowledge template"""
    if category not in ["tools", "workflows", "procedures"]:
        logger.error("Invalid category. Must be: tools, workflows, procedures")
        return False

    runtime_dir = Path("data/system_knowledge") / category
    runtime_dir.mkdir(parents=True, exist_ok=True)

    template_file = runtime_dir / f"{name}.yaml"
    if template_file.exists():
        logger.error("Template already exists: %s", template_file)
        return False

    # Build template (#825: extracted to helpers)
    builders = {
        "tools": _build_tools_template,
        "workflows": _build_workflows_template,
        "procedures": _build_procedures_template,
    }
    template = builders[category](name)

    with open(template_file, "w") as f:
        yaml.dump(template, f, default_flow_style=False, indent=2)

    logger.info("Created template: %s", template_file)
    logger.info(
        "Edit the template and run "
        "'python manage_system_knowledge.py reload' to apply"
    )
    return True


def _build_cli_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Helper for main (#825).
    """
    parser = argparse.ArgumentParser(
        description="System Knowledge Management Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage_system_knowledge.py init          # Initialize
  python manage_system_knowledge.py init --force   # Force reinstall
  python manage_system_knowledge.py list           # List files
  python manage_system_knowledge.py validate       # Validate YAML
  python manage_system_knowledge.py reload         # Reload from files
  python manage_system_knowledge.py create tools forensics
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    init_parser = subparsers.add_parser("init", help="Initialize system knowledge")
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Force reinstall (overwrites existing)",
    )

    subparsers.add_parser("list", help="List system knowledge files")

    edit_parser = subparsers.add_parser("edit", help="Edit knowledge file")
    edit_parser.add_argument(
        "category",
        choices=["tools", "workflows", "procedures"],
        help="Knowledge category",
    )
    edit_parser.add_argument("filename", help="Filename (without .yaml extension)")

    subparsers.add_parser("validate", help="Validate YAML files")
    subparsers.add_parser("reload", help="Reload knowledge from files")

    create_parser = subparsers.add_parser("create", help="Create new template")
    create_parser.add_argument(
        "category",
        choices=["tools", "workflows", "procedures"],
        help="Knowledge category",
    )
    create_parser.add_argument("name", help="Template name")
    return parser


def _dispatch_command(args) -> None:
    """Dispatch CLI command to appropriate handler.

    Helper for main (#825).
    """
    if args.command == "init":
        success = asyncio.run(init_knowledge(args.force))
        sys.exit(0 if success else 1)
    elif args.command == "list":
        list_knowledge()
    elif args.command == "edit":
        success = edit_knowledge(args.category, args.filename)
        sys.exit(0 if success else 1)
    elif args.command == "validate":
        success = validate_knowledge()
        sys.exit(0 if success else 1)
    elif args.command == "reload":
        success = asyncio.run(reload_knowledge())
        sys.exit(0 if success else 1)
    elif args.command == "create":
        success = create_template(args.category, args.name)
        sys.exit(0 if success else 1)


def main():
    """Main CLI function"""
    parser = _build_cli_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    _dispatch_command(args)


if __name__ == "__main__":
    main()
