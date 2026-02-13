# AutoBot IP Addressing Scheme

## **Critical Rule: NO LOCALHOST USAGE**

**NEVER use `localhost` in AutoBot configurations.** Each component must use its designated 127.0.0.x IP address to avoid routing confusion between hosts and containers.

## **IP Address Allocation**

| Component | IP Address | Purpose | Examples |
|-----------|------------|---------|----------|
| `127.0.0.1` | **RESERVED** | Internal processes only | System internal only |
| `127.0.0.2` | Windows Host | Windows services | Windows-side services |
| `127.0.0.3` | WSL Kali | AutoBot backend, Ollama | `https://127.0.0.3:8443` |
| `127.0.0.4` | Playwright | VNC, browser testing | `http://127.0.0.4:6080` |
| `127.0.0.5` | NPU Worker | AI processing | `http://127.0.0.5:8081` |
| `127.0.0.6` | AI Stack | ML services | `http://127.0.0.6:8080` |
| `127.0.0.7` | Redis | Database | `redis://127.0.0.7:6379` |
| `127.0.0.8` | Log Viewer | Seq logging | `http://127.0.0.8:5341` |

## **Configuration Requirements**

### **Frontend (Vue.js)**
```javascript
// ✅ CORRECT - Use specific IPs
BASE_URL: 'https://127.0.0.3:8443'
WS_BASE_URL: 'wss://127.0.0.3:8443/ws'
PLAYWRIGHT_VNC_URL: 'http://127.0.0.4:6080/vnc.html'

// ❌ WRONG - Never use localhost
BASE_URL: 'https://localhost:8443'  // NO!
```

### **Backend**
```json
{
  "backend": {
    "api_endpoint": "https://127.0.0.3:8443",
    "ollama_endpoint": "http://127.0.0.3:11434"
  }
}
```

### **Docker Containers**
- Each container gets its assigned 127.0.0.x IP
- Containers use host networking to access other components
- Never use `localhost` or `127.0.0.1` for inter-component communication

## **Why This Scheme?**

1. **Eliminates Routing Confusion**: Each component has a unique, predictable address
2. **Container Isolation**: Prevents localhost routing loops
3. **Debugging**: Easy to identify which component is being accessed
4. **Consistency**: Same addressing works across host and container environments
5. **Scalability**: Clear pattern for adding new components

## **Migration Checklist**

- [ ] Update all `localhost` references in frontend code
- [ ] Update backend configuration files
- [ ] Update Vite proxy configuration
- [ ] Update Docker service configurations
- [ ] Update environment variables
- [ ] Test all inter-component communication

## **Testing Commands**

```bash
# Test backend connectivity
curl https://127.0.0.3:8443/api/system/health

# Test VNC access
curl http://127.0.0.4:6080/vnc.html

# Test from container
docker exec autobot-playwright-vnc curl https://127.0.0.3:8443/api/system/health
```

---

**⚠️ CRITICAL**: Any use of `localhost` in AutoBot configurations is considered a bug and must be replaced with the proper 127.0.0.x address according to this scheme.
