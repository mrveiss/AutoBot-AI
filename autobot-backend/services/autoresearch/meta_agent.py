# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoResearch Meta-Agent

Issue #3224: Self-referential agent that generates code-level improvements
to a target Python module, guided by prior-generation eval results stored
in the quality-diversity archive.

Architecture:
  MetaAgent.generate_patch()
      │
      ├─ _validate_target()     ─► path safety checks
      ├─ _build_prompt()        ─► module content + archive context
      ├─ _call_llm()            ─► full modified module content from LLM
      └─ MetaPatch              ─► original + modified content + rationale

Safety constraints:
  - target_module_path must be an absolute path
  - target must have a .py extension and must not be a test file
  - module line count must be within meta_agent_max_module_lines
  - LLM output is treated as candidate code only — MetaEvalHarness
    validates and gates via tests + ApprovalGate before any live apply
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

from .config import AutoResearchConfig

logger = get_logger(__name__)


@dataclass
class MetaPatch:
    """Proposed code improvement produced by the MetaAgent."""

    patch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    target_path: str = ""  # absolute path to the target module
    original_content: str = ""
    modified_content: str = ""
    rationale: str = ""  # LLM summary of what was changed and why
    generation: int = 0
    parent_id: str | None = None
    created_at: float = field(default_factory=time.time)

    @property
    def has_changes(self) -> bool:
        """True when the LLM produced a meaningful modification."""
        return self.original_content.strip() != self.modified_content.strip()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "target_path": self.target_path,
            "original_content": self.original_content,
            "modified_content": self.modified_content,
            "has_changes": self.has_changes,
            "rationale": self.rationale,
            "generation": self.generation,
            "parent_id": self.parent_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetaPatch":
        """Reconstruct a MetaPatch from its serialised form (for Archive replay)."""
        return cls(
            patch_id=data["patch_id"],
            target_path=data.get("target_path", ""),
            original_content=data.get("original_content", ""),
            modified_content=data.get("modified_content", ""),
            rationale=data.get("rationale", ""),
            generation=data.get("generation", 0),
            parent_id=data.get("parent_id"),
            created_at=data.get("created_at", 0.0),
        )


class MetaAgent:
    """Generates code-level improvement patches for a target module.

    The agent reads the current module source, optionally reads prior
    generation eval context from the archive, and asks an LLM to produce
    an improved version of the file.  The result is a MetaPatch that can
    be validated and gated by MetaEvalHarness before any live application.
    """

    _SYSTEM_PROMPT = (
        "You are an expert software engineer specialising in improving Python code.\n"
        "You will receive a Python module and optional context about prior versions.\n\n"
        "Your task: return an improved version of the module.\n\n"
        "Rules:\n"
        "1. Return ONLY the complete modified Python file — no markdown fences, "
        "no explanations outside the file.\n"
        "2. Preserve all public function/class signatures exactly.\n"
        "3. Make minimal, focused changes — do not rewrite unnecessarily.\n"
        "4. You may add helper functions but must not remove existing public ones.\n"
        "5. Begin the file with a one-line comment: "
        "# RATIONALE: <brief summary of what you changed and why>\n"
    )

    def __init__(
        self,
        config: AutoResearchConfig | None = None,
        llm_service: Any = None,
    ) -> None:
        self.config = config or AutoResearchConfig()
        self._llm = llm_service

    async def generate_patch(
        self,
        target_module_path: Path,
        eval_context: List[Dict[str, Any]],
        generation: int,
        parent_id: str | None = None,
    ) -> MetaPatch:
        """Generate a code improvement patch for *target_module_path*.

        Args:
            target_module_path: Absolute path to the Python module to improve.
            eval_context: List of prior-generation result dicts from the archive
                          (score, rationale, etc.) for context.
            generation: Current generation index.
            parent_id: Archive entry ID of the parent generation, or None.

        Returns:
            A MetaPatch with original and proposed modified content.
        """
        self._validate_target(target_module_path)
        # #7467: was sync `target_module_path.read_text` blocking the event loop.
        original_content = await asyncio.to_thread(target_module_path.read_text, encoding="utf-8")
        self._validate_size(original_content, target_module_path)

        prompt = self._build_prompt(original_content, eval_context)
        logger.info(
            "MetaAgent: generating patch for %s (gen=%d)",
            target_module_path.name,
            generation,
        )
        modified_content = await self._call_llm(prompt)
        rationale = self._extract_rationale(modified_content)

        patch = MetaPatch(
            target_path=str(target_module_path),
            original_content=original_content,
            modified_content=modified_content,
            rationale=rationale,
            generation=generation,
            parent_id=parent_id,
        )
        if not patch.has_changes:
            logger.info("MetaAgent: LLM produced no changes for %s", target_module_path.name)
        else:
            logger.info(
                "MetaAgent: patch %s has changes (gen=%d, parent=%s)",
                patch.patch_id,
                generation,
                parent_id,
            )
        return patch

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_target(self, path: Path) -> None:
        """Raise ValueError for unsafe or disallowed targets."""
        if not path.is_absolute():
            raise ValueError(f"target_module_path must be absolute, got: {path}")
        if path.suffix != ".py":
            raise ValueError(f"target_module_path must be a .py file, got: {path.suffix}")
        stem = path.stem.lower()
        if stem.startswith("test_") or stem.endswith("_test"):
            raise ValueError(f"meta-agent must not target test files: {path.name}")
        if not path.exists():
            raise FileNotFoundError(f"Target module not found: {path}")

    def _validate_size(self, content: str, path: Path) -> None:
        """Raise ValueError if the module exceeds the configured line limit."""
        line_count = content.count("\n")
        limit = self.config.meta_agent_max_module_lines
        if line_count > limit:
            raise ValueError(f"{path.name} has {line_count} lines, exceeds limit of {limit}")

    def _build_prompt(self, original_content: str, eval_context: List[Dict[str, Any]]) -> str:
        """Compose the user prompt from module content and archive context."""
        parts = [
            "Here is the Python module to improve:\n\n```python\n",
            original_content,
            "\n```\n",
        ]
        if eval_context:
            parts.append("\nContext from prior generations (best → worst score):\n")
            for entry in eval_context[:5]:  # cap at 5 entries
                score = entry.get("score", "?")
                rationale = entry.get("rationale", "no rationale")
                parts.append(f"- score={score}: {rationale}\n")
        parts.append("\nReturn the improved module now.")
        return "".join(parts)

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM with the improvement prompt and return the response."""
        if self._llm is None:
            raise RuntimeError("MetaAgent: no LLM service configured")
        response = await self._llm.chat(
            messages=[
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=4000,
            model=self.config.meta_agent_llm_model,
        )
        return response.content.strip()

    @staticmethod
    def _extract_rationale(modified_content: str) -> str:
        """Pull the rationale comment from the first line of the LLM output."""
        first_line = modified_content.splitlines()[0] if modified_content else ""
        if first_line.startswith("# RATIONALE:"):
            return first_line[len("# RATIONALE:") :].strip()
        return "no rationale provided"
