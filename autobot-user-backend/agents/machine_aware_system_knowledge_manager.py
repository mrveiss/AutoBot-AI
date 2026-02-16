# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Machine-Aware System Knowledge Manager for AutoBot
Extends SystemKnowledgeManager with machine-specific adaptation

Issue #379: Optimized sequential awaits with asyncio.gather for concurrent operations.
"""

import asyncio
import hashlib
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import aiofiles
import yaml

from agents.system_knowledge_manager import SystemKnowledgeManager
from backend.intelligence.os_detector import LinuxDistro, OSType, get_os_detector
from knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


class MachineProfile:
    """Profile of a specific machine's capabilities and configuration"""

    def __init__(self):
        """Initialize machine profile with default capability and configuration values."""
        self.machine_id: str = ""
        self.hostname: str = ""
        self.os_type: OSType = OSType.UNKNOWN
        self.distro: Optional[LinuxDistro] = None
        self.package_manager: str = ""
        self.available_tools: Set[str] = set()
        self.architecture: str = ""
        self.is_wsl: bool = False
        self.is_root: bool = False
        self.capabilities: Set[str] = set()
        self.last_updated: datetime = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to dictionary for serialization"""
        return {
            "machine_id": self.machine_id,
            "hostname": self.hostname,
            "os_type": self.os_type.value if self.os_type else "unknown",
            "distro": self.distro.value if self.distro else None,
            "package_manager": self.package_manager,
            "available_tools": list(self.available_tools),
            "architecture": self.architecture,
            "is_wsl": self.is_wsl,
            "is_root": self.is_root,
            "capabilities": list(self.capabilities),
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MachineProfile":
        """Create profile from dictionary"""
        profile = cls()
        profile.machine_id = data.get("machine_id", "")
        profile.hostname = data.get("hostname", "")
        profile.os_type = OSType(data.get("os_type", "unknown"))
        profile.distro = LinuxDistro(data["distro"]) if data.get("distro") else None
        profile.package_manager = data.get("package_manager", "")
        profile.available_tools = set(data.get("available_tools", []))
        profile.architecture = data.get("architecture", "")
        profile.is_wsl = data.get("is_wsl", False)
        profile.is_root = data.get("is_root", False)
        profile.capabilities = set(data.get("capabilities", []))

        last_updated_str = data.get("last_updated")
        if last_updated_str:
            profile.last_updated = datetime.fromisoformat(last_updated_str)

        return profile


class MachineAwareSystemKnowledgeManager(SystemKnowledgeManager):
    """Enhanced system knowledge manager with machine-specific adaptation"""

    def __init__(self, knowledge_base: KnowledgeBase):
        """Initialize machine-aware manager with profile directory and detection lock."""
        super().__init__(knowledge_base)

        # Machine-specific paths
        self.machine_profiles_dir = self.runtime_knowledge_dir / "machine_profiles"
        self.machine_profiles_dir.mkdir(parents=True, exist_ok=True)

        # Current machine profile (protected by _profile_lock)
        self._current_machine_profile: Optional[MachineProfile] = None
        self._profile_lock = asyncio.Lock()

    @property
    def current_machine_profile(self) -> Optional[MachineProfile]:
        """Thread-safe access to current machine profile (read-only snapshot)."""
        return self._current_machine_profile

    async def initialize_machine_aware_knowledge(self, force_reinstall: bool = False):
        """Initialize system knowledge with machine-specific adaptation"""
        logger.info("Initializing machine-aware system knowledge...")

        # 1. Detect current machine profile
        await self._detect_current_machine()

        # 2. Load or create machine-specific knowledge
        machine_knowledge_dir = self._get_machine_knowledge_dir()

        # Issue #358 - avoid blocking
        dir_exists = await asyncio.to_thread(machine_knowledge_dir.exists)
        if force_reinstall or not dir_exists:
            await self._create_machine_specific_knowledge()
        else:
            # Check if machine profile changed
            if await self._has_machine_changed():
                logger.info("Machine profile changed, updating knowledge...")
                await self._create_machine_specific_knowledge()

        # 3. Import machine-specific knowledge
        await self._import_machine_specific_knowledge()

        logger.info("Machine-aware system knowledge initialization completed")

    async def _detect_current_machine(self):
        """Detect current machine capabilities and create profile"""
        logger.info("Detecting current machine profile...")

        detector = await get_os_detector()
        os_info = await detector.detect_system()

        # Create new profile
        new_profile = MachineProfile()
        new_profile.machine_id = self._generate_machine_id(os_info)
        new_profile.hostname = os_info.user or "unknown"
        new_profile.os_type = os_info.os_type
        new_profile.distro = os_info.distro
        new_profile.package_manager = os_info.package_manager
        new_profile.available_tools = os_info.capabilities
        new_profile.architecture = os_info.architecture
        new_profile.is_wsl = os_info.is_wsl
        new_profile.is_root = os_info.is_root
        new_profile.capabilities = os_info.capabilities

        # Atomically update the profile under lock
        async with self._profile_lock:
            self._current_machine_profile = new_profile

        # Save machine profile
        await self._save_machine_profile()

        logger.info(f"Machine profile detected: {new_profile.machine_id}")
        logger.info(
            f"OS: {os_info.os_type.value} ({os_info.distro.value if os_info.distro else 'N/A'})"
        )
        logger.info("Available tools: %s", len(os_info.capabilities))

    def _generate_machine_id(self, os_info) -> str:
        """Generate unique machine ID based on system characteristics"""
        # Use system-specific identifiers to create unique ID
        components = [
            os_info.os_type.value,
            os_info.distro.value if os_info.distro else "unknown",
            os_info.architecture,
            os_info.user,
            str(os_info.is_wsl),
        ]

        # Create hash of components
        machine_string = "|".join(components)
        machine_hash = hashlib.md5(
            machine_string.encode(), usedforsecurity=False
        ).hexdigest()[:12]

        return f"{os_info.os_type.value}_{machine_hash}"

    async def _save_machine_profile(self):
        """Save current machine profile to disk"""
        if not self.current_machine_profile:
            return

        profile_file = (
            self.machine_profiles_dir
            / f"{self.current_machine_profile.machine_id}.json"
        )

        try:
            async with aiofiles.open(profile_file, "w", encoding="utf-8") as f:
                await f.write(
                    json.dumps(self.current_machine_profile.to_dict(), indent=2)
                )
            logger.info("Machine profile saved: %s", profile_file)
        except OSError as e:
            logger.error("Failed to save machine profile to %s: %s", profile_file, e)

    async def _load_machine_profile(self, machine_id: str) -> Optional[MachineProfile]:
        """Load machine profile from disk"""
        profile_file = self.machine_profiles_dir / f"{machine_id}.json"

        profile_exists = await asyncio.to_thread(profile_file.exists)
        if not profile_exists:
            return None

        try:
            async with aiofiles.open(profile_file, "r", encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)
            return MachineProfile.from_dict(data)
        except OSError as e:
            logger.warning("Failed to read machine profile %s: %s", profile_file, e)
            return None
        except Exception as e:
            logger.warning("Error loading machine profile %s: %s", machine_id, e)
            return None

    def _get_machine_knowledge_dir(self) -> Path:
        """Get machine-specific knowledge directory"""
        if not self.current_machine_profile:
            return self.runtime_knowledge_dir

        return (
            self.runtime_knowledge_dir
            / "machines"
            / self.current_machine_profile.machine_id
        )

    async def _has_machine_changed(self) -> bool:
        """Check if current machine profile differs from saved profile"""
        if not self.current_machine_profile:
            return True

        saved_profile = await self._load_machine_profile(
            self.current_machine_profile.machine_id
        )
        if not saved_profile:
            return True

        # Compare key attributes
        return (
            saved_profile.available_tools
            != self.current_machine_profile.available_tools
            or saved_profile.package_manager
            != self.current_machine_profile.package_manager
            or saved_profile.capabilities != self.current_machine_profile.capabilities
        )

    async def _create_machine_specific_knowledge(self):
        """Create machine-specific knowledge from templates"""
        logger.info("Creating machine-specific knowledge...")

        machine_dir = self._get_machine_knowledge_dir()
        await asyncio.to_thread(machine_dir.mkdir, parents=True, exist_ok=True)

        # Process each category concurrently (Issue #379: independent operations)
        await asyncio.gather(
            self._adapt_tools_knowledge(),
            self._adapt_workflows_knowledge(),
            self._adapt_procedures_knowledge(),
            self._integrate_man_pages(),
        )

    async def _adapt_tools_knowledge(self):
        """Adapt tools knowledge for current machine"""
        tools_dir = self.system_knowledge_dir / "tools"
        tools_dir_exists = await asyncio.to_thread(tools_dir.exists)
        if not tools_dir_exists:
            return

        machine_tools_dir = self._get_machine_knowledge_dir() / "tools"
        await asyncio.to_thread(machine_tools_dir.mkdir, parents=True, exist_ok=True)

        # Issue #358 - wrap glob in lambda to avoid blocking
        yaml_files = await asyncio.to_thread(lambda: list(tools_dir.glob("*.yaml")))
        for yaml_file in yaml_files:
            logger.info("Adapting tools from %s", yaml_file)

            try:
                async with aiofiles.open(yaml_file, "r", encoding="utf-8") as f:
                    content = await f.read()
                    tools_data = yaml.safe_load(content)
            except OSError as e:
                logger.error("Failed to read tools file %s: %s", yaml_file, e)
                continue

            # Filter and adapt tools for this machine
            adapted_tools = self._filter_tools_for_machine(tools_data)

            if adapted_tools["tools"]:  # Only save if there are applicable tools
                machine_file = machine_tools_dir / yaml_file.name
                try:
                    async with aiofiles.open(machine_file, "w", encoding="utf-8") as f:
                        await f.write(
                            yaml.dump(adapted_tools, default_flow_style=False, indent=2)
                        )
                except OSError as e:
                    logger.error(
                        f"Failed to write adapted tools to {machine_file}: {e}"
                    )

    def _filter_tools_for_machine(self, tools_data: Dict[str, Any]) -> Dict[str, Any]:
        """Filter tools based on current machine capabilities"""
        if not self.current_machine_profile:
            return tools_data

        filtered_tools = []
        available_tools = self.current_machine_profile.available_tools
        os_type = self.current_machine_profile.os_type
        package_manager = self.current_machine_profile.package_manager

        for tool_data in tools_data.get("tools", []):
            tool_name = tool_data.get("name", "")

            # Check if tool is available or can be installed
            if tool_name in available_tools or self._can_install_tool(tool_data):
                # Adapt installation instructions for this machine
                adapted_tool = self._adapt_tool_for_machine(tool_data)
                if adapted_tool:
                    filtered_tools.append(adapted_tool)

        return {
            **tools_data,
            "tools": filtered_tools,
            "machine_profile": {
                "machine_id": self.current_machine_profile.machine_id,
                "os_type": os_type.value,
                "package_manager": package_manager,
                "filtered_at": datetime.now().isoformat(),
            },
        }

    def _can_install_tool(self, tool_data: Dict[str, Any]) -> bool:
        """Check if tool can be installed on current machine"""
        if not self.current_machine_profile:
            return False

        installation = tool_data.get("installation", {})
        package_manager = self.current_machine_profile.package_manager

        # Check if installation method exists for this package manager
        return package_manager in installation

    def _adapt_tool_for_machine(
        self, tool_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Adapt tool configuration for current machine"""
        if not self.current_machine_profile:
            return tool_data

        adapted_tool = tool_data.copy()
        package_manager = self.current_machine_profile.package_manager

        # Adapt installation instructions
        if "installation" in adapted_tool:
            installation = adapted_tool["installation"]

            if package_manager in installation:
                # Keep only the relevant installation method
                adapted_tool["installation"] = {
                    package_manager: installation[package_manager],
                    "system": (
                        f"Optimized for {self.current_machine_profile.os_type.value}"
                    ),
                }
            else:
                # No suitable installation method
                return None

        # Add machine-specific notes
        adapted_tool["machine_notes"] = [
            f"Available on {self.current_machine_profile.machine_id}",
            f"Install with: {package_manager}",
            f"Architecture: {self.current_machine_profile.architecture}",
        ]

        return adapted_tool

    async def _adapt_workflows_knowledge(self):
        """Adapt workflows for current machine capabilities"""
        workflows_dir = self.system_knowledge_dir / "workflows"
        workflows_dir_exists = await asyncio.to_thread(workflows_dir.exists)
        if not workflows_dir_exists:
            return

        machine_workflows_dir = self._get_machine_knowledge_dir() / "workflows"
        await asyncio.to_thread(
            machine_workflows_dir.mkdir, parents=True, exist_ok=True
        )

        # Issue #358 - wrap glob in lambda to avoid blocking
        yaml_files = await asyncio.to_thread(lambda: list(workflows_dir.glob("*.yaml")))
        for yaml_file in yaml_files:
            logger.info("Adapting workflow from %s", yaml_file)

            try:
                async with aiofiles.open(yaml_file, "r", encoding="utf-8") as f:
                    content = await f.read()
                    workflow_data = yaml.safe_load(content)
            except OSError as e:
                logger.error("Failed to read workflow file %s: %s", yaml_file, e)
                continue

            # Adapt workflow for machine capabilities
            adapted_workflow = self._adapt_workflow_for_machine(workflow_data)

            if adapted_workflow:  # Only save if workflow is applicable
                machine_file = machine_workflows_dir / yaml_file.name
                try:
                    async with aiofiles.open(machine_file, "w", encoding="utf-8") as f:
                        await f.write(
                            yaml.dump(
                                adapted_workflow, default_flow_style=False, indent=2
                            )
                        )
                except OSError as e:
                    logger.error(
                        f"Failed to write adapted workflow to {machine_file}: {e}"
                    )

    def _adapt_workflow_for_machine(
        self, workflow_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Adapt workflow based on machine capabilities"""
        if not self.current_machine_profile:
            return workflow_data

        available_tools = self.current_machine_profile.available_tools
        required_tools = workflow_data.get("required_tools", [])

        # Check if required tools are available
        missing_tools = []
        available_required_tools = []

        for tool_req in required_tools:
            tool_name = (
                tool_req.get("name", "")
                if isinstance(tool_req, dict)
                else str(tool_req)
            )

            if tool_name in available_tools:
                available_required_tools.append(tool_req)
            elif not tool_req.get("optional", False):
                missing_tools.append(tool_name)

        # Skip workflow if critical tools are missing
        if missing_tools:
            workflow_name = workflow_data.get("metadata", {}).get("name", "Unknown")
            logger.info(
                "Skipping workflow %s - missing tools: %s", workflow_name, missing_tools
            )
            return None

        # Adapt workflow
        adapted_workflow = workflow_data.copy()
        adapted_workflow["required_tools"] = available_required_tools

        # Add machine-specific metadata
        adapted_workflow["machine_adaptation"] = {
            "machine_id": self.current_machine_profile.machine_id,
            "adapted_at": datetime.now().isoformat(),
            "available_tools": len(available_required_tools),
            "skipped_tools": len(required_tools) - len(available_required_tools),
        }

        return adapted_workflow

    async def _adapt_procedures_knowledge(self):
        """Adapt procedures for current machine"""
        procedures_dir = self.system_knowledge_dir / "procedures"
        procedures_dir_exists = await asyncio.to_thread(procedures_dir.exists)
        if not procedures_dir_exists:
            return

        machine_procedures_dir = self._get_machine_knowledge_dir() / "procedures"
        await asyncio.to_thread(
            machine_procedures_dir.mkdir, parents=True, exist_ok=True
        )

        # Simply copy procedures for now - future enhancement could adapt commands
        # Issue #358 - wrap glob in lambda to avoid blocking
        yaml_files = await asyncio.to_thread(
            lambda: list(procedures_dir.glob("*.yaml"))
        )
        for yaml_file in yaml_files:
            machine_file = machine_procedures_dir / yaml_file.name
            await asyncio.to_thread(shutil.copy2, yaml_file, machine_file)

    async def _import_machine_specific_knowledge(self):
        """Import machine-specific knowledge into knowledge base"""
        machine_dir = self._get_machine_knowledge_dir()

        machine_dir_exists = await asyncio.to_thread(machine_dir.exists)
        if not machine_dir_exists:
            logger.warning(
                f"Machine-specific knowledge directory not found: {machine_dir}"
            )
            return

        # Import adapted knowledge using parent class methods
        original_runtime_dir = self.runtime_knowledge_dir

        try:
            # Temporarily point to machine-specific directory
            self.runtime_knowledge_dir = machine_dir

            # Import using existing methods
            await self._import_from_runtime_files()

        finally:
            # Restore original path
            self.runtime_knowledge_dir = original_runtime_dir

    async def get_machine_info(self) -> Dict[str, Any]:
        """Get current machine information"""
        # Check if profile exists, using lock for lazy initialization
        async with self._profile_lock:
            profile = self._current_machine_profile

        if not profile:
            await self._detect_current_machine()
            async with self._profile_lock:
                profile = self._current_machine_profile

        if profile:
            return profile.to_dict()
        else:
            return {"error": "Machine profile not available"}

    async def list_supported_machines(self) -> List[Dict[str, Any]]:
        """List all known machine profiles"""
        machines = []

        profiles_dir_exists = await asyncio.to_thread(self.machine_profiles_dir.exists)
        if profiles_dir_exists:
            # Issue #358 - wrap glob in lambda to avoid blocking
            profile_files = await asyncio.to_thread(
                lambda: list(self.machine_profiles_dir.glob("*.json"))
            )
            for profile_file in profile_files:
                try:
                    async with aiofiles.open(profile_file, "r", encoding="utf-8") as f:
                        content = await f.read()
                        profile_data = json.loads(content)
                    machines.append(profile_data)
                except OSError as e:
                    logger.warning("Failed to read profile %s: %s", profile_file, e)
                except Exception as e:
                    logger.warning("Error loading profile %s: %s", profile_file, e)

        return machines

    async def sync_knowledge_across_machines(self, target_machine_ids: List[str]):
        """Synchronize knowledge across multiple machines (future feature)"""
        logger.info("Knowledge sync requested for machines: %s", target_machine_ids)
        # This would implement knowledge sharing between connected AutoBot instances
        # For now, just log the request

    async def _process_single_man_page(
        self,
        command: str,
        integrator,
        profile,
        integration_results: dict,
    ) -> None:
        """
        Process a single man page command integration.

        Issue #281: Extracted from _integrate_man_pages to reduce function length
        and improve testability of individual command processing.

        Args:
            command: Command name to process
            integrator: Man page integrator instance
            profile: Current machine profile
            integration_results: Dict to update with results
        """
        integration_results["processed"] += 1

        try:
            if await self._try_use_cached_man_page(
                command, integrator, integration_results
            ):
                return

            man_info = await self._extract_man_page_info(
                command, integrator, integration_results
            )
            if not man_info:
                return

            await self._store_man_page(
                command, man_info, integrator, profile, integration_results
            )

        except Exception as e:
            integration_results["failed"] += 1
            integration_results["commands"][command] = f"error: {str(e)}"
            logger.error("Failed to integrate man page for %s: %s", command, e)

    async def _try_use_cached_man_page(
        self, command: str, integrator, integration_results: dict
    ) -> bool:
        """
        Check for recent cached man page and use it if available. Issue #620.

        Returns:
            True if cached version was used, False otherwise
        """
        cached_info = await integrator.load_cached_man_page(command)
        if cached_info and self._is_man_page_recent(cached_info):
            integration_results["cached"] += 1
            integration_results["commands"][command] = "cached"
            return True
        return False

    async def _extract_man_page_info(
        self, command: str, integrator, integration_results: dict
    ):
        """
        Validate and extract man page information. Issue #620.

        Returns:
            ManPageInfo if successful, None if man page unavailable or extraction failed
        """
        if not await integrator.check_man_page_exists(command):
            integration_results["failed"] += 1
            integration_results["commands"][command] = "no_man_page"
            return None

        man_info = await integrator.extract_man_page(command)
        if not man_info:
            integration_results["failed"] += 1
            integration_results["commands"][command] = "extraction_failed"
            return None

        return man_info

    async def _store_man_page(
        self, command: str, man_info, integrator, profile, integration_results: dict
    ) -> None:
        """
        Store man page in cache and knowledge base. Issue #620.

        Args:
            command: Command name
            man_info: Extracted man page information
            integrator: Man page integrator instance
            profile: Current machine profile
            integration_results: Results dict to update
        """
        man_info.machine_id = profile.machine_id
        await integrator.cache_man_page(man_info)
        await self._save_man_page_knowledge(man_info, integrator)
        integration_results["successful"] += 1
        integration_results["commands"][command] = "success"
        logger.debug("Integrated man page for %s", command)

    async def _setup_man_page_integrator(self, profile: MachineProfile):
        """
        Initialize man page integrator and determine commands to process. Issue #620.

        Args:
            profile: Current machine profile

        Returns:
            Tuple of (integrator, commands_to_integrate) or (None, []) if unavailable
        """
        from agents.man_page_knowledge_integrator import get_man_page_integrator

        integrator = await get_man_page_integrator()
        machine_dir = self._get_machine_knowledge_dir()
        integrator.knowledge_base_dir = machine_dir.parent.parent

        commands_to_integrate = [
            cmd
            for cmd in integrator.priority_commands
            if cmd in profile.available_tools
        ]
        logger.info("Integrating man pages for %d commands", len(commands_to_integrate))
        return integrator, commands_to_integrate

    def _create_integration_results_dict(self) -> dict:
        """Create initial integration results dictionary. Issue #620."""
        return {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "cached": 0,
            "commands": {},
        }

    async def _integrate_man_pages(self):
        """Integrate man pages for tools available on this machine. Issue #620."""
        async with self._profile_lock:
            profile = self._current_machine_profile

        if not profile:
            logger.warning("No machine profile available for man page integration")
            return

        if profile.os_type.value != "linux":
            logger.info("Man page integration skipped for %s", profile.os_type.value)
            return

        logger.info("Integrating man pages for available tools...")

        try:
            integrator, commands = await self._setup_man_page_integrator(profile)
            results = self._create_integration_results_dict()

            for command in commands:
                await self._process_single_man_page(
                    command, integrator, profile, results
                )

            logger.info(
                "Man page integration complete: %d successful, %d failed, %d cached",
                results["successful"],
                results["failed"],
                results["cached"],
            )
            await self._save_man_page_integration_summary(results)

        except ImportError:
            logger.warning("Man page integrator not available")
        except Exception as e:
            logger.error("Error during man page integration: %s", e)

    def _is_man_page_recent(self, man_info, max_age_hours: int = 24) -> bool:
        """Check if man page cache is recent enough"""
        if not man_info.last_updated:
            return False

        try:
            from datetime import datetime, timedelta

            last_updated = datetime.fromisoformat(man_info.last_updated)
            age_threshold = datetime.now() - timedelta(hours=max_age_hours)

            return last_updated > age_threshold
        except Exception:
            return False

    async def _save_man_page_knowledge(self, man_info, integrator):
        """Save man page as machine-specific knowledge YAML"""
        machine_dir = self._get_machine_knowledge_dir()
        man_knowledge_dir = machine_dir / "man_pages"
        await asyncio.to_thread(man_knowledge_dir.mkdir, parents=True, exist_ok=True)

        # Convert to AutoBot knowledge format
        knowledge_data = integrator.convert_to_knowledge_yaml(man_info)

        # Get profile snapshot under lock
        async with self._profile_lock:
            profile = self._current_machine_profile

        # Add machine-specific metadata
        knowledge_data["metadata"].update(
            {
                "machine_id": profile.machine_id if profile else "unknown",
                "os_type": profile.os_type.value if profile else "unknown",
                "package_manager": profile.package_manager if profile else "unknown",
                "integration_type": "machine_aware_man_pages",
            }
        )

        # Save as YAML
        yaml_file = man_knowledge_dir / f"{man_info.command}.yaml"
        try:
            async with aiofiles.open(yaml_file, "w", encoding="utf-8") as f:
                await f.write(
                    yaml.dump(knowledge_data, default_flow_style=False, indent=2)
                )
            logger.debug(
                f"Saved man page knowledge for {man_info.command} to {yaml_file}"
            )
        except OSError as e:
            logger.error("Failed to save man page knowledge to %s: %s", yaml_file, e)

    async def _save_man_page_integration_summary(self, results: Dict[str, Any]):
        """Save man page integration summary"""
        machine_dir = self._get_machine_knowledge_dir()
        summary_file = machine_dir / "man_page_integration_summary.json"

        # Get profile snapshot under lock
        async with self._profile_lock:
            profile = self._current_machine_profile

        summary_data = {
            **results,
            "integration_date": datetime.now().isoformat(),
            "machine_id": profile.machine_id if profile else "unknown",
            "total_available_tools": (len(profile.available_tools) if profile else 0),
        }

        try:
            async with aiofiles.open(summary_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(summary_data, indent=2))
            logger.info("Saved man page integration summary to %s", summary_file)
        except OSError as e:
            logger.error(
                f"Failed to save man page integration summary to {summary_file}: {e}"
            )

    async def get_man_page_summary(self) -> Dict[str, Any]:
        """Get summary of integrated man pages for current machine"""
        machine_dir = self._get_machine_knowledge_dir()
        summary_file = machine_dir / "man_page_integration_summary.json"

        summary_exists = await asyncio.to_thread(summary_file.exists)
        if not summary_exists:
            return {
                "status": "not_integrated",
                "message": "Man pages not yet integrated",
            }

        try:
            async with aiofiles.open(summary_file, "r") as f:
                content = await f.read()
                summary = json.loads(content)

            # Add current file counts
            man_pages_dir = machine_dir / "man_pages"
            man_pages_exists = await asyncio.to_thread(man_pages_dir.exists)
            if man_pages_exists:
                # Issue #358 - use lambda to avoid calling glob() in main thread
                yaml_files = await asyncio.to_thread(
                    lambda: list(man_pages_dir.glob("*.yaml"))
                )
                summary["current_man_page_files"] = len(yaml_files)
                summary["available_commands"] = [f.stem for f in yaml_files]
            else:
                summary["current_man_page_files"] = 0
                summary["available_commands"] = []

            return summary

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error reading integration summary: {e}",
            }

    def _build_tool_searchable_text(self, tool: Dict[str, Any]) -> str:
        """
        Build searchable text from tool data for man page search.

        Combines tool name, purpose, usage, options, and examples into
        a single searchable string. Issue #620.
        """
        usage_basic = tool.get("usage", {}).get("basic", "")
        # Build searchable text using list + join (O(n)) instead of += (O(n²))
        text_parts = [f"{tool.get('name', '')} {tool.get('purpose', '')} {usage_basic}"]
        # Add options text
        text_parts.extend(option.lower() for option in tool.get("options", []))
        # Add examples
        text_parts.extend(
            f"{example.get('description', '')} {example.get('command', '')}".lower()
            for example in tool.get("common_examples", [])
        )
        return " ".join(text_parts)

    def _create_search_result(
        self,
        tool: Dict[str, Any],
        knowledge_data: Dict[str, Any],
        yaml_file: Path,
        relevance_score: int,
    ) -> Dict[str, Any]:
        """
        Create a search result dict from tool and metadata.

        Returns formatted result with command, purpose, source, and score. Issue #620.
        """
        return {
            "command": tool.get("name"),
            "purpose": tool.get("purpose"),
            "source": "man_page",
            "machine_id": knowledge_data.get("metadata", {}).get("machine_id"),
            "file_path": str(yaml_file),
            "relevance_score": relevance_score,
        }

    async def search_man_page_knowledge(self, query: str) -> List[Dict[str, Any]]:
        """Search through integrated man page knowledge"""
        machine_dir = self._get_machine_knowledge_dir()
        man_pages_dir = machine_dir / "man_pages"

        man_pages_exists = await asyncio.to_thread(man_pages_dir.exists)
        if not man_pages_exists:
            return []

        results = []
        query_lower = query.lower()

        # Issue #358 - use lambda to avoid calling glob() in main thread
        yaml_files = await asyncio.to_thread(lambda: list(man_pages_dir.glob("*.yaml")))
        for yaml_file in yaml_files:
            try:
                async with aiofiles.open(yaml_file, "r") as f:
                    content = await f.read()
                    knowledge_data = yaml.safe_load(content)

                for tool in knowledge_data.get("tools", []):
                    searchable_text = self._build_tool_searchable_text(tool)
                    if query_lower in searchable_text:
                        score = searchable_text.count(query_lower)
                        results.append(
                            self._create_search_result(
                                tool, knowledge_data, yaml_file, score
                            )
                        )

            except Exception as e:
                logger.error(
                    f"Error searching man page knowledge file {yaml_file}: {e}"
                )

        results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return results
