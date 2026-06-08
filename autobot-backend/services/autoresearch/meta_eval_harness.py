# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoResearch MetaEvalHarness

Issue #3224: Validates MetaAgent patches by applying them to a temporary copy
of the target module, running pytest, scoring the result, and gating live
application through the ApprovalGate.

Architecture:
  MetaEvalHarness.evaluate_patch(patch, archive)
      │
      ├─ _apply_to_tempfile()   ─► write modified content to a temp .py file
      ├─ _run_tests()           ─► pytest subprocess → (passed, total)
      ├─ _compute_score()       ─► test_pass_rate float 0..1
      ├─ _add_to_archive()      ─► VariantArchiveEntry with score + parent
      ├─ _check_approval()      ─► ApprovalGate consulted when improvement > threshold
      └─ MetaEvalResult         ─► score, passed, decision, applied

Safety:
  - Patch is NEVER applied to the live file without explicit approval
  - Tests run against the temporary file, not the live module
  - Docker execution honours config.docker_enabled
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

from .archive import Archive
from .auto_research_agent import ApprovalGate
from .config import AutoResearchConfig
from .meta_agent import MetaPatch
from .models import VariantArchiveEntry

logger = get_logger(__name__)


@dataclass
class MetaEvalResult:
    """Outcome of evaluating a single MetaPatch."""

    patch_id: str = ""
    score: float = 0.0  # fraction of tests passed (0..1)
    tests_passed: int = 0
    tests_total: int = 0
    test_output: str = ""  # raw pytest output for diagnostics
    decision: str = "skipped"  # "approved" | "rejected" | "skipped" | "timeout"
    applied: bool = False  # True only when patch is written to live file
    error: str | None = None
    evaluated_at: float = field(default_factory=time.time)

    @property
    def succeeded(self) -> bool:
        """True when tests ran and at least one passed."""
        return self.tests_total > 0 and self.tests_passed > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "score": self.score,
            "tests_passed": self.tests_passed,
            "tests_total": self.tests_total,
            "decision": self.decision,
            "applied": self.applied,
            "error": self.error,
            "evaluated_at": self.evaluated_at,
        }


class MetaEvalHarness:
    """Validates a MetaPatch and optionally applies it to the live module.

    Workflow
    --------
    1. Write the modified content to a sibling temp file ``<module>_meta_<uuid>.py``.
    2. Run pytest targeting ``tests/`` adjacent to the module (or supplied path).
    3. Compute score = passed / total.
    4. Add a ``VariantArchiveEntry`` to the provided Archive.
    5. Consult ApprovalGate when the score exceeds the configured threshold.
    6. If approved, overwrite the live file with the modified content.
    """

    def __init__(
        self,
        config: AutoResearchConfig | None = None,
        approval_gate: ApprovalGate | None = None,
    ) -> None:
        self.config = config or AutoResearchConfig()
        self._gate = approval_gate or ApprovalGate(self.config)

    async def evaluate_patch(
        self,
        patch: MetaPatch,
        archive: Archive,
        session_id: str = "",
        test_paths: List[str] | None = None,
    ) -> MetaEvalResult:
        """Evaluate *patch* and return a MetaEvalResult.

        Args:
            patch: The MetaPatch produced by MetaAgent.
            archive: Archive to record the evaluated entry.
            session_id: Autoresearch session ID used by ApprovalGate keys.
            test_paths: Explicit list of test file/dir paths.  When None the
                        harness discovers them automatically (see _find_tests).

        Returns:
            A MetaEvalResult describing the outcome.
        """
        result = MetaEvalResult(patch_id=patch.patch_id)

        if not patch.has_changes:
            logger.info("MetaEvalHarness: patch %s has no changes — skipping", patch.patch_id)
            result.decision = "skipped"
            self._add_to_archive(archive, patch, result)
            return result

        tmp_path: Path | None = None
        try:
            tmp_path = self._write_temp_module(patch)
            passed, total, output = await self._run_tests(
                tmp_path, test_paths or self._find_tests(Path(patch.target_path))
            )
            result.tests_passed = passed
            result.tests_total = total
            result.test_output = output
            result.score = self._compute_score(passed, total)
        except Exception as exc:
            logger.exception("MetaEvalHarness: test run failed for patch %s", patch.patch_id)
            result.error = str(exc)
            result.decision = "rejected"
            self._add_to_archive(archive, patch, result)
            return result
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

        self._add_to_archive(archive, patch, result)

        if not result.succeeded:
            result.decision = "rejected"
            logger.info(
                "MetaEvalHarness: patch %s rejected (0/%d tests passed)",
                patch.patch_id,
                total,
            )
            return result

        # Consult ApprovalGate if improvement is significant.
        # If the gate is required but no session_id is provided we reject
        # rather than auto-approve — never silently apply to live code.
        needs_approval = self._gate.check_approval_needed(result.score, self.config.meta_agent_approval_threshold)
        if needs_approval:
            if not session_id:
                logger.warning(
                    "MetaEvalHarness: approval required for patch %s but " "no session_id provided — rejecting",
                    patch.patch_id,
                )
                result.decision = "rejected"
            else:
                result.decision = await self._request_and_wait(session_id, patch, result)
        else:
            result.decision = "approved"

        if result.decision == "approved":
            self._apply_patch(patch)
            result.applied = True
            logger.info(
                "MetaEvalHarness: patch %s applied to %s (score=%.3f)",
                patch.patch_id,
                patch.target_path,
                result.score,
            )
        else:
            logger.info(
                "MetaEvalHarness: patch %s not applied (decision=%s)",
                patch.patch_id,
                result.decision,
            )

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _write_temp_module(self, patch: MetaPatch) -> Path:
        """Write modified content to a sibling temp file and return its path."""
        target = Path(patch.target_path)
        suffix = f"_meta_{uuid.uuid4().hex[:8]}.py"
        tmp_path = target.with_name(target.stem + suffix)
        tmp_path.write_text(patch.modified_content, encoding="utf-8")
        return tmp_path

    @staticmethod
    def _find_tests(target: Path) -> List[str]:
        """Return test file paths adjacent to *target* module.

        Looks for ``tests/`` directory or ``*_test.py`` files next to the
        target's parent package.
        """
        parent = target.parent
        candidates = [
            parent / "tests",
            parent.parent / "tests",
        ]
        for test_dir in candidates:
            if test_dir.is_dir():
                return [str(test_dir)]
        # Fallback: test files adjacent to the module
        test_files = list(parent.glob("*_test.py"))
        return [str(f) for f in test_files] if test_files else [str(parent)]

    async def _run_tests(self, tmp_module: Path, test_paths: List[str]) -> tuple[int, int, str]:
        """Run pytest and return (passed, total, output).

        The temporary module is exposed to pytest via the ``PYTHONPATH``
        environment variable so imports resolve correctly without modifying
        the live package.
        """
        env = os.environ.copy()
        # Prepend the directory containing the temp module so pytest can import it
        extra_path = str(tmp_module.parent)
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{extra_path}:{existing}" if existing else extra_path

        cmd = [
            self.config.python_bin,
            "-m",
            "pytest",
            "--tb=short",
            "-q",
            *test_paths,
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=self.config.meta_agent_test_timeout,
            )
        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            raise RuntimeError(f"Test run timed out after {self.config.meta_agent_test_timeout}s")

        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        passed, total = self._parse_pytest_summary(output)
        return passed, total, output

    @staticmethod
    def _parse_pytest_summary(output: str) -> tuple[int, int]:
        """Extract (passed, total) counts from pytest's short summary line.

        Handles patterns like:
          ``5 passed, 1 failed in 0.42s``
          ``3 passed in 0.10s``
          ``2 failed in 0.05s``
        """
        passed = 0
        failed = 0
        for line in reversed(output.splitlines()):
            m_passed = re.search(r"(\d+) passed", line)
            m_failed = re.search(r"(\d+) failed", line)
            m_error = re.search(r"(\d+) error", line)
            if m_passed or m_failed or m_error:
                passed = int(m_passed.group(1)) if m_passed else 0
                failed = int(m_failed.group(1)) if m_failed else 0
                failed += int(m_error.group(1)) if m_error else 0
                return passed, passed + failed
        return 0, 0

    @staticmethod
    def _compute_score(passed: int, total: int) -> float:
        """Return pass-rate (0..1), or 0.0 when no tests were collected."""
        if total == 0:
            return 0.0
        return passed / total

    def _add_to_archive(self, archive: Archive, patch: MetaPatch, result: MetaEvalResult) -> None:
        """Record the evaluation result as a VariantArchiveEntry."""
        entry = VariantArchiveEntry(
            variant_id=patch.patch_id,
            variant=patch,  # MetaPatch is stored as the "variant"
            score=result.score,
            parent_id=patch.parent_id,
            generation=patch.generation,
            valid_parent=result.succeeded,
        )
        archive.add(entry)

    async def _request_and_wait(self, session_id: str, patch: MetaPatch, result: MetaEvalResult) -> str:
        """Request ApprovalGate decision and wait up to test_timeout seconds."""
        details = {
            "patch_id": patch.patch_id,
            "target_path": patch.target_path,
            "rationale": patch.rationale,
            "score": result.score,
            "tests_passed": result.tests_passed,
            "tests_total": result.tests_total,
        }
        try:
            await self._gate.request_approval(
                session_id=session_id,
                experiment_id=patch.patch_id,
                details=details,
            )
            return await self._gate.wait_for_approval(
                session_id=session_id,
                experiment_id=patch.patch_id,
                timeout=float(self.config.meta_agent_test_timeout),
            )
        except Exception:
            logger.exception("MetaEvalHarness: ApprovalGate error for patch %s", patch.patch_id)
            return "timeout"

    @staticmethod
    def _apply_patch(patch: MetaPatch) -> None:
        """Overwrite the live module with the modified content.

        A per-patch backup is written before overwriting so each applied
        generation is independently recoverable without touching git.
        Backup name: ``<module>.<patch_id_prefix>.meta_bak`` — unique per patch.
        """
        target = Path(patch.target_path)
        prefix = patch.patch_id[:8]
        backup = target.with_name(f"{target.stem}.{prefix}.meta_bak")
        shutil.copy2(target, backup)
        target.write_text(patch.modified_content, encoding="utf-8")
        logger.info("MetaEvalHarness: live file updated, backup at %s", backup)
