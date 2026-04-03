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
import json
import logging
import re
import tempfile
import time
from pathlib import Path
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


_ENV_PARAM_MAP = {
    "max_steps": "AUTOBOT_EXP_MAX_STEPS",
    "learning_rate": "AUTOBOT_EXP_LEARNING_RATE",
    "batch_size": "AUTOBOT_EXP_BATCH_SIZE",
    "block_size": "AUTOBOT_EXP_BLOCK_SIZE",
    "n_layer": "AUTOBOT_EXP_N_LAYER",
    "n_head": "AUTOBOT_EXP_N_HEAD",
    "n_embd": "AUTOBOT_EXP_N_EMBD",
    "dropout": "AUTOBOT_EXP_DROPOUT",
    "warmup_steps": "AUTOBOT_EXP_WARMUP_STEPS",
    "weight_decay": "AUTOBOT_EXP_WEIGHT_DECAY",
}


class ExperimentRunner:
    """Run autoresearch experiments as isolated subprocesses or Docker containers."""

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
        self._current_container_name: Optional[str] = None

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
        """Spawn training subprocess or Docker container and capture output."""
        if self.config.docker_enabled:
            return await self._execute_in_docker(experiment)
        return await self._execute_subprocess(experiment)

    async def _execute_subprocess(self, experiment: Experiment) -> ExperimentResult:
        """Execute training as a bare subprocess (original behaviour)."""
        cmd = self._build_command(experiment)
        logger.info(
            "Starting training for experiment %s (subprocess): %s",
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

    async def _execute_in_docker(self, experiment: Experiment) -> ExperimentResult:
        """Execute training inside an isolated Docker container."""
        self._current_container_name = f"autobot_exp_{experiment.id}"
        with tempfile.TemporaryDirectory(prefix="autobot_exp_") as output_dir:
            cmd = self._build_docker_command(experiment, Path(output_dir))
            logger.info(
                "Starting training for experiment %s (docker): %s",
                experiment.id,
                " ".join(cmd),
            )
            start = time.monotonic()
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                self._current_process = process

                stdout, _ = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.config.docker_timeout,
                )
            except asyncio.TimeoutError:
                wall_time = time.monotonic() - start
                return await self._handle_docker_timeout(wall_time)

            wall_time = time.monotonic() - start
            container_log = stdout.decode("utf-8", errors="replace") if stdout else ""

            if process.returncode != 0:
                return ExperimentResult(
                    error_message=(
                        f"Docker container exited with code {process.returncode}"
                    ),
                    raw_output=container_log,
                    wall_time_seconds=wall_time,
                )

            return self._parse_docker_output(Path(output_dir), wall_time)

    def _build_docker_command(
        self, experiment: Experiment, output_dir: Path
    ) -> list[str]:
        """Build the docker run command for a containerised experiment."""
        hp = experiment.hyperparams
        self._validate_extra_params(hp.extra)
        self._validate_mount_path(Path(self.config.autoresearch_dir))
        env_flags = self._build_docker_env_flags(hp)
        container_name = self._current_container_name or f"autobot_exp_{experiment.id}"

        cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "none",
            "--memory",
            self.config.docker_memory_limit,
            "--cpus",
            str(self.config.docker_cpu_limit),
            "-v",
            f"{self.config.autoresearch_dir}:/experiment:ro",
            "-v",
            f"{output_dir}:/output",
        ]
        cmd.extend(env_flags)
        cmd.append(self.config.docker_image)
        return cmd

    @staticmethod
    def _validate_mount_path(path: Path) -> None:
        """Reject obviously unsafe mount paths (root or non-absolute)."""
        resolved = path.resolve()
        if not resolved.is_absolute() or resolved == Path("/"):
            raise ValueError(
                f"autoresearch_dir is unsafe to mount: {path}"
            )

    @staticmethod
    def _build_docker_env_flags(hp: object) -> list[str]:
        """Return --env flags mapping hyperparams to AUTOBOT_EXP_* variables."""
        flags: list[str] = []
        for attr, env_key in _ENV_PARAM_MAP.items():
            value = getattr(hp, attr)
            flags.extend(["--env", f"{env_key}={value}"])
        for extra_key, extra_val in hp.extra.items():
            env_key = f"AUTOBOT_EXP_EXTRA_{extra_key.upper()}"
            flags.extend(["--env", f"{env_key}={extra_val}"])
        return flags

    async def _handle_docker_timeout(self, wall_time: float) -> ExperimentResult:
        """Kill the container after a timeout and return a timeout result."""
        if self._current_process and self._current_process.returncode is None:
            if self._current_container_name:
                try:
                    kill_proc = await asyncio.create_subprocess_exec(
                        "docker", "kill", self._current_container_name
                    )
                    await kill_proc.wait()
                except Exception:
                    logger.exception(
                        "Failed to docker kill container %s after timeout",
                        self._current_container_name,
                    )
            self._current_process.kill()
            await self._current_process.wait()

        return ExperimentResult(
            error_message=(
                f"Docker experiment timed out after {self.config.docker_timeout}s"
            ),
            wall_time_seconds=wall_time,
        )

    def _parse_docker_output(
        self, output_dir: Path, wall_time: float
    ) -> ExperimentResult:
        """Read result.json from the container output mount and parse it."""
        result_path = output_dir / "result.json"
        if not result_path.exists():
            return ExperimentResult(
                error_message="Container produced no result.json",
                wall_time_seconds=wall_time,
            )

        with result_path.open(encoding="utf-8") as fh:
            payload = json.load(fh)

        stdout_text = payload.get("stdout", "")
        returncode = payload.get("returncode", -1)

        if returncode != 0:
            stderr_text = payload.get("stderr", "")
            return ExperimentResult(
                error_message=f"Training exited with code {returncode}",
                raw_output=stdout_text + stderr_text,
                wall_time_seconds=wall_time,
            )

        return self.parser.parse(stdout_text, wall_time=wall_time)

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
