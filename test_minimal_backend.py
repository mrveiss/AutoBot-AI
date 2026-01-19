#!/usr/bin/env python3
"""
Minimal backend to test basic FastAPI functionality
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Set up minimal logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/api/hello")
async def hello():
    return {"message": "Hello from minimal backend!"}

@app.get("/api/system/health")
async def health():
    return {"status": "healthy", "backend": "minimal"}

@app.post("/api/workflow/execute")
async def execute_workflow(request: dict):
    user_message = request.get("user_message", "")
    
    # Simple greeting response
    if user_message.lower().strip() in ["hello", "hi", "hey"]:
        return {
            "success": True,
            "type": "direct_execution",
            "result": {
                "status": "success",
                "response_text": "Hello! I'm AutoBot's minimal backend. The main backend had performance issues, but this proves the basic functionality works. What can I help you with?"
            }
        }
    
    return {
        "success": True,
        "type": "direct_execution", 
        "result": {
            "status": "success",
            "response_text": f"You said: '{user_message}'. This is a minimal backend response - the full backend is having performance issues."
        }
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting minimal backend...")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")