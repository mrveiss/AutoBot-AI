# ✅ AutoBot Native VM Deployment - READY TO DEPLOY

## 🎯 **PRIMARY ACCESS POINT: `http://<frontend-ip>`**

Your complete AutoBot native deployment system is ready! After deployment, access the full
application at your frontend role's address.

---

## 🏗️ **DEPLOYMENT ARCHITECTURE**

### **Example Role Layout:**

AutoBot has no fixed machine count — roles run in Docker, on one VM, or split across
however many machines the operator scales to. The layout below is one worked example
using Hyper-V VMs, one per role, plus a control/backend machine:

- **1 control/backend machine** (`<backend-ip>`): Backend + Terminal + noVNC
- **5 role VMs** (`<frontend-ip>`, `<npu-ip>`, `<database-ip>`, `<aiml-ip>`, `<browser-ip>`): Native services (no Docker containers)

| Role | IP | Hostname | Native Services | SystemD Services |
|---------|----|-----------|-----------------| ----------------|
| **Control/Backend** | `<backend-ip>` | autobot-backend | FastAPI + Terminal + noVNC | autobot-backend, ttyd, tigervnc |
| **Frontend** | `<frontend-ip>` | autobot-frontend | **Vue.js App + Nginx** | autobot-frontend, nginx |
| **NPU Worker** | `<npu-ip>` | autobot-npu | NPU Worker + OpenVINO | autobot-npu-worker |
| **Database** | `<database-ip>` | autobot-database | Redis Stack + RedisInsight | redis-stack-server |
| **AI Stack** | `<aiml-ip>` | autobot-aistack | AI Stack + Ollama | autobot-ai-stack, ollama |
| **Browser** | `<browser-ip>` | autobot-browser | Playwright + VNC | autobot-browser, autobot-vnc |

---

## 🚀 **QUICK DEPLOYMENT**

```bash
cd ansible

# 1. Test connectivity
ansible all -i inventory/production.yml -m ping --ask-pass

# 2. Setup VMs (expand LVM, set hostnames)
./deploy-native.sh --setup-vms --ask-pass

# 3. Deploy all native services  
./deploy-native.sh --full --ask-pass

# 4. Access AutoBot
firefox http://<frontend-ip>
```

---

## 📡 **SERVICE ENDPOINTS AFTER DEPLOYMENT**

### **🌐 Primary Access:**
- **AutoBot Application**: `http://<frontend-ip>`

### **📊 Service APIs:**
- **Backend API**: `http://<backend-ip>:8001`
- **NPU Worker**: `http://<npu-ip>:8081`
- **AI Stack**: `http://<aiml-ip>:8080`
- **Browser Service**: `http://<browser-ip>:3000`

### **🗄️ Data Services:**
- **Redis**: `redis://<database-ip>:6379`
- **RedisInsight**: `http://<database-ip>:8002`
- **Ollama**: `http://<aiml-ip>:11434`

### **🖥️ Management:**
- **Terminal**: `http://<backend-ip>:7681`
- **noVNC**: `http://<backend-ip>:6080`
- **VNC**: `vnc://<browser-ip>:5900`

---

## 🔧 **SPECIAL: NPU Worker Hardware Access**

The NPU worker role requires **hardware passthrough** for optimal AI performance:

### **Hyper-V Configuration Required:**
```powershell
# Enable GPU passthrough for the NPU worker role
Add-VMGpuPartitionAdapter -VMName "autobot-npu" -AdapterName "Intel Arc Graphics"

# Enable NPU access
$npu = Get-PnpDevice | Where-Object {$_.Name -like "*Intel AI Boost*"}
Add-VMAssignableDevice -VMName "autobot-npu" -LocationPath $npu.LocationPath
```

**📋 Complete hardware setup guide**: `ansible/docs/HARDWARE_PASSTHROUGH_SETUP.md`

---

## ✅ **VALIDATION & TESTING**

### **Test Deployment:**
```bash
# Validate all services
python3 scripts/validate-native-deployment.py

# Expected results after deployment:
# ✅ 10/10 services healthy
# ✅ All deployment machines responding
# ✅ Frontend accessible at its configured address
```

### **Current Status (Before Deployment):**
```bash
# Tested: Scripts working correctly
✅ Backend running (<backend-ip>:8001)
✅ noVNC running (<backend-ip>:6080)
⏳ Role machines ready for deployment
✅ Deployment scripts validated
✅ Hardware passthrough documented
```

---

## 🎉 **PERFORMANCE BENEFITS**

### **Native Deployment Advantages:**
- ⚡ **Zero Docker overhead** - services run directly on OS
- ⚡ **Maximum performance** - no containerization layer
- ⚡ **Direct hardware access** - NPU and GPU passthrough  
- ⚡ **VM-level isolation** - stronger security than containers, when roles run on separate machines
- ⚡ **SystemD management** - native Linux service lifecycle
- ⚡ **Resource efficiency** - no container orchestration overhead

### **Perfect Service Separation:**

Each role can be given dedicated machine resources when scaled out, e.g. in this example layout:
- **ai-stack** → AI Stack role (16GB RAM)
- **npu-worker** → NPU Worker role (8GB RAM + NPU/GPU access)
- **redis-stack** → Database role (8GB RAM)
- **frontend** → Frontend role (4GB RAM)
- **browser** → Browser role (4GB RAM)

---

## 🎯 **SUCCESS CRITERIA**

**✅ Deployment Successful When:**
1. All deployment machines respond to ping
2. **AutoBot loads at its frontend role's address**
3. All 10 services show "healthy" in validation
4. NPU Worker has hardware access
5. Backend connects to every role's services

Run the deploy command below once the checklist above is satisfied.

---

*Next: Run `./deploy-native.sh --full --ask-pass` to deploy all services to your machines*
