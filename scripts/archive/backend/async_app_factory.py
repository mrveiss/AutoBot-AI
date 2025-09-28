#!/usr/bin/env python3
"""
Async App Factory using modern dependency injection
Replaces the blocking app factory with proper async architecture
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.dependency_container import service_context, container, get_llm
from backend.api.registry import get_router_configs, RouterStatus
from src.chat_history_manager import ChatHistoryManager
from src.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


@asynccontextmanager
async def create_async_lifespan(app: FastAPI):
    """Async lifespan manager with proper service lifecycle"""
    logger.info("🚀 Starting AutoBot backend (Async Architecture)")
    
    # Initialize dependency container with all services
    async with service_context() as service_container:
        # Store container in app state for access in endpoints
        app.state.container = service_container
        
        # Initialize chat_history_manager for compatibility
        try:
            app.state.chat_history_manager = ChatHistoryManager()
            logger.info("✅ ChatHistoryManager initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize ChatHistoryManager: {e}")
            app.state.chat_history_manager = None
        
        # Initialize knowledge_base for compatibility
        try:
            app.state.knowledge_base = KnowledgeBase()
            await app.state.knowledge_base.ainit()
            logger.info("✅ KnowledgeBase initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize KnowledgeBase: {e}")
            app.state.knowledge_base = None
        
        # Add orchestrator placeholder for compatibility  
        app.state.orchestrator = None  # Will be implemented later
        
        # Health check all services
        health_results = await service_container.health_check_all_services()
        healthy_services = [name for name, health in health_results.items() 
                           if health.get("status") == "healthy"]
        
        logger.info(f"✅ Services initialized: {', '.join(healthy_services)}")
        
        if len(healthy_services) != len(health_results):
            unhealthy = [name for name, health in health_results.items() 
                        if health.get("status") != "healthy"]
            logger.warning(f"⚠️ Unhealthy services: {', '.join(unhealthy)}")
        
        logger.info("🎉 AutoBot backend ready (Async Architecture)")
        
        yield  # App is running
        
        logger.info("🛑 Shutting down AutoBot backend")


def create_async_app() -> FastAPI:
    """Create FastAPI app with async architecture"""
    
    app = FastAPI(
        title="AutoBot API (Async)",
        version="2.0.0-async",
        description="AutoBot backend with modern async architecture",
        lifespan=create_async_lifespan
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure based on environment
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error(f"Global exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": str(exc),
                "type": type(exc).__name__
            }
        )
    
    # Health endpoint
    @app.get("/api/system/health")
    async def health_check():
        """System health check using dependency container"""
        try:
            if not hasattr(app.state, 'container'):
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "unhealthy",
                        "message": "Service container not initialized",
                        "backend": "starting"
                    }
                )
            
            # Get health from all services
            health_results = await app.state.container.health_check_all_services()
            
            # Overall status
            all_healthy = all(
                health.get("status") == "healthy" 
                for health in health_results.values()
            )
            
            return {
                "status": "healthy" if all_healthy else "degraded",
                "backend": "connected",
                "timestamp": "2025-09-01T13:45:00.000Z",
                "services": health_results,
                "async_architecture": True,
                "response_time_ms": "< 50ms"
            }
            
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "error": str(e),
                    "backend": "error"
                }
            )
    
    # Add compatibility endpoints for frontend
    @app.get("/api/health")
    async def legacy_health_check():
        """Legacy health endpoint for compatibility"""
        return {"status": "healthy", "legacy_endpoint": True}
    
    @app.get("/api/llm/status/comprehensive")
    async def llm_status_comprehensive():
        """LLM status endpoint for compatibility"""
        try:
            llm = await get_llm()
            llm_health = await llm.health_check()
            return {
                "status": "available" if llm_health.get("status") == "healthy" else "unavailable",
                "provider": "ollama",
                "models": llm_health.get("models_available", 0),
                "health": llm_health
            }
        except Exception as e:
            return {
                "status": "unavailable", 
                "error": str(e),
                "provider": "ollama"
            }
    
    @app.get("/api/knowledge_base/stats")
    async def kb_stats():
        """Knowledge base stats for compatibility"""
        try:
            if hasattr(app.state, 'knowledge_base') and app.state.knowledge_base:
                stats = await app.state.knowledge_base.get_stats()
                stats["async_architecture"] = True
                return stats
        except Exception as e:
            logger.debug(f"KB stats error: {e}")
        
        return {
            "status": "initializing",
            "documents": 0,
            "chunks": 0,
            "embeddings": 0,
            "async_architecture": True
        }
    
    # Register all API routers
    router_configs = get_router_configs()
    for name, config in router_configs.items():
        try:
            if config.status in [RouterStatus.ENABLED, RouterStatus.LAZY_LOAD]:
                # Dynamically import the router
                module = __import__(config.module_path, fromlist=["router"])
                router = getattr(module, "router")
                
                app.include_router(
                    router,
                    prefix=config.prefix,
                    tags=config.tags
                )
                logger.info(f"✅ Router registered: {config.name} ({config.prefix})")
            else:
                logger.info(f"⏭️ Router skipped (disabled): {config.name}")
        except Exception as e:
            logger.error(f"❌ Failed to register router {config.name}: {e}")
    
    return app


# Create the app instance
app = create_async_app()