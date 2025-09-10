# AutoBot Port Mappings

This document lists all port mappings used by AutoBot services.

## Container Services

| Service | Container Port | Host Port | Description |
|---------|---------------|-----------|-------------|
| autobot-redis | 6379 | 6379 | Redis database |
| autobot-redis | 8002 | 8002 | RedisInsight Web UI |
| autobot-npu-worker | 8081 | 8081 | NPU inference API |
| autobot-ai-stack | 8080 | 8080 | AI services API |
| autobot-playwright-vnc | 3000 | 3000 | Playwright service API ✅ |
| autobot-playwright-vnc | 5901 | 5901 | VNC server (avoids Kali's default 5900) ✅ |
| autobot-playwright-vnc | 6080 | 6080 | noVNC web interface ✅ |

## Local Services

| Service | Port | Description |
|---------|------|-------------|
| Backend (FastAPI) | 8001 | Main AutoBot API |
| Frontend (Vite) | 5173 | Vue.js development server |
| Ollama | 11434 | Local LLM service |

## Important Notes

- RedisInsight runs on port 8002 both inside the container and on the host (8002:8002)
- The backend API on port 8001 is completely separate from RedisInsight
- VNC port 5901 is used to avoid conflict with Kali Linux's default TigerVNC on port 5900
- All ports are configurable through environment variables or config files

## Quick Access URLs

- **Backend API**: http://localhost:8001
- **Frontend**: http://localhost:5173
- **RedisInsight**: http://localhost:8002
- **NPU Worker**: http://localhost:8081
- **AI Stack**: http://localhost:8080
- **Playwright API**: http://localhost:3000
- **Playwright Browser (noVNC)**: http://localhost:6080/vnc.html
