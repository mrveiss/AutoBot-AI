# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml
from jinja2 import Environment, FileSystemLoader, Template

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from constants.ttl_constants import TTL_24_HOURS

logger = get_logger(__name__)


def _detect_structured_format(content: str) -> str:
    """
    Detect whether content is JSON or XML/HTML.

    Issue #4395: Identifies structured data formats so _truncate_large_file
    can snap to semantically valid boundaries instead of mid-token cuts.

    Args:
        content: File content (first 512 chars sufficient for detection).

    Returns:
        "json" | "xml" | "unknown"
    """
    stripped = content.lstrip()
    if stripped.startswith(("{", "[")):
        return "json"
    if stripped.startswith("<"):
        return "xml"
    return "unknown"


def _json_head_boundary(content: str, target: int) -> int:
    """
    Find the largest position ≤ target that ends a complete JSON value at the
    top level of the document.

    Issue #4395: Prevents leaving unterminated strings, arrays, or objects in
    the head section when JSON content is truncated.

    Scans backward from *target* for the pattern ``},\\n`` or ``],\\n`` —
    i.e. a closing bracket followed by a comma/newline, which is a safe entry
    boundary between sibling JSON values.  Internal commas (inside strings or
    between object fields) are excluded because they are not preceded by ``}``
    or ``]``.

    Args:
        content: Full JSON string.
        target: Ideal cut position (typically 40% of max_chars).

    Returns:
        Adjusted position (after the trailing newline), or *target* if no
        safe boundary is found within 1000 chars of *target*.
    """
    search_start = max(0, target - 1000)
    # Walk backward from target looking for },\n or ],\n
    for i in range(min(target, len(content) - 1), search_start, -1):
        if content[i] == "\n" and i >= 2 and content[i - 1] == "," and content[i - 2] in ("}", "]"):
            return i + 1
    # Fallback: accept a bare },\n or ],\n without the comma (last entry)
    for i in range(min(target, len(content) - 1), search_start, -1):
        if content[i] == "\n" and i >= 1 and content[i - 1] in ("}", "]"):
            return i + 1
    return target


def _json_tail_boundary(content: str, target: int) -> int:
    """
    Find the smallest position ≥ target that starts a complete JSON value at
    the top level of the document.

    Issue #4395: Ensures the tail section of truncated JSON begins on a clean
    entry boundary (a line that opens an array element or object key).

    Scans forward from *target* for a newline followed by a non-whitespace
    character — these typically indicate the start of a new JSON entry.

    Args:
        content: Full JSON string.
        target: Ideal cut position (typically len - 40% of max_chars).

    Returns:
        Adjusted position, or *target* if no safe boundary found.
    """
    search_end = min(len(content), target + 500)
    for i in range(target, search_end):
        next_is_non_ws = i + 1 < len(content) and content[i + 1] not in (" ", "\t", "\r", "\n")
        if content[i] == "\n" and next_is_non_ws:
            return i + 1
    return target


def _xml_head_boundary(content: str, target: int) -> int:
    """
    Find the largest position ≤ target that follows a complete XML closing tag.

    Issue #4395: Avoids cutting in the middle of an XML element.  Scans
    backward from *target* for the end of a closing tag (``>`` preceded by
    ``/something``).

    Args:
        content: Full XML/HTML string.
        target: Ideal cut position.

    Returns:
        Adjusted position (character after the ``>``), or *target* if not found.
    """
    search_start = max(0, target - 500)
    for i in range(min(target, len(content) - 1), search_start, -1):
        if content[i] == ">" and i > 0:
            # Confirm this looks like a closing tag: find matching '</'
            tag_start = content.rfind("</", search_start, i)
            if tag_start != -1:
                return i + 1
    return target


def _xml_tail_boundary(content: str, target: int) -> int:
    """
    Find the smallest position ≥ target that precedes an XML opening tag.

    Issue #4395: Ensures the tail section starts at a clean element boundary.

    Args:
        content: Full XML/HTML string.
        target: Ideal cut position.

    Returns:
        Adjusted position, or *target* if not found.
    """
    search_end = min(len(content), target + 500)
    for i in range(target, search_end):
        if content[i] == "<" and i + 1 < len(content) and content[i + 1] != "/":
            return i
    return target


def _is_binary_content(content: str) -> bool:
    """
    Detect binary content masquerading as text (e.g. null bytes in decoded strings).

    Issue #4396: Binary files opened with UTF-8 decoding can slip through as
    str objects that contain null bytes (\\x00).  Passing such content to
    _truncate_large_file would produce a broken LLM context entry.  This helper
    lets callers bail out early with a safe placeholder.

    Args:
        content: String to inspect.

    Returns:
        True when null bytes are present (strong binary signal), else False.
    """
    return "\x00" in content


def _is_cjk(ch: str) -> bool:
    """Return True if *ch* is a CJK ideograph (each character is its own word)."""
    cp = ord(ch)
    return (
        0x3000 <= cp <= 0x9FFF  # CJK Unified Ideographs + CJK Symbols/Punctuation
        or 0xF900 <= cp <= 0xFAFF  # CJK Compatibility Ideographs
        or 0x20000 <= cp <= 0x2FA1F  # CJK Extension B–F + Compatibility Supplement
    )


def _snap_to_char_boundary(content: str, pos: int, search_forward: bool = True) -> int:
    """
    Snap a string slice position to a Unicode-safe word boundary.

    Issue #4394: Python str indexing is already codepoint-safe (no mid-codepoint
    splits possible), but this helper snaps the cut to the nearest whitespace so
    truncation does not break mid-word for multi-byte characters (emoji 4-byte,
    CJK 3-byte, accented 2-byte).

    Issue #4436: CJK text has no spaces between characters — each codepoint is its
    own word, so whitespace snapping is unnecessary. When the character at *pos* is
    CJK, return *pos* immediately instead of scanning and falling back anyway.

    Args:
        content: The full string being sliced.
        pos: Proposed slice position.
        search_forward: If True search forward for whitespace (head cut);
                        if False search backward (tail cut).

    Returns:
        Adjusted position at or near a whitespace boundary, within ±100 chars.
    """
    limit = 100  # Maximum chars to search for a boundary
    length = len(content)
    pos = max(0, min(pos, length))

    if pos < length and _is_cjk(content[pos]):
        return pos

    if search_forward:
        end = min(pos + limit, length)
        for i in range(pos, end):
            if content[i].isspace():
                return i
        return pos  # No whitespace found within limit — use original
    else:
        start = max(pos - limit, 0)
        for i in range(pos, start, -1):
            if content[i - 1].isspace():
                return i
        return pos  # No whitespace found within limit — use original


def _truncate_large_file(content: str, max_chars: int = 20000) -> str:
    """
    Smart head/tail truncation for large file content.

    Issue #4346: Preserves critical first and last sections of large files
    (>max_chars) with a truncation marker, optimizing LLM context usage.

    Issue #4394: Truncation boundaries are snapped to whitespace so that
    multi-byte Unicode characters (emoji 4-byte, CJK 3-byte, accented 2-byte)
    are never split mid-word.  Python str indexing is already codepoint-safe,
    but word-boundary snapping prevents cut points inside multi-byte words.

    Issue #4395: Structured data (JSON/XML) is truncated at semantically valid
    element/entry boundaries so that each half remains well-formed and the LLM
    can reason about the data even when it is too large to fit in context.

    Strategy:
    - Files smaller than max_chars: returned unchanged
    - Files larger than max_chars: keep first 40% + ellipsis marker + last 40%
    - JSON/XML: boundaries snapped to complete entry/element edges
    - Otherwise: boundaries snapped to whitespace (Issue #4394)
    - Marker format: "[...N chars TRUNCATED...]"

    Args:
        content: File content to potentially truncate
        max_chars: Threshold for truncation (default 20000)

    Returns:
        Truncated content with marker if needed, otherwise original content
    """
    if len(content) <= max_chars:
        return content

    # Issue #4396: binary content (null bytes) must not be passed to the LLM
    if _is_binary_content(content):
        logger.warning(
            "Binary content detected (%d chars) — skipping truncation, returning placeholder",
            len(content),
        )
        return "[Binary file content omitted — not suitable for LLM context]"

    # Calculate sections: preserve first 40% and last 40% of max_chars
    section_size = (max_chars // 5) * 2  # 40% of max_chars

    fmt = _detect_structured_format(content)
    if fmt == "json":
        # Issue #4395: snap to complete JSON entry boundaries
        head_end = _json_head_boundary(content, section_size)
        tail_start = _json_tail_boundary(content, len(content) - section_size)
    elif fmt == "xml":
        # Issue #4395: snap to complete XML element boundaries
        head_end = _xml_head_boundary(content, section_size)
        tail_start = _xml_tail_boundary(content, len(content) - section_size)
    else:
        # Issue #4394: snap to whitespace so multi-byte chars are not split mid-word
        head_end = _snap_to_char_boundary(content, section_size, search_forward=True)
        tail_start = _snap_to_char_boundary(content, len(content) - section_size, search_forward=False)

    # Ensure tail_start > head_end to avoid overlap on pathological inputs
    if tail_start <= head_end:
        head_end = section_size
        tail_start = len(content) - section_size

    head = content[:head_end]
    tail = content[tail_start:]
    truncated_chars = len(content) - head_end - (len(content) - tail_start)

    marker = f"\n\n[...{truncated_chars} chars TRUNCATED...]\n\n"
    truncated = f"{head}{marker}{tail}"

    logger.info(
        "Truncated large file: %d chars -> %d chars (marker: %d chars removed)",
        len(content),
        len(truncated),
        truncated_chars,
    )

    return truncated


def _build_skill_context(skills: List[Dict] | None) -> str:
    """
    Build a skill context section from ranked skills.

    Issue #4337: Injects available skills into system prompt for agent awareness.

    Args:
        skills: List of ranked skill dictionaries (from SkillRanker)

    Returns:
        Rendered skill context string or empty string if no skills
    """
    if not skills:
        return ""

    skill_lines = []
    for i, skill in enumerate(skills, 1):
        name = skill.get("name", "Unknown")
        description = skill.get("description", "")
        # Format: 1. SkillName: brief description
        if description:
            skill_lines.append(f"{i}. {name}: {description}")
        else:
            skill_lines.append(f"{i}. {name}")

    if not skill_lines:
        return ""

    skills_text = "\n".join(skill_lines)
    header = "\n\n## Available Skills\nThe following skills are available for this agent to use:\n"
    return header + skills_text


# Issue #380: Module-level constant for supported prompt file extensions
_SUPPORTED_PROMPT_EXTENSIONS = frozenset({".md", ".txt", ".prompt"})

# Issue #4484: YAML prompt file extensions
_YAML_EXTENSIONS = frozenset({".yml", ".yaml"})

# Issue #4484: Section assembly order for YAML-sectioned prompts
_YAML_SECTION_ORDER = ("role", "objective", "tools", "examples", "instructions")


def _get_ssot_template_vars() -> Dict[str, str]:
    """
    Build a dict of SSOT-derived Jinja variables available to every prompt template.

    Issue #6724: lets prompts reference deployment IPs/ports as ``{{ vm_main }}``
    instead of hardcoding the literal IP. Caller kwargs to ``get()`` still win
    over these defaults. Returns an empty dict if SSOT config can't be loaded so
    legacy templates with literal text continue to render.
    """
    try:
        from autobot_shared.ssot_config import config

        return {
            "vm_main": config.vm.main,
            "vm_frontend": config.vm.frontend,
            "vm_npu": config.vm.npu,
            "vm_redis": config.vm.redis,
            "vm_aistack": config.vm.aistack,
            "vm_chromadb": config.vm.chromadb,
            "vm_browser": config.vm.browser,
            "vm_tts": config.vm.tts,
            "vm_slm": config.vm.slm,
            "vm_ollama": config.vm.ollama,
            "port_backend": str(config.port.backend),
            "port_frontend": str(config.port.frontend),
            "port_redis": str(config.port.redis),
            "port_npu": str(config.port.npu),
            "port_aistack": str(config.port.aistack),
            "port_chromadb": str(config.port.chromadb),
            "port_browser": str(config.port.browser),
            "port_tts": str(config.port.tts),
            "port_slm": str(config.port.slm),
            "port_ollama": str(config.port.ollama),
            "port_vnc": str(config.port.vnc),
        }
    except Exception as exc:
        logger.debug("Could not load SSOT vars for prompt templates: %s", exc)
        return {}


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
            # Resolve relative to backend root (#793)
            self.prompts_dir = Path(__file__).parent / "resources" / "prompts"
        self.prompts: Dict[str, str] = {}
        self.templates: Dict[str, Template] = {}
        # Issue #4484: keyed by prompt_key -> {section_name -> raw text}
        self.yaml_sections: Dict[str, Dict[str, str]] = {}
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.prompts_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=True,  # Enable autoescaping for security
        )

        # Store project root for context file scanning (#4345)
        self._root_dir = Path(__file__).parent.parent

        # Scan context files for injection patterns before loading prompts (#4345)
        try:
            self.load_and_scan_context_files()
        except ValueError as e:
            # Critical injection detected - log but don't fail init
            logger.error("Context file injection detected during init: %s", e)
            # In production, this would be more severe; for now, log and continue

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

    def truncate_large_file(self, content: str, max_chars: int = 20000) -> str:
        """
        Public method to truncate large file content using smart head/tail strategy.

        Issue #4346: Applies smart truncation to preserve context while limiting tokens.

        Args:
            content: File content to potentially truncate
            max_chars: Threshold for truncation (default 20000)

        Returns:
            Truncated content with marker if needed, otherwise original content
        """
        return _truncate_large_file(content, max_chars)

    def _assemble_yaml_sections(self, sections: Dict[str, str]) -> str:
        """
        Assemble a YAML prompt's sections into a single string.

        Issue #4484: Section order is role -> objective -> tools -> examples ->
        instructions. Unknown sections are appended after in sorted order.

        Args:
            sections: Mapping of section name to raw text.

        Returns:
            Assembled prompt string.
        """
        parts = []
        seen: set = set()
        for name in _YAML_SECTION_ORDER:
            if name in sections:
                parts.append(sections[name].strip())
                seen.add(name)
        for name in sorted(sections):
            if name not in seen:
                parts.append(sections[name].strip())
        return "\n\n".join(p for p in parts if p)

    def _load_yaml_prompt_file(self, file_path: Path) -> None:
        """
        Load a YAML-sectioned prompt file.

        Issue #4484: Parses named sections (role, objective, instructions,
        examples, tools) and stores them in ``self.yaml_sections``.  The
        assembled prompt is also stored in ``self.prompts`` / ``self.templates``
        so that callers that do not use overrides work transparently.

        Expected YAML structure::

            role: |
              You are ...
            objective: |
              Your goal is ...
            instructions: |
              1. Do this

        Args:
            file_path: Path to the ``.yml`` / ``.yaml`` file to load.
        """
        try:
            relative_path = file_path.relative_to(self.prompts_dir)
            prompt_key = self._path_to_key(relative_path)
            raw = file_path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw)

            if not isinstance(data, dict):
                logger.warning(
                    "YAML prompt %s must be a mapping; got %s — skipping",
                    file_path,
                    type(data).__name__,
                )
                return

            sections: Dict[str, str] = {k: str(v) for k, v in data.items() if isinstance(v, str)}
            self.yaml_sections[prompt_key] = sections

            assembled = self._assemble_yaml_sections(sections)
            self.prompts[prompt_key] = assembled
            self.templates[prompt_key] = self.jinja_env.from_string(assembled)
            logger.debug("Loaded YAML prompt: %s from %s", prompt_key, file_path)
        except yaml.YAMLError as exc:
            logger.error("YAML parse error in %s: %s", file_path, exc)
        except Exception as exc:
            logger.error("Error loading YAML prompt from %s: %s", file_path, exc)

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
        Supports .md, .txt, .prompt, and .yml/.yaml files.
        Uses Redis caching for faster loading.
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
        # Issue #4484: also load YAML-sectioned prompts
        for file_path in self.prompts_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.name.startswith(".") or file_path.name.startswith("_"):
                continue
            if file_path.suffix in _YAML_EXTENSIONS:
                self._load_yaml_prompt_file(file_path)
            elif file_path.suffix in _SUPPORTED_PROMPT_EXTENSIONS:
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

    def get(
        self,
        prompt_key: str,
        overrides: Dict[str, str] | None = None,
        **kwargs,
    ) -> str:
        """
        Get a prompt by key with optional template variable substitution.

        Issue #4484: For YAML-sectioned prompts, ``overrides`` replaces
        individual sections before assembly.  Each key in ``overrides`` must
        match a section name (role, objective, tools, examples, instructions,
        or any custom section defined in the YAML file).  Overridden prompts
        are cached under a key derived from a hash of the overrides dict so
        they do not collide with the base-assembled version.

        Args:
            prompt_key: Dot notation key for the prompt
                        (e.g., 'orchestrator.system_prompt')
            overrides: Optional section overrides for YAML prompts.
                       Keys are section names; values are replacement text.
            **kwargs: Template variables for Jinja2 substitution

        Returns:
            Rendered prompt content

        Raises:
            KeyError: If prompt key is not found
        """
        # Issue #6724: inject SSOT VM/port defaults so templates can use {{ vm_main }}
        # etc. without each caller needing to pass them. Caller kwargs win on conflict.
        merged_kwargs = {**_get_ssot_template_vars(), **kwargs}

        # Issue #4484: handle YAML section overrides
        if overrides and prompt_key in self.yaml_sections:
            return self._get_with_overrides(prompt_key, overrides, **merged_kwargs)

        if prompt_key not in self.templates:
            # Try fallback strategies
            fallback_prompt = self._try_fallbacks(prompt_key)
            if fallback_prompt is None:
                available_keys = sorted(self.prompts)
                raise KeyError(f"Prompt '{prompt_key}' not found. Available prompts: " f"{available_keys}")
            return fallback_prompt

        try:
            template = self.templates[prompt_key]
            return template.render(**merged_kwargs)
        except Exception as e:
            logger.error("Error rendering template '%s': %s", prompt_key, e)
            # Return raw content as fallback
            return self.prompts.get(prompt_key, f"Error loading prompt: {prompt_key}")

    def _get_with_overrides(
        self,
        prompt_key: str,
        overrides: Dict[str, str],
        **kwargs,
    ) -> str:
        """
        Assemble a YAML prompt with per-section overrides and render it.

        Issue #4484: The override cache key includes a hash of the overrides
        dict so each unique override set caches separately from the base prompt
        and from other override combinations.

        Args:
            prompt_key: Dot notation key for the YAML prompt.
            overrides: Section name -> replacement text mapping.
            **kwargs: Jinja2 template variables forwarded to render().

        Returns:
            Rendered assembled prompt string.
        """
        overrides_hash = hashlib.md5(json.dumps(overrides, sort_keys=True).encode(), usedforsecurity=False).hexdigest()[
            :8
        ]
        cache_key = f"{prompt_key}.__overrides_{overrides_hash}"

        if cache_key not in self.templates:
            merged = dict(self.yaml_sections[prompt_key])
            merged.update(overrides)
            assembled = self._assemble_yaml_sections(merged)
            self.templates[cache_key] = self.jinja_env.from_string(assembled)
            logger.debug("Cached overridden YAML prompt '%s' (hash %s)", prompt_key, overrides_hash)

        try:
            return self.templates[cache_key].render(**kwargs)
        except Exception as e:
            logger.error("Error rendering overridden template '%s': %s", prompt_key, e)
            assembled = self._assemble_yaml_sections({**self.yaml_sections[prompt_key], **overrides})
            return assembled

    def _try_fallbacks(self, prompt_key: str) -> str | None:
        """
        Try various fallback strategies for missing prompts.

        1. Look for similar keys (case insensitive)
        2. Look for default variants
        3. Look in default/ directory
        """
        # Strategy 1: Case insensitive match
        for key in self.prompts:
            if key.lower() == prompt_key.lower():
                logger.warning(f"Using case-insensitive match '{key}' for '{prompt_key}'")
                return self.prompts[key]

        # Strategy 2: Look for default variant
        if not prompt_key.startswith("default."):
            default_key = f"default.{prompt_key}"
            if default_key in self.prompts:
                logger.warning(f"Using default variant '{default_key}' for '{prompt_key}'")
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

    def list_prompts(self, filter_pattern: str | None = None) -> List[str]:
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

    def _scan_for_injection(self, content: str, file_name: str) -> Dict[str, Any]:
        """
        Scan context files for prompt injection patterns.

        Issue #4345: Detects prompt injection attempts in context files
        (AGENTS.md, CLAUDE.md, .cursorrules, SOUL.md, etc.) before they
        are injected into system prompts.

        Detects:
        - "ignore previous instructions" patterns
        - Role-switching attempts ("you are now", "you are a")
        - Invisible Unicode characters (U+200B-U+206F)
        - System prompt override attempts
        - Command injection patterns

        Args:
            content: File content to scan
            file_name: Name of the file being scanned (for logging)

        Returns:
            Dictionary with detection results:
                - detected: bool, whether injection was found
                - risk_level: string risk level
                - patterns: list of detected patterns
                - suspicious_chars: list of invisible Unicode found
        """
        try:
            from security.prompt_injection_detector import (
                InjectionRisk,
                get_prompt_injection_detector,
            )

            detector = get_prompt_injection_detector(strict_mode=True)
            result = detector.detect_injection(content, context="context_file")

            detection = {
                "detected": result.blocked,
                "risk_level": result.risk_level.value,
                "patterns": result.detected_patterns,
                "file_name": file_name,
            }

            if result.blocked:
                logger.warning(
                    "🚨 Prompt injection detected in context file '%s': %s",
                    file_name,
                    result.detected_patterns,
                )

                # Log audit trail
                try:
                    audit_msg = (
                        f"INJECTION_ATTEMPT | File: {file_name} | "
                        f"Risk: {result.risk_level.value} | "
                        f"Patterns: {len(result.detected_patterns)}"
                    )
                    logger.critical(audit_msg)
                except Exception as audit_error:
                    logger.error("Failed to log injection audit: %s", audit_error)

            elif result.risk_level != InjectionRisk.SAFE:
                logger.info(
                    "⚠️ Suspicious patterns in context file '%s' " "(risk: %s): %s",
                    file_name,
                    result.risk_level.value,
                    result.detected_patterns,
                )

            return detection

        except Exception as e:
            logger.error("Error scanning context file '%s' for injection: %s", file_name, e)
            return {
                "detected": False,
                "risk_level": "error",
                "patterns": [],
                "file_name": file_name,
                "error": str(e),
            }

    def load_and_scan_context_files(self, project_root: Path | None = None) -> Dict[str, Any]:
        """
        Load and scan context files for prompt injection patterns.

        Issue #4345: Scans AGENTS.md, CLAUDE.md, .cursorrules, SOUL.md before
        injecting into system prompts. Blocks injection if HIGH/CRITICAL risk
        detected.

        Args:
            project_root: Root directory to search for context files.
                         Defaults to parent of prompt manager's root.

        Returns:
            Dictionary with scan results:
                - scanned_files: list of scanned files
                - total_scanned: number of files scanned
                - detections: list of detection results
                - has_critical: bool, whether any critical risk detected
                - blocked: bool, whether injection was blocked

        Raises:
            ValueError: If HIGH or CRITICAL risk detected
        """
        if project_root is None:
            project_root = self._root_dir

        context_files = [
            "AGENTS.md",
            "CLAUDE.md",
            ".cursorrules",
            "SOUL.md",
            "GEMINI.md",  # Additional context file
        ]

        scan_results = {
            "scanned_files": [],
            "total_scanned": 0,
            "detections": [],
            "has_critical": False,
            "has_high": False,
            "blocked": False,
        }

        try:
            for context_file in context_files:
                file_path = project_root / context_file

                if not file_path.exists():
                    logger.debug("Context file not found: %s", context_file)
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8")
                    scan_results["scanned_files"].append(context_file)
                    scan_results["total_scanned"] += 1

                    # Scan for injection patterns
                    detection = self._scan_for_injection(content, context_file)
                    scan_results["detections"].append(detection)

                    # Track risk levels
                    if detection["risk_level"] == "critical":
                        scan_results["has_critical"] = True
                    elif detection["risk_level"] == "high":
                        scan_results["has_high"] = True

                except Exception as e:
                    logger.error("Error reading context file %s: %s", context_file, e)
                    scan_results["detections"].append(
                        {
                            "file_name": context_file,
                            "detected": False,
                            "risk_level": "error",
                            "error": str(e),
                            "patterns": [],
                        }
                    )

            # Determine if injection should be blocked
            if scan_results["has_critical"]:
                scan_results["blocked"] = True
                blocked_files = [d["file_name"] for d in scan_results["detections"] if d["risk_level"] == "critical"]
                error_msg = (
                    f"🚨 CRITICAL prompt injection detected in context files: "
                    f"{', '.join(blocked_files)}. Injection blocked."
                )
                logger.critical(error_msg)
                raise ValueError(error_msg)

            # Log summary
            if scan_results["total_scanned"] > 0:
                logger.info(
                    "Context file scan complete: %d files scanned, %d detections",
                    scan_results["total_scanned"],
                    len([d for d in scan_results["detections"] if d.get("detected")]),
                )

            return scan_results

        except ValueError:
            # Re-raise ValueError for critical injections
            raise
        except Exception as e:
            logger.error("Error in context file scanning: %s", e)
            return scan_results

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
            return {key: content for key, content in self.prompts.items() if "." not in key}

        prefix = f"{category}."
        return {key: content for key, content in self.prompts.items() if key.startswith(prefix)}

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
                    file_hash = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()

                    # Use relative path as key
                    relative_path = str(file_path.relative_to(self.prompts_dir))
                    file_states[relative_path] = file_hash

                except Exception as e:
                    logger.warning("Error processing prompt file %s: %s", file_path, e)

        return file_states

    def _load_prompt_change_cache(self) -> Dict[str, str] | None:
        """Load cached prompt file states from Redis"""
        try:
            from autobot_shared.redis_client import get_redis_client

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
            from autobot_shared.redis_client import get_redis_client

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
                        "last_updated": datetime.now(tz=timezone.utc).isoformat(),
                        "file_count": len(current_state),
                    }
                ),
            )

            logger.debug("Updated prompt change cache with %s files", len(current_state))

        except Exception as e:
            logger.debug("Failed to update prompt change cache: %s", e)

    def _get_cache_key(self) -> str:
        """Generate cache key based on prompts directory content hash"""
        try:
            # Get all prompt file paths and their modification times
            files_info = []
            for file_path in self.prompts_dir.rglob("*"):
                if file_path.is_file() and file_path.suffix in _SUPPORTED_PROMPT_EXTENSIONS:
                    files_info.append(f"{file_path}:{file_path.stat().st_mtime}")

            # Create hash of file info
            content = "\n".join(sorted(files_info))
            cache_hash = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()[:12]
            return f"autobot:prompts:cache:{cache_hash}"
        except Exception as e:
            logger.warning("Failed to generate cache key: %s", e)
            return "autobot:prompts:cache:default"

    def _load_from_redis_cache(self, cache_key: str) -> Dict | None:
        """Load prompts from Redis cache using dedicated prompts database"""
        try:
            from autobot_shared.redis_client import get_redis_client

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
            from autobot_shared.redis_client import get_redis_client

            redis_client = get_redis_client(database="prompts")
            if not redis_client:
                return

            # Cache for 24 hours in dedicated prompts database (DB 2)
            redis_client.setex(cache_key, TTL_24_HOURS, json.dumps(data))
            logger.debug("Saved prompts to Redis prompts database (DB 2): %s", cache_key)
        except Exception as e:
            logger.debug("Redis prompts cache save failed: %s", e)


get_prompt_manager = lazy_singleton(PromptManager)


def get_prompt(prompt_key: str, **kwargs) -> str:
    """
    Convenience function to get a prompt using the global prompt manager.

    Args:
        prompt_key: Dot notation key for the prompt
        **kwargs: Template variables for substitution

    Returns:
        Rendered prompt content
    """
    return get_prompt_manager().get(prompt_key, **kwargs)


def _build_dynamic_context(
    session_id: str | None,
    user_name: str | None,
    user_role: str | None,
    available_tools: List[str] | None,
    recent_context: str | None,
    additional_params: Dict | None,
    tool_descriptions: Dict | None = None,
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
        tool_descriptions: Optional mapping of tool_name -> compressed description (Issue #5827)

    Returns:
        Rendered dynamic context string
    """
    try:
        dynamic_template_key = "default.agent.system.dynamic_context"
        return get_prompt_manager().get(
            dynamic_template_key,
            session_id=session_id or "N/A",
            current_date=datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
            current_time=datetime.now(tz=timezone.utc).strftime("%H:%M:%S"),
            user_name=user_name,
            user_role=user_role,
            available_tools=available_tools or [],
            recent_context=recent_context or "",
            additional_params=additional_params or {},
            tool_descriptions=tool_descriptions,
        )
    except KeyError:
        logger.warning("Dynamic context template not found, using minimal dynamic section")
        return (
            f"\n\n## Session Context\nSession ID: {session_id or 'N/A'}\nDate:"
            f"{datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}"
        )


def get_optimized_prompt(
    base_prompt_key: str,
    session_id: str | None = None,
    user_name: str | None = None,
    user_role: str | None = None,
    available_tools: List[str] | None = None,
    recent_context: str | None = None,
    additional_params: Dict | None = None,
    tool_descriptions: Dict | None = None,
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
        tool_descriptions: Optional mapping of tool_name -> compressed description (Issue #5827)

    Returns:
        Combined prompt with static prefix + dynamic suffix
    """
    # Get static base prompt with includes rendered (will be cached by vLLM)
    base_prompt = get_prompt_manager().get(base_prompt_key)

    # Build dynamic context section (Issue #620: extracted helper)
    dynamic_context = _build_dynamic_context(
        session_id,
        user_name,
        user_role,
        available_tools,
        recent_context,
        additional_params,
        tool_descriptions,
    )

    # Combine: static prefix + dynamic suffix (CRITICAL for vLLM prefix caching)
    return f"{base_prompt}\n\n{dynamic_context}"


def list_available_prompts(filter_pattern: str | None = None) -> List[str]:
    """
    Convenience function to list available prompts.

    Args:
        filter_pattern: Optional regex pattern to filter keys

    Returns:
        List of matching prompt keys
    """
    return get_prompt_manager().list_prompts(filter_pattern)


def reload_prompts() -> None:
    """
    Convenience function to reload all prompts.
    """
    get_prompt_manager().reload()


# Issue #1327: Supported languages for prompt language injection.
# Canonical copy lives in personality_service.SUPPORTED_LANGUAGES;
# duplicated here to avoid circular-import issues at call time.
SUPPORTED_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "ru": "Russian",
    "it": "Italian",
    "nl": "Dutch",
    "hi": "Hindi",
}


def resolve_language(request_language=None):
    """Resolve response language from request, personality, or default.

    Issue #1327: Shared utility for all agents and handlers.
    Priority: request param > personality profile > 'en'.
    """
    if request_language:
        return request_language
    try:
        from services.personality_service import get_personality_manager

        profile = get_personality_manager().get_active_profile()
        if profile and profile.language_code:
            return profile.language_code
    except Exception:
        pass
    return "en"


def get_language_instruction(language_code):
    """Build a language instruction block for system prompts.

    Issue #1327: Returns empty string for English (default),
    so no noise is added when language is not explicitly set.
    """
    if not language_code or language_code == "en":
        return ""
    lang_name = SUPPORTED_LANGUAGES.get(language_code, language_code)
    return (
        f"\n\n**Language Requirement:** You MUST respond in "
        f"{lang_name} ({language_code}). "
        f"All your responses, explanations, and generated "
        f"content must be in {lang_name}."
    )
