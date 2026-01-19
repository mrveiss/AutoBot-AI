"""
Main entry point for AutoBot AI Stack Container
Sets up environment and starts the AI API server
"""

import os
import sys
import logging
import asyncio
from pathlib import Path

# Add src to Python path
sys.path.insert(0, '/app/src')
sys.path.insert(0, '/app')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/app/logs/ai_container.log', mode='a')
    ]
)

logger = logging.getLogger(__name__)


def setup_environment():
    """Setup container environment"""
    # Create required directories
    os.makedirs('/app/data', exist_ok=True)
    os.makedirs('/app/models', exist_ok=True)
    os.makedirs('/app/logs', exist_ok=True)
    
    # Set environment variables for AI stack
    os.environ.setdefault('PYTHONPATH', '/app:/app/src')
    os.environ.setdefault('AI_SERVER_HOST', '0.0.0.0')
    os.environ.setdefault('AI_SERVER_PORT', '8080')
    os.environ.setdefault('AI_SERVER_WORKERS', '1')
    
    # Ollama configuration (will connect to host Ollama)
    os.environ.setdefault('OLLAMA_HOST', 'host.docker.internal:11434')
    
    # Redis configuration (will connect to AutoBot Redis container)
    os.environ.setdefault('REDIS_HOST', 'autobot-redis')
    os.environ.setdefault('REDIS_PORT', '6379')
    
    # Vector database configuration
    os.environ.setdefault('CHROMA_DB_PATH', '/app/data/chroma_db')
    
    # Disable external API calls by default (privacy-first)
    os.environ.setdefault('DISABLE_EXTERNAL_APIS', 'true')
    
    logger.info("Container environment setup completed")


def check_dependencies():
    """Check if required dependencies are available"""
    try:
        import langchain
        import llama_index
        import chromadb
        import transformers
        import fastapi
        logger.info("All required AI dependencies available")
        return True
    except ImportError as e:
        logger.error(f"Missing required dependency: {e}")
        return False


def main():
    """Main entry point"""
    try:
        logger.info("Starting AutoBot AI Stack Container")
        
        # Setup environment
        setup_environment()
        
        # Check dependencies
        if not check_dependencies():
            logger.error("Dependency check failed")
            sys.exit(1)
        
        # Import and run server
        from ai_api_server import app
        import uvicorn
        
        host = os.getenv("AI_SERVER_HOST", "0.0.0.0")
        port = int(os.getenv("AI_SERVER_PORT", "8080"))
        workers = int(os.getenv("AI_SERVER_WORKERS", "1"))
        
        logger.info(f"Starting AI API server on {host}:{port}")
        
        uvicorn.run(
            app,
            host=host,
            port=port,
            workers=workers,
            log_level="info",
            access_log=True,
            reload=False
        )
        
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()