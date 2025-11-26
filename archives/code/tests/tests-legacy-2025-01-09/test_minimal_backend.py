#!/usr/bin/env python3
"""
Minimal backend test to verify service_monitor router works
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Create minimal app
app = FastAPI(title="Test Backend")

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and register service_monitor router
try:
    from backend.api.service_monitor import router as service_router
    app.include_router(service_router, prefix="/api")
    print("✅ Service monitor router registered successfully")
    print(f"Routes: {[route.path for route in service_router.routes]}")
except Exception as e:
    print(f"❌ Failed to register service_monitor router: {e}")
    import traceback
    traceback.print_exc()

@app.get("/")
async def root():
    return {"message": "Test backend running"}

@app.get("/test")
async def test():
    return {"status": "ok", "message": "Test endpoint"}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting test backend on http://localhost:8002")
    uvicorn.run(app, host="0.0.0.0", port=8002)
