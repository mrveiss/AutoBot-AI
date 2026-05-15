# ✅ AutoBot Native VM Deployment - READY TO DEPLOY

## 🎯 **PRIMARY ACCESS POINT: http://172.16.168.21**

Your complete AutoBot native deployment system is ready! After deployment, access the full application at **http://172.16.168.21**.

---

## 🏗️ **DEPLOYMENT ARCHITECTURE**

### **6-Machine Infrastructure:**
- **1 WSL Machine** (172.16.168.20): Backend + Terminal + noVNC
- **5 Hyper-V VMs** (172.16.168.21-25): Native services (no Docker containers)

| Machine | IP | Hostname | Native Services | SystemD Services |
|---------|----|-----------|-----------------| ----------------|
| **WSL** | 172.16.168.20 | autobot-backend | FastAPI + Terminal + noVNC | autobot-backend, ttyd, tigervnc |
| **VM1** | 172.16.168.21 | autobot-frontend | **Vue.js App + Nginx** | autobot-frontend, nginx |
| **VM2** | 172.16.168.22 | autobot-npu | NPU Worker + OpenVINO | autobot-npu-worker |
| **VM3** | 172.16.168.23 | autobot-database | Redis Stack + RedisInsight | redis-stack-server |
| **VM4** | 172.16.168.24 | autobot-aistack | AI Stack + Ollama | autobot-ai-stack, ollama |
| **VM5** | 172.16.168.25 | autobot-browser | Playwright + VNC | autobot-browser, autobot-vnc |

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
firefox http://172.16.168.21
```

---

## 📡 **SERVICE ENDPOINTS AFTER DEPLOYMENT**

### **🌐 Primary Access:**
- **AutoBot Application**: http://172.16.168.21

### **📊 Service APIs:**
- **Backend API**: http://172.16.168.20:8001
- **NPU Worker**: http://172.16.168.22:8081  
- **AI Stack**: http://172.16.168.24:8080
- **Browser Service**: http://172.16.168.25:3000

### **🗄️ Data Services:**
- **Redis**: redis://172.16.168.23:6379
- **RedisInsight**: http://172.16.168.23:8002
- **Ollama**: http://172.16.168.24:11434

### **🖥️ Management:**
- **Terminal**: http://172.16.168.20:7681
- **noVNC**: http://172.16.168.20:6080  
- **VNC**: vnc://172.16.168.25:5900

---

## 🔧 **SPECIAL: NPU Worker Hardware Access**

VM2 (NPU Worker) requires **hardware passthrough** for optimal AI performance:

### **Hyper-V Configuration Required:**
```powershell
# Enable GPU passthrough for VM2
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
# ✅ All VMs responding
# ✅ Frontend accessible at 172.16.168.21
```

### **Current Status (Before Deployment):**
```bash
# Tested: Scripts working correctly
✅ WSL Backend running (172.16.168.20:8001)
✅ WSL noVNC running (172.16.168.20:6080)  
⏳ VMs ready for deployment (172.16.168.21-25)
✅ Deployment scripts validated
✅ Hardware passthrough documented
```

---

## 🎉 **PERFORMANCE BENEFITS**

### **Native Deployment Advantages:**
- ⚡ **Zero Docker overhead** - services run directly on OS
- ⚡ **Maximum performance** - no containerization layer
- ⚡ **Direct hardware access** - NPU and GPU passthrough  
- ⚡ **SystemD management** - native Linux service lifecycle
- ⚡ **VM-level isolation** - stronger security than containers
- ⚡ **Resource efficiency** - no container orchestration overhead

### **Perfect Service Separation:**
Each of the 5 original Docker services now has dedicated VM resources:
- **ai-stack** → VM4 (16GB RAM)
- **npu-worker** → VM2 (8GB RAM + NPU/GPU access)
- **redis-stack** → VM3 (8GB RAM)
- **frontend** → VM1 (4GB RAM)
- **browser** → VM5 (4GB RAM)

---

## 🎯 **SUCCESS CRITERIA**

**✅ Deployment Successful When:**
1. All VMs respond to ping
2. **AutoBot loads at http://172.16.168.21**
3. All 10 services show "healthy" in validation
4. NPU Worker has hardware access
5. Backend connects to all VM services

Run the deploy command below once the checklist above is satisfied.

---

*Next: Run `./deploy-native.sh --full --ask-pass` to deploy all services to your VMs*
