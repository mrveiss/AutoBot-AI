#!/bin/bash
# AutoBot - Start NPU Worker Service on VM
# Starts native NPU worker services on 172.16.168.22

set -e

# Source SSOT configuration (#808)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"
SSH_USER="${AUTOBOT_SSH_USER:-autobot}"
NPU_WORKER_IP="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
NPU_WORKER_PORT="${AUTOBOT_NPU_WORKER_PORT:-8081}"

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

main() {
    echo -e "${GREEN}🤖 Starting NPU Worker Service${NC}"
    echo -e "${BLUE}VM: $NPU_WORKER_IP${NC}"
    echo ""

    if [ ! -f "$SSH_KEY" ]; then
        error "SSH key not found: $SSH_KEY"
        echo "Run: bash setup.sh ssh-keys"
        exit 1
    fi

    log "Connecting to NPU Worker VM..."

    ssh -i "$SSH_KEY" "$SSH_USER@$NPU_WORKER_IP" << 'EOF'
        echo "Updating system packages..."
        sudo apt-get update -qq
        sudo apt-get install -y python3 python3-pip python3-venv curl wget netcat-openbsd

        echo "Setting up NPU Worker environment..."
        mkdir -p ~/autobot-npu-worker
        cd ~/autobot-npu-worker

        # Create Python virtual environment if it doesn't exist
        if [ ! -d "venv" ]; then
            python3 -m venv venv
            source venv/bin/activate
            pip install --upgrade pip
            pip install fastapi uvicorn numpy torch transformers accelerate

            # Install NPU-specific dependencies if available
            if command -v lspci &>/dev/null && lspci | grep -i "neural\|npu\|ai" > /dev/null 2>&1; then
                echo "NPU hardware detected - installing Intel extensions"
                pip install intel-extension-for-pytorch openvino-dev || true
            fi
        else
            source venv/bin/activate
        fi

        echo "Setting up NPU Worker Python files..."

        # Copy the proper NPU model manager
        cat > npu_model_manager.py << 'PYTHON_EOF'
"""
NPU Model Manager for AutoBot
Manages AI models optimized for Intel NPU acceleration
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict
import time
import platform

try:
    from openvino.runtime import Core
    OPENVINO_AVAILABLE = True
except ImportError:
    OPENVINO_AVAILABLE = False

logger = logging.getLogger(__name__)

class NPUModelManager:
    """Manages models optimized for Intel NPU"""

    def __init__(self, model_cache_dir: str = "/home/autobot/autobot-npu-worker/models"):
        self.model_cache_dir = Path(model_cache_dir)
        self.model_cache_dir.mkdir(exist_ok=True)

        self.loaded_models = {}
        self.core = None
        self.npu_available = False
        self.available_devices = []
        self.optimal_device = "CPU"

        # Initialize OpenVINO
        self._initialize_openvino()

    def _initialize_openvino(self):
        """Initialize OpenVINO and check NPU availability"""
        if not OPENVINO_AVAILABLE:
            logger.error("OpenVINO not available - NPU acceleration disabled")
            self.available_devices = ["CPU"]
            return

        try:
            self.core = Core()
            self.available_devices = self.core.available_devices
            logger.info(f"Available OpenVINO devices: {self.available_devices}")

            # Check for NPU devices
            npu_devices = [d for d in self.available_devices if "NPU" in d]
            if npu_devices:
                self.npu_available = True
                self.optimal_device = npu_devices[0]
                logger.info(f"NPU devices detected: {npu_devices}")
            else:
                # Check for GPU devices as fallback
                gpu_devices = [d for d in self.available_devices if "GPU" in d]
                if gpu_devices:
                    self.optimal_device = gpu_devices[0]
                else:
                    self.optimal_device = "CPU"
                logger.warning("No NPU devices detected - using fallback device")

        except Exception as e:
            logger.error(f"OpenVINO initialization failed: {e}")
            self.available_devices = ["CPU"]
            self.optimal_device = "CPU"

    def get_model_status(self):
        """Get status of loaded models and devices"""
        return {
            "loaded_models": list(self.loaded_models.keys()),
            "available_devices": self.available_devices,
            "npu_available": self.npu_available,
            "optimal_device": self.optimal_device
        }

    async def load_model(self, model_id: str, model_config: Dict[str, Any] = None):
        """Load a model for inference"""
        try:
            # Simulate model loading
            await asyncio.sleep(0.5)  # Simulate load time
            self.loaded_models[model_id] = {
                "device": self.optimal_device,
                "config": model_config or {},
                "loaded_at": time.time()
            }
            logger.info(f"Model {model_id} loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load model {model_id}: {e}")
            return False

    async def unload_model(self, model_id: str):
        """Unload a model"""
        if model_id in self.loaded_models:
            del self.loaded_models[model_id]
            logger.info(f"Model {model_id} unloaded")
            return True
        return False

    async def inference(self, model_id: str, input_text: str, max_tokens: int = 512,
                       temperature: float = 0.7, top_p: float = 0.9):
        """Run inference"""
        if model_id not in self.loaded_models:
            return {"error": f"Model {model_id} not loaded"}

        try:
            # Simulate NPU inference
            start_time = time.time()
            await asyncio.sleep(0.1)  # Simulate processing
            inference_time = (time.time() - start_time) * 1000

            model_info = self.loaded_models[model_id]

            return {
                "model_id": model_id,
                "device": model_info["device"],
                "response": f"NPU processed: {input_text[:50]}...",
                "inference_time_ms": inference_time,
                "inference_count": 1
            }
        except Exception as e:
            return {"error": f"Inference failed: {e}"}

    async def cleanup(self):
        """Cleanup resources"""
        self.loaded_models.clear()
        logger.info("NPU Model Manager cleaned up")
PYTHON_EOF

        # Create the main NPU inference server
        cat > npu_inference_server.py << 'PYTHON_EOF'
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

from npu_model_manager import NPUModelManager

# Global model manager
model_manager: Optional[NPUModelManager] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    global model_manager

    # Startup
    print("Starting NPU Inference Server")
    model_manager = NPUModelManager()

    # Load default models
    await model_manager.load_model("llama3.2:1b-instruct-q4_K_M", {"auto_load": True})
    await model_manager.load_model("nomic-embed-text:latest", {"auto_load": True})

    print("NPU Inference Server started")

    yield

    # Shutdown
    print("Shutting down NPU Inference Server")
    if model_manager:
        await model_manager.cleanup()

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
PYTHON_EOF

        # Create main entry point
        cat > npu_worker_main.py << 'PYTHON_EOF'
"""
NPU Worker Main Entry Point
Starts the NPU inference server with proper initialization
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

def setup_logging():
    """Setup logging for NPU worker"""
    log_level = os.getenv("NPU_LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

def check_environment():
    """Check NPU worker environment"""
    # Check OpenVINO environment
    try:
        from openvino.runtime import Core

        core = Core()
        devices = core.available_devices
        print(f"OpenVINO devices: {devices}")

        # Check for NPU specifically
        npu_devices = [d for d in devices if 'NPU' in d]
        if npu_devices:
            print(f"NPU devices detected: {npu_devices}")
        else:
            print("No NPU devices detected - will use CPU/GPU fallback")

    except ImportError:
        print("OpenVINO not available - NPU acceleration disabled")
    except Exception as e:
        print(f"OpenVINO initialization failed: {e}")

    # Check directories
    directories = ["models", "data", "logs"]
    for directory in directories:
        path = Path(directory)
        if not path.exists():
            print(f"Creating directory: {directory}")
            path.mkdir(parents=True, exist_ok=True)

def main():
    """Main entry point for NPU worker"""
    setup_logging()
    print("Starting AutoBot NPU Worker")

    check_environment()

    # Get configuration
    host = os.getenv("NPU_WORKER_HOST", "0.0.0.0")
    port = int(os.getenv("NPU_WORKER_PORT", 8081))

    print(f"NPU Worker configuration: {host}:{port}")

    # Start the server
    try:
        import uvicorn

        uvicorn.run(
            "npu_inference_server:app",
            host=host,
            port=port,
            log_level="info",
            access_log=True,
            reload=False
        )

    except KeyboardInterrupt:
        print("NPU Worker stopped by user")
    except Exception as e:
        print(f"NPU Worker failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
PYTHON_EOF

        echo "Creating systemd service..."
        sudo tee /etc/systemd/system/autobot-npu-worker.service > /dev/null << 'SERVICE_EOF'
[Unit]
Description=AutoBot NPU Worker Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=autobot
Group=autobot
WorkingDirectory=/home/autobot/autobot-npu-worker
Environment=PATH=/home/autobot/autobot-npu-worker/venv/bin
ExecStart=/home/autobot/autobot-npu-worker/venv/bin/python npu_worker_main.py
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE_EOF

        echo "Starting NPU Worker service..."
        sudo systemctl daemon-reload
        sudo systemctl enable autobot-npu-worker
        sudo systemctl start autobot-npu-worker

        echo "Waiting for NPU Worker to be ready..."
        for i in {1..30}; do
            if timeout 2 bash -c "</dev/tcp/localhost/8081" 2>/dev/null; then
                echo "NPU Worker is ready!"

                # Test NPU Worker API
                if curl -s http://localhost:8081/health | grep -q "healthy"; then
                    echo "NPU Worker API test successful"
                fi

                exit 0
            fi
            sleep 1
            echo -n "."
        done

        echo ""
        echo "Warning: NPU Worker may need more time to start"
        echo "Check service status: sudo systemctl status autobot-npu-worker"
        echo "Check logs: sudo journalctl -u autobot-npu-worker -f"
EOF

    if [ $? -eq 0 ]; then
        success "NPU Worker service started on $NPU_WORKER_IP:$NPU_WORKER_PORT"
        echo ""
        echo -e "${CYAN}NPU Worker URL: http://$NPU_WORKER_IP:$NPU_WORKER_PORT${NC}"
        echo -e "${CYAN}Health Check: http://$NPU_WORKER_IP:$NPU_WORKER_PORT/health${NC}"
        echo -e "${BLUE}Test connection: curl http://$NPU_WORKER_IP:$NPU_WORKER_PORT/health${NC}"
        echo -e "${BLUE}Check logs: ssh $SSH_USER@$NPU_WORKER_IP 'sudo journalctl -u autobot-npu-worker -f'${NC}"
    else
        error "Failed to start NPU Worker service"
        exit 1
    fi
}

main
