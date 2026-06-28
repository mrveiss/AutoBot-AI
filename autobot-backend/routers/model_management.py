# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Model Management API Router (Issue #904)

Endpoints for training, deploying, and serving code completion models.
"""

import threading
import time
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from autobot_shared.db_session import session_scope
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from models.ml_model import MLModel
from user_management.database import db_session_context

logger = get_logger(__name__)

router = APIRouter(tags=["ml-models"])

# _sync_session_lock guards the one-time creation of the sync session factory
# used only by _train_background, which runs in a thread (not the event loop).
# All async endpoints use db_session_context() directly (#10570).
_sync_session_factory = None
_sync_session_lock = threading.Lock()


def _get_sync_session():
    """Return a sync session context manager for use in background threads (#10570).

    Background training runs in a thread via BackgroundTasks.add_task, so
    awaiting an async session is not possible there.  We derive a sync
    sessionmaker from the canonical async engine's .sync_engine so that
    both sync and async paths share the same underlying connection pool
    and configuration — no second engine is created.
    """
    global _sync_session_factory
    if _sync_session_factory is None:
        with _sync_session_lock:
            if _sync_session_factory is None:
                from sqlalchemy.orm import sessionmaker

                from user_management.database import get_async_engine

                _sync_session_factory = sessionmaker(bind=get_async_engine().sync_engine)
    return session_scope(_sync_session_factory)


def _get_trainer_class():
    """Lazy import CompletionTrainer to avoid torchmetrics at module load."""
    from training.completion_trainer import CompletionTrainer

    return CompletionTrainer


# Active model cache — guarded by _model_lock to prevent torn reads/writes (#2846).
# Both the async activate_model endpoint and the thread-pool background task write
# these globals; threading.Lock is required (asyncio.Lock is not thread-safe).
_active_model = None
_active_version: str | None = None
_model_lock = threading.Lock()


# =============================================================================
# Request/Response Models
# =============================================================================


class TrainRequest(BaseModel):
    """Request to trigger model training."""

    language: str | None = Field(None, description="Filter training data by language")
    pattern_type: str | None = Field(None, description="Filter training data by pattern type")
    num_epochs: int = Field(default=10, ge=1, le=100)
    batch_size: int = Field(default=32, ge=1, le=256)
    notes: str | None = Field(None, description="Training notes")


class TrainResponse(BaseModel):
    """Response from training trigger."""

    status: str
    message: str
    training_started: bool


class ModelResponse(BaseModel):
    """Model metadata for API response."""

    id: int
    version: str
    model_type: str
    language: str | None
    pattern_type: str | None
    metrics: Dict[str, float | None]
    is_active: bool
    created_at: str


class ModelListResponse(BaseModel):
    """List of models with pagination."""

    models: List[ModelResponse]
    total: int


class PredictRequest(BaseModel):
    """Request for code completion prediction."""

    context: str = Field(..., description="Code context for completion")
    language: str = Field(default="python", description="Programming language")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of suggestions")


class PredictResponse(BaseModel):
    """Completion predictions with confidence."""

    suggestions: List[str]
    confidence: float
    model_version: str


# =============================================================================
# API Endpoints
# =============================================================================


def _register_trained_model(trainer, request, final_metrics, duration):
    """Helper for _train_background. Ref: #1088.

    Persists the trained model checkpoint as an MLModel record in the database.
    Looks up the most recently modified checkpoint file in trainer.model_dir and
    writes all training metrics into the record.
    """
    with _get_sync_session() as db:
        model_files = list(Path(trainer.model_dir).glob("completion_model_v*.pt"))
        if model_files:
            latest_checkpoint = max(model_files, key=lambda p: p.stat().st_mtime)
            version = latest_checkpoint.stem.replace("completion_model_", "")
            model_record = MLModel(
                version=version,
                model_type="lstm_completion",
                language=request.language,
                pattern_type=request.pattern_type,
                file_path=str(latest_checkpoint),
                config=trainer.model.get_config(),
                val_loss=final_metrics.get("val_loss"),
                accuracy=final_metrics.get("accuracy"),
                mrr=final_metrics.get("mrr"),
                hit_at_1=final_metrics.get("hit@1"),
                hit_at_5=final_metrics.get("hit@5"),
                hit_at_10=final_metrics.get("hit@10"),
                epochs_trained=trainer.current_epoch,
                training_duration_seconds=duration,
                num_parameters=sum(p.numel() for p in trainer.model.parameters()),
                notes=request.notes,
            )
            db.add(model_record)
            db.commit()
            logger.info("Training complete: %s", version)


def _train_background(request):
    """Helper for train_model. Ref: #1088.

    Runs the full training pipeline (init, prepare, train, save, register)
    in a background task. Errors are caught and logged without re-raising.
    """
    try:
        start_time = time.time()
        trainer = _get_trainer_class()(language=request.language, pattern_type=request.pattern_type)
        trainer.prepare_data(batch_size=request.batch_size)
        history = trainer.train(num_epochs=request.num_epochs)
        trainer.save_checkpoint(is_best=True)
        duration = int(time.time() - start_time)
        final_metrics = history["metrics"][-1] if history["metrics"] else {}
        _register_trained_model(trainer, request, final_metrics, duration)
    except Exception as e:
        logger.error("Training failed: %s", e, exc_info=True)


@router.post("/train", response_model=TrainResponse)
async def train_model(request: TrainRequest, background_tasks: BackgroundTasks):
    """
    Trigger model training in background.

    - **language**: Filter training data by language (python, typescript, vue)
    - **pattern_type**: Filter by pattern type
    - **num_epochs**: Number of training epochs
    - **batch_size**: Training batch size
    """
    background_tasks.add_task(_train_background, request)
    return TrainResponse(
        status="success",
        message="Training started in background",
        training_started=True,
    )


@router.get("/models", response_model=ModelListResponse)
async def list_models(
    language: str | None = Query(None),
    is_active: bool | None = Query(None),
):
    """
    List all trained models.

    - **language**: Filter by training language
    - **is_active**: Filter by active status
    """
    from sqlalchemy import select

    async with db_session_context() as db:
        stmt = select(MLModel)

        if language:
            stmt = stmt.where(MLModel.language == language)
        if is_active is not None:
            stmt = stmt.where(MLModel.is_active == is_active)

        stmt = stmt.order_by(MLModel.created_at.desc())
        result = await db.execute(stmt)
        models = result.scalars().all()

        return ModelListResponse(
            models=[
                ModelResponse(
                    id=m.id,
                    version=m.version,
                    model_type=m.model_type,
                    language=m.language,
                    pattern_type=m.pattern_type,
                    metrics={
                        "val_loss": m.val_loss,
                        "accuracy": m.accuracy,
                        "mrr": m.mrr,
                        "hit@1": m.hit_at_1,
                        "hit@5": m.hit_at_5,
                        "hit@10": m.hit_at_10,
                    },
                    is_active=m.is_active,
                    created_at=m.created_at.isoformat(),
                )
                for m in models
            ],
            total=len(models),
        )


@router.get("/models/{version}", response_model=Dict)
async def get_model(version: str):
    """Get detailed model metadata by version."""
    from sqlalchemy import select

    async with db_session_context() as db:
        result = await db.execute(select(MLModel).where(MLModel.version == version))
        model = result.scalars().first()

        if not model:
            raise HTTPException(status_code=404, detail="Model not found")

        return model.to_dict()


@router.post("/models/{version}/activate")
async def activate_model(version: str):
    """
    Set a model as active for serving predictions.

    Deactivates any currently active model.
    """
    from sqlalchemy import select, update

    async with db_session_context() as db:
        result = await db.execute(select(MLModel).where(MLModel.version == version))
        model = result.scalars().first()

        if not model:
            raise HTTPException(status_code=404, detail="Model not found")

        # Deactivate all other models
        await db.execute(update(MLModel).values(is_active=False, deployed_at=None))

        # Activate this model
        model.is_active = True
        model.deployed_at = now_utc()
        # commit handled by db_session_context()

    # Load model into memory then atomically publish both globals (#2846).
    # Loading outside the session avoids holding the DB connection during a
    # potentially slow checkpoint read; only the final pointer swap is locked.
    trainer = _get_trainer_class()()
    trainer.load_checkpoint(version)
    with _model_lock:
        global _active_model, _active_version
        _active_model = trainer
        _active_version = version

    logger.info("Activated model: %s", version)

    return {
        "status": "success",
        "message": f"Model {version} is now active",
        "version": version,
    }


@router.get("/evaluate")
async def get_evaluation_metrics():
    """
    Get evaluation metrics for active model.

    Returns latest metrics from validation set.
    """
    with _model_lock:
        active_model_snapshot = _active_model
        active_version_snapshot = _active_version

    if active_model_snapshot is None:
        raise HTTPException(status_code=400, detail="No active model")

    from sqlalchemy import select

    async with db_session_context() as db:
        result = await db.execute(select(MLModel).where(MLModel.version == active_version_snapshot))
        model = result.scalars().first()

        if not model:
            raise HTTPException(status_code=404, detail="Active model not found in DB")

        return {
            "version": model.version,
            "metrics": {
                "val_loss": model.val_loss,
                "accuracy": model.accuracy,
                "mrr": model.mrr,
                "hit@1": model.hit_at_1,
                "hit@5": model.hit_at_5,
                "hit@10": model.hit_at_10,
            },
            "training_info": {
                "epochs_trained": model.epochs_trained,
                "training_duration_seconds": model.training_duration_seconds,
                "num_parameters": model.num_parameters,
            },
        }


@router.post("/predict", response_model=PredictResponse)
async def predict_completion(request: PredictRequest):
    """
    Get code completion predictions from active model.

    - **context**: Code context for completion
    - **language**: Programming language
    - **top_k**: Number of suggestions to return
    """
    with _model_lock:
        active_model_snapshot = _active_model
        active_version_snapshot = _active_version

    if active_model_snapshot is None:
        raise HTTPException(status_code=400, detail="No active model. Activate a model first.")

    try:
        # Tokenize context
        tokenizer = active_model_snapshot.train_loader.dataset.tokenizer
        context_ids = tokenizer.encode(request.context, max_length=128)
        import torch

        input_tensor = torch.tensor([context_ids], dtype=torch.long).to(active_model_snapshot.device)

        # Get predictions
        predictions = active_model_snapshot.model.predict(input_tensor, top_k=request.top_k)

        # Decode token IDs to text
        token_ids = predictions["tokens"][0].cpu().tolist()
        suggestions = [tokenizer.decode([tid]) for tid in token_ids]

        confidence = predictions["confidence"][0].item()

        return PredictResponse(
            suggestions=suggestions,
            confidence=confidence,
            model_version=active_version_snapshot,
        )

    except Exception as e:
        logger.error("Prediction failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
