# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoResearch Experiment Runner

Issue #2597: Execute training runs as isolated subprocesses with timeout
enforcement and structured result parsing.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Optional

from .config import AutoResearchConfig
from .models import Experiment, ExperimentResult, ExperimentState
from .parser import ExperimentOutputParser
from .store import ExperimentStore

logger = logging.getLogger(__name__)

# Allowlist pattern for extra hyperparameter keys — alphanumeric + underscore only
_EXTRA_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# Keys that cannot be overridden via hp.extra (already set explicitly)
_RESERVED_KEYS = frozenset(
    {
        "max_steps",
        "learning_rate",
        "batch_size",
        "block_size",
        "n_layer",
        "n_head",
        "n_embd",
        "dropout",
        "warmup_steps",
        "weight_decay",
    }
)


class ExperimentRunner:
    """Run autoresearch experiments as isolated subprocesses."""

    def __init__(
        self,
        config: Optional[AutoResearchConfig] = None,
        store: Optional[ExperimentStore] = None,
        parser: Optional[ExperimentOutputParser] = None,
    ):
        self.config = config or AutoResearchConfig()
        self.store = store or ExperimentStore(self.config)
        self.parser = parser or ExperimentOutputParser()
        self._running: bool = False
        self._lock = asyncio.Lock()
        self._current_process: Optional[asyncio.subprocess.Process] = None

    async def run_experiment(self, experiment: Experiment) -> Experiment:
        """Execute a single experiment and persist results.

        Args:
            experiment: Experiment with hypothesis and hyperparams set.

        Returns:
            Updated experiment with result and final state.
        """
        async with self._lock:
            if self._running:
                raise RuntimeError("An experiment is already running")
            self._running = True

        old_state = experiment.state
        experiment.state = ExperimentState.RUNNING
        experiment.started_at = time.time()
        await self.store.save_experiment(experiment, old_state=old_state)

        try:
            result = await self._execute_training(experiment)
            experiment.result = result
            experiment.completed_at = time.time()

            if result.success:
                experiment.state = ExperimentState.COMPLETED
                # _evaluate_result sets state to KEPT or DISCARDED
                await self._evaluate_result(experiment)
            else:
                experiment.state = ExperimentState.FAILED
                logger.warning(
                    "Experiment %s failed: %s",
                    experiment.id,
                    result.error_message,
                )
        except asyncio.CancelledError:
            experiment.state = ExperimentState.FAILED
            experiment.result = ExperimentResult(error_message="Experiment cancelled")
            experiment.completed_at = time.time()
            raise
        except Exception as exc:
            experiment.state = ExperimentState.FAILED
            experiment.result = ExperimentResult(error_message=str(exc))
            experiment.completed_at = time.time()
            logger.exception("Experiment %s raised exception", experiment.id)
        finally:
            self._running = False
            self._current_process = None
            # Single save with old_state=RUNNING → final state (no intermediate saves)
            await self.store.save_experiment(experiment, old_state=old_state)

        return experiment

    async def _execute_training(self, experiment: Experiment) -> ExperimentResult:
        """Spawn training subprocess and capture output."""
        cmd = self._build_command(experiment)
        logger.info(
            "Starting training for experiment %s: %s",
            experiment.id,
            " ".join(cmd),
        )

        start = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(self.config.autoresearch_dir),
            )
            self._current_process = process

            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=self.config.default_training_timeout,
            )
        except asyncio.TimeoutError:
            if self._current_process:
                self._current_process.kill()
                await self._current_process.wait()
            wall_time = time.monotonic() - start
            return ExperimentResult(
                error_message=(
                    f"Training timed out after "
                    f"{self.config.default_training_timeout}s"
                ),
                wall_time_seconds=wall_time,
            )

        wall_time = time.monotonic() - start
        output = stdout.decode("utf-8", errors="replace") if stdout else ""

        if process.returncode != 0:
            return ExperimentResult(
                error_message=f"Training exited with code {process.returncode}",
                raw_output=output,
                wall_time_seconds=wall_time,
            )

        return self.parser.parse(output, wall_time=wall_time)

    def _build_command(self, experiment: Experiment) -> list[str]:
        """Build the subprocess command for a training run."""
        hp = experiment.hyperparams
        self._validate_extra_params(hp.extra)
        cmd = [
            self.config.python_bin,
            str(self.config.train_script),
            f"--max_steps={hp.max_steps}",
            f"--learning_rate={hp.learning_rate}",
            f"--batch_size={hp.batch_size}",
            f"--block_size={hp.block_size}",
            f"--n_layer={hp.n_layer}",
            f"--n_head={hp.n_head}",
            f"--n_embd={hp.n_embd}",
            f"--dropout={hp.dropout}",
            f"--warmup_steps={hp.warmup_steps}",
            f"--weight_decay={hp.weight_decay}",
        ]
        for key, val in hp.extra.items():
            cmd.append(f"--{key}={val}")
        return cmd

    @staticmethod
    def _validate_extra_params(extra: dict) -> None:
        """Validate extra hyperparameter keys to prevent flag injection."""
        for key in extra:
            if key in _RESERVED_KEYS:
                raise ValueError(f"Extra param '{key}' conflicts with a built-in flag")
            if not _EXTRA_KEY_PATTERN.match(key):
                raise ValueError(
                    f"Invalid extra param key '{key}': "
                    "must be lowercase alphanumeric/underscore, 1-64 chars"
                )
        for key, val in extra.items():
            if not isinstance(val, (int, float, str, bool)):
                raise ValueError(
                    f"Extra param values must be scalar, got {type(val).__name__}"
                )
            if isinstance(val, str) and (len(val) > 256 or "--" in val):
                raise ValueError(
                    f"Extra param '{key}': string values must be ≤256 chars "
                    "and cannot contain '--'"
                )

    async def _evaluate_result(self, experiment: Experiment) -> None:
        """Decide whether to keep or discard based on improvement threshold."""
        if experiment.result is None or experiment.result.val_bpb is None:
            return

        baseline = await self.store.get_baseline()
        if baseline is None:
            # First experiment becomes baseline
            await self.store.set_baseline(experiment.result.val_bpb)
            experiment.baseline_val_bpb = experiment.result.val_bpb
            experiment.state = ExperimentState.KEPT
            logger.info(
                "First experiment — baseline set to %.4f",
                experiment.result.val_bpb,
            )
            return

        experiment.baseline_val_bpb = baseline
        improvement = baseline - experiment.result.val_bpb

        if improvement >= self.config.improvement_threshold:
            experiment.state = ExperimentState.KEPT
            await self.store.set_baseline(experiment.result.val_bpb)
            logger.info(
                "Experiment %s KEPT — val_bpb improved by %.4f (%.2f%%)",
                experiment.id,
                improvement,
                (improvement / baseline) * 100,
            )
        else:
            experiment.state = ExperimentState.DISCARDED
            logger.info(
                "Experiment %s DISCARDED — improvement %.4f below threshold %.4f",
                experiment.id,
                improvement,
                self.config.improvement_threshold,
            )

    async def cancel(self) -> None:
        """Cancel the currently running experiment."""
        if self._current_process and self._current_process.returncode is None:
            self._current_process.kill()
            logger.info("Cancelled running experiment")

    @property
    def is_running(self) -> bool:
        return self._running
