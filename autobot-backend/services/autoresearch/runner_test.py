# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
ExperimentRunner Unit Tests

Issue #2637: Comprehensive tests for subprocess execution, timeout handling,
cancellation, concurrent run rejection, evaluation logic, and parameter
validation.
Issue #3261: Tests for append_result, reorg_results, filter_prompts.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.logging_manager import get_logger
from services.autoresearch.config import AutoResearchConfig
from services.autoresearch.models import (
    Experiment,
    ExperimentResult,
    ExperimentState,
    HyperParams,
    ScorerResult,
)
from services.autoresearch.runner import (
    _EXTRA_KEY_PATTERN,
    _RESERVED_KEYS,
    ExperimentRunner,
    append_result,
    filter_prompts,
    reorg_results,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> AutoResearchConfig:
    """Build a test config with sensible defaults."""
    defaults = {
        "default_training_timeout": 10,
        "improvement_threshold": 0.01,
    }
    defaults.update(overrides)
    return AutoResearchConfig(**defaults)


def _make_store() -> AsyncMock:
    """Build a mock ExperimentStore."""
    store = AsyncMock()
    store.save_experiment = AsyncMock()
    store.get_baseline = AsyncMock(return_value=None)
    store.set_baseline = AsyncMock()
    return store


def _make_parser(result: ExperimentResult | None = None) -> MagicMock:
    """Build a mock parser returning a predetermined result."""
    parser = MagicMock()
    if result is None:
        result = ExperimentResult(val_bpb=5.5, steps_completed=5000)
    parser.parse.return_value = result
    return parser


def _make_runner(
    config: AutoResearchConfig | None = None,
    store: AsyncMock | None = None,
    parser: MagicMock | None = None,
) -> ExperimentRunner:
    """Build an ExperimentRunner with all I/O mocked."""
    return ExperimentRunner(
        config=config or _make_config(),
        store=store or _make_store(),
        parser=parser or _make_parser(),
    )


def _make_experiment(**overrides) -> Experiment:
    """Build a test Experiment."""
    defaults = {
        "hypothesis": "test hypothesis",
        "state": ExperimentState.PENDING,
    }
    defaults.update(overrides)
    return Experiment(**defaults)


# ---------------------------------------------------------------------------
# _validate_extra_params tests
# ---------------------------------------------------------------------------


class TestValidateExtraParams:
    """Tests for ExperimentRunner._validate_extra_params."""

    def test_valid_params_accepted(self) -> None:
        ExperimentRunner._validate_extra_params({"custom_lr": 0.001, "warmup_ratio": 0.1})

    def test_reserved_key_rejected(self) -> None:
        for key in ("max_steps", "learning_rate", "batch_size"):
            with pytest.raises(ValueError, match="conflicts with a built-in flag"):
                ExperimentRunner._validate_extra_params({key: 42})

    def test_uppercase_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be lowercase"):
            ExperimentRunner._validate_extra_params({"BadKey": 1})

    def test_key_starting_with_digit_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be lowercase"):
            ExperimentRunner._validate_extra_params({"1bad": 1})

    def test_key_with_dash_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be lowercase"):
            ExperimentRunner._validate_extra_params({"bad-key": 1})

    def test_key_too_long_rejected(self) -> None:
        long_key = "a" * 65
        with pytest.raises(ValueError, match="must be lowercase"):
            ExperimentRunner._validate_extra_params({long_key: 1})

    def test_non_scalar_value_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be scalar"):
            ExperimentRunner._validate_extra_params({"key": [1, 2, 3]})

    def test_dict_value_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be scalar"):
            ExperimentRunner._validate_extra_params({"key": {"nested": True}})

    def test_string_with_double_dash_rejected(self) -> None:
        with pytest.raises(ValueError, match="cannot contain '--'"):
            ExperimentRunner._validate_extra_params({"key": "--inject"})

    def test_string_too_long_rejected(self) -> None:
        with pytest.raises(ValueError, match="256 chars"):
            ExperimentRunner._validate_extra_params({"key": "x" * 257})

    def test_bool_value_accepted(self) -> None:
        ExperimentRunner._validate_extra_params({"use_flash": True})

    def test_int_value_accepted(self) -> None:
        ExperimentRunner._validate_extra_params({"seed": 42})

    def test_empty_dict_accepted(self) -> None:
        ExperimentRunner._validate_extra_params({})

    def test_all_reserved_keys_are_lowercase(self) -> None:
        """Sanity check: all reserved keys match the key pattern format."""
        for key in _RESERVED_KEYS:
            assert _EXTRA_KEY_PATTERN.match(key), f"Reserved key '{key}' doesn't match pattern"


# ---------------------------------------------------------------------------
# _build_command tests
# ---------------------------------------------------------------------------


class TestBuildCommand:
    """Tests for ExperimentRunner._build_command."""

    def test_basic_command_structure(self) -> None:
        runner = _make_runner()
        exp = _make_experiment()
        cmd = runner._build_command(exp)

        assert cmd[0] == runner.config.python_bin
        assert str(runner.config.train_script) in cmd[1]
        assert any("--max_steps=" in arg for arg in cmd)
        assert any("--learning_rate=" in arg for arg in cmd)

    def test_extra_params_appended(self) -> None:
        runner = _make_runner()
        exp = _make_experiment(hyperparams=HyperParams(extra={"seed": 42, "use_flash": True}))
        cmd = runner._build_command(exp)

        assert "--seed=42" in cmd
        assert "--use_flash=True" in cmd

    def test_custom_python_executable(self) -> None:
        config = _make_config()
        config.python_executable = "/usr/bin/python3.12"
        runner = _make_runner(config=config)
        exp = _make_experiment()
        cmd = runner._build_command(exp)

        assert cmd[0] == "/usr/bin/python3.12"

    def test_all_hyperparams_included(self) -> None:
        runner = _make_runner()
        hp = HyperParams()
        exp = _make_experiment(hyperparams=hp)
        cmd = runner._build_command(exp)

        expected_flags = [
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
        ]
        for flag in expected_flags:
            assert any(f"--{flag}=" in arg for arg in cmd), f"Missing --{flag} in command"


# ---------------------------------------------------------------------------
# _execute_training tests (subprocess mocking)
# ---------------------------------------------------------------------------


class TestExecuteTraining:
    """Tests for ExperimentRunner._execute_training with mocked subprocess."""

    @pytest.mark.asyncio
    async def test_successful_training(self) -> None:
        expected_result = ExperimentResult(val_bpb=5.5, steps_completed=5000)
        parser = _make_parser(result=expected_result)
        runner = _make_runner(parser=parser)
        exp = _make_experiment()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(
                b"step 5000 | train loss 4.0 | val loss 4.1 | val_bpb 5.5\n",
                None,
            )
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner._execute_training(exp)

        assert result.val_bpb == 5.5
        parser.parse.assert_called_once()

    @pytest.mark.asyncio
    async def test_nonzero_exit_code(self) -> None:
        runner = _make_runner()
        exp = _make_experiment()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"segfault", None))
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner._execute_training(exp)

        assert not result.success
        assert "exited with code 1" in result.error_message
        assert result.raw_output == "segfault"

    @pytest.mark.asyncio
    async def test_timeout_kills_process(self) -> None:
        config = _make_config(default_training_timeout=1)
        runner = _make_runner(config=config)
        exp = _make_experiment()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_process.kill = AsyncMock()
        mock_process.wait = AsyncMock()
        mock_process.returncode = None

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            runner._current_process = mock_process
            result = await runner._execute_training(exp)

        assert not result.success
        assert "timed out" in result.error_message
        mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_stdout_handled(self) -> None:
        parser = _make_parser(result=ExperimentResult(error_message="Empty training output"))
        runner = _make_runner(parser=parser)
        exp = _make_experiment()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", None))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            await runner._execute_training(exp)

        # Parser called with empty string
        parser.parse.assert_called_once()
        call_args = parser.parse.call_args
        assert call_args[0][0] == ""

    @pytest.mark.asyncio
    async def test_none_stdout_handled(self) -> None:
        parser = _make_parser(result=ExperimentResult(error_message="Empty training output"))
        runner = _make_runner(parser=parser)
        exp = _make_experiment()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(None, None))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            await runner._execute_training(exp)

        parser.parse.assert_called_once()
        call_args = parser.parse.call_args
        assert call_args[0][0] == ""


# ---------------------------------------------------------------------------
# run_experiment tests (full flow)
# ---------------------------------------------------------------------------


class TestRunExperiment:
    """Tests for ExperimentRunner.run_experiment end-to-end flow."""

    @pytest.mark.asyncio
    async def test_successful_run_sets_completed(self) -> None:
        store = _make_store()
        result = ExperimentResult(val_bpb=5.5, steps_completed=5000)
        parser = _make_parser(result=result)
        runner = _make_runner(store=store, parser=parser)
        exp = _make_experiment()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"ok", None))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            updated = await runner.run_experiment(exp)

        assert updated.result is not None
        assert updated.result.val_bpb == 5.5
        assert updated.started_at is not None
        assert updated.completed_at is not None
        # Store should be called twice: once for RUNNING, once for final state
        assert store.save_experiment.call_count == 2

    @pytest.mark.asyncio
    async def test_failed_run_sets_failed_state(self) -> None:
        store = _make_store()
        runner = _make_runner(store=store)
        exp = _make_experiment()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"error", None))
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            updated = await runner.run_experiment(exp)

        assert updated.state == ExperimentState.FAILED
        assert updated.result.error_message is not None

    @pytest.mark.asyncio
    async def test_exception_during_training_sets_failed(self) -> None:
        store = _make_store()
        runner = _make_runner(store=store)
        exp = _make_experiment()

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=OSError("No such file"),
        ):
            updated = await runner.run_experiment(exp)

        assert updated.state == ExperimentState.FAILED
        assert "No such file" in updated.result.error_message

    @pytest.mark.asyncio
    async def test_running_flag_cleared_after_completion(self) -> None:
        store = _make_store()
        result = ExperimentResult(val_bpb=5.5)
        runner = _make_runner(store=store, parser=_make_parser(result=result))
        exp = _make_experiment()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"ok", None))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            await runner.run_experiment(exp)

        assert runner.is_running is False
        assert runner._current_process is None

    @pytest.mark.asyncio
    async def test_running_flag_cleared_after_failure(self) -> None:
        store = _make_store()
        runner = _make_runner(store=store)
        exp = _make_experiment()

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=RuntimeError("boom"),
        ):
            await runner.run_experiment(exp)

        assert runner.is_running is False

    @pytest.mark.asyncio
    async def test_concurrent_run_rejected(self) -> None:
        store = _make_store()
        runner = _make_runner(store=store)
        # Simulate already running
        runner._running = True

        exp = _make_experiment()
        with pytest.raises(RuntimeError, match="already running"):
            await runner.run_experiment(exp)

    @pytest.mark.asyncio
    async def test_cancellation_sets_failed_state(self):
        store = _make_store()
        runner = _make_runner(store=store)
        exp = _make_experiment()

        async def _slow_communicate():
            await asyncio.sleep(10)
            return (b"", None)

        mock_process = AsyncMock()
        mock_process.communicate = _slow_communicate
        mock_process.returncode = None
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            task = asyncio.create_task(runner.run_experiment(exp))
            # Give the task a moment to start
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert exp.state == ExperimentState.FAILED
        assert exp.result is not None
        assert "cancelled" in exp.result.error_message.lower()
        assert runner.is_running is False


# ---------------------------------------------------------------------------
# _evaluate_result tests
# ---------------------------------------------------------------------------


class TestEvaluateResult:
    """Tests for ExperimentRunner._evaluate_result decision logic."""

    @pytest.mark.asyncio
    async def test_first_experiment_becomes_baseline(self) -> None:
        store = _make_store()
        store.get_baseline.return_value = None
        runner = _make_runner(store=store)

        exp = _make_experiment(
            state=ExperimentState.COMPLETED,
            result=ExperimentResult(val_bpb=5.5),
        )
        await runner._evaluate_result(exp)

        assert exp.state == ExperimentState.KEPT
        assert exp.baseline_val_bpb == 5.5
        store.set_baseline.assert_called_once_with(5.5)

    @pytest.mark.asyncio
    async def test_improvement_above_threshold_kept(self) -> None:
        store = _make_store()
        store.get_baseline.return_value = 6.0
        config = _make_config(improvement_threshold=0.01)
        runner = _make_runner(config=config, store=store)

        exp = _make_experiment(
            state=ExperimentState.COMPLETED,
            result=ExperimentResult(val_bpb=5.5),
        )
        await runner._evaluate_result(exp)

        assert exp.state == ExperimentState.KEPT
        assert exp.baseline_val_bpb == 6.0
        store.set_baseline.assert_called_once_with(5.5)

    @pytest.mark.asyncio
    async def test_improvement_below_threshold_discarded(self) -> None:
        store = _make_store()
        store.get_baseline.return_value = 6.0
        config = _make_config(improvement_threshold=1.0)
        runner = _make_runner(config=config, store=store)

        exp = _make_experiment(
            state=ExperimentState.COMPLETED,
            result=ExperimentResult(val_bpb=5.5),
        )
        await runner._evaluate_result(exp)

        assert exp.state == ExperimentState.DISCARDED
        assert exp.baseline_val_bpb == 6.0
        store.set_baseline.assert_not_called()

    @pytest.mark.asyncio
    async def test_worse_result_discarded(self) -> None:
        store = _make_store()
        store.get_baseline.return_value = 5.0
        runner = _make_runner(store=store)

        exp = _make_experiment(
            state=ExperimentState.COMPLETED,
            result=ExperimentResult(val_bpb=5.5),
        )
        await runner._evaluate_result(exp)

        assert exp.state == ExperimentState.DISCARDED

    @pytest.mark.asyncio
    async def test_no_result_skips_evaluation(self) -> None:
        store = _make_store()
        runner = _make_runner(store=store)

        exp = _make_experiment(state=ExperimentState.COMPLETED, result=None)
        await runner._evaluate_result(exp)

        # State should remain COMPLETED (not changed to KEPT or DISCARDED)
        assert exp.state == ExperimentState.COMPLETED
        store.get_baseline.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_val_bpb_skips_evaluation(self) -> None:
        store = _make_store()
        runner = _make_runner(store=store)

        exp = _make_experiment(
            state=ExperimentState.COMPLETED,
            result=ExperimentResult(val_bpb=None),
        )
        await runner._evaluate_result(exp)

        assert exp.state == ExperimentState.COMPLETED
        store.get_baseline.assert_not_called()

    @pytest.mark.asyncio
    async def test_exact_threshold_kept(self) -> None:
        """Improvement exactly equal to threshold should be KEPT."""
        store = _make_store()
        store.get_baseline.return_value = 6.0
        config = _make_config(improvement_threshold=0.5)
        runner = _make_runner(config=config, store=store)

        exp = _make_experiment(
            state=ExperimentState.COMPLETED,
            result=ExperimentResult(val_bpb=5.5),
        )
        await runner._evaluate_result(exp)

        assert exp.state == ExperimentState.KEPT


# ---------------------------------------------------------------------------
# cancel tests
# ---------------------------------------------------------------------------


class TestCancel:
    """Tests for ExperimentRunner.cancel."""

    @pytest.mark.asyncio
    async def test_cancel_kills_running_process(self) -> None:
        runner = _make_runner()
        mock_process = MagicMock()
        mock_process.returncode = None
        mock_process.kill = MagicMock()
        runner._current_process = mock_process

        await runner.cancel()
        mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_noop_when_no_process(self) -> None:
        runner = _make_runner()
        runner._current_process = None
        # Should not raise
        await runner.cancel()

    @pytest.mark.asyncio
    async def test_cancel_noop_when_process_finished(self) -> None:
        runner = _make_runner()
        mock_process = MagicMock()
        mock_process.returncode = 0  # already finished
        mock_process.kill = MagicMock()
        runner._current_process = mock_process

        await runner.cancel()
        mock_process.kill.assert_not_called()


# ---------------------------------------------------------------------------
# is_running property tests
# ---------------------------------------------------------------------------


class TestIsRunning:
    """Tests for ExperimentRunner.is_running property."""

    def test_initially_not_running(self) -> None:
        runner = _make_runner()
        assert runner.is_running is False

    def test_reflects_internal_flag(self) -> None:
        runner = _make_runner()
        runner._running = True
        assert runner.is_running is True


# ---------------------------------------------------------------------------
# Docker isolation tests (issue #3223)
# ---------------------------------------------------------------------------


def _make_docker_config(**overrides) -> AutoResearchConfig:
    """Build a docker-enabled test config."""
    defaults = {
        "default_training_timeout": 10,
        "improvement_threshold": 0.01,
        "docker_enabled": True,
        "docker_image": "ghcr.io/mrveiss/autobot-autoresearch:test",
        "docker_memory_limit": "2g",
        "docker_cpu_limit": 1.0,
        "docker_timeout": 30,
    }
    defaults.update(overrides)
    return AutoResearchConfig(**defaults)


class TestDockerCommand:
    """Tests for ExperimentRunner._build_docker_command."""

    def test_docker_run_flags_present(self) -> None:
        config = _make_docker_config()
        runner = _make_runner(config=config)
        exp = _make_experiment()

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cmd = runner._build_docker_command(exp, Path(tmp))

        assert cmd[0] == "docker"
        assert "run" in cmd
        assert "--rm" in cmd
        assert "--network" in cmd
        assert "none" in cmd

    def test_memory_and_cpu_flags(self) -> None:
        config = _make_docker_config(docker_memory_limit="3g", docker_cpu_limit=1.5)
        runner = _make_runner(config=config)
        exp = _make_experiment()

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cmd = runner._build_docker_command(exp, Path(tmp))

        assert "--memory" in cmd
        mem_idx = cmd.index("--memory")
        assert cmd[mem_idx + 1] == "3g"

        assert "--cpus" in cmd
        cpu_idx = cmd.index("--cpus")
        assert cmd[cpu_idx + 1] == "1.5"

    def test_image_at_end_of_command(self) -> None:
        config = _make_docker_config()
        runner = _make_runner(config=config)
        exp = _make_experiment()

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cmd = runner._build_docker_command(exp, Path(tmp))

        assert cmd[-1] == config.docker_image

    def test_env_flags_contain_hyperparams(self) -> None:
        config = _make_docker_config()
        runner = _make_runner(config=config)
        hp = HyperParams(max_steps=1000, learning_rate=0.001)
        exp = _make_experiment(hyperparams=hp)

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cmd = runner._build_docker_command(exp, Path(tmp))

        env_values = [cmd[i + 1] for i, v in enumerate(cmd) if v == "--env"]
        assert any("AUTOBOT_EXP_MAX_STEPS=1000" in v for v in env_values)
        assert any("AUTOBOT_EXP_LEARNING_RATE=0.001" in v for v in env_values)

    def test_extra_params_in_env_flags(self) -> None:
        config = _make_docker_config()
        runner = _make_runner(config=config)
        hp = HyperParams(extra={"seed": 42})
        exp = _make_experiment(hyperparams=hp)

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cmd = runner._build_docker_command(exp, Path(tmp))

        env_values = [cmd[i + 1] for i, v in enumerate(cmd) if v == "--env"]
        assert any("AUTOBOT_EXP_EXTRA_SEED=42" in v for v in env_values)

    def test_container_name_flag_present(self) -> None:
        config = _make_docker_config()
        runner = _make_runner(config=config)
        exp = _make_experiment()
        runner._current_container_name = f"autobot_exp_{exp.id}"

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cmd = runner._build_docker_command(exp, Path(tmp))

        assert "--name" in cmd
        name_idx = cmd.index("--name")
        assert cmd[name_idx + 1] == f"autobot_exp_{exp.id}"

    def test_unsafe_mount_path_raises(self) -> None:
        runner = _make_runner()
        with pytest.raises(ValueError, match="unsafe"):
            runner._validate_mount_path(Path("/"))

    def test_volume_mounts_present(self) -> None:
        config = _make_docker_config()
        runner = _make_runner(config=config)
        exp = _make_experiment()

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cmd = runner._build_docker_command(exp, Path(tmp))

        volume_args = [cmd[i + 1] for i, v in enumerate(cmd) if v == "-v"]
        assert any("/experiment:ro" in v for v in volume_args)
        assert any("/output" in v for v in volume_args)


class TestExecuteInDocker:
    """Tests for ExperimentRunner._execute_in_docker with mocked subprocess."""

    @pytest.mark.asyncio
    async def test_successful_docker_run_reads_output(self):
        import json
        import os
        import tempfile

        config = _make_docker_config()
        expected_result = ExperimentResult(val_bpb=4.8, steps_completed=1000)
        parser = _make_parser(result=expected_result)
        runner = _make_runner(config=config, parser=parser)
        exp = _make_experiment()

        output_payload = json.dumps({"returncode": 0, "stdout": "step 1000 val_bpb 4.8\n", "stderr": ""}).encode(
            "utf-8"
        )

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(output_payload, None))
        mock_process.returncode = 0

        # Capture the output directory created by _execute_in_docker so we
        # can pre-populate result.json before the method reads it.
        original_tmp = tempfile.TemporaryDirectory

        class _CapturingTmpDir:
            """Context manager that writes result.json on __enter__."""

            def __init__(self, *args, **kwargs) -> None:
                self._real = original_tmp(*args, **kwargs)

            def __enter__(self):
                path = self._real.__enter__()
                result_file = os.path.join(path, "result.json")
                with open(result_file, "w", encoding="utf-8") as fh:
                    json.dump(
                        {
                            "returncode": 0,
                            "stdout": "step 1000 val_bpb 4.8\n",
                            "stderr": "",
                        },
                        fh,
                    )
                return path

            def __exit__(self, *args):
                return self._real.__exit__(*args)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch(
                "services.autoresearch.runner.tempfile.TemporaryDirectory",
                _CapturingTmpDir,
            ):
                result = await runner._execute_in_docker(exp)

        assert result.val_bpb == 4.8
        parser.parse.assert_called_once()

    @pytest.mark.asyncio
    async def test_docker_uses_create_subprocess_exec(self):
        """docker_enabled=True must call asyncio.create_subprocess_exec with 'docker'."""
        import json
        import os
        import tempfile

        config = _make_docker_config()
        runner = _make_runner(config=config)
        exp = _make_experiment()

        original_tmp = tempfile.TemporaryDirectory

        class _PrePopTmpDir:
            def __init__(self, *args, **kwargs) -> None:
                self._real = original_tmp(*args, **kwargs)

            def __enter__(self):
                path = self._real.__enter__()
                with open(os.path.join(path, "result.json"), "w", encoding="utf-8") as fh:
                    json.dump({"returncode": 0, "stdout": "", "stderr": ""}, fh)
                return path

            def __exit__(self, *args):
                return self._real.__exit__(*args)

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", None))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            with patch(
                "services.autoresearch.runner.tempfile.TemporaryDirectory",
                _PrePopTmpDir,
            ):
                await runner._execute_in_docker(exp)

        first_call_args = mock_exec.call_args_list[0][0]
        assert first_call_args[0] == "docker"
        assert "run" in first_call_args

    @pytest.mark.asyncio
    async def test_docker_timeout_returns_error_result(self):
        config = _make_docker_config(docker_timeout=1)
        runner = _make_runner(config=config)
        exp = _make_experiment()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_process.returncode = None
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        # docker kill subprocess mock
        mock_kill_process = AsyncMock()
        mock_kill_process.returncode = 0
        mock_kill_process.wait = AsyncMock()

        import tempfile

        original_tmp = tempfile.TemporaryDirectory

        class _EmptyTmpDir:
            def __init__(self, *args, **kwargs) -> None:
                self._real = original_tmp(*args, **kwargs)

            def __enter__(self):
                return self._real.__enter__()

            def __exit__(self, *args):
                return self._real.__exit__(*args)

        call_count = 0
        kill_args_captured = []

        async def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_process
            kill_args_captured.extend(args)
            return mock_kill_process

        with patch("asyncio.create_subprocess_exec", side_effect=_side_effect):
            with patch(
                "services.autoresearch.runner.tempfile.TemporaryDirectory",
                _EmptyTmpDir,
            ):
                result = await runner._execute_in_docker(exp)

        assert not result.success
        assert "timed out" in result.error_message
        # docker kill must target container name, not host PID
        assert "docker" in kill_args_captured
        assert "kill" in kill_args_captured
        container_name = kill_args_captured[kill_args_captured.index("kill") + 1]
        assert container_name.startswith("autobot_exp_")

    @pytest.mark.asyncio
    async def test_docker_nonzero_exit_returns_error(self):
        import json
        import os
        import tempfile

        config = _make_docker_config()
        runner = _make_runner(config=config)
        exp = _make_experiment()

        original_tmp = tempfile.TemporaryDirectory

        class _PrePopTmpDir:
            def __init__(self, *args, **kwargs) -> None:
                self._real = original_tmp(*args, **kwargs)

            def __enter__(self):
                path = self._real.__enter__()
                with open(os.path.join(path, "result.json"), "w", encoding="utf-8") as fh:
                    json.dump(
                        {"returncode": 1, "stdout": "err\n", "stderr": "crash"},
                        fh,
                    )
                return path

            def __exit__(self, *args):
                return self._real.__exit__(*args)

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", None))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch(
                "services.autoresearch.runner.tempfile.TemporaryDirectory",
                _PrePopTmpDir,
            ):
                result = await runner._execute_in_docker(exp)

        assert not result.success
        assert "exited with code 1" in result.error_message

    @pytest.mark.asyncio
    async def test_missing_result_json_returns_error(self) -> None:
        config = _make_docker_config()
        runner = _make_runner(config=config)
        exp = _make_experiment()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", None))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner._execute_in_docker(exp)

        assert not result.success
        assert "result.json" in result.error_message


class TestDockerFallback:
    """Verify docker_enabled=False uses subprocess, not Docker."""

    @pytest.mark.asyncio
    async def test_subprocess_path_when_docker_disabled(self) -> None:
        config = _make_config(docker_enabled=False)
        expected_result = ExperimentResult(val_bpb=5.5, steps_completed=5000)
        parser = _make_parser(result=expected_result)
        runner = _make_runner(config=config, parser=parser)
        exp = _make_experiment()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"step 5000", None))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            result = await runner._execute_training(exp)

        # Must not call docker
        first_call_args = mock_exec.call_args_list[0][0]
        assert first_call_args[0] != "docker"
        assert result.val_bpb == 5.5


# ---------------------------------------------------------------------------
# append_result tests  (Issue #3261)
# ---------------------------------------------------------------------------


class TestAppendResult:
    """Tests for append_result()."""

    def test_creates_file_on_first_write(self, tmp_path) -> None:
        result_file = tmp_path / "results.jsonl"
        append_result(result_file, "exp1", "p1", ScorerResult(score=0.9))
        assert result_file.exists()

    def test_record_contains_key_and_score(self, tmp_path) -> None:
        result_file = tmp_path / "results.jsonl"
        append_result(result_file, "exp1", "p1", ScorerResult(score=0.9))
        record = json.loads(result_file.read_text(encoding="utf-8").strip())
        assert record["experiment_id"] == "exp1"
        assert record["prompt_id"] == "p1"
        assert record["score"] == 0.9
        assert record["error"] is None

    def test_error_record_stored(self, tmp_path) -> None:
        result_file = tmp_path / "results.jsonl"
        append_result(result_file, "exp1", "p1", ScorerResult(score=None, error="timeout"))
        record = json.loads(result_file.read_text(encoding="utf-8").strip())
        assert record["error"] == "timeout"
        assert record["score"] is None

    def test_multiple_appends_produce_multiple_lines(self, tmp_path) -> None:
        result_file = tmp_path / "results.jsonl"
        append_result(result_file, "exp1", "p1", ScorerResult(score=0.9))
        append_result(result_file, "exp1", "p2", ScorerResult(score=0.8))
        lines = [l for l in result_file.read_text(encoding="utf-8").splitlines() if l]
        assert len(lines) == 2

    def test_creates_parent_directories(self, tmp_path) -> None:
        result_file = tmp_path / "deep" / "nested" / "results.jsonl"
        append_result(result_file, "exp1", "p1", ScorerResult(score=1.0))
        assert result_file.exists()


# ---------------------------------------------------------------------------
# reorg_results tests  (Issue #3261)
# ---------------------------------------------------------------------------


class TestReorgResults:
    """Tests for reorg_results()."""

    def test_returns_empty_dict_for_missing_file(self, tmp_path) -> None:
        result_file = tmp_path / "missing.jsonl"
        assert reorg_results(result_file) == {}

    def test_deduplicates_last_write_wins(self, tmp_path) -> None:
        result_file = tmp_path / "results.jsonl"
        append_result(result_file, "exp1", "p1", ScorerResult(score=None, error="first"))
        append_result(result_file, "exp1", "p1", ScorerResult(score=0.9))
        results = reorg_results(result_file)
        assert ("exp1", "p1") in results
        assert results[("exp1", "p1")].score == 0.9
        assert results[("exp1", "p1")].error is None

    def test_file_rewritten_without_duplicates(self, tmp_path) -> None:
        result_file = tmp_path / "results.jsonl"
        append_result(result_file, "exp1", "p1", ScorerResult(score=None, error="err"))
        append_result(result_file, "exp1", "p1", ScorerResult(score=0.7))
        reorg_results(result_file)
        lines = [l for l in result_file.read_text(encoding="utf-8").splitlines() if l]
        assert len(lines) == 1

    def test_sorted_output(self, tmp_path) -> None:
        result_file = tmp_path / "results.jsonl"
        append_result(result_file, "exp1", "p2", ScorerResult(score=0.5))
        append_result(result_file, "exp1", "p1", ScorerResult(score=0.8))
        append_result(result_file, "exp1", "p3", ScorerResult(score=0.3))
        reorg_results(result_file)
        lines = [l for l in result_file.read_text(encoding="utf-8").splitlines() if l]
        prompt_ids = [json.loads(l)["prompt_id"] for l in lines]
        assert prompt_ids == sorted(prompt_ids)

    def test_skips_malformed_lines(self, tmp_path) -> None:
        result_file = tmp_path / "results.jsonl"
        result_file.write_text(
            '{"experiment_id":"e","prompt_id":"p","score":1.0,"error":null}\n' "not-json\n",
            encoding="utf-8",
        )
        results = reorg_results(result_file)
        assert len(results) == 1

    def test_returns_correct_scorer_results(self, tmp_path) -> None:
        result_file = tmp_path / "results.jsonl"
        append_result(result_file, "exp1", "p1", ScorerResult(score=0.42))
        results = reorg_results(result_file)
        sr = results[("exp1", "p1")]
        assert isinstance(sr, ScorerResult)
        assert sr.score == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# filter_prompts tests  (Issue #3261)
# ---------------------------------------------------------------------------


class TestFilterPrompts:
    """Tests for filter_prompts()."""

    def test_no_resume_returns_all_prompts(self, tmp_path) -> None:
        result_file = tmp_path / "results.jsonl"
        prompts = [("e", "p1"), ("e", "p2"), ("e", "p3")]
        assert filter_prompts(prompts, result_file, resume=False) == prompts

    def test_resume_skips_successful_results(self, tmp_path) -> None:
        result_file = tmp_path / "results.jsonl"
        append_result(result_file, "e", "p1", ScorerResult(score=0.9))
        prompts = [("e", "p1"), ("e", "p2")]
        remaining = filter_prompts(prompts, result_file, resume=True)
        assert remaining == [("e", "p2")]

    def test_resume_with_no_prior_results_returns_all(self, tmp_path) -> None:
        result_file = tmp_path / "results.jsonl"
        prompts = [("e", "p1"), ("e", "p2")]
        remaining = filter_prompts(prompts, result_file, resume=True)
        assert remaining == prompts

    def test_retry_failures_requeues_error_results(self, tmp_path) -> None:
        result_file = tmp_path / "results.jsonl"
        append_result(result_file, "e", "p1", ScorerResult(score=None, error="timeout"))
        append_result(result_file, "e", "p2", ScorerResult(score=0.8))
        prompts = [("e", "p1"), ("e", "p2"), ("e", "p3")]
        remaining = filter_prompts(prompts, result_file, resume=True, retry_failures=True)
        assert ("e", "p1") in remaining  # error → retried
        assert ("e", "p2") not in remaining  # success → skipped
        assert ("e", "p3") in remaining  # unseen → included

    def test_resume_without_retry_keeps_errors_skipped(self, tmp_path) -> None:
        result_file = tmp_path / "results.jsonl"
        append_result(result_file, "e", "p1", ScorerResult(score=None, error="err"))
        prompts = [("e", "p1"), ("e", "p2")]
        remaining = filter_prompts(prompts, result_file, resume=True, retry_failures=False)
        # Error result without retry_failures: skip (treat as done)
        assert ("e", "p1") not in remaining
        assert ("e", "p2") in remaining

    def test_empty_prompts_returns_empty(self, tmp_path) -> None:
        result_file = tmp_path / "results.jsonl"
        assert filter_prompts([], result_file, resume=True) == []

    def test_all_prompts_complete_returns_empty(self, tmp_path) -> None:
        result_file = tmp_path / "results.jsonl"
        prompts = [("e", "p1"), ("e", "p2")]
        for _, pid in prompts:
            append_result(result_file, "e", pid, ScorerResult(score=0.5))
        remaining = filter_prompts(prompts, result_file, resume=True)
        assert remaining == []
