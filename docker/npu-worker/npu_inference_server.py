"""
NPU Inference Server
FastAPI server for high-performance NPU inference
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import structlog

from npu_model_manager import NPUModelManager

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Global model manager
model_manager: Optional[NPUModelManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    global model_manager
    
    # Startup
    logger.info("Starting NPU Inference Server")
    model_manager = NPUModelManager()
    
    # Load default models if configured
    default_models = os.getenv("NPU_DEFAULT_MODELS", "").split(",")
    for model_id in default_models:
        if model_id.strip():
            await model_manager.load_model(
                model_id.strip(), 
                {"auto_load": True}
            )
    
    logger.info("NPU Inference Server started")
    
    yield
    
    # Shutdown
    logger.info("Shutting down NPU Inference Server")
    if model_manager:
        await model_manager.cleanup()
    logger.info("NPU Inference Server stopped")


# Create FastAPI app
app = FastAPI(
    title="AutoBot NPU Inference Server",
    description="High-performance AI inference using Intel NPU",
    version="1.0.0",
    lifespan=lifespan
)


# Request/Response Models
class InferenceRequest(BaseModel):
    model_id: str
    input_text: str
    max_tokens: Optional[int] = 512
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9


class InferenceResponse(BaseModel):
    model_id: str
    device: str
    response: str
    inference_time_ms: float
    inference_count: int


class ModelLoadRequest(BaseModel):
    model_id: str
    model_config: Dict[str, Any] = {}


class HealthResponse(BaseModel):
    status: str
    npu_available: bool
    loaded_models: int
    optimal_device: str


# API Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    if not model_manager:
        raise HTTPException(status_code=503, detail="Model manager not initialized")
    
    status = model_manager.get_model_status()
    
    return HealthResponse(
        status="healthy",
        npu_available=status["npu_available"],
        loaded_models=len(status["loaded_models"]),
        optimal_device=status["optimal_device"]
    )


@app.get("/models")
async def list_models():
    """List loaded models and their status"""
    if not model_manager:
        raise HTTPException(status_code=503, detail="Model manager not initialized")
    
    return model_manager.get_model_status()


@app.post("/models/load")
async def load_model(request: ModelLoadRequest):
    """Load a model for inference"""
    if not model_manager:
        raise HTTPException(status_code=503, detail="Model manager not initialized")
    
    success = await model_manager.load_model(request.model_id, request.model_config)
    
    if success:
        return {"status": "success", "model_id": request.model_id}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to load model {request.model_id}")


@app.delete("/models/{model_id}")
async def unload_model(model_id: str):
    """Unload a model to free memory"""
    if not model_manager:
        raise HTTPException(status_code=503, detail="Model manager not initialized")
    
    success = await model_manager.unload_model(model_id)
    
    if success:
        return {"status": "success", "model_id": model_id}
    else:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")


@app.post("/inference", response_model=InferenceResponse)
async def run_inference(request: InferenceRequest):
    """Run inference on NPU"""
    if not model_manager:
        raise HTTPException(status_code=503, detail="Model manager not initialized")
    
    result = await model_manager.inference(
        model_id=request.model_id,
        input_text=request.input_text,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p
    )
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    
    return InferenceResponse(**result)


@app.get("/devices")
async def list_devices():
    """List available OpenVINO devices"""
    if not model_manager:
        raise HTTPException(status_code=503, detail="Model manager not initialized")
    
    status = model_manager.get_model_status()
    
    return {
        "available_devices": status["available_devices"],
        "npu_available": status["npu_available"],
        "optimal_device": status["optimal_device"]
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "AutoBot NPU Inference Server",
        "version": "1.0.0",
        "description": "High-performance AI inference using Intel NPU"
    }


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("NPU_WORKER_HOST", "0.0.0.0")
    port = int(os.getenv("NPU_WORKER_PORT", 8081))
    workers = int(os.getenv("NPU_WORKER_WORKERS", 1))
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        workers=workers,
        log_level="info"
    )