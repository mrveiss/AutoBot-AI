"""
NPU Worker Main Entry Point
Starts the NPU inference server with proper initialization
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, '/app/src')

import structlog
from npu_inference_server import app

# Configure logging
def setup_logging():
    """Setup structured logging for NPU worker"""
    log_level = os.getenv("NPU_LOG_LEVEL", "INFO").upper()
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Configure structlog
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


def check_environment():
    """Check NPU worker environment"""
    logger = structlog.get_logger()
    
    # Check OpenVINO environment
    try:
        import openvino as ov
        from openvino.runtime import Core
        
        core = Core()
        devices = core.available_devices
        logger.info("OpenVINO initialized", devices=devices)
        
        # Check for NPU specifically
        npu_devices = [d for d in devices if 'NPU' in d]
        if npu_devices:
            logger.info("NPU devices detected", npu_devices=npu_devices)
        else:
            logger.warning("No NPU devices detected - will use CPU/GPU fallback")
            
    except ImportError:
        logger.error("OpenVINO not available - NPU acceleration disabled")
    except Exception as e:
        logger.error("OpenVINO initialization failed", error=str(e))
    
    # Check environment variables
    required_env = ["NPU_WORKER_HOST", "NPU_WORKER_PORT"]
    for env_var in required_env:
        value = os.getenv(env_var)
        if value:
            logger.info(f"Environment: {env_var}={value}")
        else:
            logger.warning(f"Environment variable {env_var} not set")
    
    # Check directories
    directories = ["/app/models", "/app/data", "/app/logs"]
    for directory in directories:
        path = Path(directory)
        if path.exists():
            logger.info(f"Directory exists: {directory}")
        else:
            logger.warning(f"Creating directory: {directory}")
            path.mkdir(parents=True, exist_ok=True)


def main():
    """Main entry point for NPU worker"""
    # Setup logging first
    setup_logging()
    logger = structlog.get_logger()
    
    logger.info("Starting AutoBot NPU Worker")
    
    # Check environment
    check_environment()
    
    # Get configuration
    host = os.getenv("NPU_WORKER_HOST", "0.0.0.0")
    port = int(os.getenv("NPU_WORKER_PORT", 8081))
    workers = int(os.getenv("NPU_WORKER_WORKERS", 1))
    
    logger.info(
        "NPU Worker configuration",
        host=host,
        port=port,
        workers=workers
    )
    
    # Start the server
    try:
        import uvicorn
        
        uvicorn.run(
            "npu_inference_server:app",
            host=host,
            port=port,
            workers=workers,
            log_level="info",
            access_log=True,
            reload=False
        )
        
    except KeyboardInterrupt:
        logger.info("NPU Worker stopped by user")
    except Exception as e:
        logger.error("NPU Worker failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()