# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
System Knowledge Manager for AutoBot
Manages immutable system knowledge templates and their runtime copies
"""

import asyncio
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import aiofiles
import yaml

from agents.kb_librarian import KBLibrarian
from agents.kb_librarian.stable_ids import SystemFactIds, SystemFactStoreError
from agents.system_knowledge_defaults import DefaultKnowledgeMixin
from agents.system_knowledge_runtime import sync_runtime_copy, sync_runtime_text
from autobot_shared.logging_manager import get_logger
from autobot_shared.system_knowledge_paths import system_knowledge_dirs
from constants.threshold_constants import CategoryDefaults
from knowledge_base import KnowledgeBase

logger = get_logger(__name__)


class SystemKnowledgeManager(DefaultKnowledgeMixin):
    """Manages system knowledge templates and runtime knowledge base integration"""

    def __init__(self, knowledge_base: KnowledgeBase):
        """Initialize manager with knowledge base and directory paths."""
        self.knowledge_base = knowledge_base
        self.librarian = KBLibrarian(knowledge_base)

        # Template, runtime and backup dirs all come from ONE root; the template tree is read-only here.
        dirs = system_knowledge_dirs()
        self.system_knowledge_dir = dirs.templates
        self.runtime_knowledge_dir = dirs.runtime
        self.backup_dir = dirs.backup
        self.fact_ids = SystemFactIds()
        self._import_failures: List[str] = []
        self._import_unresolved: List[str] = []

        # Ensure directories exist
        self.runtime_knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    async def initialize_system_knowledge(self, force_reinstall: bool = False):
        """Initialize system knowledge from templates with intelligent change detection"""
        logger.info("Initializing system knowledge...")

        if force_reinstall:
            await self._backup_current_knowledge()
            await self._clear_system_knowledge()

        # Check if system knowledge needs updating based on file changes
        needs_update, changed_files = await self._check_system_knowledge_changes()

        if not force_reinstall and not needs_update:
            logger.info("System knowledge is up-to-date, skipping initialization")
            return

        if changed_files:
            ellipsis = "..." if len(changed_files) > 3 else ""
            logger.info(f"Detected changes in {len(changed_files)} files: " f"{changed_files[:3]}{ellipsis}")

        # Import all system knowledge
        failed = await self._import_system_knowledge()
        if failed:
            # No cache write: the next start sees the files as changed and retries the failed items.
            logger.error("System knowledge import incomplete: %d item(s) failed, will retry", failed)
            return

        # Update the change tracking cache
        await self._update_system_knowledge_cache()

        logger.info("System knowledge initialization completed")

    async def _check_system_knowledge_changes(self) -> tuple[bool, List[str]]:
        """Check if system knowledge files have changed since last import"""
        try:
            # Get current file states
            current_state = await self._get_system_knowledge_file_state()

            # Load cached state from Redis
            cached_state = await self._load_file_state_cache()

            if not cached_state:
                logger.info("No cached file state found - first import needed")
                return True, list(current_state.keys())

            # Compare states to find changes
            changed_files = []

            # Check for modified or new files
            for file_path, current_hash in current_state.items():
                if file_path not in cached_state:
                    changed_files.append(f"{file_path} (new)")
                elif cached_state[file_path] != current_hash:
                    changed_files.append(f"{file_path} (modified)")

            # Check for deleted files
            for file_path in cached_state:
                if file_path not in current_state:
                    changed_files.append(f"{file_path} (deleted)")

            needs_update = len(changed_files) > 0
            return needs_update, changed_files

        except Exception as e:
            logger.warning("Error checking system knowledge changes: %s", e)
            # On error, assume update is needed
            return True, ["error-triggered-update"]

    async def _get_system_knowledge_file_state(self) -> Dict[str, str]:
        """Get current state (hash) of all system knowledge files"""
        file_states = {}

        dir_exists = await asyncio.to_thread(self.system_knowledge_dir.exists)
        if not dir_exists:
            return file_states

        # Issue #358 - wrap glob in lambda to avoid blocking
        yaml_files = await asyncio.to_thread(lambda: list(self.system_knowledge_dir.rglob("*.yaml")))
        for file_path in yaml_files:
            try:
                # Get file content hash
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    content = await f.read()
                file_hash = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()

                # Use relative path as key
                relative_path = str(file_path.relative_to(self.system_knowledge_dir))
                file_states[relative_path] = file_hash

            except OSError as e:
                logger.warning("Failed to read file %s: %s", file_path, e)
            except Exception as e:
                logger.warning("Error processing file %s: %s", file_path, e)

        return file_states

    async def _load_file_state_cache(self) -> Dict[str, str] | None:
        """Load cached file states from Redis"""
        try:
            from autobot_shared.redis_client import get_redis_client

            redis_client = get_redis_client(database="knowledge")

            if not redis_client:
                return None

            cache_key = "autobot:system_knowledge:file_states"
            # Issue #361 - avoid blocking
            cached_data = await asyncio.to_thread(redis_client.get, cache_key)

            if cached_data:
                data = json.loads(cached_data)
                # Extract file_states from the wrapper if it exists
                return data.get("file_states", data)

        except Exception as e:
            logger.debug("Redis cache load failed for system knowledge: %s", e)

        return None

    async def _update_system_knowledge_cache(self):
        """Update the cached file states in Redis"""
        try:
            from autobot_shared.redis_client import get_redis_client

            redis_client = get_redis_client(database="knowledge")

            if not redis_client:
                logger.warning("Redis not available for system knowledge caching")
                return

            # Get current file states
            current_state = await self._get_system_knowledge_file_state()

            # Cache for 30 days (system knowledge doesn't change often)
            cache_key = "autobot:system_knowledge:file_states"
            ttl_seconds = 30 * 24 * 60 * 60  # 30 days

            # Issue #361 - avoid blocking
            await asyncio.to_thread(
                redis_client.setex,
                cache_key,
                ttl_seconds,
                json.dumps(
                    {
                        "file_states": current_state,
                        "last_updated": datetime.now(tz=timezone.utc).isoformat(),
                        "file_count": len(current_state),
                    }
                ),
            )

            logger.info(f"Updated system knowledge cache with {len(current_state)} files")

        except Exception as e:
            logger.warning("Failed to update system knowledge cache: %s", e)

    async def _backup_current_knowledge(self):
        """Backup current system knowledge"""
        dir_exists = await asyncio.to_thread(self.runtime_knowledge_dir.exists)
        if not dir_exists:
            return

        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"backup_{timestamp}"

        dir_exists = await asyncio.to_thread(self.runtime_knowledge_dir.exists)
        if dir_exists:
            await asyncio.to_thread(shutil.copytree, self.runtime_knowledge_dir, backup_path)
            logger.info("Backed up system knowledge to %s", backup_path)

    async def _clear_system_knowledge(self):
        """Clear current system knowledge"""
        dir_exists = await asyncio.to_thread(self.runtime_knowledge_dir.exists)
        if dir_exists:
            await asyncio.to_thread(shutil.rmtree, self.runtime_knowledge_dir)
        await asyncio.to_thread(self.runtime_knowledge_dir.mkdir, parents=True, exist_ok=True)

        # Clear from knowledge base
        await self._clear_system_knowledge_from_kb()

    async def _clear_system_knowledge_from_kb(self):
        """Clear system knowledge entries from knowledge base"""
        # This would need to be implemented based on your KB's delete functionality
        logger.info("Clearing system knowledge from knowledge base")

    async def _import_system_knowledge(self) -> int:
        """Import all system knowledge from templates. Returns how many items failed to store."""
        self._import_failures, self._import_unresolved = [], []
        await self.fact_ids.load()
        dir_exists = await asyncio.to_thread(self.system_knowledge_dir.exists)
        if not dir_exists:
            # Never generate into the tracked template tree: defaults go to the runtime dir.
            logger.warning(f"System knowledge directory not found: {self.system_knowledge_dir}")
            await self._create_default_system_knowledge()
            await self._import_from_runtime_files()
        else:
            await self._import_tools_knowledge()
            await self._import_workflows_knowledge()
            await self._import_procedures_knowledge()
        self._report_unresolved()
        return len(self._import_failures)

    async def _copy_to_runtime(self, template: Path, kind: str) -> None:
        """Mirror a template into the runtime dir, keeping an operator-edited copy (#18556)."""
        await asyncio.to_thread(sync_runtime_copy, template, self.runtime_knowledge_dir, f"{kind}/{template.name}")

    async def _save_yaml_file(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """Write generated YAML into the runtime dir, keeping an operator-edited file (#18556)."""
        try:
            relative = str(file_path.relative_to(self.runtime_knowledge_dir))
            text = yaml.dump(data, default_flow_style=False, indent=2)
            await asyncio.to_thread(sync_runtime_text, text, self.runtime_knowledge_dir, relative)
            return True
        except (OSError, ValueError) as e:
            logger.error("Failed to save YAML file %s: %s", file_path, e)
            return False

    async def _create_default_system_knowledge(self):
        """Create default system knowledge templates."""
        logger.info("Creating default system knowledge templates...")

        # Create directory structure (runtime dir: the tracked template tree is never written)
        tools_dir = self.runtime_knowledge_dir / "tools"
        workflows_dir = self.runtime_knowledge_dir / "workflows"
        procedures_dir = self.runtime_knowledge_dir / "procedures"
        await asyncio.gather(
            asyncio.to_thread(tools_dir.mkdir, parents=True, exist_ok=True),
            asyncio.to_thread(workflows_dir.mkdir, parents=True, exist_ok=True),
            asyncio.to_thread(procedures_dir.mkdir, parents=True, exist_ok=True),
        )

        # Save steganography tools and workflow in parallel
        await asyncio.gather(
            self._save_yaml_file(tools_dir / "steganography.yaml", self._get_steganography_tools_data()),
            self._save_yaml_file(
                workflows_dir / "image_forensics.yaml",
                self._get_image_forensics_workflow_data(),
            ),
        )

        logger.info("Default system knowledge templates created")

    async def _import_tools_knowledge(self):
        """Import tools knowledge from YAML templates"""
        tools_dir = self.system_knowledge_dir / "tools"
        dir_exists = await asyncio.to_thread(tools_dir.exists)
        if not dir_exists:
            return

        # Issue #358 - wrap glob in lambda to avoid blocking
        yaml_files = await asyncio.to_thread(lambda: list(tools_dir.glob("*.yaml")))
        for yaml_file in yaml_files:
            logger.info("Importing tools from %s", yaml_file)

            try:
                async with aiofiles.open(yaml_file, "r", encoding="utf-8") as f:
                    content = await f.read()
                    tools_data = yaml.safe_load(content)
            except OSError as e:
                logger.error("Failed to read tools file %s: %s", yaml_file, e)
                continue

            await self._copy_to_runtime(yaml_file, "tools")

            # Import tools into knowledge base
            for tool_data in tools_data.get("tools", []):
                await self._import_single_tool(tool_data)

    async def _import_single_tool(self, tool_data: Dict[str, Any]):
        """Import a single tool into the knowledge base"""
        tool_name = tool_data.get("name", "unknown")

        # Convert YAML structure to librarian format
        tool_info = {
            "name": tool_name,
            "type": tool_data.get("type", "command-line tool"),
            "purpose": tool_data.get("purpose", ""),
            "category": tool_data.get("type", CategoryDefaults.GENERAL),
            "platform": "linux",
            "installation": self._format_installation(tool_data.get("installation", {})),
            "usage": self._format_usage(tool_data.get("usage", {})),
            "command_examples": tool_data.get("common_examples", []),
            "troubleshooting": self._format_troubleshooting(tool_data.get("troubleshooting", [])),
            "security_notes": "\n".join(tool_data.get("security_notes", [])),
            "related_tools": tool_data.get("related_tools", []),
            "output_formats": "\n".join(tool_data.get("output_formats", [])),
            "limitations": "\n".join(tool_data.get("limitations", [])),
            "verified": "system_knowledge",
        }

        try:
            result = await self.librarian.store_tool_knowledge(tool_info, ref=self.fact_ids.of("tool", tool_name))
        except SystemFactStoreError as e:
            return self._record_import_failure("tool", tool_name, e)
        self._log_imported("tool", tool_name, result)

    async def _import_workflows_knowledge(self):
        """Import workflow knowledge from YAML templates"""
        workflows_dir = self.system_knowledge_dir / "workflows"
        dir_exists = await asyncio.to_thread(workflows_dir.exists)
        if not dir_exists:
            return

        # Issue #358 - wrap glob in lambda to avoid blocking
        yaml_files = await asyncio.to_thread(lambda: list(workflows_dir.glob("*.yaml")))
        for yaml_file in yaml_files:
            logger.info("Importing workflow from %s", yaml_file)

            try:
                async with aiofiles.open(yaml_file, "r", encoding="utf-8") as f:
                    content = await f.read()
                    workflow_data = yaml.safe_load(content)
            except OSError as e:
                logger.error("Failed to read workflow file %s: %s", yaml_file, e)
                continue

            await self._copy_to_runtime(yaml_file, "workflows")

            # Import workflow into knowledge base
            await self._import_single_workflow(workflow_data)

    async def _import_single_workflow(self, workflow_data: Dict[str, Any]):
        """Import a single workflow into knowledge base"""
        metadata = workflow_data.get("metadata", {})
        workflow_name = metadata.get("name", "Unknown Workflow")

        # Convert to librarian format
        workflow_info = {
            "name": workflow_name,
            "type": metadata.get("category", CategoryDefaults.GENERAL),
            "complexity": metadata.get("complexity", "medium"),
            "estimated_time": metadata.get("estimated_time", "varies"),
            "objective": workflow_data.get("objective", ""),
            "prerequisites": workflow_data.get("prerequisites", []),
            "required_tools": workflow_data.get("required_tools", []),
            "workflow_steps": workflow_data.get("workflow_steps", []),
            "decision_points": workflow_data.get("decision_points", []),
            "quality_checks": workflow_data.get("quality_checks", []),
            "pitfalls": self._format_pitfalls(workflow_data.get("common_pitfalls", [])),
            "category": "workflows",
        }

        try:
            result = await self.librarian.store_workflow_knowledge(
                workflow_info, ref=self.fact_ids.of("workflow", workflow_name)
            )
        except SystemFactStoreError as e:
            return self._record_import_failure("workflow", workflow_name, e)
        self._log_imported("workflow", workflow_name, result)

    async def _import_procedures_knowledge(self):
        """Import procedures knowledge from YAML templates"""
        procedures_dir = self.system_knowledge_dir / "procedures"
        dir_exists = await asyncio.to_thread(procedures_dir.exists)
        if not dir_exists:
            return

        # Issue #358 - wrap glob in lambda to avoid blocking
        yaml_files = await asyncio.to_thread(lambda: list(procedures_dir.glob("*.yaml")))
        for yaml_file in yaml_files:
            logger.info("Importing procedure from %s", yaml_file)

            try:
                async with aiofiles.open(yaml_file, "r", encoding="utf-8") as f:
                    content = await f.read()
                    procedure_data = yaml.safe_load(content)
            except OSError as e:
                logger.error("Failed to read procedure file %s: %s", yaml_file, e)
                continue

            await self._copy_to_runtime(yaml_file, "procedures")

            # Import procedure into knowledge base
            await self._import_single_procedure(procedure_data)

    async def _import_single_procedure(self, procedure_data: Dict[str, Any]):
        """Import a single procedure into knowledge base"""
        title = procedure_data.get("title", "System Procedure")

        # Convert to librarian format
        doc_info = {
            "title": title,
            "type": procedure_data.get("type", "procedure"),
            "category": procedure_data.get("category", "system"),
            "overview": procedure_data.get("overview", ""),
            "procedures": procedure_data.get("procedures", []),
            "steps": procedure_data.get("steps", []),
            "common_issues": self._format_procedure_issues(procedure_data.get("common_issues", [])),
            "best_practices": procedure_data.get("best_practices", []),
            "examples": procedure_data.get("examples", []),
            "verification": procedure_data.get("verification", []),
        }

        try:
            result = await self.librarian.store_system_documentation(doc_info, ref=self.fact_ids.of("procedure", title))
        except SystemFactStoreError as e:
            return self._record_import_failure("procedure", title, e)
        self._log_imported("procedure", title, result)

    async def reload_system_knowledge(self):
        """Reload system knowledge from runtime files"""
        logger.info("Reloading system knowledge from runtime files...")

        # Clear current system knowledge from KB
        await self._clear_system_knowledge_from_kb()

        self._import_failures = []
        await self.fact_ids.load()
        # Reimport from runtime files
        await self._import_from_runtime_files()

        if self._import_failures:
            logger.error(
                "System knowledge reload incomplete: %d item(s) failed: %s",
                len(self._import_failures),
                ", ".join(self._import_failures),
            )
            return
        logger.info("System knowledge reloaded successfully")

    async def _import_runtime_tools(self):
        """Import tools from runtime directory."""
        tools_dir = self.runtime_knowledge_dir / "tools"
        if not await asyncio.to_thread(tools_dir.exists):
            return
        yaml_files = await asyncio.to_thread(lambda: list(tools_dir.glob("*.yaml")))
        for yaml_file in yaml_files:
            try:
                async with aiofiles.open(yaml_file, "r", encoding="utf-8") as f:
                    tools_data = yaml.safe_load(await f.read())
                for tool_data in tools_data.get("tools", []):
                    await self._import_single_tool(tool_data)
            except OSError as e:
                logger.error("Failed to read tools file %s: %s", yaml_file, e)

    async def _import_runtime_workflows(self):
        """Import workflows from runtime directory."""
        workflows_dir = self.runtime_knowledge_dir / "workflows"
        if not await asyncio.to_thread(workflows_dir.exists):
            return
        yaml_files = await asyncio.to_thread(lambda: list(workflows_dir.glob("*.yaml")))
        for yaml_file in yaml_files:
            try:
                async with aiofiles.open(yaml_file, "r", encoding="utf-8") as f:
                    await self._import_single_workflow(yaml.safe_load(await f.read()))
            except OSError as e:
                logger.error("Failed to read workflow file %s: %s", yaml_file, e)

    async def _import_runtime_procedures(self):
        """Import procedures from runtime directory."""
        procedures_dir = self.runtime_knowledge_dir / "procedures"
        if not await asyncio.to_thread(procedures_dir.exists):
            return
        yaml_files = await asyncio.to_thread(lambda: list(procedures_dir.glob("*.yaml")))
        for yaml_file in yaml_files:
            try:
                async with aiofiles.open(yaml_file, "r", encoding="utf-8") as f:
                    await self._import_single_procedure(yaml.safe_load(await f.read()))
            except OSError as e:
                logger.error("Failed to read procedure file %s: %s", yaml_file, e)

    async def _import_from_runtime_files(self):
        """Import system knowledge from runtime files."""
        await self._import_runtime_tools()
        await self._import_runtime_workflows()
        await self._import_runtime_procedures()

    def get_knowledge_categories(self) -> Dict[str, Any]:
        """
        Get knowledge base categories structure.

        Returns a dictionary with success status and categories structure
        that can be used by the knowledge base stats system.

        Returns:
            Dict with 'success' boolean and 'categories' dict
        """
        try:
            # Return basic category structure for system knowledge
            categories = {
                "documentation": {
                    "description": "System documentation and guides",
                    "subcategories": {
                        "setup": "Setup and installation guides",
                        "configuration": "Configuration files and options",
                        "troubleshooting": "Problem resolution guides",
                    },
                },
                "system": {
                    "description": "System knowledge and procedures",
                    "subcategories": {
                        "commands": "System commands and utilities",
                        "workflows": "Automated workflows and procedures",
                        "security": "Security tools and practices",
                    },
                },
                "configuration": {
                    "description": "Configuration templates and examples",
                    "subcategories": {
                        "templates": "Configuration templates",
                        "examples": "Example configurations",
                        "best_practices": "Configuration best practices",
                    },
                },
            }

            return {"success": True, "categories": categories}

        except Exception as e:
            logger.error("Failed to get knowledge categories: %s", e)
            return {
                "success": False,
                "error": "Failed to retrieve knowledge categories",
                "categories": {},
            }
