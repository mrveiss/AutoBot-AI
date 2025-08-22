#!/usr/bin/env python3
"""
Simple NPU Worker for Development
=================================

A lightweight NPU Worker that provides the expected API endpoints
without requiring actual NPU hardware.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("npu_worker")

app = FastAPI(
    title="AutoBot NPU Worker (Simple)",
    description="Lightweight NPU Worker for development",
    version="1.0.0",
)

# Mock NPU state
npu_state = {
    "device": "CPU",  # Fallback to CPU
    "models_loaded": {},
    "requests_processed": 0,
    "start_time": datetime.now(),
}


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    device: str
    models_loaded: int
    uptime_seconds: float
    requests_processed: int


class InferenceRequest(BaseModel):
    """Inference request"""

    model: str
    input_text: str
    max_tokens: Optional[int] = 100
    temperature: Optional[float] = 0.7


class InferenceResponse(BaseModel):
    """Inference response"""

    model: str
    output_text: str
    processing_time: float
    device_used: str


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """NPU Worker health check endpoint"""
    uptime = (datetime.now() - npu_state["start_time"]).total_seconds()

    return HealthResponse(
        status="healthy",
        device=npu_state["device"],
        models_loaded=len(npu_state["models_loaded"]),
        uptime_seconds=uptime,
        requests_processed=npu_state["requests_processed"],
    )


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "AutoBot NPU Worker (Simple)",
        "status": "running",
        "version": "1.0.0",
        "device": npu_state["device"],
    }


@app.get("/info")
async def info():
    """Get NPU Worker information"""
    uptime = (datetime.now() - npu_state["start_time"]).total_seconds()

    return {
        "service": "AutoBot NPU Worker",
        "version": "1.0.0",
        "device": npu_state["device"],
        "models_loaded": list(npu_state["models_loaded"].keys()),
        "uptime_seconds": uptime,
        "requests_processed": npu_state["requests_processed"],
        "capabilities": ["text_generation", "code_analysis", "semantic_search"],
    }


@app.post("/inference", response_model=InferenceResponse)
async def process_inference(request: InferenceRequest):
    """Process inference request (mock implementation)"""
    import time

    start_time = time.time()

    # Simulate processing time
    await asyncio.sleep(0.1)

    # Mock response based on input
    if "code" in request.input_text.lower():
        output_text = (
            f"# Code analysis for: {request.input_text[:50]}...\n"
            "# This is a mock response from NPU Worker"
        )
    elif "search" in request.input_text.lower():
        output_text = (
            f"Search results for '{request.input_text}': "
            "[mock result 1, mock result 2, mock result 3]"
        )
    else:
        output_text = (
            f"NPU Worker processed: {request.input_text}\n\n"
            "This is a development mock response. The actual NPU Worker "
            "would provide AI-accelerated inference here."
        )

    processing_time = time.time() - start_time
    npu_state["requests_processed"] += 1

    return InferenceResponse(
        model=request.model,
        output_text=output_text,
        processing_time=processing_time,
        device_used=npu_state["device"],
    )


@app.get("/models")
async def list_models():
    """List available models"""
    return {
        "models": [
            {"name": "code-analyzer", "type": "code_analysis", "status": "ready"},
            {"name": "semantic-search", "type": "embedding", "status": "ready"},
            {"name": "text-generator", "type": "text_generation", "status": "ready"},
        ]
    }


@app.post("/models/{model_name}/load")
async def load_model(model_name: str):
    """Load a model (mock implementation)"""
    # Simulate model loading
    await asyncio.sleep(1)

    npu_state["models_loaded"][model_name] = {
        "loaded_at": datetime.now(),
        "device": npu_state["device"],
    }

    return {
        "status": "success",
        "model": model_name,
        "device": npu_state["device"],
        "message": f"Model {model_name} loaded successfully (mock)",
    }


@app.delete("/models/{model_name}")
async def unload_model(model_name: str):
    """Unload a model"""
    if model_name in npu_state["models_loaded"]:
        del npu_state["models_loaded"][model_name]
        return {"status": "success", "message": f"Model {model_name} unloaded"}
    else:
        raise HTTPException(status_code=404, detail=f"Model {model_name} not found")


@app.get("/stats")
async def get_stats():
    """Get NPU Worker statistics"""
    return {
        "device": npu_state["device"],
        "models_loaded": len(npu_state["models_loaded"]),
        "requests_processed": npu_state["requests_processed"],
        "uptime_seconds": (datetime.now() - npu_state["start_time"]).total_seconds(),
        "memory_usage": "N/A (mock)",
        "cpu_usage": "N/A (mock)",
    }


if __name__ == "__main__":
    host = os.getenv("NPU_WORKER_HOST", "0.0.0.0")
    port = int(os.getenv("NPU_WORKER_PORT", "8081"))

    logger.info(f"Starting NPU Worker (Simple) on {host}:{port}")
    logger.info(f"Device: {npu_state['device']}")
    logger.info("This is a development version - no actual NPU required")

    uvicorn.run(app, host=host, port=port, log_level="info")
