# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Centralized Prompt Management System

This module provides a unified way to load, format, and manage all prompts
across the AutoBot application, eliminating hardcoded prompts in Python code.
"""

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, Template

from src.constants.path_constants import PATH

logger = logging.getLogger(__name__)

# Issue #380: Module-level constant for supported prompt file extensions
_SUPPORTED_PROMPT_EXTENSIONS = frozenset({".md", ".txt", ".prompt"})


class PromptManager:
    """
    Centralized prompt manager that loads and manages all prompts from the
    prompts/ directory.

    Features:
    - Automatic prompt discovery and loading
    - Template support with Jinja2 for dynamic content
    - Organized prompt structure with dot notation (e.g., 'orchestrator.system_prompt')
    - Fallback mechanisms for missing prompts
    - Hot reloading capability for development
    """

    def __init__(self, prompts_dir: str = "prompts"):
        """Initialize prompt manager with prompts directory."""
        # Get absolute path to prompts directory
        if Path(prompts_dir).is_absolute():
            self.prompts_dir = Path(prompts_dir)
        else:
            # Use centralized PathConstants (Issue #380)
            self.prompts_dir = PATH.PROJECT_ROOT / prompts_dir
        self.prompts: Dict[str, str] = {}
        self.templates: Dict[str, Template] = {}
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.prompts_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=True,  # Enable autoescaping for security
        )

        # Load all prompts on initialization
        self.load_all_prompts()

    def _restore_from_cache(self, cached_data: Dict) -> bool:
        """
        Restore prompts and templates from cached data.

        Recreates Jinja2 templates from cached prompt content. Issue #620.

        Args:
            cached_data: Dictionary containing cached prompts

        Returns:
            True if restoration successful, False otherwise
        """
        if not cached_data or "prompts" not in cached_data:
            return False

        self.prompts = cached_data["prompts"]
        for key, content in self.prompts.items():
            self.templates[key] = self.jinja_env.from_string(content)
        logger.info("Loaded %d prompts from Redis cache (FAST)", len(self.prompts))
        return True

    def _load_prompt_file(self, file_path: Path) -> None:
        """
        Load a single prompt file into the prompts and templates dictionaries.

        Generates a dot-notation key from the file path and stores both
        raw content and Jinja2 template. Issue #620.

        Args:
            file_path: Path to the prompt file to load
        """
        try:
            relative_path = file_path.relative_to(self.prompts_dir)
            prompt_key = self._path_to_key(relative_path)
            content = file_path.read_text(encoding="utf-8").strip()

            self.prompts[prompt_key] = content
            self.templates[prompt_key] = self.jinja_env.from_string(content)
            logger.debug("Loaded prompt: %s from %s", prompt_key, file_path)
        except Exception as e:
            logger.error("Error loading prompt from %s: %s", file_path, e)

    def load_all_prompts(self) -> None:
        """
        Discover and load all prompt files from the prompts directory.
        Supports .md, .txt, and .prompt files. Uses Redis caching for faster loading.
        """
        if not self.prompts_dir.exists():
            logger.warning("Prompts directory '%s' not found", self.prompts_dir)
            return

        needs_update, changed_files = self._check_prompt_changes()

        # Try Redis cache if no updates needed (Issue #620: uses helper)
        if not needs_update:
            cache_key = self._get_cache_key()
            if self._restore_from_cache(self._load_from_redis_cache(cache_key)):
                return

        if changed_files:
            logger.info(
                "Detected prompt changes in %d files: %s%s",
                len(changed_files),
                changed_files[:3],
                "..." if len(changed_files) > 3 else "",
            )

        # Load from files (Issue #620: uses helper)
        for file_path in self.prompts_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix not in _SUPPORTED_PROMPT_EXTENSIONS:
                continue
            if file_path.name.startswith(".") or file_path.name.startswith("_"):
                continue
            self._load_prompt_file(file_path)

        # Cache and finalize
        self._save_to_redis_cache(self._get_cache_key(), {"prompts": self.prompts})
        self._update_prompt_change_cache()
        logger.info("Loaded %s prompts from %s", len(self.prompts), self.prompts_dir)

    def _path_to_key(self, path: Path) -> str:
        """
        Convert file path to dot notation key.

        Examples:
        - orchestrator/system_prompt.md -> orchestrator.system_prompt
        - default/agent.system.main.md -> default.agent.system.main
        - task_system_prompt.txt -> task_system_prompt
        """
        # Remove extension and convert path separators to dots
        key_parts = []

        # Add directory parts
        if path.parent != Path("."):
            key_parts.extend(path.parent.parts)

        # Add filename without extension
        filename = path.stem
        # Handle files that already have dot notation in filename
        key_parts.append(filename)

        return ".".join(key_parts)

    def get(self, prompt_key: str, **kwargs) -> str:
        """
        Get a prompt by key with optional template variable substitution.

        Args:
            prompt_key: Dot notation key for the prompt
                        (e.g., 'orchestrator.system_prompt')
            **kwargs: Template variables for Jinja2 substitution

        Returns:
            Rendered prompt content

        Raises:
            KeyError: If prompt key is not found
        """
        if prompt_key not in self.templates:
            # Try fallback strategies
            fallback_prompt = self._try_fallbacks(prompt_key)
            if fallback_prompt is None:
                available_keys = sorted(self.prompts)
                raise KeyError(
                    f"Prompt '{prompt_key}' not found. Available prompts: "
                    f"{available_keys}"
                )
            return fallback_prompt

        try:
            template = self.templates[prompt_key]
            return template.render(**kwargs)
        except Exception as e:
            logger.error("Error rendering template '%s': %s", prompt_key, e)
            # Return raw content as fallback
            return self.prompts.get(prompt_key, f"Error loading prompt: {prompt_key}")

    def _try_fallbacks(self, prompt_key: str) -> Optional[str]:
        """
        Try various fallback strategies for missing prompts.

        1. Look for similar keys (case insensitive)
        2. Look for default variants
        3. Look in default/ directory
        """
        # Strategy 1: Case insensitive match
        for key in self.prompts:
            if key.lower() == prompt_key.lower():
                logger.warning(
                    f"Using case-insensitive match '{key}' for '{prompt_key}'"
                )
                return self.prompts[key]

        # Strategy 2: Look for default variant
        if not prompt_key.startswith("default."):
            default_key = f"default.{prompt_key}"
            if default_key in self.prompts:
                logger.warning(
                    f"Using default variant '{default_key}' for '{prompt_key}'"
                )
                return self.prompts[default_key]

        # Strategy 3: Look for similar patterns
        similar_keys = [key for key in self.prompts if prompt_key.split(".")[-1] in key]
        if similar_keys:
            best_match = similar_keys[0]  # Take first match
            logger.warning("Using similar prompt '%s' for '%s'", best_match, prompt_key)
            return self.prompts[best_match]

        return None

    def get_raw(self, prompt_key: str) -> str:
        """
        Get raw prompt content without template rendering.

        Args:
            prompt_key: Dot notation key for the prompt

        Returns:
            Raw prompt content
        """
        if prompt_key not in self.prompts:
            fallback_prompt = self._try_fallbacks(prompt_key)
            if fallback_prompt is None:
                raise KeyError(f"Prompt '{prompt_key}' not found")
            return fallback_prompt

        return self.prompts[prompt_key]

    def list_prompts(self, filter_pattern: Optional[str] = None) -> List[str]:
        """
        List all available prompt keys, optionally filtered by pattern.

        Args:
            filter_pattern: Optional regex pattern to filter keys

        Returns:
            List of matching prompt keys
        """
        keys = list(self.prompts)

        if filter_pattern:
            pattern = re.compile(filter_pattern, re.IGNORECASE)
            keys = [key for key in keys if pattern.search(key)]

        return sorted(keys)

    def reload(self) -> None:
        """
        Reload all prompts from disk. Useful for development.
        """
        logger.info("Reloading all prompts...")
        self.prompts.clear()
        self.templates.clear()
        self.load_all_prompts()

    def exists(self, prompt_key: str) -> bool:
        """
        Check if a prompt exists.

        Args:
            prompt_key: Dot notation key for the prompt

        Returns:
            True if prompt exists, False otherwise
        """
        return prompt_key in self.prompts or self._try_fallbacks(prompt_key) is not None

    def add_prompt(self, prompt_key: str, content: str) -> None:
        """
        Add or update a prompt programmatically.

        Args:
            prompt_key: Dot notation key for the prompt
            content: Prompt content
        """
        self.prompts[prompt_key] = content
        self.templates[prompt_key] = Template(content)
        logger.debug("Added/updated prompt: %s", prompt_key)

    def get_categories(self) -> List[str]:
        """
        Get all unique prompt categories (top-level directories).

        Returns:
            List of category names
        """
        categories = set()
        for key in self.prompts:
            if "." in key:
                categories.add(key.split(".")[0])
            else:
                categories.add("root")
        return sorted(categories)

    def get_prompts_by_category(self, category: str) -> Dict[str, str]:
        """
        Get all prompts for a specific category.

        Args:
            category: Category name (e.g., 'orchestrator', 'default')

        Returns:
            Dictionary of prompt keys and content for the category
        """
        if category == "root":
            return {
                key: content for key, content in self.prompts.items() if "." not in key
            }

        prefix = f"{category}."
        return {
            key: content
            for key, content in self.prompts.items()
            if key.startswith(prefix)
        }

    def _check_prompt_changes(self) -> tuple[bool, List[str]]:
        """Check if prompt files have changed since last load"""
        try:
            # Get current file states
            current_state = self._get_prompt_file_state()

            # Load cached state from Redis
            cached_state = self._load_prompt_change_cache()

            if not cached_state:
                logger.debug("No cached prompt state found - first load needed")
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
            logger.debug("Error checking prompt changes: %s", e)
            # On error, assume update is needed
            return True, ["error-triggered-update"]

    def _get_prompt_file_state(self) -> Dict[str, str]:
        """Get current state (hash) of all prompt files"""
        file_states = {}

        if not self.prompts_dir.exists():
            return file_states

        # Issue #380: Use module-level constant for O(1) lookup
        for file_path in self.prompts_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix in _SUPPORTED_PROMPT_EXTENSIONS:
                # Skip hidden files and special files
                if file_path.name.startswith(".") or file_path.name.startswith("_"):
                    continue

                try:
                    # Get file content hash
                    content = file_path.read_text(encoding="utf-8")
                    file_hash = hashlib.md5(
                        content.encode(), usedforsecurity=False
                    ).hexdigest()

                    # Use relative path as key
                    relative_path = str(file_path.relative_to(self.prompts_dir))
                    file_states[relative_path] = file_hash

                except Exception as e:
                    logger.warning("Error processing prompt file %s: %s", file_path, e)

        return file_states

    def _load_prompt_change_cache(self) -> Optional[Dict[str, str]]:
        """Load cached prompt file states from Redis"""
        try:
            from src.utils.redis_client import get_redis_client

            redis_client = get_redis_client(database="prompts")

            if not redis_client:
                return None

            cache_key = "autobot:prompts:file_states"
            cached_data = redis_client.get(cache_key)

            if cached_data:
                data = json.loads(cached_data)
                return data.get("file_states", data)

        except Exception as e:
            logger.debug("Redis prompt change cache load failed: %s", e)

        return None

    def _update_prompt_change_cache(self):
        """Update the cached prompt file states in Redis"""
        try:
            from src.utils.redis_client import get_redis_client

            redis_client = get_redis_client(database="prompts")

            if not redis_client:
                return

            # Get current file states
            current_state = self._get_prompt_file_state()

            # Cache for 24 hours (prompts might change during development)
            cache_key = "autobot:prompts:file_states"
            ttl_seconds = 24 * 60 * 60  # 24 hours

            redis_client.setex(
                cache_key,
                ttl_seconds,
                json.dumps(
                    {
                        "file_states": current_state,
                        "last_updated": datetime.now().isoformat(),
                        "file_count": len(current_state),
                    }
                ),
            )

            logger.debug(
                "Updated prompt change cache with %s files", len(current_state)
            )

        except Exception as e:
            logger.debug("Failed to update prompt change cache: %s", e)

    def _get_cache_key(self) -> str:
        """Generate cache key based on prompts directory content hash"""
        try:
            # Get all prompt file paths and their modification times
            files_info = []
            for file_path in self.prompts_dir.rglob("*"):
                if (
                    file_path.is_file()
                    and file_path.suffix in _SUPPORTED_PROMPT_EXTENSIONS
                ):
                    files_info.append(f"{file_path}:{file_path.stat().st_mtime}")

            # Create hash of file info
            content = "\n".join(sorted(files_info))
            cache_hash = hashlib.md5(
                content.encode(), usedforsecurity=False
            ).hexdigest()[:12]
            return f"autobot:prompts:cache:{cache_hash}"
        except Exception as e:
            logger.warning("Failed to generate cache key: %s", e)
            return "autobot:prompts:cache:default"

    def _load_from_redis_cache(self, cache_key: str) -> Optional[Dict]:
        """Load prompts from Redis cache using dedicated prompts database"""
        try:
            from src.utils.redis_client import get_redis_client

            redis_client = get_redis_client(database="prompts")
            if not redis_client:
                return None

            cached_data = redis_client.get(cache_key)
            if cached_data:
                logger.debug("Loading prompts from Redis prompts database (DB 2)")
                return json.loads(cached_data)
        except Exception as e:
            logger.debug("Redis prompts cache load failed: %s", e)
        return None

    def _save_to_redis_cache(self, cache_key: str, data: Dict) -> None:
        """Save prompts to Redis cache using dedicated prompts database"""
        try:
            from src.utils.redis_client import get_redis_client

            redis_client = get_redis_client(database="prompts")
            if not redis_client:
                return

            # Cache for 24 hours in dedicated prompts database (DB 2)
            redis_client.setex(cache_key, 86400, json.dumps(data))
            logger.debug(
                "Saved prompts to Redis prompts database (DB 2): %s", cache_key
            )
        except Exception as e:
            logger.debug("Redis prompts cache save failed: %s", e)


# Global prompt manager instance
prompt_manager = PromptManager()


def get_prompt(prompt_key: str, **kwargs) -> str:
    """
    Convenience function to get a prompt using the global prompt manager.

    Args:
        prompt_key: Dot notation key for the prompt
        **kwargs: Template variables for substitution

    Returns:
        Rendered prompt content
    """
    return prompt_manager.get(prompt_key, **kwargs)


def _build_dynamic_context(
    session_id: Optional[str],
    user_name: Optional[str],
    user_role: Optional[str],
    available_tools: Optional[List[str]],
    recent_context: Optional[str],
    additional_params: Optional[Dict],
) -> str:
    """
    Build dynamic context section for optimized prompts.

    Renders the dynamic context template with session-specific variables.
    Falls back to minimal context if template not found. Issue #620.

    Args:
        session_id: Current session identifier
        user_name: User's display name
        user_role: User's role/permissions
        available_tools: List of available tool names
        recent_context: Recent conversation context or task history
        additional_params: Additional dynamic parameters

    Returns:
        Rendered dynamic context string
    """
    try:
        dynamic_template_key = "default.agent.system.dynamic_context"
        return prompt_manager.get(
            dynamic_template_key,
            session_id=session_id or "N/A",
            current_date=datetime.now().strftime("%Y-%m-%d"),
            current_time=datetime.now().strftime("%H:%M:%S"),
            user_name=user_name,
            user_role=user_role,
            available_tools=available_tools or [],
            recent_context=recent_context or "",
            additional_params=additional_params or {},
        )
    except KeyError:
        logger.warning(
            "Dynamic context template not found, using minimal dynamic section"
        )
        return (
            f"\n\n## Session Context\nSession ID: {session_id or 'N/A'}\nDate:"
            f"{datetime.now().strftime('%Y-%m-%d')}"
        )


def get_optimized_prompt(
    base_prompt_key: str,
    session_id: Optional[str] = None,
    user_name: Optional[str] = None,
    user_role: Optional[str] = None,
    available_tools: Optional[List[str]] = None,
    recent_context: Optional[str] = None,
    additional_params: Optional[Dict] = None,
) -> str:
    """
    Get a prompt optimized for vLLM prefix caching.

    This function returns a prompt structured for maximum cache efficiency:
    1. Static base prompt FIRST (will be cached by vLLM)
    2. Dynamic context LAST (NOT cached, but minimal tokens)

    Args:
        base_prompt_key: The static base prompt key (e.g., 'default.agent.system.main')
        session_id: Current session identifier
        user_name: User's display name
        user_role: User's role/permissions
        available_tools: List of available tool names
        recent_context: Recent conversation context or task history
        additional_params: Additional dynamic parameters

    Returns:
        Combined prompt with static prefix + dynamic suffix
    """
    # Get static base prompt with includes rendered (will be cached by vLLM)
    base_prompt = prompt_manager.get(base_prompt_key)

    # Build dynamic context section (Issue #620: extracted helper)
    dynamic_context = _build_dynamic_context(
        session_id,
        user_name,
        user_role,
        available_tools,
        recent_context,
        additional_params,
    )

    # Combine: static prefix + dynamic suffix (CRITICAL for vLLM prefix caching)
    return f"{base_prompt}\n\n{dynamic_context}"


def list_available_prompts(filter_pattern: Optional[str] = None) -> List[str]:
    """
    Convenience function to list available prompts.

    Args:
        filter_pattern: Optional regex pattern to filter keys

    Returns:
        List of matching prompt keys
    """
    return prompt_manager.list_prompts(filter_pattern)


def reload_prompts() -> None:
    """
    Convenience function to reload all prompts.
    """
    prompt_manager.reload()
