# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoResearch Output Parser

Issue #2597: Parse training output to extract val_bpb and other metrics.

Autoresearch (Karpathy) outputs lines like:
  step 5000 | train loss 4.0191 | val loss 4.0540 | val_bpb 5.846
  tokens/sec: 12345.67
"""

from __future__ import annotations

import re

from autobot_shared.logging_manager import get_logger

from .models import ExperimentResult

logger = get_logger(__name__)

# Regex patterns for autoresearch output
_STEP_PATTERN = re.compile(
    r"step\s+(\d+)\s*\|\s*" r"train loss\s+([\d.]+)\s*\|\s*" r"val loss\s+([\d.]+)\s*\|\s*" r"val_bpb\s+([\d.]+)"
)
_TOKENS_PATTERN = re.compile(r"tokens/sec:\s*([\d.]+)")
_ERROR_PATTERN = re.compile(r"(?:Error|Exception|Traceback|CUDA out of memory)", re.I)


class ExperimentOutputParser:
    """Parse autoresearch training output into structured metrics."""

    def parse(self, output: str, wall_time: float = 0.0) -> ExperimentResult:
        """Parse raw training output and return structured result.

        Args:
            output: Raw stdout/stderr from training subprocess.
            wall_time: Elapsed wall-clock time in seconds.

        Returns:
            ExperimentResult with extracted metrics.
        """
        result = ExperimentResult(raw_output=output, wall_time_seconds=wall_time)

        if not output.strip():
            result.error_message = "Empty training output"
            return result

        error = self._detect_error(output)
        if error:
            result.error_message = error

        last_step = self._parse_last_step(output)
        if last_step:
            result.steps_completed = last_step["step"]
            result.train_loss = last_step["train_loss"]
            result.val_loss = last_step["val_loss"]
            result.val_bpb = last_step["val_bpb"]

        tps = self._parse_tokens_per_second(output)
        if tps is not None:
            result.tokens_per_second = tps

        return result

    def _parse_last_step(self, output: str) -> dict | None:
        """Extract metrics from the last step line in output."""
        matches = _STEP_PATTERN.findall(output)
        if not matches:
            return None
        last = matches[-1]
        return {
            "step": int(last[0]),
            "train_loss": float(last[1]),
            "val_loss": float(last[2]),
            "val_bpb": float(last[3]),
        }

    def _parse_tokens_per_second(self, output: str) -> float | None:
        """Extract tokens/sec throughput."""
        match = _TOKENS_PATTERN.search(output)
        if match:
            return float(match.group(1))
        return None

    def _detect_error(self, output: str) -> str | None:
        """Detect error patterns in output."""
        for line in output.splitlines():
            if _ERROR_PATTERN.search(line):
                return line.strip()
        return None
