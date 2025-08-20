"""
Centralized Prompt Management System

This module provides a unified way to load, format, and manage all prompts
across the AutoBot application, eliminating hardcoded prompts in Python code.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, Template

logger = logging.getLogger(__name__)


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
        self.prompts_dir = Path(prompts_dir)
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

    def load_all_prompts(self) -> None:
        """
        Discover and load all prompt files from the prompts directory.
        Supports .md, .txt, and .prompt files.
        """
        if not self.prompts_dir.exists():
            logger.warning(f"Prompts directory '{self.prompts_dir}' not found")
            return

        supported_extensions = {".md", ".txt", ".prompt"}

        for file_path in self.prompts_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix in supported_extensions:
                # Skip hidden files and special files
                if file_path.name.startswith(".") or file_path.name.startswith("_"):
                    continue

                try:
                    # Generate prompt key from file path
                    # e.g., prompts/orchestrator/system_prompt.md ->
                    # orchestrator.system_prompt
                    relative_path = file_path.relative_to(self.prompts_dir)
                    prompt_key = self._path_to_key(relative_path)

                    # Load content
                    content = file_path.read_text(encoding="utf-8").strip()

                    # Store both raw content and as Jinja2 template
                    self.prompts[prompt_key] = content
                    self.templates[prompt_key] = self.jinja_env.from_string(content)

                    logger.debug(f"Loaded prompt: {prompt_key} from {file_path}")

                except Exception as e:
                    logger.error(f"Error loading prompt from {file_path}: {e}")

        logger.info(f"Loaded {len(self.prompts)} prompts from {self.prompts_dir}")

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
                available_keys = sorted(self.prompts.keys())
                raise KeyError(
                    f"Prompt '{prompt_key}' not found. Available prompts: "
                    f"{available_keys}"
                )
            return fallback_prompt

        try:
            template = self.templates[prompt_key]
            return template.render(**kwargs)
        except Exception as e:
            logger.error(f"Error rendering template '{prompt_key}': {e}")
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
        for key in self.prompts.keys():
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
        similar_keys = [
            key for key in self.prompts.keys() if prompt_key.split(".")[-1] in key
        ]
        if similar_keys:
            best_match = similar_keys[0]  # Take first match
            logger.warning(f"Using similar prompt '{best_match}' for '{prompt_key}'")
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
        keys = list(self.prompts.keys())

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
        logger.debug(f"Added/updated prompt: {prompt_key}")

    def get_categories(self) -> List[str]:
        """
        Get all unique prompt categories (top-level directories).

        Returns:
            List of category names
        """
        categories = set()
        for key in self.prompts.keys():
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
