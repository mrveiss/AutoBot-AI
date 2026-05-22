# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoResearch Routes Integration Tests

Issue #2637: Tests for REST API endpoints covering experiment CRUD,
baseline management, status, and cancellation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from autobot_shared.logging_manager import get_logger
from services.autoresearch.models import (
    Experiment,
    ExperimentState,
    ExperimentStats,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# App + client setup (auth middleware bypassed for unit tests)
# ---------------------------------------------------------------------------


def _build_app(
    store: AsyncMock | None = None,
    runner: MagicMock | None = None,
) -> FastAPI:
    """Build a FastAPI app with the autoresearch router and mocked deps."""
    with patch("auth_middleware.check_admin_permission", return_value=True):
        from services.autoresearch.routes import router

    app = FastAPI()
    app.include_router(router, prefix="/autoresearch")

    if store is not None:
        app.state.autoresearch_store = store
    if runner is not None:
        app.state.autoresearch_runner = runner

    return app


def _make_store() -> AsyncMock:
    """Build a mock ExperimentStore."""
    store = AsyncMock()
    store.save_experiment = AsyncMock()
    store.get_experiment = AsyncMock(return_value=None)
    store.list_experiments = AsyncMock(return_value=[])
    store.get_baseline = AsyncMock(return_value=None)
    store.set_baseline = AsyncMock()
    store.get_stats = AsyncMock(return_value=ExperimentStats(total_experiments=0))
    return store


def _make_runner(is_running: bool = False) -> MagicMock:
    """Build a mock ExperimentRunner."""
    runner = MagicMock()
    runner.is_running = is_running
    runner.run_experiment = AsyncMock()
    runner.cancel = AsyncMock()
    return runner


def _sample_experiment(**overrides) -> Experiment:
    """Build a sample experiment for test responses."""
    defaults = {
        "id": "exp-001",
        "hypothesis": "Test hypothesis",
        "state": ExperimentState.PENDING,
    }
    defaults.update(overrides)
    return Experiment(**defaults)


# ---------------------------------------------------------------------------
# POST /autoresearch/experiments
# ---------------------------------------------------------------------------


class TestCreateExperiment:
    """Tests for POST /autoresearch/experiments."""

    def test_create_experiment_success(self) -> None:
        store = _make_store()
        runner = _make_runner(is_running=False)
        app = _build_app(store=store, runner=runner)
        client = TestClient(app)

        response = client.post(
            "/autoresearch/experiments",
            json={
                "hypothesis": "Increase learning rate",
                "description": "Test higher LR",
                "tags": ["lr_sweep"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["state"] == "pending"
        store.save_experiment.assert_called_once()

    def test_create_experiment_with_hyperparams(self) -> None:
        store = _make_store()
        runner = _make_runner(is_running=False)
        app = _build_app(store=store, runner=runner)
        client = TestClient(app)

        response = client.post(
            "/autoresearch/experiments",
            json={
                "hypothesis": "Custom LR",
                "hyperparams": {"learning_rate": 1e-2, "batch_size": 128},
            },
        )

        assert response.status_code == 200

    def test_create_experiment_minimal_payload(self) -> None:
        store = _make_store()
        runner = _make_runner(is_running=False)
        app = _build_app(store=store, runner=runner)
        client = TestClient(app)

        response = client.post(
            "/autoresearch/experiments",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "pending"

    def test_create_experiment_conflict_when_running(self) -> None:
        store = _make_store()
        runner = _make_runner(is_running=True)
        app = _build_app(store=store, runner=runner)
        client = TestClient(app)

        response = client.post(
            "/autoresearch/experiments",
            json={"hypothesis": "Won't run"},
        )

        assert response.status_code == 409
        assert "already running" in response.json()["detail"].lower()

    def test_create_experiment_hypothesis_too_long(self) -> None:
        store = _make_store()
        runner = _make_runner(is_running=False)
        app = _build_app(store=store, runner=runner)
        client = TestClient(app)

        response = client.post(
            "/autoresearch/experiments",
            json={"hypothesis": "x" * 1001},
        )

        assert response.status_code == 422

    def test_create_experiment_description_too_long(self) -> None:
        store = _make_store()
        runner = _make_runner(is_running=False)
        app = _build_app(store=store, runner=runner)
        client = TestClient(app)

        response = client.post(
            "/autoresearch/experiments",
            json={"description": "x" * 5001},
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /autoresearch/experiments
# ---------------------------------------------------------------------------


class TestListExperiments:
    """Tests for GET /autoresearch/experiments."""

    def test_list_empty(self) -> None:
        store = _make_store()
        app = _build_app(store=store, runner=_make_runner())
        client = TestClient(app)

        response = client.get("/autoresearch/experiments")

        assert response.status_code == 200
        data = response.json()
        assert data["experiments"] == []
        assert data["count"] == 0
        assert data["offset"] == 0

    def test_list_returns_experiments(self) -> None:
        store = _make_store()
        exp1 = _sample_experiment(id="exp-1")
        exp2 = _sample_experiment(id="exp-2")
        store.list_experiments.return_value = [exp1, exp2]
        app = _build_app(store=store, runner=_make_runner())
        client = TestClient(app)

        response = client.get("/autoresearch/experiments")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["experiments"][0]["id"] == "exp-1"

    def test_list_with_state_filter(self) -> None:
        store = _make_store()
        app = _build_app(store=store, runner=_make_runner())
        client = TestClient(app)

        client.get("/autoresearch/experiments?state=kept")

        call_kwargs = store.list_experiments.call_args[1]
        assert call_kwargs["state"] == ExperimentState.KEPT

    def test_list_with_invalid_state(self) -> None:
        store = _make_store()
        app = _build_app(store=store, runner=_make_runner())
        client = TestClient(app)

        response = client.get("/autoresearch/experiments?state=bogus")

        assert response.status_code == 400
        assert "Invalid state" in response.json()["detail"]

    def test_list_with_pagination(self) -> None:
        store = _make_store()
        app = _build_app(store=store, runner=_make_runner())
        client = TestClient(app)

        client.get("/autoresearch/experiments?limit=10&offset=5")

        call_kwargs = store.list_experiments.call_args[1]
        assert call_kwargs["limit"] == 10
        assert call_kwargs["offset"] == 5

    def test_list_limit_out_of_range(self) -> None:
        store = _make_store()
        app = _build_app(store=store, runner=_make_runner())
        client = TestClient(app)

        response = client.get("/autoresearch/experiments?limit=999")
        assert response.status_code == 422

    def test_list_negative_offset(self) -> None:
        store = _make_store()
        app = _build_app(store=store, runner=_make_runner())
        client = TestClient(app)

        response = client.get("/autoresearch/experiments?offset=-1")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /autoresearch/experiments/{experiment_id}
# ---------------------------------------------------------------------------


class TestGetExperiment:
    """Tests for GET /autoresearch/experiments/{experiment_id}."""

    def test_get_existing_experiment(self) -> None:
        store = _make_store()
        exp = _sample_experiment(id="exp-001", hypothesis="found it")
        store.get_experiment.return_value = exp
        app = _build_app(store=store, runner=_make_runner())
        client = TestClient(app)

        response = client.get("/autoresearch/experiments/exp-001")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "exp-001"
        assert data["hypothesis"] == "found it"

    def test_get_nonexistent_experiment(self) -> None:
        store = _make_store()
        store.get_experiment.return_value = None
        app = _build_app(store=store, runner=_make_runner())
        client = TestClient(app)

        response = client.get("/autoresearch/experiments/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /autoresearch/experiments/stats
# ---------------------------------------------------------------------------


class TestGetStats:
    """Tests for GET /autoresearch/experiments/stats."""

    def test_get_stats_empty(self) -> None:
        store = _make_store()
        app = _build_app(store=store, runner=_make_runner())
        client = TestClient(app)

        response = client.get("/autoresearch/experiments/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_experiments"] == 0

    def test_get_stats_with_data(self) -> None:
        store = _make_store()
        store.get_stats.return_value = ExperimentStats(
            total_experiments=10,
            completed=5,
            kept=3,
            failed=2,
            best_val_bpb=5.2,
        )
        app = _build_app(store=store, runner=_make_runner())
        client = TestClient(app)

        response = client.get("/autoresearch/experiments/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_experiments"] == 10
        assert data["kept"] == 3
        assert data["best_val_bpb"] == 5.2


# ---------------------------------------------------------------------------
# POST /autoresearch/experiments/baseline
# ---------------------------------------------------------------------------


class TestSetBaseline:
    """Tests for POST /autoresearch/experiments/baseline."""

    def test_set_baseline_success(self) -> None:
        store = _make_store()
        app = _build_app(store=store, runner=_make_runner())
        client = TestClient(app)

        response = client.post(
            "/autoresearch/experiments/baseline",
            json={"val_bpb": 6.0},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["baseline_val_bpb"] == 6.0
        store.set_baseline.assert_called_once_with(6.0)

    def test_set_baseline_missing_field(self) -> None:
        store = _make_store()
        app = _build_app(store=store, runner=_make_runner())
        client = TestClient(app)

        response = client.post(
            "/autoresearch/experiments/baseline",
            json={},
        )

        assert response.status_code == 422

    def test_set_baseline_invalid_type(self) -> None:
        store = _make_store()
        app = _build_app(store=store, runner=_make_runner())
        client = TestClient(app)

        response = client.post(
            "/autoresearch/experiments/baseline",
            json={"val_bpb": "not_a_number"},
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /autoresearch/status
# ---------------------------------------------------------------------------


class TestGetStatus:
    """Tests for GET /autoresearch/status."""

    def test_status_idle(self) -> None:
        store = _make_store()
        runner = _make_runner(is_running=False)
        store.get_baseline.return_value = None
        app = _build_app(store=store, runner=runner)
        client = TestClient(app)

        response = client.get("/autoresearch/status")

        assert response.status_code == 200
        data = response.json()
        assert data["running"] is False
        assert data["baseline_val_bpb"] is None

    def test_status_running_with_baseline(self) -> None:
        store = _make_store()
        runner = _make_runner(is_running=True)
        store.get_baseline.return_value = 6.0
        app = _build_app(store=store, runner=runner)
        client = TestClient(app)

        response = client.get("/autoresearch/status")

        assert response.status_code == 200
        data = response.json()
        assert data["running"] is True
        assert data["baseline_val_bpb"] == 6.0


# ---------------------------------------------------------------------------
# POST /autoresearch/cancel
# ---------------------------------------------------------------------------


class TestCancelExperiment:
    """Tests for POST /autoresearch/cancel."""

    def test_cancel_running_experiment(self) -> None:
        runner = _make_runner(is_running=True)
        app = _build_app(store=_make_store(), runner=runner)
        client = TestClient(app)

        response = client.post("/autoresearch/cancel")

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        runner.cancel.assert_called_once()

    def test_cancel_when_not_running(self) -> None:
        runner = _make_runner(is_running=False)
        app = _build_app(store=_make_store(), runner=runner)
        client = TestClient(app)

        response = client.post("/autoresearch/cancel")

        assert response.status_code == 409
        assert "not currently running" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Prompt Optimizer endpoints — Issue #3211
# ---------------------------------------------------------------------------


def _make_optimizer(
    current_session=None,
    registered_targets: list[str] | None = None,
) -> MagicMock:
    """Build a mock PromptOptimizer."""
    opt = MagicMock()
    opt.current_session = current_session
    opt.get_registered_targets = MagicMock(return_value=registered_targets or [])
    opt.get_target = MagicMock(return_value=None)
    opt.cancel = MagicMock()
    return opt


def _build_app_with_optimizer(optimizer: MagicMock) -> FastAPI:
    """Build app with autoresearch router and a pre-set optimizer on app.state."""
    with patch("auth_middleware.check_admin_permission", return_value=True):
        from services.autoresearch.routes import router

    app = FastAPI()
    app.include_router(router, prefix="/autoresearch")
    app.state.autoresearch_optimizer = optimizer
    app.state.autoresearch_store = _make_store()
    app.state.autoresearch_runner = _make_runner()
    return app


class TestGetOptimizerStatus:
    """Tests for GET /autoresearch/prompt-optimizer/status — Issue #3211."""

    def test_status_no_session(self) -> None:
        opt = _make_optimizer(current_session=None)
        app = _build_app_with_optimizer(opt)
        client = TestClient(app)

        response = client.get("/autoresearch/prompt-optimizer/status")

        assert response.status_code == 200
        assert response.json() == {"running": False, "session": None}

    def test_status_with_session(self) -> None:
        session = MagicMock()
        session.to_dict.return_value = {"status": "running", "round": 1}
        opt = _make_optimizer(current_session=session)
        app = _build_app_with_optimizer(opt)
        client = TestClient(app)

        response = client.get("/autoresearch/prompt-optimizer/status")

        assert response.status_code == 200
        data = response.json()
        assert data["running"] is True
        assert data["session"]["status"] == "running"


class TestStartOptimization:
    """Tests for POST /autoresearch/prompt-optimizer/start — Issue #3211."""

    def test_start_success(self) -> None:
        target_entry = (MagicMock(), MagicMock())
        opt = _make_optimizer(current_session=None)
        opt.get_target = MagicMock(return_value=target_entry)
        app = _build_app_with_optimizer(opt)
        client = TestClient(app)

        response = client.post(
            "/autoresearch/prompt-optimizer/start",
            json={"agent_name": "autoresearch_hypothesis", "max_rounds": 2},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert data["agent_name"] == "autoresearch_hypothesis"

    def test_start_conflict_when_already_running(self) -> None:
        session = MagicMock()
        opt = _make_optimizer(current_session=session)
        app = _build_app_with_optimizer(opt)
        client = TestClient(app)

        response = client.post(
            "/autoresearch/prompt-optimizer/start",
            json={"agent_name": "autoresearch_hypothesis"},
        )

        assert response.status_code == 409

    def test_start_unknown_target_returns_400(self) -> None:
        opt = _make_optimizer(current_session=None)
        opt.get_target = MagicMock(return_value=None)
        opt.get_registered_targets = MagicMock(return_value=["autoresearch_hypothesis"])
        app = _build_app_with_optimizer(opt)
        client = TestClient(app)

        response = client.post(
            "/autoresearch/prompt-optimizer/start",
            json={"agent_name": "nonexistent_agent"},
        )

        assert response.status_code == 400
        assert "nonexistent_agent" in response.json()["detail"]


class TestCancelOptimization:
    """Tests for POST /autoresearch/prompt-optimizer/cancel — Issue #3211."""

    def test_cancel_running_session(self) -> None:
        session = MagicMock()
        opt = _make_optimizer(current_session=session)
        app = _build_app_with_optimizer(opt)
        client = TestClient(app)

        response = client.post("/autoresearch/prompt-optimizer/cancel")

        assert response.status_code == 200
        assert response.json()["status"] == "cancelling"
        opt.cancel.assert_called_once()

    def test_cancel_no_session_returns_409(self) -> None:
        opt = _make_optimizer(current_session=None)
        app = _build_app_with_optimizer(opt)
        client = TestClient(app)

        response = client.post("/autoresearch/prompt-optimizer/cancel")

        assert response.status_code == 409


class TestListOptimizationTargets:
    """Tests for GET /autoresearch/prompt-optimizer/targets — Issue #3211."""

    def test_returns_registered_targets(self) -> None:
        opt = _make_optimizer(registered_targets=["autoresearch_hypothesis", "agent_b"])
        app = _build_app_with_optimizer(opt)
        client = TestClient(app)

        response = client.get("/autoresearch/prompt-optimizer/targets")

        assert response.status_code == 200
        assert response.json() == {"targets": ["autoresearch_hypothesis", "agent_b"]}

    def test_returns_empty_when_no_targets(self) -> None:
        opt = _make_optimizer(registered_targets=[])
        app = _build_app_with_optimizer(opt)
        client = TestClient(app)

        response = client.get("/autoresearch/prompt-optimizer/targets")

        assert response.status_code == 200
        assert response.json() == {"targets": []}
