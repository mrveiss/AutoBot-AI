# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
ExperimentRunner Unit Tests

Issue #2637: Comprehensive tests for subprocess execution, timeout handling,
cancellation, concurrent run rejection, evaluation logic, and parameter
validation.
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.autoresearch.config import AutoResearchConfig
from services.autoresearch.models import (
    Experiment,
    ExperimentResult,
    ExperimentState,
    HyperParams,
)
from services.autoresearch.runner import (
    _EXTRA_KEY_PATTERN,
    _RESERVED_KEYS,
    ExperimentRunner,
)

logger = logging.getLogger(__name__)


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

    def test_valid_params_accepted(self):
        ExperimentRunner._validate_extra_params(
            {"custom_lr": 0.001, "warmup_ratio": 0.1}
        )

    def test_reserved_key_rejected(self):
        for key in ("max_steps", "learning_rate", "batch_size"):
            with pytest.raises(ValueError, match="conflicts with a built-in flag"):
                ExperimentRunner._validate_extra_params({key: 42})

    def test_uppercase_key_rejected(self):
        with pytest.raises(ValueError, match="must be lowercase"):
            ExperimentRunner._validate_extra_params({"BadKey": 1})

    def test_key_starting_with_digit_rejected(self):
        with pytest.raises(ValueError, match="must be lowercase"):
            ExperimentRunner._validate_extra_params({"1bad": 1})

    def test_key_with_dash_rejected(self):
        with pytest.raises(ValueError, match="must be lowercase"):
            ExperimentRunner._validate_extra_params({"bad-key": 1})

    def test_key_too_long_rejected(self):
        long_key = "a" * 65
        with pytest.raises(ValueError, match="must be lowercase"):
            ExperimentRunner._validate_extra_params({long_key: 1})

    def test_non_scalar_value_rejected(self):
        with pytest.raises(ValueError, match="must be scalar"):
            ExperimentRunner._validate_extra_params({"key": [1, 2, 3]})

    def test_dict_value_rejected(self):
        with pytest.raises(ValueError, match="must be scalar"):
            ExperimentRunner._validate_extra_params({"key": {"nested": True}})

    def test_string_with_double_dash_rejected(self):
        with pytest.raises(ValueError, match="cannot contain '--'"):
            ExperimentRunner._validate_extra_params({"key": "--inject"})

    def test_string_too_long_rejected(self):
        with pytest.raises(ValueError, match="256 chars"):
            ExperimentRunner._validate_extra_params({"key": "x" * 257})

    def test_bool_value_accepted(self):
        ExperimentRunner._validate_extra_params({"use_flash": True})

    def test_int_value_accepted(self):
        ExperimentRunner._validate_extra_params({"seed": 42})

    def test_empty_dict_accepted(self):
        ExperimentRunner._validate_extra_params({})

    def test_all_reserved_keys_are_lowercase(self):
        """Sanity check: all reserved keys match the key pattern format."""
        for key in _RESERVED_KEYS:
            assert _EXTRA_KEY_PATTERN.match(
                key
            ), f"Reserved key '{key}' doesn't match pattern"


# ---------------------------------------------------------------------------
# _build_command tests
# ---------------------------------------------------------------------------


class TestBuildCommand:
    """Tests for ExperimentRunner._build_command."""

    def test_basic_command_structure(self):
        runner = _make_runner()
        exp = _make_experiment()
        cmd = runner._build_command(exp)

        assert cmd[0] == runner.config.python_bin
        assert str(runner.config.train_script) in cmd[1]
        assert any("--max_steps=" in arg for arg in cmd)
        assert any("--learning_rate=" in arg for arg in cmd)

    def test_extra_params_appended(self):
        runner = _make_runner()
        exp = _make_experiment(
            hyperparams=HyperParams(extra={"seed": 42, "use_flash": True})
        )
        cmd = runner._build_command(exp)

        assert "--seed=42" in cmd
        assert "--use_flash=True" in cmd

    def test_custom_python_executable(self):
        config = _make_config()
        config.python_executable = "/usr/bin/python3.12"
        runner = _make_runner(config=config)
        exp = _make_experiment()
        cmd = runner._build_command(exp)

        assert cmd[0] == "/usr/bin/python3.12"

    def test_all_hyperparams_included(self):
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
            assert any(
                f"--{flag}=" in arg for arg in cmd
            ), f"Missing --{flag} in command"


# ---------------------------------------------------------------------------
# _execute_training tests (subprocess mocking)
# ---------------------------------------------------------------------------


class TestExecuteTraining:
    """Tests for ExperimentRunner._execute_training with mocked subprocess."""

    @pytest.mark.asyncio
    async def test_successful_training(self):
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
    async def test_nonzero_exit_code(self):
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
    async def test_timeout_kills_process(self):
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
    async def test_empty_stdout_handled(self):
        parser = _make_parser(
            result=ExperimentResult(error_message="Empty training output")
        )
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
    async def test_none_stdout_handled(self):
        parser = _make_parser(
            result=ExperimentResult(error_message="Empty training output")
        )
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
    async def test_successful_run_sets_completed(self):
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
    async def test_failed_run_sets_failed_state(self):
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
    async def test_exception_during_training_sets_failed(self):
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
    async def test_running_flag_cleared_after_completion(self):
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
    async def test_running_flag_cleared_after_failure(self):
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
    async def test_concurrent_run_rejected(self):
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
    async def test_first_experiment_becomes_baseline(self):
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
    async def test_improvement_above_threshold_kept(self):
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
    async def test_improvement_below_threshold_discarded(self):
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
    async def test_worse_result_discarded(self):
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
    async def test_no_result_skips_evaluation(self):
        store = _make_store()
        runner = _make_runner(store=store)

        exp = _make_experiment(state=ExperimentState.COMPLETED, result=None)
        await runner._evaluate_result(exp)

        # State should remain COMPLETED (not changed to KEPT or DISCARDED)
        assert exp.state == ExperimentState.COMPLETED
        store.get_baseline.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_val_bpb_skips_evaluation(self):
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
    async def test_exact_threshold_kept(self):
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
    async def test_cancel_kills_running_process(self):
        runner = _make_runner()
        mock_process = MagicMock()
        mock_process.returncode = None
        mock_process.kill = MagicMock()
        runner._current_process = mock_process

        await runner.cancel()
        mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_noop_when_no_process(self):
        runner = _make_runner()
        runner._current_process = None
        # Should not raise
        await runner.cancel()

    @pytest.mark.asyncio
    async def test_cancel_noop_when_process_finished(self):
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

    def test_initially_not_running(self):
        runner = _make_runner()
        assert runner.is_running is False

    def test_reflects_internal_flag(self):
        runner = _make_runner()
        runner._running = True
        assert runner.is_running is True
