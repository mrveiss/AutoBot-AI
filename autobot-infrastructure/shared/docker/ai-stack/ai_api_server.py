"""
AI API Server for AutoBot AI Stack Container
Provides HTTP endpoints for AI agents running in container
"""

import logging
import os
import sys
import time
import traceback
from contextlib import asynccontextmanager
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add src to path for imports (works in Docker /app and native /opt/autobot/...)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from agents.base_agent import AgentResponse, deserialize_agent_request
from agents.chat_agent import ChatAgent
from agents.classification_agent import ClassificationAgent
from agents.rag_agent import get_rag_agent

logger = logging.getLogger(__name__)


class AIContainerServer:
    """HTTP server for AI agents in container"""

    def __init__(self):
        self.agents: Dict[str, Any] = {}
        self.startup_time = time.time()

    async def initialize_agents(self):
        """Initialize all AI agents"""
        logger.info("Initializing AI agents in container...")

        # Initialize agents individually to catch specific failures
        try:
            self.agents["chat"] = ChatAgent()
            logger.info("Chat agent initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize chat agent: {e}")
            logger.error(traceback.format_exc())

        try:
            self.agents["rag"] = get_rag_agent()
            logger.info("RAG agent initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize RAG agent: {e}")
            logger.error(traceback.format_exc())

        try:
            self.agents["classification"] = ClassificationAgent()
            logger.info("Classification agent initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize classification agent: {e}")
            logger.error(traceback.format_exc())

        logger.info(f"Initialized {len(self.agents)} AI agents total")

    async def cleanup_agents(self):
        """Cleanup all agents"""
        logger.info("Cleaning up AI agents...")
        self.agents.clear()


# Global server instance
ai_server = AIContainerServer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager"""
    # Startup
    await ai_server.initialize_agents()
    yield
    # Shutdown
    await ai_server.cleanup_agents()


# Create FastAPI app
app = FastAPI(
    title="AutoBot AI Stack",
    description="AI processing services for AutoBot",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "AutoBot AI Stack",
        "status": "running",
        "uptime_seconds": time.time() - ai_server.startup_time,
        "agents": list(ai_server.agents.keys()),
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        health_status = {}
        overall_healthy = True

        for agent_type, agent in ai_server.agents.items():
            try:
                if hasattr(agent, "health_check"):
                    health = await agent.health_check()
                    health_status[agent_type] = health.to_dict()
                    if health.status.value not in ["healthy", "degraded"]:
                        overall_healthy = False
                else:
                    # Simple ping for agents without health_check
                    health_status[agent_type] = {
                        "status": "healthy",
                        "agent_type": agent_type,
                    }
            except Exception as e:
                health_status[agent_type] = {"status": "unhealthy", "error": str(e)}
                overall_healthy = False

        status_code = 200 if overall_healthy else 503

        return JSONResponse(
            status_code=status_code,
            content={
                "status": "healthy" if overall_healthy else "unhealthy",
                "agents": health_status,
                "uptime_seconds": time.time() - ai_server.startup_time,
            },
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503, content={"status": "unhealthy", "error": str(e)}
        )


@app.get("/agents")
async def list_agents():
    """List available agents and their capabilities"""
    agents_info = []

    for agent_type, agent in ai_server.agents.items():
        try:
            capabilities = []
            if hasattr(agent, "get_capabilities"):
                capabilities = agent.get_capabilities()
            elif hasattr(agent, "capabilities"):
                capabilities = agent.capabilities

            agents_info.append(
                {
                    "type": agent_type,
                    "capabilities": capabilities,
                    "url": f"/agents/{agent_type}",
                }
            )
        except Exception as e:
            logger.error(f"Error getting info for agent {agent_type}: {e}")

    return {"agents": agents_info, "count": len(agents_info)}


@app.post("/agents/{agent_type}/process")
async def process_agent_request(agent_type: str, request: Request):
    """Process a request for specific agent type"""
    if agent_type not in ai_server.agents:
        raise HTTPException(
            status_code=404, detail=f"Agent type '{agent_type}' not found"
        )

    agent_request = None
    try:
        # Parse request body
        request_data = await request.body()
        agent_request = deserialize_agent_request(request_data.decode())

        # Get agent and process request
        agent = ai_server.agents[agent_type]

        if hasattr(agent, "execute_with_tracking"):
            response = await agent.execute_with_tracking(agent_request)
        elif hasattr(agent, "process_request"):
            response = await agent.process_request(agent_request)
        else:
            # Fallback for legacy agents
            response = AgentResponse(
                request_id=agent_request.request_id,
                agent_type=agent_type,
                status="error",
                result=None,
                error="Agent does not support standardized interface",
            )

        return JSONResponse(content=response.to_dict(), media_type="application/json")

    except Exception as e:
        logger.error("Error processing request for %s: %s", agent_type, e)
        logger.error(traceback.format_exc())

        req_id = getattr(agent_request, "request_id", "unknown") if agent_request else "unknown"
        error_response = AgentResponse(
            request_id=req_id,
            agent_type=agent_type,
            status="error",
            result=None,
            error=f"Processing error: {str(e)}",
        )

        return JSONResponse(status_code=500, content=error_response.to_dict())


@app.get("/agents/{agent_type}/health")
async def agent_health(agent_type: str):
    """Get health status for specific agent"""
    if agent_type not in ai_server.agents:
        raise HTTPException(
            status_code=404, detail=f"Agent type '{agent_type}' not found"
        )

    try:
        agent = ai_server.agents[agent_type]

        if hasattr(agent, "health_check"):
            health = await agent.health_check()
            return health.to_dict()
        else:
            return {
                "agent_type": agent_type,
                "status": "healthy",
                "message": "Basic health check passed",
            }

    except Exception as e:
        logger.error(f"Health check failed for {agent_type}: {e}")
        return JSONResponse(
            status_code=503,
            content={"agent_type": agent_type, "status": "unhealthy", "error": str(e)},
        )


@app.get("/agents/{agent_type}/capabilities")
async def agent_capabilities(agent_type: str):
    """Get capabilities for specific agent"""
    if agent_type not in ai_server.agents:
        raise HTTPException(
            status_code=404, detail=f"Agent type '{agent_type}' not found"
        )

    try:
        agent = ai_server.agents[agent_type]

        capabilities = []
        if hasattr(agent, "get_capabilities"):
            capabilities = agent.get_capabilities()
        elif hasattr(agent, "capabilities"):
            capabilities = agent.capabilities

        return {"agent_type": agent_type, "capabilities": capabilities}

    except Exception as e:
        logger.error(f"Error getting capabilities for {agent_type}: {e}")
        return JSONResponse(
            status_code=500, content={"agent_type": agent_type, "error": str(e)}
        )


@app.get("/stats")
async def get_statistics():
    """Get performance statistics for all agents"""
    stats = {
        "container_uptime_seconds": time.time() - ai_server.startup_time,
        "agents": {},
    }

    for agent_type, agent in ai_server.agents.items():
        try:
            if hasattr(agent, "get_statistics"):
                stats["agents"][agent_type] = agent.get_statistics()
            else:
                stats["agents"][agent_type] = {
                    "agent_type": agent_type,
                    "status": "active",
                }
        except Exception as e:
            stats["agents"][agent_type] = {"agent_type": agent_type, "error": str(e)}

    return stats


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}")
    logger.error(traceback.format_exc())

    return JSONResponse(
        status_code=500, content={"error": "Internal server error", "detail": str(exc)}
    )


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Get configuration from environment
    host = os.getenv("AI_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("AI_SERVER_PORT", "8080"))
    workers = int(os.getenv("AI_SERVER_WORKERS", "1"))

    # TLS Configuration - Issue #725 Phase 5
    tls_enabled = os.getenv("AI_SERVER_TLS_ENABLED", "false").lower() == "true"
    ssl_keyfile = None
    ssl_certfile = None

    if tls_enabled:
        cert_dir = os.getenv("AUTOBOT_TLS_CERT_DIR", "/etc/autobot/certs")
        ssl_keyfile = os.path.join(cert_dir, "server-key.pem")
        ssl_certfile = os.path.join(cert_dir, "server-cert.pem")
        port = int(os.getenv("AI_SERVER_TLS_PORT", "8445"))
        logging.info("TLS enabled - using HTTPS on port %s", port)

    uvicorn_config = {
        "app": "ai_api_server:app",
        "host": host,
        "port": port,
        "workers": workers,
        "log_level": "info",
        "access_log": True,
        "reload": False,
    }

    if tls_enabled and ssl_keyfile and ssl_certfile:
        uvicorn_config["ssl_keyfile"] = ssl_keyfile
        uvicorn_config["ssl_certfile"] = ssl_certfile

    uvicorn.run(**uvicorn_config)
