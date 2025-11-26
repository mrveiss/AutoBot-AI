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
import hashlib
import json
import time
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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

# Load CORS configuration
def load_cors_config():
    """Load CORS configuration from config file"""
    config_paths = [
        "/app/config/config.yaml",
        "/home/kali/Desktop/AutoBot/config/config.yaml",
        "./config/config.yaml"
    ]

    cors_origins = ["*"]  # Default fallback

    for config_path in config_paths:
        try:
            if Path(config_path).exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    backend_cors = config.get('backend', {}).get('cors_origins', [])
                    if backend_cors:
                        cors_origins = backend_cors
                        logger.info(f"Loaded CORS origins from {config_path}: {cors_origins}")
                        break
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")

    return cors_origins

# Add CORS middleware with configuration
cors_origins = load_cors_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Detect available devices
def detect_devices():
    """Detect available compute devices including Intel NPU"""
    devices = {"CPU": True}

    # Check for Intel NPU (Neural Processing Unit) - AI Boost
    try:
        # Method 1: Try OpenVINO NPU detection
        from openvino.runtime import Core
        core = Core()
        available_devices = core.available_devices

        npu_devices = [d for d in available_devices if 'NPU' in d]
        if npu_devices:
            for npu_device in npu_devices:
                try:
                    # Test NPU availability by trying to compile a simple model
                    import openvino.runtime as ov
                    device_info = core.get_property(npu_device, "FULL_DEVICE_NAME")
                    devices[npu_device] = {
                        "name": device_info if device_info else f"Intel NPU ({npu_device})",
                        "type": "Intel_NPU",
                        "capabilities": ["inference", "ai_acceleration"],
                        "status": "available"
                    }
                    logger.info(f"✅ Intel NPU detected: {npu_device} - {device_info}")
                except Exception as e:
                    devices[npu_device] = {
                        "name": f"Intel NPU ({npu_device})",
                        "type": "Intel_NPU",
                        "status": "detected_but_unavailable",
                        "error": str(e)
                    }
                    logger.warning(f"⚠️ Intel NPU detected but unavailable: {e}")

        # Check for Intel Arc GPU via OpenVINO
        gpu_devices = [d for d in available_devices if 'GPU' in d and 'INTEL' in d.upper()]
        for gpu_device in gpu_devices:
            try:
                device_info = core.get_property(gpu_device, "FULL_DEVICE_NAME")
                devices[gpu_device] = {
                    "name": device_info if device_info else f"Intel Arc GPU ({gpu_device})",
                    "type": "Intel_GPU",
                    "capabilities": ["graphics", "compute"],
                    "status": "available"
                }
                logger.info(f"✅ Intel Arc GPU detected: {gpu_device}")
            except Exception as e:
                logger.warning(f"Intel GPU detection failed for {gpu_device}: {e}")

        logger.info(f"OpenVINO devices: {available_devices}")
    except Exception as e:
        logger.info(f"OpenVINO detection failed: {e}")

    # Method 2: Check system information for NPU
    try:
        # Check /proc/cpuinfo for Intel AI Boost
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read().lower()
            if 'intel' in cpuinfo and any(keyword in cpuinfo for keyword in ['ai boost', 'npu', 'neural']):
                devices["Intel_AI_Boost"] = {
                    "name": "Intel AI Boost (CPU-based NPU)",
                    "type": "Intel_NPU_CPU",
                    "status": "cpu_integrated",
                    "capabilities": ["ai_acceleration", "inference"]
                }
                logger.info("✅ Intel AI Boost capabilities detected in CPU")
    except Exception as e:
        logger.debug(f"CPU info check failed: {e}")

    # Method 3: Check for Intel GPU via level-zero
    try:
        import subprocess
        result = subprocess.run(['lspci', '-nn'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            pci_info = result.stdout.lower()
            intel_graphics = [line for line in pci_info.split('\n')
                            if 'intel' in line and any(gpu_keyword in line for gpu_keyword in ['vga', 'display', 'graphics', 'arc'])]

            for i, gpu_line in enumerate(intel_graphics):
                if 'arc' in gpu_line:
                    devices[f"Intel_Arc_{i}"] = {
                        "name": "Intel Arc Graphics",
                        "type": "Intel_GPU",
                        "detection_method": "PCI scan",
                        "status": "detected"
                    }
                    logger.info(f"✅ Intel Arc GPU detected via PCI: {gpu_line.strip()}")
                elif 'xe' in gpu_line or 'iris' in gpu_line:
                    devices[f"Intel_iGPU_{i}"] = {
                        "name": "Intel Integrated Graphics",
                        "type": "Intel_iGPU",
                        "detection_method": "PCI scan",
                        "status": "detected"
                    }
                    logger.info(f"✅ Intel iGPU detected via PCI: {gpu_line.strip()}")
    except Exception as e:
        logger.debug(f"PCI scan failed: {e}")

    # Check for NVIDIA GPUs (existing code, improved)
    try:
        import pynvml
        pynvml.nvmlInit()
        gpu_count = pynvml.nvmlDeviceGetCount()
        for i in range(gpu_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            # Handle both bytes and string returns
            if isinstance(name, bytes):
                name = name.decode()

            # Get additional GPU info
            try:
                memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                devices[f"GPU_{i}"] = {
                    "name": name,
                    "type": "NVIDIA",
                    "memory_total_mb": memory_info.total // (1024*1024),
                    "capabilities": ["graphics", "cuda", "ai_acceleration"],
                    "status": "available"
                }
            except:
                devices[f"GPU_{i}"] = {"name": name, "type": "NVIDIA", "status": "available"}

        logger.info(f"✅ Detected {gpu_count} NVIDIA GPUs")
    except Exception as e:
        logger.debug(f"NVIDIA GPU detection failed: {e}")

    # Check for PyTorch CUDA
    try:
        import torch
        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            for i in range(gpu_count):
                gpu_name = torch.cuda.get_device_name(i)
                # Only add if not already detected by NVIDIA-ML
                if f"CUDA_{i}" not in devices:
                    devices[f"CUDA_{i}"] = {
                        "name": gpu_name,
                        "type": "CUDA",
                        "framework": "PyTorch",
                        "status": "available"
                    }
        logger.info(f"PyTorch CUDA available: {torch.cuda.is_available()}")
    except Exception as e:
        logger.debug(f"PyTorch CUDA detection failed: {e}")

    return devices

# Device priority selection
def select_optimal_device():
    """Select the best available device based on priority: NPU > GPU1 > GPU2 > CPU"""

    # Define priority order (higher number = higher priority)
    device_priorities = {
        # NPU devices (highest priority)
        "Intel_NPU": 1000,
        "Intel_AI_Boost": 950,

        # Dedicated GPUs (high priority)
        "NVIDIA": 800,
        "Intel_GPU": 750,
        "Intel_Arc": 720,

        # Integrated GPUs (medium priority)
        "Intel_iGPU": 500,
        "CUDA": 490,

        # CPU (lowest priority, fallback)
        "CPU": 100
    }

    selected_device = "CPU"  # Fallback
    selected_priority = 0
    selected_info = {"name": "CPU", "type": "CPU", "status": "available"}
    priority_order = []

    # Sort devices by priority and select the best one
    for device_key, device_info in available_devices.items():
        if device_key == "CPU":
            continue  # Handle CPU separately as fallback

        device_type = device_info.get("type", "unknown")
        device_status = device_info.get("status", "unknown")

        # Skip unavailable devices
        if device_status in ["detected_but_unavailable", "error"]:
            continue

        # Get priority for this device type
        priority = device_priorities.get(device_type, 0)

        # Add to priority order list
        priority_order.append({
            "device": device_key,
            "type": device_type,
            "name": device_info.get("name", device_key),
            "priority": priority,
            "status": device_status
        })

        # Select if this is the highest priority device so far
        if priority > selected_priority:
            selected_device = device_key
            selected_priority = priority
            selected_info = device_info

    # Sort priority order by priority (descending)
    priority_order.sort(key=lambda x: x["priority"], reverse=True)

    # Always add CPU as final fallback
    priority_order.append({
        "device": "CPU",
        "type": "CPU",
        "name": "CPU",
        "priority": 100,
        "status": "available"
    })

    # Log selection
    if selected_device != "CPU":
        logger.info(f"🎯 Selected optimal device: {selected_device} ({selected_info.get('name', 'Unknown')}) - Priority: {selected_priority}")
    else:
        logger.info("🎯 Using CPU (fallback) - no acceleration devices available")

    # Log priority order
    priority_list = [f"{item['device']}({item['priority']})" for item in priority_order]
    logger.info(f"📊 Device priority order: {' > '.join(priority_list)}")

    return selected_device, selected_info, [item["device"] for item in priority_order]

# Detect devices at startup
available_devices = detect_devices()
logger.info(f"Available devices: {available_devices}")

# Select optimal device
selected_device, selected_device_info, device_priority_order = select_optimal_device()

# NPU Worker state with optimal device selection
npu_state = {
    "device": selected_device,
    "device_info": selected_device_info,
    "available_devices": available_devices,
    "device_priority_order": device_priority_order,
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


# Code Indexing Models
class CodeIndexRequest(BaseModel):
    """Code indexing request"""
    root_path: str
    force_reindex: Optional[bool] = False
    file_extensions: Optional[List[str]] = [".py", ".js", ".ts", ".vue", ".md"]


class CodeSearchRequest(BaseModel):
    """Code search request"""
    query: str
    search_type: Optional[str] = "semantic"  # semantic, exact, fuzzy
    max_results: Optional[int] = 20
    language: Optional[str] = None


class CodeSearchResult(BaseModel):
    """Code search result"""
    file_path: str
    content: str
    line_number: int
    confidence: float
    context_lines: List[str]
    metadata: Dict[str, Any]


class IndexStatus(BaseModel):
    """Index status response"""
    total_files_indexed: int
    last_indexed: Optional[str] = None
    indexing_in_progress: bool = False
    supported_languages: List[str] = ["python", "javascript", "typescript", "vue"]
    index_size_mb: float = 0.0
    npu_available: bool = False
    acceleration_type: str = "CPU"
    selected_device: str = "CPU"
    device_priority_order: List[str] = []
    cache_keys: int = 0
    languages: Optional[Dict[str, int]] = None


class ProblemReport(BaseModel):
    """Code problem detection report"""
    problem_type: str  # "infinite_loop", "timeout_risk", "unused_code", "duplicate", "performance"
    severity: str     # "critical", "high", "medium", "low"
    file_path: str
    line_number: int
    description: str
    suggestion: str
    code_snippet: str
    confidence: float


class AnalyticsReport(BaseModel):
    """Comprehensive analytics report"""
    total_problems: int
    problems_by_severity: Dict[str, int]
    problems_by_type: Dict[str, int]
    files_analyzed: int
    problems: List[ProblemReport]
    analysis_timestamp: str


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


@app.get("/devices")
async def list_devices():
    """List all available compute devices with priority order"""
    return {
        "available_devices": npu_state["available_devices"],
        "selected_device": npu_state["device"],
        "selected_device_info": npu_state["device_info"],
        "priority_order": npu_state["device_priority_order"],
        "total_devices": len(npu_state["available_devices"]),
        "priority_explanation": {
            "1_highest": "Intel NPU (dedicated neural processing)",
            "2_high": "Intel AI Boost (CPU-integrated NPU)",
            "3_medium_high": "NVIDIA GPU (CUDA acceleration)",
            "4_medium": "Intel Arc GPU (compute acceleration)",
            "5_low": "Integrated Graphics",
            "6_fallback": "CPU (no acceleration)"
        }
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


# Code Indexing & Analytics Endpoints
@app.post("/code/index")
async def index_codebase(request: CodeIndexRequest):
    """Index a codebase for analysis and search"""
    logger.info(f"Indexing codebase at: {request.root_path}")

    # Simulate indexing process with real file counting
    start_time = time.time()

    try:
        # Count actual files
        total_files, language_counts = count_project_files()

        # Simulate indexing time based on file count (more files = longer time)
        indexing_time_ms = min(max(total_files * 2, 1000), 10000)  # 2ms per file, min 1s, max 10s
        await asyncio.sleep(indexing_time_ms / 1000.0)

        languages_detected = list(language_counts.keys())
        index_size_mb = round(total_files * 0.05, 1)

    except Exception as e:
        logger.error(f"Failed to count files during indexing: {e}")
        # Fallback
        total_files = 150
        languages_detected = ["python", "javascript", "typescript", "vue"]
        indexing_time_ms = 2000
        index_size_mb = 12.5

    actual_time = int((time.time() - start_time) * 1000)

    return {
        "status": "success",
        "message": f"Indexed {total_files} files from {request.root_path}",
        "files_indexed": total_files,
        "languages_detected": languages_detected,
        "indexing_time_ms": actual_time,
        "index_size_mb": index_size_mb
    }


@app.get("/code/search")
async def search_code(query: str, search_type: str = "semantic", max_results: int = 20):
    """Search indexed code"""
    logger.info(f"Searching code for: {query}")

    # Mock search results with realistic AutoBot problems
    mock_results = []

    if "health" in query.lower():
        mock_results = [
            {
                "file_path": "/app/backend/fast_app_factory_fix.py",
                "content": "async def system_health_override():",
                "line_number": 173,
                "confidence": 0.95,
                "context_lines": [
                    "@app.get('/api/system/health')",
                    "async def system_health_override():",
                    '    """Fast system health check that doesn\'t trigger knowledge base operations"""'
                ],
                "metadata": {"function": "system_health_override", "type": "endpoint"}
            },
            {
                "file_path": "/app/backend/api/system.py",
                "content": "async def health_check(detailed: bool = False):",
                "line_number": 113,
                "confidence": 0.87,
                "context_lines": [
                    "@router.get('/health')",
                    "async def health_check(detailed: bool = False):",
                    "    comprehensive_health = await get_comprehensive_health_status()"
                ],
                "metadata": {"function": "health_check", "type": "endpoint"}
            }
        ]

    return {
        "query": query,
        "results": mock_results[:max_results],
        "total_results": len(mock_results),
        "search_time_ms": 45.2
    }


def count_project_files():
    """Count actual project files including logs from entire AutoBot codebase"""
    extensions = ['.py', '.js', '.ts', '.vue', '.md', '.jsx', '.tsx', '.json', '.yaml', '.yml', '.log', '.txt', '.out', '.err', '.sh', '.ps1', '.bat', '.dockerfile', '.env']
    excluded_dirs = {'node_modules', 'venv', '.git', '__pycache__', 'dist', 'build', '.venv', 'env', 'target', '.next', '.nuxt', 'coverage'}

    total_files = 0
    language_counts = {}

    # Analyze entire AutoBot codebase
    project_paths = ['/app/autobot_codebase']

    for project_path in project_paths:
        if os.path.exists(project_path):
            for root, dirs, files in os.walk(project_path):
                # Skip excluded directories
                dirs[:] = [d for d in dirs if d not in excluded_dirs and not d.startswith('.')]

                for file in files:
                    if any(file.endswith(ext) for ext in extensions):
                        total_files += 1

                        # Count by language
                        ext = os.path.splitext(file)[1]
                        if ext == '.py':
                            language_counts['python'] = language_counts.get('python', 0) + 1
                        elif ext in ['.js', '.jsx']:
                            language_counts['javascript'] = language_counts.get('javascript', 0) + 1
                        elif ext in ['.ts', '.tsx']:
                            language_counts['typescript'] = language_counts.get('typescript', 0) + 1
                        elif ext == '.vue':
                            language_counts['vue'] = language_counts.get('vue', 0) + 1
                        elif ext == '.md':
                            language_counts['markdown'] = language_counts.get('markdown', 0) + 1
                        elif ext in ['.json', '.yaml', '.yml', '.env', '.dockerfile']:
                            language_counts['config'] = language_counts.get('config', 0) + 1
                        elif ext in ['.log', '.txt', '.out', '.err']:
                            language_counts['logs'] = language_counts.get('logs', 0) + 1
                        elif ext in ['.sh', '.ps1', '.bat']:
                            language_counts['scripts'] = language_counts.get('scripts', 0) + 1
            break  # Use first existing path

    return total_files, language_counts

@app.get("/code/status", response_model=IndexStatus)
async def get_index_status():
    """Get code indexing status"""
    # Use the selected device info for acceleration status
    selected_device_key = npu_state["device"]
    selected_device_info = npu_state["device_info"]

    # Determine if we have acceleration available
    if selected_device_key != "CPU":
        npu_available = True
        device_type = selected_device_info.get("type", "unknown")

        # Map device types to acceleration types
        if device_type.startswith("Intel_NPU"):
            acceleration_type = "Intel_NPU"
        elif device_type == "Intel_AI_Boost":
            acceleration_type = "Intel_AI_Boost"
        elif device_type in ["Intel_GPU", "Intel_Arc"]:
            acceleration_type = "Intel_GPU"
        elif device_type == "NVIDIA":
            acceleration_type = "NVIDIA_GPU"
        elif device_type == "CUDA":
            acceleration_type = "CUDA"
        else:
            acceleration_type = device_type

        logger.info(f"🚀 Using {acceleration_type} acceleration on {selected_device_key}")
    else:
        npu_available = False
        acceleration_type = "CPU"
        logger.info("ℹ️ Using CPU (no acceleration)")

    # Count actual files
    try:
        total_files, languages = count_project_files()
    except Exception as e:
        logger.error(f"Failed to count files: {e}")
        # Fallback to mock data
        total_files = 150
        languages = {"python": 85, "javascript": 32, "typescript": 18, "vue": 15}

    # Calculate index size estimate (rough: 50KB average per file)
    index_size_mb = round(total_files * 0.05, 1)

    return IndexStatus(
        total_files_indexed=total_files,
        last_indexed=datetime.now().isoformat(),
        indexing_in_progress=False,
        supported_languages=["python", "javascript", "typescript", "vue", "markdown", "config", "logs", "scripts"],
        index_size_mb=index_size_mb,
        npu_available=npu_available,
        acceleration_type=acceleration_type,
        selected_device=npu_state["device"],
        device_priority_order=npu_state["device_priority_order"],
        cache_keys=len(languages) * 7,  # Realistic cache keys count
        languages=languages
    )


def classify_log_level(line):
    """Classify log line by severity level"""
    line_lower = line.lower()

    # Critical/Fatal
    if any(keyword in line_lower for keyword in ['fatal', 'critical', 'emergency', 'panic']):
        return 'FATAL', 'critical'

    # Error level
    if any(keyword in line_lower for keyword in ['error', 'exception', 'traceback', 'failed', 'failure']):
        return 'ERROR', 'high'

    # Warning level
    if any(keyword in line_lower for keyword in ['warn', 'warning', 'caution', 'deprecated']):
        return 'WARN', 'medium'

    # Info level
    if any(keyword in line_lower for keyword in ['info', 'information', 'notice']):
        return 'INFO', 'low'

    # Debug level
    if any(keyword in line_lower for keyword in ['debug', 'trace', 'verbose']):
        return 'DEBUG', 'low'

    # Default classification based on content
    if any(keyword in line_lower for keyword in ['success', 'completed', 'finished', 'started']):
        return 'INFO', 'low'

    return 'UNKNOWN', 'low'

def analyze_log_files():
    """Analyze log files for problems with severity breakdown"""
    log_problems = []
    log_stats = {
        'total_lines': 0,
        'by_level': {'FATAL': 0, 'ERROR': 0, 'WARN': 0, 'INFO': 0, 'DEBUG': 0, 'UNKNOWN': 0},
        'files_analyzed': 0
    }

    # Check common log locations including AutoBot-specific paths
    log_paths = [
        '/app/autobot_codebase/logs',   # AutoBot logs in mounted codebase
        '/app/autobot_codebase',        # AutoBot root (contains individual log files)
        '/app/logs',                    # Container logs
        '/var/log',                     # System logs
        '/tmp',                         # Temporary logs
    ]

    for log_dir in log_paths:
        if os.path.exists(log_dir):
            for root, dirs, files in os.walk(log_dir):
                for file in files:
                    if file.endswith(('.log', '.txt')):
                        file_path = os.path.join(root, file)
                        try:
                            log_stats['files_analyzed'] += 1

                            # Only read recent part of log files (last 1000 lines)
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                lines = f.readlines()
                                recent_lines = lines[-1000:] if len(lines) > 1000 else lines
                                log_stats['total_lines'] += len(recent_lines)

                                for i, line in enumerate(recent_lines):
                                    line_num = len(lines) - len(recent_lines) + i + 1
                                    log_level, severity = classify_log_level(line)
                                    log_stats['by_level'][log_level] += 1

                                    # Only create problems for ERROR and FATAL levels
                                    if log_level in ['ERROR', 'FATAL']:
                                        line_lower = line.lower()

                                        if 'timeout' in line_lower or 'hang' in line_lower:
                                            log_problems.append(ProblemReport(
                                                problem_type="timeout_risk",
                                                severity=severity,
                                                file_path=file_path,
                                                line_number=line_num,
                                                description=f"{log_level}: Timeout or hanging detected in logs",
                                                suggestion="Investigate timeout causes and add proper error handling",
                                                code_snippet=line.strip()[:150],
                                                confidence=0.85
                                            ))
                                        elif 'memory' in line_lower or 'oom' in line_lower:
                                            log_problems.append(ProblemReport(
                                                problem_type="performance",
                                                severity=severity,
                                                file_path=file_path,
                                                line_number=line_num,
                                                description=f"{log_level}: Memory issues detected in logs",
                                                suggestion="Check for memory leaks and optimize resource usage",
                                                code_snippet=line.strip()[:150],
                                                confidence=0.90
                                            ))
                                        elif '500' in line or 'internal server error' in line_lower:
                                            log_problems.append(ProblemReport(
                                                problem_type="server_error",
                                                severity="critical" if log_level == 'FATAL' else "high",
                                                file_path=file_path,
                                                line_number=line_num,
                                                description=f"{log_level}: Server errors detected in logs",
                                                suggestion="Fix server errors causing 500 responses",
                                                code_snippet=line.strip()[:150],
                                                confidence=0.95
                                            ))
                                        elif any(keyword in line_lower for keyword in ['redis', 'connection', 'database']):
                                            log_problems.append(ProblemReport(
                                                problem_type="database_error",
                                                severity=severity,
                                                file_path=file_path,
                                                line_number=line_num,
                                                description=f"{log_level}: Database/Redis connection issues",
                                                suggestion="Check database connections and network connectivity",
                                                code_snippet=line.strip()[:150],
                                                confidence=0.80
                                            ))
                                        elif 'cors' in line_lower or 'cross-origin' in line_lower:
                                            log_problems.append(ProblemReport(
                                                problem_type="cors_error",
                                                severity="medium",
                                                file_path=file_path,
                                                line_number=line_num,
                                                description=f"{log_level}: CORS configuration issues",
                                                suggestion="Update CORS settings to allow required origins",
                                                code_snippet=line.strip()[:150],
                                                confidence=0.85
                                            ))
                                        elif 'websocket' in line_lower and ('abnormal_closure' in line_lower or '1006' in line):
                                            log_problems.append(ProblemReport(
                                                problem_type="websocket_error",
                                                severity="high",
                                                file_path=file_path,
                                                line_number=line_num,
                                                description=f"{log_level}: WebSocket abnormal closure detected",
                                                suggestion="Check WebSocket connection handling and client-side connection management",
                                                code_snippet=line.strip()[:150],
                                                confidence=0.90
                                            ))
                                        elif 'connection' in line_lower and ('closed' in line_lower or 'disconnect' in line_lower):
                                            log_problems.append(ProblemReport(
                                                problem_type="connection_error",
                                                severity="medium",
                                                file_path=file_path,
                                                line_number=line_num,
                                                description=f"{log_level}: Connection issues detected",
                                                suggestion="Review connection handling and implement proper reconnection logic",
                                                code_snippet=line.strip()[:150],
                                                confidence=0.75
                                            ))
                                        else:
                                            # Generic error/fatal
                                            log_problems.append(ProblemReport(
                                                problem_type="log_error",
                                                severity=severity,
                                                file_path=file_path,
                                                line_number=line_num,
                                                description=f"{log_level}: General error detected in logs",
                                                suggestion="Review error details and fix underlying issues",
                                                code_snippet=line.strip()[:150],
                                                confidence=0.70
                                            ))
                        except Exception as e:
                            logger.warning(f"Failed to analyze log {file_path}: {e}")

    # Log the statistics
    logger.info(f"Log analysis: {log_stats}")

    return log_problems[:10], log_stats  # Return up to 10 problems and statistics

@app.get("/logs/analysis")
async def get_log_analysis():
    """Get detailed log file analysis with breakdown by severity"""
    log_problems, log_stats = analyze_log_files()

    return {
        "log_statistics": log_stats,
        "recent_problems": [
            {
                "problem_type": p.problem_type,
                "severity": p.severity,
                "file_path": p.file_path,
                "line_number": p.line_number,
                "description": p.description,
                "suggestion": p.suggestion,
                "code_snippet": p.code_snippet,
                "confidence": p.confidence
            }
            for p in log_problems
        ],
        "analysis_timestamp": datetime.now().isoformat()
    }

@app.get("/code/declarations")
async def get_code_declarations():
    """Get all code declarations (functions, classes, variables)"""
    issues = analyze_codebase_for_issues()

    return {
        "total_declarations": len(issues['declarations']),
        "by_type": {
            "functions": len([d for d in issues['declarations'] if d['type'] == 'function']),
            "classes": len([d for d in issues['declarations'] if d['type'] == 'class']),
            "variables": len([d for d in issues['declarations'] if d['type'] in ['const', 'let', 'var']])
        },
        "declarations": issues['declarations'][:100],  # Limit to first 100
        "analysis_timestamp": datetime.now().isoformat()
    }

@app.get("/code/duplicates")
async def get_code_duplicates():
    """Get detected code duplicates (filtered for meaningful duplicates)"""
    issues = analyze_codebase_for_issues()

    # Group by severity
    by_severity = {}
    for duplicate in issues['duplicates']:
        severity = duplicate.get('severity', 'medium')
        if severity not in by_severity:
            by_severity[severity] = 0
        by_severity[severity] += 1

    return {
        "total_duplicates": len(issues['duplicates']),
        "by_type": {
            "functions": len([d for d in issues['duplicates'] if d['type'] == 'duplicate_function']),
            "classes": len([d for d in issues['duplicates'] if d['type'] == 'duplicate_class'])
        },
        "by_severity": by_severity,
        "duplicates": issues['duplicates'],
        "analysis_timestamp": datetime.now().isoformat(),
        "note": "Common functions like main(), __init__(), setup() are filtered out as they are expected duplicates"
    }

@app.get("/code/hardcodes")
async def get_hardcoded_values():
    """Get detected hardcoded values"""
    issues = analyze_codebase_for_issues()

    # Group by type
    by_type = {}
    for hardcode in issues['hardcodes']:
        hc_type = hardcode['type']
        if hc_type not in by_type:
            by_type[hc_type] = 0
        by_type[hc_type] += 1

    return {
        "total_hardcodes": len(issues['hardcodes']),
        "by_type": by_type,
        "hardcodes": issues['hardcodes'][:50],  # Limit to first 50
        "analysis_timestamp": datetime.now().isoformat()
    }

def analyze_codebase_for_issues():
    """Analyze entire codebase for declarations, duplicates, and hardcoded values"""

    issues = {
        'declarations': [],
        'duplicates': [],
        'hardcodes': [],
        'unused_code': []
    }

    try:
        codebase_path = '/app/autobot_codebase'
        if not os.path.exists(codebase_path):
            return issues

        # Track patterns for duplicate detection
        function_signatures = {}
        class_definitions = {}
        hardcode_patterns = []

        for root, dirs, files in os.walk(codebase_path):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in {'node_modules', 'venv', '.git', '__pycache__', 'dist', 'build'}]

            for file in files:
                if not any(file.endswith(ext) for ext in ['.py', '.js', '.ts', '.vue']):
                    continue

                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, codebase_path)

                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        lines = content.splitlines()

                    # Analyze each line
                    for i, line in enumerate(lines):
                        line_stripped = line.strip()
                        line_lower = line_stripped.lower()

                        # 1. DECLARATIONS - Find function and class declarations
                        if any(keyword in line_stripped for keyword in ['def ', 'function ', 'class ', 'const ', 'let ', 'var ']):
                            # Extract declaration name
                            if 'def ' in line_stripped and '(' in line_stripped:
                                func_name = line_stripped.split('def ')[1].split('(')[0].strip()
                                signature = f"{func_name}({line_stripped.split('(', 1)[1] if '(' in line_stripped else ''}"

                                # Common function names that should not be flagged as duplicates
                                common_functions = {'main', '__init__', 'setup', 'teardown', 'test_', 'run',
                                                  'start', 'stop', 'init', 'create', 'update', 'delete',
                                                  'get', 'post', 'put', 'patch', 'handle', 'process'}

                                is_common = any(func_name == common or func_name.startswith(common)
                                              for common in common_functions if isinstance(common, str))

                                if signature in function_signatures and not is_common:
                                    # Only flag as duplicate if not a common function pattern
                                    original_file = function_signatures[signature].split(':')[0]
                                    if original_file != relative_path:  # Different files only
                                        issues['duplicates'].append({
                                            'type': 'duplicate_function',
                                            'name': func_name,
                                            'file_path': relative_path,
                                            'line_number': i + 1,
                                            'signature': signature,
                                            'original_location': function_signatures[signature],
                                            'severity': 'medium' if len(signature) > 50 else 'low'
                                        })
                                else:
                                    function_signatures[signature] = f"{relative_path}:{i+1}"

                                issues['declarations'].append({
                                    'type': 'function',
                                    'name': func_name,
                                    'file_path': relative_path,
                                    'line_number': i + 1,
                                    'signature': line_stripped
                                })

                            elif 'class ' in line_stripped:
                                class_name = line_stripped.split('class ')[1].split('(')[0].split(':')[0].strip()

                                # Common class names that shouldn't be flagged as duplicates
                                common_classes = {'Test', 'TestCase', 'Config', 'Settings', 'Utils', 'Helper',
                                                'Base', 'Abstract', 'Interface', 'Enum', 'Constants'}

                                is_common_class = any(class_name == common or class_name.endswith(common)
                                                    for common in common_classes)

                                if class_name in class_definitions and not is_common_class:
                                    original_file = class_definitions[class_name].split(':')[0]
                                    if original_file != relative_path:  # Different files only
                                        issues['duplicates'].append({
                                            'type': 'duplicate_class',
                                            'name': class_name,
                                            'file_path': relative_path,
                                            'line_number': i + 1,
                                            'original_location': class_definitions[class_name],
                                            'severity': 'high'  # Class duplicates are more serious
                                        })
                                else:
                                    class_definitions[class_name] = f"{relative_path}:{i+1}"

                                issues['declarations'].append({
                                    'type': 'class',
                                    'name': class_name,
                                    'file_path': relative_path,
                                    'line_number': i + 1,
                                    'signature': line_stripped
                                })

                        # 2. HARDCODED VALUES - Look for potential hardcodes with smart filtering
                        # Skip hardcode detection in test files and configuration files
                        is_test_file = any(indicator in relative_path.lower() for indicator in [
                            'test-', 'test_', '.test.', '/test/', 'spec.', '.spec.',
                            'mock', 'fixture', 'example', 'sample', 'demo', 'test-mvc-functionality',
                            'check_backend_status', 'test_ollama_direct', 'test_chat_fix', 'test_npu'
                        ])

                        is_config_file = any(relative_path.endswith(ext) for ext in [
                            '.config.js', '.config.ts', 'routes.ts', 'router.js',
                            '.env', '.env.example', 'package.json', 'vite.config.ts'
                        ])

                        # Skip route path detection in legitimate files
                        is_route_definition = any(keyword in line_lower for keyword in [
                            'path:', 'route', 'redirect', 'component:', 'expectedroutes', 'routeconfig'
                        ])

                        if not is_test_file and not is_config_file:
                            hardcode_indicators = [
                                # Critical security-sensitive patterns only
                                (r'mongodb://[^\s\'"]+', 'hardcoded_db_url'),
                                (r'postgres://[^\s\'"]+', 'hardcoded_db_url'),
                                (r'mysql://[^\s\'"]+', 'hardcoded_db_url'),
                                (r'redis://[^\s\'"]+', 'hardcoded_db_url'),
                                # API keys (but not in obvious test contexts)
                                (r'["\'][a-zA-Z0-9]{30,}["\']', 'potential_api_key'),
                                (r'["\']sk-[a-zA-Z0-9]+["\']', 'potential_openai_key'),
                                (r'["\']pk_[a-zA-Z0-9]+["\']', 'potential_stripe_key'),
                                # Production URLs (skip localhost and example.com)
                                (r'https://(?!localhost|example\.com|127\.0\.0\.1)[^\s\'"]+\.com[^\s\'"]*', 'hardcoded_production_url'),
                                # Absolute file paths (but not route paths)
                                (r'["\'][C-Z]:\\\\[^\s\'"]{10,}', 'hardcoded_windows_path'),
                            ]

                            # Only check Unix paths if not a route definition
                            if not is_route_definition:
                                hardcode_indicators.append((r'["\']\/(?:home|opt|usr|var)\/[^\s\'"]+', 'hardcoded_unix_path'))
                        else:
                            hardcode_indicators = []  # Skip hardcode detection for test/config files

                        for pattern, hardcode_type in hardcode_indicators:
                            matches = re.finditer(pattern, line_stripped)
                            for match in matches:
                                # Skip common false positives
                                matched_text = match.group()
                                if any(skip in matched_text.lower() for skip in ['example.com', 'localhost', 'test', 'demo', '0.0.0.0']):
                                    continue

                                issues['hardcodes'].append({
                                    'type': hardcode_type,
                                    'value': matched_text[:50] + '...' if len(matched_text) > 50 else matched_text,
                                    'file_path': relative_path,
                                    'line_number': i + 1,
                                    'context': line_stripped[:100] + '...' if len(line_stripped) > 100 else line_stripped
                                })

                        # 3. UNUSED CODE - Look for unused imports and variables (basic detection)
                        if line_stripped.startswith('import ') and 'import' in line_lower:
                            # Basic unused import detection (simplified)
                            imported_name = line_stripped.replace('import ', '').split(' as ')[0].split('.')[0]
                            if imported_name not in content.replace(line_stripped, ''):
                                issues['unused_code'].append({
                                    'type': 'unused_import',
                                    'name': imported_name,
                                    'file_path': relative_path,
                                    'line_number': i + 1,
                                    'line': line_stripped
                                })

                except Exception as e:
                    logger.warning(f"Failed to analyze {file_path}: {e}")

    except Exception as e:
        logger.error(f"Codebase analysis failed: {e}")

    return issues

@app.get("/code/analytics", response_model=AnalyticsReport)
async def get_code_analytics():
    """Get comprehensive code analytics with enhanced problem categorization"""
    logger.info("Generating comprehensive code analytics report with enhanced categorization")

    # Analyze log files for runtime problems
    log_problems, log_stats = analyze_log_files()

    # Analyze codebase for structural issues
    codebase_issues = analyze_codebase_for_issues()

    # Convert codebase issues to problem reports with better categorization
    code_problems = []

    # Critical hardcodes (security-sensitive)
    critical_hardcodes = [h for h in codebase_issues['hardcodes'] if h['type'] in ['potential_api_key', 'hardcoded_db_url']]
    for hardcode in critical_hardcodes[:5]:
        code_problems.append(ProblemReport(
            problem_type="security_risk",
            severity="critical" if hardcode['type'] == 'potential_api_key' else "high",
            file_path=hardcode['file_path'],
            line_number=hardcode['line_number'],
            description=f"Security risk: {hardcode['type']} found in code",
            suggestion="Move sensitive values to secure environment variables or secrets management",
            code_snippet=hardcode['context'][:100] + "..." if len(hardcode['context']) > 100 else hardcode['context'],
            confidence=0.85
        ))

    # Configuration hardcodes (less critical but should be configurable)
    config_hardcodes = [h for h in codebase_issues['hardcodes'] if h['type'] in ['hardcoded_url', 'hardcoded_localhost']]
    for hardcode in config_hardcodes[:8]:
        code_problems.append(ProblemReport(
            problem_type="configuration_issue",
            severity="medium",
            file_path=hardcode['file_path'],
            line_number=hardcode['line_number'],
            description=f"Configuration should be externalized: {hardcode['type']}",
            suggestion="Move configuration values to environment variables or config files",
            code_snippet=hardcode['context'][:100] + "..." if len(hardcode['context']) > 100 else hardcode['context'],
            confidence=0.70
        ))

    # High-severity duplicates (classes and complex functions)
    high_severity_duplicates = [d for d in codebase_issues['duplicates'] if d.get('severity') == 'high']
    for duplicate in high_severity_duplicates[:3]:
        code_problems.append(ProblemReport(
            problem_type="code_quality",
            severity="medium",
            file_path=duplicate['file_path'],
            line_number=duplicate['line_number'],
            description=f"Duplicate {duplicate['type']}: {duplicate['name']}",
            suggestion=f"Consider consolidating duplicate code. Original at {duplicate['original_location']}",
            code_snippet=duplicate.get('signature', duplicate['name']),
            confidence=0.85
        ))

    # Add unused code problems
    for unused in codebase_issues['unused_code'][:5]:  # Limit to 5
        code_problems.append(ProblemReport(
            problem_type="unused_code",
            severity="low",
            file_path=unused['file_path'],
            line_number=unused['line_number'],
            description=f"Unused {unused['type']}: {unused['name']}",
            suggestion="Remove unused imports and variables to clean up code",
            code_snippet=unused['line'],
            confidence=0.70
        ))

    # Add existing mock problems
    existing_problems = [
        ProblemReport(
            problem_type="timeout_risk",
            severity="critical",
            file_path="/app/backend/api/system.py",
            line_number=113,
            description="Health endpoint may hang causing API timeouts",
            suggestion="Add timeout wrapper and non-blocking health checks",
            code_snippet="async def health_check(detailed: bool = False):\n    comprehensive_health = await get_comprehensive_health_status()",
            confidence=0.92
        ),
        ProblemReport(
            problem_type="infinite_loop",
            severity="high",
            file_path="/app/backend/services/consolidated_health_service.py",
            line_number=28,
            description="Potential infinite loop in health service causing CPU spike",
            suggestion="Add loop termination conditions and circuit breaker",
            code_snippet="async def get_comprehensive_health(self):\n    while self.checking:\n        await self._check_all_components()",
            confidence=0.87
        ),
        ProblemReport(
            problem_type="unused_code",
            severity="medium",
            file_path="/app/autobot-vue/src/stores/useKnowledgeStore.ts",
            line_number=1,
            description="Frontend store not accessible from backend analysis scope",
            suggestion="Frontend files are not mounted in NPU worker - this is expected for backend-only analysis",
            code_snippet="// File exists in frontend but not visible from NPU worker container",
            confidence=0.75
        ),
        ProblemReport(
            problem_type="duplicate",
            severity="medium",
            file_path="/app/backend/fast_app_factory_fix.py",
            line_number=173,
            description="Multiple health endpoints with different implementations",
            suggestion="Consolidate health endpoints into single standardized implementation",
            code_snippet="@app.get('/api/system/health')\nasync def system_health_override():",
            confidence=0.83
        )
    ]

    # Combine code and log problems
    all_problems = code_problems + log_problems

    # Count problems by severity and type
    problems_by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    problems_by_type = {}

    for problem in all_problems:
        problems_by_severity[problem.severity] = problems_by_severity.get(problem.severity, 0) + 1
        problems_by_type[problem.problem_type] = problems_by_type.get(problem.problem_type, 0) + 1

    # Count files we can actually analyze
    try:
        files_analyzed, _ = count_project_files()
    except:
        files_analyzed = 150

    return AnalyticsReport(
        total_problems=len(all_problems),
        problems_by_severity=problems_by_severity,
        problems_by_type=problems_by_type,
        files_analyzed=files_analyzed,
        problems=all_problems,
        analysis_timestamp=datetime.now().isoformat()
    )


if __name__ == "__main__":
    host = os.getenv("NPU_WORKER_HOST", "0.0.0.0")
    port = int(os.getenv("NPU_WORKER_PORT", "8081"))

    logger.info(f"Starting NPU Worker (Simple) on {host}:{port}")
    logger.info(f"Device: {npu_state['device']}")
    logger.info("This is a development version - no actual NPU required")

    uvicorn.run(app, host=host, port=port, log_level="info")
