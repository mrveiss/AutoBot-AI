# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Model Management API Router (Issue #904)

Endpoints for training, deploying, and serving code completion models.
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from models.ml_model import MLModel
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autobot_shared.ssot_config import config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ml-models"])

# Database setup — deferred to avoid crash when config.database is unavailable
_engine = None
_SessionLocal = None


def _get_session():
    """Return a new SQLAlchemy session, creating the engine on first call.

    Deferred from module level to avoid DB connection at import time (Issue #940).
    """
    global _engine, _SessionLocal
    if _SessionLocal is None:
        db_url = (
            f"postgresql://{config.database.user}:{config.database.password}"
            f"@{config.database.host}:{config.database.port}/{config.database.name}"
        )
        _engine = create_engine(db_url)
        _SessionLocal = sessionmaker(bind=_engine)
    return _SessionLocal()


def _get_trainer_class():
    """Lazy import CompletionTrainer to avoid torchmetrics at module load."""
    from training.completion_trainer import CompletionTrainer

    return CompletionTrainer


# Active model cache
_active_model = None
_active_version: Optional[str] = None


# =============================================================================
# Request/Response Models
# =============================================================================


class TrainRequest(BaseModel):
    """Request to trigger model training."""

    language: Optional[str] = Field(
        None, description="Filter training data by language"
    )
    pattern_type: Optional[str] = Field(
        None, description="Filter training data by pattern type"
    )
    num_epochs: int = Field(default=10, ge=1, le=100)
    batch_size: int = Field(default=32, ge=1, le=256)
    notes: Optional[str] = Field(None, description="Training notes")


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
    language: Optional[str]
    pattern_type: Optional[str]
    metrics: Dict[str, Optional[float]]
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
    db = _get_session()
    try:
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
            logger.info(f"Training complete: {version}")
    finally:
        db.close()


def _train_background(request):
    """Helper for train_model. Ref: #1088.

    Runs the full training pipeline (init, prepare, train, save, register)
    in a background task. Errors are caught and logged without re-raising.
    """
    try:
        start_time = time.time()
        trainer = _get_trainer_class()(
            language=request.language, pattern_type=request.pattern_type
        )
        trainer.prepare_data(batch_size=request.batch_size)
        history = trainer.train(num_epochs=request.num_epochs)
        trainer.save_checkpoint(is_best=True)
        duration = int(time.time() - start_time)
        final_metrics = history["metrics"][-1] if history["metrics"] else {}
        _register_trained_model(trainer, request, final_metrics, duration)
    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)


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
    language: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
):
    """
    List all trained models.

    - **language**: Filter by training language
    - **is_active**: Filter by active status
    """
    db = _get_session()
    try:
        query = db.query(MLModel)

        if language:
            query = query.filter(MLModel.language == language)
        if is_active is not None:
            query = query.filter(MLModel.is_active == is_active)

        models = query.order_by(MLModel.created_at.desc()).all()

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
    finally:
        db.close()


@router.get("/models/{version}", response_model=Dict)
async def get_model(version: str):
    """Get detailed model metadata by version."""
    db = _get_session()
    try:
        model = db.query(MLModel).filter(MLModel.version == version).first()

        if not model:
            raise HTTPException(status_code=404, detail="Model not found")

        return model.to_dict()
    finally:
        db.close()


@router.post("/models/{version}/activate")
async def activate_model(version: str):
    """
    Set a model as active for serving predictions.

    Deactivates any currently active model.
    """
    global _active_model, _active_version

    db = _get_session()
    try:
        # Find model
        model = db.query(MLModel).filter(MLModel.version == version).first()

        if not model:
            raise HTTPException(status_code=404, detail="Model not found")

        # Deactivate all other models
        db.query(MLModel).update({"is_active": False, "deployed_at": None})

        # Activate this model
        model.is_active = True
        model.deployed_at = datetime.utcnow()
        db.commit()

        # Load model into memory
        trainer = _get_trainer_class()()
        trainer.load_checkpoint(version)
        _active_model = trainer
        _active_version = version

        logger.info(f"Activated model: {version}")

        return {
            "status": "success",
            "message": f"Model {version} is now active",
            "version": version,
        }
    finally:
        db.close()


@router.get("/evaluate")
async def get_evaluation_metrics():
    """
    Get evaluation metrics for active model.

    Returns latest metrics from validation set.
    """
    if _active_model is None:
        raise HTTPException(status_code=400, detail="No active model")

    db = _get_session()
    try:
        model = db.query(MLModel).filter(MLModel.version == _active_version).first()

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
    finally:
        db.close()


@router.post("/predict", response_model=PredictResponse)
async def predict_completion(request: PredictRequest):
    """
    Get code completion predictions from active model.

    - **context**: Code context for completion
    - **language**: Programming language
    - **top_k**: Number of suggestions to return
    """
    if _active_model is None:
        raise HTTPException(
            status_code=400, detail="No active model. Activate a model first."
        )

    try:
        # Tokenize context
        tokenizer = _active_model.train_loader.dataset.tokenizer
        context_ids = tokenizer.encode(request.context, max_length=128)
        import torch

        input_tensor = torch.tensor([context_ids], dtype=torch.long).to(
            _active_model.device
        )

        # Get predictions
        predictions = _active_model.model.predict(input_tensor, top_k=request.top_k)

        # Decode token IDs to text
        token_ids = predictions["tokens"][0].cpu().tolist()
        suggestions = [tokenizer.decode([tid]) for tid in token_ids]

        confidence = predictions["confidence"][0].item()

        return PredictResponse(
            suggestions=suggestions,
            confidence=confidence,
            model_version=_active_version,
        )

    except Exception as e:
        logger.error(f"Prediction failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
