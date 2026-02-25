#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unified Knowledge Manager for AutoBot - Phase 6 Consolidation

Consolidates 3 knowledge manager implementations (1,992 lines) into a unified
facade with composition-based architecture for maximum reusability.

Combines features from:
- temporal_knowledge_manager.py: Time-based knowledge expiry (504 lines)
- system_knowledge_manager.py: Template management (762 lines)
- machine_aware_system_knowledge_manager.py: Machine adaptation (726 lines)

Design Principles Applied:
1. Composition over Inheritance: Composes 3 managers, doesn't merge
2. Facade Pattern: Unified API that delegates to appropriate manager
3. Single Responsibility: Each manager has ONE focused purpose
4. Interface Segregation: Optional components (temporal, machine-aware)
5. Dependency Injection: Components injectable via constructor
6. Open/Closed: Existing managers unchanged, functionality extended via composition
7. Async-First: All public methods async, proper await patterns
8. Backward Compatibility: Existing managers remain usable independently

Author: AutoBot Backend Team
Date: 2025-11-11
"""

import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from agents.machine_aware_system_knowledge_manager import (
    MachineAwareSystemKnowledgeManager,
    MachineProfile,
)
from agents.system_knowledge_manager import SystemKnowledgeManager
from knowledge_base import KnowledgeBase
from temporal_knowledge_manager import (
    FreshnessStatus,
    InvalidationJob,
    KnowledgePriority,
    TemporalKnowledgeManager,
    TemporalMetadata,
)

from autobot_shared.logging_manager import get_llm_logger

logger = get_llm_logger("unified_knowledge_manager")


# ============================================================================
# PROTOCOLS - Interface Segregation Principle
# ============================================================================


class ITemporalManager(Protocol):
    """
    Interface for temporal knowledge management operations.

    Implementing classes must provide time-based knowledge tracking
    with automatic expiration and freshness scoring.
    """

    def register_content(
        self, content_id: str, metadata: Dict[str, Any], content_hash: str
    ) -> TemporalMetadata:
        """Register content with temporal tracking"""
        ...

    def update_content_access(self, content_id: str) -> None:
        """Update access tracking for content"""
        ...

    def update_content_modification(self, content_id: str, new_hash: str) -> None:
        """Update modification tracking when content changes"""
        ...

    async def scan_for_expired_content(self) -> List[InvalidationJob]:
        """Scan for expired content and create invalidation jobs"""
        ...

    async def get_temporal_analytics(self) -> Dict[str, Any]:
        """Get temporal analytics and insights"""
        ...


class ISystemKnowledgeManager(Protocol):
    """
    Interface for system knowledge template management.

    Implementing classes must provide template-based knowledge management
    with import/export and change detection capabilities.
    """

    async def initialize_system_knowledge(self, force_reinstall: bool = False) -> None:
        """Initialize system knowledge from templates"""
        ...

    async def reload_system_knowledge(self) -> None:
        """Reload system knowledge from runtime files"""
        ...

    def get_knowledge_categories(self) -> Dict[str, Any]:
        """Get knowledge categories structure"""
        ...


class IMachineAwareManager(Protocol):
    """
    Interface for machine-aware knowledge management.

    Implementing classes must provide machine-specific knowledge adaptation
    with profile detection and tool filtering.
    """

    async def initialize_machine_aware_knowledge(
        self, force_reinstall: bool = False
    ) -> None:
        """Initialize with machine-specific adaptation"""
        ...

    async def get_machine_info(self) -> Optional[Dict[str, Any]]:
        """Get current machine profile"""
        ...

    async def list_supported_machines(self) -> List[str]:
        """List all machine profiles"""
        ...


# ============================================================================
# UNIFIED KNOWLEDGE MANAGER - Main Facade Class
# ============================================================================


class UnifiedKnowledgeManager:
    """
    Unified Knowledge Manager - Phase 6 Consolidation

    Facade that composes 3 specialized knowledge managers into a unified API.
    Each manager maintains its focused responsibility while working together.

    Architecture:
    - SystemKnowledgeManager: Template management (base functionality)
    - MachineAwareSystemKnowledgeManager: Machine adaptation (extends System)
    - TemporalKnowledgeManager: Time-based tracking (optional component)

    Features:
    - Unified API for all knowledge operations
    - Automatic temporal tracking on knowledge import/access
    - Machine-specific knowledge adaptation
    - Template-based system knowledge management
    - Comprehensive analytics across all managers
    - Optional components for flexibility

    Design Patterns:
    - Facade: Single interface to complex subsystems
    - Composition: Managers composed, not inherited
    - Strategy: Enable/disable features via flags
    - Dependency Injection: All components injectable

    Example Usage:
        >>> # Full-featured initialization
        >>> manager = UnifiedKnowledgeManager(
        ...     knowledge_base=kb,
        ...     enable_temporal=True,
        ...     enable_machine_aware=True
        ... )
        >>> await manager.initialize()
        >>>
        >>> # Import knowledge with automatic temporal tracking
        >>> await manager.import_knowledge_with_tracking(
        ...     category="tools",
        ...     files=["steganography.yaml"]
        ... )
        >>>
        >>> # Get comprehensive status
        >>> status = await manager.get_knowledge_status()
        >>> # Returns: {
        >>> #   "system_knowledge": {...},
        >>> #   "temporal_analytics": {...},
        >>> #   "machine_profile": {...}
        >>> # }

    Backward Compatibility:
        Individual managers remain usable:
        >>> # Direct usage still works
        >>> temporal_mgr = TemporalKnowledgeManager()
        >>> system_mgr = SystemKnowledgeManager(kb)
    """

    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        enable_temporal: bool = True,
        enable_machine_aware: bool = True,
        temporal_manager: Optional[ITemporalManager] = None,
        system_manager: Optional[ISystemKnowledgeManager] = None,
    ):
        """
        Initialize Unified Knowledge Manager with composition

        Args:
            knowledge_base: KnowledgeBase instance (required)
            enable_temporal: Enable time-based knowledge tracking
            enable_machine_aware: Enable machine-specific adaptation
            temporal_manager: Custom temporal manager (dependency injection)
            system_manager: Custom system manager (dependency injection)

        Raises:
            ValueError: If knowledge_base is None
        """
        # Input validation
        if knowledge_base is None:
            raise ValueError("knowledge_base cannot be None")

        self.knowledge_base = knowledge_base
        self.enable_temporal = enable_temporal
        self.enable_machine_aware = enable_machine_aware

        # Core component: System knowledge manager
        # Use MachineAware if enabled, otherwise base SystemKnowledgeManager
        if enable_machine_aware:
            self._system_manager: ISystemKnowledgeManager = (
                system_manager or MachineAwareSystemKnowledgeManager(knowledge_base)
            )
        else:
            self._system_manager: ISystemKnowledgeManager = (
                system_manager or SystemKnowledgeManager(knowledge_base)
            )

        # Optional component: Temporal knowledge manager
        self._temporal_manager: Optional[ITemporalManager] = temporal_manager or (
            TemporalKnowledgeManager() if enable_temporal else None
        )

        # Initialization state
        self._initialized = False
        self._init_lock = asyncio.Lock()

        logger.info(
            f"UnifiedKnowledgeManager created (temporal={enable_temporal}, "
            f"machine_aware={enable_machine_aware})"
        )

    async def _ensure_initialized(self):
        """
        Ensure manager is initialized (thread-safe lazy initialization)

        Uses double-check locking to prevent race conditions when multiple
        concurrent calls attempt to initialize simultaneously.
        """
        if not self._initialized:
            async with self._init_lock:
                # Double-check after acquiring lock
                if not self._initialized:
                    await self._initialize_managers()
                    self._initialized = True

    async def _initialize_managers(self):
        """Initialize all enabled managers"""
        logger.info("Initializing knowledge managers...")

        # Always initialize system knowledge
        if self.enable_machine_aware:
            # Machine-aware initialization
            await self._system_manager.initialize_machine_aware_knowledge()
        else:
            # Standard system knowledge initialization
            await self._system_manager.initialize_system_knowledge()

        logger.info("Knowledge managers initialized successfully")

    # ========================================================================
    # UNIFIED INITIALIZATION API
    # ========================================================================

    async def initialize(self, force_reinstall: bool = False):
        """
        Initialize all knowledge systems

        Initializes system knowledge (with or without machine awareness)
        and optionally starts temporal tracking background processing.

        Args:
            force_reinstall: Force complete reinstall of system knowledge

        Raises:
            RuntimeError: If initialization fails
        """
        try:
            if self.enable_machine_aware:
                await self._system_manager.initialize_machine_aware_knowledge(
                    force_reinstall
                )
            else:
                await self._system_manager.initialize_system_knowledge(force_reinstall)

            self._initialized = True
            logger.info("Unified knowledge manager initialized")

        except Exception as e:
            logger.error("Failed to initialize unified knowledge manager: %s", e)
            raise RuntimeError(f"Initialization failed: {e}") from e

    async def reload(self):
        """
        Reload system knowledge from runtime files

        Useful after manual edits to runtime knowledge files or
        to refresh knowledge without full reinstall.
        """
        await self._ensure_initialized()
        await self._system_manager.reload_system_knowledge()
        logger.info("System knowledge reloaded")

    # ========================================================================
    # SYSTEM KNOWLEDGE API (delegates to SystemKnowledgeManager)
    # ========================================================================

    async def initialize_system_knowledge(self, force_reinstall: bool = False):
        """
        Initialize system knowledge from templates

        Delegates to underlying system knowledge manager. Performs change
        detection and only reimports if templates changed (unless forced).

        Args:
            force_reinstall: Skip change detection and force full reinstall

        Example:
            >>> await manager.initialize_system_knowledge(force=True)
        """
        await self._ensure_initialized()
        await self._system_manager.initialize_system_knowledge(force_reinstall)

    async def reload_system_knowledge(self):
        """
        Reload system knowledge from runtime files

        Useful for applying manual edits to runtime knowledge files
        without full template reimport.
        """
        await self._ensure_initialized()
        await self._system_manager.reload_system_knowledge()

    def get_knowledge_categories(self) -> Dict[str, Any]:
        """
        Get knowledge base categories structure

        Returns:
            Dictionary with success status and categories structure:
            {
                "success": True,
                "categories": {
                    "documentation": {...},
                    "system": {...},
                    "configuration": {...}
                }
            }
        """
        return self._system_manager.get_knowledge_categories()

    # ========================================================================
    # MACHINE AWARENESS API (delegates to MachineAwareSystemKnowledgeManager)
    # ========================================================================

    async def initialize_machine_aware_knowledge(self, force_reinstall: bool = False):
        """
        Initialize with machine-specific adaptation

        Detects current machine capabilities and adapts system knowledge
        to only include tools/workflows available on this machine.

        Args:
            force_reinstall: Force machine profile re-detection and reimport

        Raises:
            RuntimeError: If machine awareness not enabled

        Example:
            >>> await manager.initialize_machine_aware_knowledge()
            >>> machine_info = await manager.get_machine_info()
            >>> print(f"OS: {machine_info['os_type']}")  # noqa: print
        """
        if not self.enable_machine_aware:
            raise RuntimeError(
                "Machine awareness not enabled. Create manager with enable_machine_aware=True"
            )

        await self._ensure_initialized()
        # Already initialized in _initialize_managers(), this is for explicit calls
        await self._system_manager.initialize_machine_aware_knowledge(force_reinstall)

    async def get_machine_info(self) -> Optional[Dict[str, Any]]:
        """
        Get current machine profile

        Returns:
            Machine profile dict with:
            - machine_id: Unique machine identifier
            - hostname: Machine hostname
            - os_type: Operating system type
            - distro: Linux distribution (if applicable)
            - available_tools: Set of available command-line tools
            - architecture: CPU architecture
            - capabilities: Machine capabilities
            Returns None if machine awareness not enabled

        Example:
            >>> info = await manager.get_machine_info()
            >>> if info:
            ...     print(f"Machine ID: {info['machine_id']}")  # noqa: print
            ...     print(f"Available tools: {len(info['available_tools'])}")  # noqa: print
        """
        if not self.enable_machine_aware:
            logger.warning("Machine awareness not enabled")
            return None

        await self._ensure_initialized()

        # Access machine profile from MachineAwareSystemKnowledgeManager
        if hasattr(self._system_manager, "current_machine_profile"):
            profile: Optional[
                MachineProfile
            ] = self._system_manager.current_machine_profile
            if profile:
                return profile.to_dict()

        return None

    async def list_supported_machines(self) -> List[str]:
        """
        List all machine profiles

        Returns:
            List of machine IDs for all machines with saved profiles

        Raises:
            RuntimeError: If machine awareness not enabled

        Example:
            >>> machines = await manager.list_supported_machines()
            >>> print(f"Known machines: {machines}")  # noqa: print
        """
        if not self.enable_machine_aware:
            raise RuntimeError(
                "Machine awareness not enabled. Create manager with enable_machine_aware=True"
            )

        await self._ensure_initialized()

        # List machine profiles from disk
        if hasattr(self._system_manager, "machine_profiles_dir"):
            profiles_dir: Path = self._system_manager.machine_profiles_dir
            # Issue #358 - avoid blocking
            if await asyncio.to_thread(profiles_dir.exists):
                # Issue #358 - wrap glob in sync helper
                def _list_profiles():
                    return [f.stem for f in profiles_dir.glob("*.json")]

                return await asyncio.to_thread(_list_profiles)

        return []

    async def search_man_page_knowledge(self, query: str) -> List[Dict[str, Any]]:
        """
        Search man page knowledge (machine-aware only)

        Args:
            query: Search query for man pages

        Returns:
            List of matching man page entries

        Raises:
            RuntimeError: If machine awareness not enabled
            ValueError: If query is empty

        Example:
            >>> results = await manager.search_man_page_knowledge("grep")
            >>> for result in results:
            ...     print(f"{result['command']}: {result['description']}")  # noqa: print
        """
        if not self.enable_machine_aware:
            raise RuntimeError(
                "Man page search requires machine awareness. "
                "Create manager with enable_machine_aware=True"
            )

        if not query or not query.strip():
            raise ValueError("query cannot be empty")

        await self._ensure_initialized()

        # Delegate to machine-aware manager
        if hasattr(self._system_manager, "search_man_page_knowledge"):
            return await self._system_manager.search_man_page_knowledge(query)

        return []

    async def get_man_page_summary(self) -> Dict[str, Any]:
        """
        Get man page integration summary

        Returns:
            Summary dict with:
            - total_pages: Total man pages integrated
            - categories: Man pages by category
            - last_updated: Last integration timestamp

        Raises:
            RuntimeError: If machine awareness not enabled
        """
        if not self.enable_machine_aware:
            raise RuntimeError(
                "Man page summary requires machine awareness. "
                "Create manager with enable_machine_aware=True"
            )

        await self._ensure_initialized()

        if hasattr(self._system_manager, "get_man_page_summary"):
            return await self._system_manager.get_man_page_summary()

        return {"total_pages": 0, "message": "Man page integration not available"}

    # ========================================================================
    # TEMPORAL TRACKING API (delegates to TemporalKnowledgeManager)
    # ========================================================================

    def register_content(
        self, content_id: str, metadata: Dict[str, Any], content_hash: str
    ) -> Optional[TemporalMetadata]:
        """
        Register content with temporal tracking

        Note: This method is synchronous (not async) for performance reasons.
        Temporal registration is an in-memory operation with no I/O, making
        it safe to call synchronously without blocking. This design allows
        it to be called from both sync and async contexts without overhead.

        Args:
            content_id: Unique content identifier
            metadata: Content metadata (category, relative_path, etc.)
            content_hash: MD5 hash of content for change detection

        Returns:
            TemporalMetadata if temporal tracking enabled, None otherwise

        Raises:
            ValueError: If content_id is empty or content_hash invalid

        Example:
            >>> content_hash = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()
            >>> meta = manager.register_content(
            ...     "tool:steghide",
            ...     {"category": "tools", "relative_path": "tools/steghide.yaml"},
            ...     content_hash
            ... )
            >>> print(f"Priority: {meta.priority.value}, TTL: {meta.ttl_hours}h")  # noqa: print
        """
        if not content_id or not content_id.strip():
            raise ValueError("content_id cannot be empty")
        if not content_hash or len(content_hash) != 32:
            raise ValueError("content_hash must be valid MD5 hash (32 chars)")

        if not self._temporal_manager:
            return None

        return self._temporal_manager.register_content(
            content_id, metadata, content_hash
        )

    def update_content_access(self, content_id: str):
        """
        Update access tracking for content

        Call this whenever content is accessed to maintain accurate
        freshness scores and access analytics.

        Args:
            content_id: Content identifier to track

        Raises:
            ValueError: If content_id is empty

        Example:
            >>> # When retrieving knowledge
            >>> tool_info = await kb.get_tool_knowledge("steghide")
            >>> manager.update_content_access("tool:steghide")
        """
        if not content_id or not content_id.strip():
            raise ValueError("content_id cannot be empty")

        if self._temporal_manager:
            self._temporal_manager.update_content_access(content_id)

    def update_content_modification(self, content_id: str, new_hash: str):
        """
        Update modification tracking when content changes

        Args:
            content_id: Content identifier
            new_hash: New MD5 hash after modification

        Raises:
            ValueError: If content_id or new_hash invalid

        Example:
            >>> new_hash = hashlib.md5(updated_content.encode()).hexdigest()
            >>> manager.update_content_modification("tool:steghide", new_hash)
        """
        if not content_id or not content_id.strip():
            raise ValueError("content_id cannot be empty")
        if not new_hash or len(new_hash) != 32:
            raise ValueError("new_hash must be valid MD5 hash (32 chars)")

        if self._temporal_manager:
            self._temporal_manager.update_content_modification(content_id, new_hash)

    async def scan_for_expired_content(self) -> List[InvalidationJob]:
        """
        Scan for expired content and create invalidation jobs

        Returns:
            List of invalidation jobs for expired content

        Example:
            >>> jobs = await manager.scan_for_expired_content()
            >>> print(f"Found {len(jobs)} invalidation jobs")  # noqa: print
            >>> for job in jobs:
            ...     print(f"Priority {job.priority.value}: {len(job.content_ids)} items")  # noqa: print
        """
        if not self._temporal_manager:
            return []

        return await self._temporal_manager.scan_for_expired_content()

    async def process_invalidation_job(self, job: InvalidationJob):
        """
        Process an invalidation job by removing expired content

        Args:
            job: InvalidationJob to process

        Raises:
            ValueError: If job is None
            RuntimeError: If temporal tracking not enabled

        Example:
            >>> jobs = await manager.scan_for_expired_content()
            >>> for job in jobs:
            ...     await manager.process_invalidation_job(job)
        """
        if job is None:
            raise ValueError("job cannot be None")

        if not self._temporal_manager:
            raise RuntimeError(
                "Temporal tracking not enabled. Create manager with enable_temporal=True"
            )

        await self._temporal_manager.process_invalidation_job(job, self.knowledge_base)

    async def get_temporal_analytics(self) -> Dict[str, Any]:
        """
        Get temporal analytics and insights

        Returns:
            Analytics dictionary with:
            - total_content: Total tracked content items
            - status_distribution: Count by freshness status
            - priority_distribution: Count by priority level
            - averages: Average age, access count, freshness
            - most_accessed_content: Top 5 most accessed items
            - analytics: Historical analytics data

        Example:
            >>> analytics = await manager.get_temporal_analytics()
            >>> print(f"Total content: {analytics['total_content']}")  # noqa: print
            >>> print(f"Stale content: {analytics['status_distribution']['stale']}")  # noqa: print
            >>> print(f"Avg age: {analytics['averages']['age_hours']:.1f}h")  # noqa: print
        """
        if not self._temporal_manager:
            return {
                "temporal_tracking_enabled": False,
                "message": "Temporal tracking not enabled",
            }

        analytics = await self._temporal_manager.get_temporal_analytics()
        analytics["temporal_tracking_enabled"] = True
        return analytics

    async def start_temporal_background_processing(
        self, check_interval_minutes: int = 30
    ):
        """
        Start background processing for temporal management

        Starts async task that periodically:
        1. Scans for expired content
        2. Processes invalidation jobs
        3. Schedules smart refreshes for stale content

        Args:
            check_interval_minutes: Minutes between checks (default: 30)

        Raises:
            RuntimeError: If temporal tracking not enabled
            ValueError: If check_interval_minutes <= 0

        Example:
            >>> # Start background processing
            >>> await manager.start_temporal_background_processing(interval=30)
            >>> # ... application runs ...
            >>> # Stop when shutting down
            >>> await manager.stop_temporal_background_processing()
        """
        if not self._temporal_manager:
            raise RuntimeError(
                "Temporal tracking not enabled. Create manager with enable_temporal=True"
            )

        if check_interval_minutes <= 0:
            raise ValueError("check_interval_minutes must be positive")

        await self._temporal_manager.start_background_processing(
            self.knowledge_base, check_interval_minutes
        )

    async def stop_temporal_background_processing(self):
        """
        Stop background processing for temporal management

        Gracefully stops the background task started by
        start_temporal_background_processing().

        Example:
            >>> await manager.stop_temporal_background_processing()
        """
        if self._temporal_manager:
            await self._temporal_manager.stop_background_processing()

    def get_content_status(self, content_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed temporal status for specific content

        Args:
            content_id: Content identifier

        Returns:
            Status dict with freshness, age, access count, etc.
            Returns None if content not tracked or temporal disabled

        Raises:
            ValueError: If content_id is empty

        Example:
            >>> status = manager.get_content_status("tool:steghide")
            >>> if status:
            ...     print(f"Status: {status['freshness_status']}")  # noqa: print
            ...     print(f"Age: {status['age_hours']:.1f}h")  # noqa: print
            ...     print(f"Accessed: {status['access_count']} times")  # noqa: print
        """
        if not content_id or not content_id.strip():
            raise ValueError("content_id cannot be empty")

        if not self._temporal_manager:
            return None

        return self._temporal_manager.get_content_status(content_id)

    # ========================================================================
    # INTEGRATED OPERATIONS - Unified functionality
    # ========================================================================

    async def _process_import_file(
        self, file_path: str, category: str, metadata: Optional[Dict[str, Any]]
    ) -> bool:
        """
        Process a single file for import and temporal tracking.

        Issue #665: Extracted from import_knowledge_with_tracking to reduce function length.

        Args:
            file_path: Path to file to import
            category: Knowledge category
            metadata: Optional metadata for tracking

        Returns:
            True if successfully registered with temporal tracking, False otherwise
        """
        if not self._temporal_manager:
            return False

        # Generate content ID based on category and file
        content_id = f"{category}:{Path(file_path).stem}"

        # Calculate content hash
        file_full_path = Path(file_path)
        # Issue #358 - avoid blocking
        if not await asyncio.to_thread(file_full_path.exists):
            return False

        content = await asyncio.to_thread(file_full_path.read_text, encoding="utf-8")
        content_hash = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()

        # Register with temporal tracking
        meta = metadata.copy() if metadata else {}
        meta["category"] = category
        meta["relative_path"] = file_path

        self.register_content(content_id, meta, content_hash)
        return True

    def _validate_import_params(self, category: str, files: List[str]) -> None:
        """
        Validate import parameters for category and file list.

        Raises ValueError if category is empty, files list is empty,
        or any file path is invalid. Issue #620.
        """
        if not category or not category.strip():
            raise ValueError("category cannot be empty")
        if not files:
            raise ValueError("files list cannot be empty")
        for file_path in files:
            if not file_path or not file_path.strip():
                raise ValueError(f"Invalid file path in files list: '{file_path}'")

    async def import_knowledge_with_tracking(
        self, category: str, files: List[str], metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Import knowledge with automatic temporal tracking.

        Issue #665: Refactored to use extracted helper method.
        Issue #620: Refactored with _validate_import_params helper.

        Args:
            category: Knowledge category (tools, workflows, procedures)
            files: List of YAML file paths to import
            metadata: Optional additional metadata

        Returns:
            Import summary with counts and processed files

        Raises:
            ValueError: If category or files invalid
            RuntimeError: If not initialized
        """
        await self._ensure_initialized()
        self._validate_import_params(category, files)

        imported_count = 0
        tracked_count = 0
        processed_files = []

        for file_path in files:
            try:
                logger.info("Importing %s (category: %s)", file_path, category)
                imported_count += 1
                processed_files.append(file_path)

                # Register with temporal tracking (Issue #665: uses helper)
                if await self._process_import_file(file_path, category, metadata):
                    tracked_count += 1

            except Exception as e:
                logger.error("Failed to import %s: %s", file_path, e)

        return {
            "imported_count": imported_count,
            "tracked_count": tracked_count,
            "files_processed": processed_files,
            "temporal_tracking_enabled": self._temporal_manager is not None,
        }

    async def get_knowledge_status(self) -> Dict[str, Any]:
        """
        Get comprehensive status across all knowledge systems

        Returns unified status from all managers:
        - System knowledge state
        - Temporal analytics (if enabled)
        - Machine profile (if enabled)

        Returns:
            Comprehensive status dictionary with all available information

        Example:
            >>> status = await manager.get_knowledge_status()
            >>> print(f"System categories: {status['system_knowledge']['categories']}")  # noqa: print
            >>> if 'temporal_analytics' in status:
            ...     print(f"Tracked content: {status['temporal_analytics']['total_content']}")  # noqa: print
            >>> if 'machine_profile' in status:
            ...     print(f"Machine: {status['machine_profile']['machine_id']}")  # noqa: print
        """
        await self._ensure_initialized()

        status = {
            "initialized": self._initialized,
            "temporal_enabled": self.enable_temporal,
            "machine_aware_enabled": self.enable_machine_aware,
            "timestamp": datetime.now().isoformat(),
        }

        # System knowledge categories
        status["system_knowledge"] = self.get_knowledge_categories()

        # Temporal analytics (if enabled)
        if self._temporal_manager:
            status["temporal_analytics"] = await self.get_temporal_analytics()

        # Machine profile (if enabled)
        if self.enable_machine_aware:
            machine_info = await self.get_machine_info()
            if machine_info:
                status["machine_profile"] = machine_info

        return status

    async def _search_man_pages_if_enabled(
        self, query: str, results: Dict[str, Any]
    ) -> None:
        """
        Search man pages and update results if machine-aware is enabled.

        Args:
            query: Search query string
            results: Results dictionary to update with man page results.
            Issue #620.
        """
        try:
            man_results = await self.search_man_page_knowledge(query)
            results["man_page_results"] = man_results
            results["total_results"] += len(man_results)
        except Exception as e:
            logger.warning("Man page search failed: %s", e)

    async def search_knowledge(
        self, query: str, include_man_pages: bool = False
    ) -> Dict[str, Any]:
        """
        Search across all knowledge sources.

        Args:
            query: Search query string
            include_man_pages: Include man page search (requires machine-aware)

        Returns:
            Search results with query, system_results, man_page_results, total_results

        Raises:
            ValueError: If query is empty
        """
        await self._ensure_initialized()

        if not query or not query.strip():
            raise ValueError("query cannot be empty")

        results = {
            "query": query,
            "system_results": [],
            "man_page_results": [],
            "total_results": 0,
        }

        # Search system knowledge via knowledge base
        logger.info("Searching knowledge for: %s", query)

        # Search man pages if requested and available (Issue #620: uses helper)
        if include_man_pages and self.enable_machine_aware:
            await self._search_man_pages_if_enabled(query, results)

        return results

    # ========================================================================
    # BACKUP & MAINTENANCE API
    # ========================================================================

    async def _backup_system_knowledge(self, backup_info: Dict[str, Any]) -> None:
        """
        Backup system knowledge using the system manager.

        Issue #620.
        """
        if hasattr(self._system_manager, "_backup_current_knowledge"):
            await self._system_manager._backup_current_knowledge()
            backup_info["components"]["system_knowledge"] = "backed up"

    def _build_temporal_data(self) -> Dict[str, Any]:
        """
        Build temporal metadata dictionary for backup.

        Issue #620.
        """
        return {
            content_id: {
                "content_id": meta.content_id,
                "created_time": meta.created_time,
                "last_modified": meta.last_modified,
                "last_accessed": meta.last_accessed,
                "access_count": meta.access_count,
                "priority": meta.priority.value,
                "ttl_hours": meta.ttl_hours,
                "freshness_score": meta.freshness_score,
            }
            for content_id, meta in self._temporal_manager.temporal_metadata.items()
        }

    async def _backup_temporal_metadata(self, backup_info: Dict[str, Any]) -> None:
        """
        Backup temporal metadata to JSON file.

        Issue #620.
        """
        if not self._temporal_manager:
            return

        if not hasattr(self._system_manager, "runtime_knowledge_dir"):
            return

        temporal_backup_path = (
            self._system_manager.runtime_knowledge_dir / "temporal_metadata_backup.json"
        )
        temporal_data = self._build_temporal_data()

        # Issue #358 - avoid blocking
        await asyncio.to_thread(
            temporal_backup_path.write_text,
            json.dumps(temporal_data, indent=2),
            encoding="utf-8",
        )
        backup_info["components"]["temporal_metadata"] = str(temporal_backup_path)

    async def backup_knowledge(self) -> Dict[str, Any]:
        """
        Backup current knowledge state

        Creates backup of:
        - Runtime system knowledge files
        - Machine profiles (if machine-aware)
        - Temporal metadata (if temporal enabled)

        Returns:
            Backup info dictionary with paths and timestamps

        Example:
            >>> backup_info = await manager.backup_knowledge()
            >>> print(f"Backup created at: {backup_info['backup_path']}")  # noqa: print
        """
        await self._ensure_initialized()

        backup_info = {"timestamp": datetime.now().isoformat(), "components": {}}

        await self._backup_system_knowledge(backup_info)
        await self._backup_temporal_metadata(backup_info)

        logger.info("Knowledge backup completed: %s", backup_info["components"])
        return backup_info

    async def cleanup_expired_content(self) -> Dict[str, int]:
        """
        Clean up expired content across all systems

        Scans for and removes expired content based on temporal tracking.

        Returns:
            Cleanup summary with counts by priority

        Example:
            >>> summary = await manager.cleanup_expired_content()
            >>> print(f"Removed {sum(summary.values())} expired items")  # noqa: print
        """
        if not self._temporal_manager:
            return {"message": "Temporal tracking not enabled"}

        # Scan for expired content
        invalidation_jobs = await self.scan_for_expired_content()

        # Process all invalidation jobs
        cleanup_counts = {}
        for job in invalidation_jobs:
            await self.process_invalidation_job(job)
            cleanup_counts[job.priority.value] = len(job.content_ids)

        logger.info("Cleanup completed: %s", cleanup_counts)
        return cleanup_counts


# ============================================================================
# GLOBAL INSTANCE (Singleton Pattern, thread-safe)
# ============================================================================

import threading

_unified_knowledge_manager_instance: Optional[UnifiedKnowledgeManager] = None
_unified_knowledge_manager_lock = threading.Lock()


def get_unified_knowledge_manager(
    knowledge_base: Optional[KnowledgeBase] = None,
    enable_temporal: bool = True,
    enable_machine_aware: bool = True,
) -> UnifiedKnowledgeManager:
    """
    Get global UnifiedKnowledgeManager instance (singleton, thread-safe)

    Args:
        knowledge_base: KnowledgeBase instance (required on first call)
        enable_temporal: Enable temporal tracking
        enable_machine_aware: Enable machine-specific adaptation

    Returns:
        Global UnifiedKnowledgeManager instance

    Raises:
        ValueError: If knowledge_base not provided on first call

    Example:
        >>> # First call - provide knowledge_base
        >>> manager = get_unified_knowledge_manager(kb, enable_temporal=True)
        >>> # Subsequent calls - reuse instance
        >>> manager = get_unified_knowledge_manager()
    """
    global _unified_knowledge_manager_instance

    if _unified_knowledge_manager_instance is None:
        with _unified_knowledge_manager_lock:
            # Double-check after acquiring lock
            if _unified_knowledge_manager_instance is None:
                if knowledge_base is None:
                    raise ValueError(
                        "knowledge_base required on first call to get_unified_knowledge_manager()"
                    )

                _unified_knowledge_manager_instance = UnifiedKnowledgeManager(
                    knowledge_base=knowledge_base,
                    enable_temporal=enable_temporal,
                    enable_machine_aware=enable_machine_aware,
                )

    return _unified_knowledge_manager_instance


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    # Main Manager
    "UnifiedKnowledgeManager",
    # Protocols
    "ITemporalManager",
    "ISystemKnowledgeManager",
    "IMachineAwareManager",
    # Global Instance
    "get_unified_knowledge_manager",
    # Re-export from composed managers for convenience
    "TemporalMetadata",
    "FreshnessStatus",
    "KnowledgePriority",
    "InvalidationJob",
    "MachineProfile",
]
