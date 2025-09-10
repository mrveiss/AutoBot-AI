# 🚀 AutoBot Native VM Deployment Guide

**Your Infrastructure Ready**: 5 VMs (172.16.168.21-25) + 1 WSL machine (172.16.168.20)  
**Credentials**: user=`autobot`, password=`autobot`, sudo access  
**Configuration**: Dynamic memory, 50GB LVM (will auto-expand)  
**Deployment**: **NATIVE** - No Docker containers, services run directly on machines

---

## ⚡ **QUICK START** (5 minutes to deploy!)

### **1. Test VM Connectivity**
```bash
cd /home/kali/Desktop/AutoBot/ansible

# Test all VMs are accessible
ansible all -i inventory/production.yml -m ping --ask-pass
# Enter password: autobot
```

### **2. Setup VMs (Hostnames + LVM Expansion)**
```bash
# This will:
# - Set proper hostnames (autobot-frontend, autobot-database, etc.)
# - Expand LVM to use full disk
# - Install base packages
# - Configure logging and directories
./deploy-native.sh --setup-vms --ask-pass
```

### **3. Full Native AutoBot Deployment**
```bash
# Complete NATIVE deployment - services run directly on VMs (no Docker)
./deploy-native.sh --full --ask-pass
```

### **4. Access AutoBot**
```bash
# 🎯 PRIMARY APP ACCESS POINT:
http://172.16.168.21  # Complete AutoBot application (native Vue.js + Nginx)

# Additional management interfaces:
http://172.16.168.20:7681  # Terminal access (WSL)
http://172.16.168.20:6080  # noVNC desktop (WSL)
```

---

## 📊 **NATIVE DEPLOYMENT ARCHITECTURE**

| Machine | IP | Hostname | Native Services | SystemD Services | Resources |
|---------|----|-----------|-----------------|-----------------|----|
| **WSL** | 172.16.168.20 | autobot-backend | FastAPI Backend + Terminal + noVNC | autobot-backend, ttyd, tigervnc | 8GB RAM |
| **VM1** | 172.16.168.21 | autobot-frontend | Nginx + Node.js 18 + Vue.js | autobot-frontend, nginx | 4GB RAM |
| **VM2** | 172.16.168.22 | autobot-npu | NPU Worker + OpenVINO | autobot-npu-worker | 8GB RAM |
| **VM3** | 172.16.168.23 | autobot-database | Redis Stack 7.4 + RedisInsight | redis-stack-server | 8GB RAM |
| **VM4** | 172.16.168.24 | autobot-aistack | Python 3.11 + AI Stack + Ollama | autobot-ai-stack, ollama | 16GB RAM |
| **VM5** | 172.16.168.25 | autobot-browser | Node.js + Playwright + VNC | autobot-browser, autobot-vnc | 4GB RAM |

**Total Infrastructure**: 5 Hyper-V VMs + 1 WSL machine = 6 machines running native services  
**Service Distribution**: Each of the 5 original Docker services gets its own VM, plus WSL for backend

---

## 🔧 **STEP-BY-STEP DEPLOYMENT**

### **Phase 1: VM Preparation** (Required first!)
```bash
# Setup VM names and expand LVM storage
./deploy.sh --setup-vms --ask-pass

# What this does:
# ✅ Sets hostname to autobot-[frontend|backend|database|aiml|browser] 
# ✅ Expands LVM to use full 50GB disk
# ✅ Updates /etc/hosts with all VM addresses
# ✅ Installs essential packages (python3, git, curl, etc.)
# ✅ Creates AutoBot directory structure (/opt/autobot/)
# ✅ Configures logging and log rotation
```

### **Phase 2: Native Service Deployment** (All-in-one)
```bash  
# Deploy all AutoBot services natively on VMs (no containers)
./deploy-native.sh --deploy --ask-pass

# What this does:
# ✅ Installs Redis Stack 7.4 natively on VM3 
# ✅ Installs Node.js 18 + Vue.js build on VM1
# ✅ Installs Python 3.11 + AI services on VM4
# ✅ Installs Playwright + VNC server on VM5
# ✅ Creates SystemD services for all components
# ✅ Configures service networking and health checks
```

### **Phase 3: Validation** (Included in --full)
```bash
# Validate all native services are running
./deploy-native.sh --validate --ask-pass
```

---

## ✅ **VERIFICATION COMMANDS**

### **Check VM Status**
```bash
# Test connectivity to all VMs
ansible all -m ping --ask-pass

# Check disk usage after LVM expansion
ansible all -m shell -a "df -h /" --ask-pass

# Verify hostnames
ansible all -m shell -a "hostname" --ask-pass

# Check memory and CPU
ansible all -m shell -a "free -h && nproc" --ask-pass
```

### **Check Native AutoBot Services**
```bash
# Health check all native services
./deploy-native.sh --validate --ask-pass

# Check specific VM native services
ansible autobot-frontend -m systemctl -a "name=nginx state=started" --ask-pass
ansible autobot-frontend -m systemctl -a "name=autobot-frontend state=started" --ask-pass
ansible autobot-database -m systemctl -a "name=redis-stack-server state=started" --ask-pass
ansible autobot-aiml -m systemctl -a "name=autobot-ai-stack state=started" --ask-pass
ansible autobot-aiml -m systemctl -a "name=ollama state=started" --ask-pass
ansible autobot-browser -m systemctl -a "name=autobot-browser state=started" --ask-pass
```

### **View Logs**
```bash
# Check native deployment logs
tail -f /tmp/autobot-native-deployment/native-deployment-*.log

# Check native AutoBot service logs on VMs
ansible all -m shell -a "journalctl -u autobot-* --since '1 hour ago'" --ask-pass

# Check individual service logs
ansible autobot-frontend -m shell -a "journalctl -u autobot-frontend -n 20" --ask-pass
ansible autobot-database -m shell -a "journalctl -u redis-stack-server -n 20" --ask-pass
ansible autobot-aiml -m shell -a "journalctl -u ollama -n 20" --ask-pass
```

---

## 🛠️ **TROUBLESHOOTING**

### **Common Issues & Solutions**

**🔴 SSH Connection Failed**
```bash
# Verify VM is running and accessible
ping 172.16.168.21

# Test SSH manually
ssh autobot@172.16.168.21
# Password: autobot
```

**🔴 Ansible Permission Denied**
```bash  
# Use --ask-pass for password authentication
ansible all -m ping --ask-pass
```

**🔴 LVM Expansion Failed**
```bash
# Check current disk usage
ansible all -m shell -a "lvdisplay && df -h /" --ask-pass

# Manual LVM expansion on specific VM
ssh autobot@172.16.168.21
sudo lvextend -l +100%FREE /dev/ubuntu-vg/ubuntu-lv
sudo resize2fs /dev/ubuntu-vg/ubuntu-lv
```

**🔴 Native Service Won't Start**
```bash
# Check native service status
ansible autobot-frontend -m systemctl -a "name=autobot-frontend status" --ask-pass

# View native service logs
ansible autobot-frontend -m shell -a "journalctl -u autobot-frontend -n 50" --ask-pass

# Check all AutoBot services on a VM
ansible autobot-aiml -m shell -a "systemctl status autobot-*" --ask-pass
```

### **Reset and Retry**
```bash
# Reset a specific VM to clean state (if needed)
ansible autobot-frontend -m shell -a "sudo systemctl stop autobot-* && sudo rm -rf /opt/autobot/*" --ask-pass

# Re-run native deployment
./deploy-native.sh --full --ask-pass
```

---

## 📈 **EXPECTED RESULTS**

### **After VM Setup** (./deploy-native.sh --setup-vms):
- ✅ All VMs have unique hostnames (autobot-frontend, autobot-database, etc.)
- ✅ LVM expanded to ~50GB available space  
- ✅ Network connectivity between all VMs
- ✅ Base packages and directories ready

### **After Native Deployment** (./deploy-native.sh --full):
- ✅ AutoBot frontend accessible at http://172.16.168.21 (native Nginx + Vue.js)
- ✅ All 5 services running natively across 4 VMs (no containers)
- ✅ Redis Stack 7.4 operational natively on VM3
- ✅ AI/ML stack with Ollama running natively on VM4
- ✅ Browser automation with native Playwright and VNC on VM5
- ✅ Backend stays on host, connects to VM services

### **Performance Benefits of Native Deployment**:
- ⚡ **Zero containerization overhead** - services run directly on VM OS
- ⚡ **Maximum performance** - no Docker layer, direct hardware access
- ⚡ **Resource efficiency** - no container orchestration overhead
- ⚡ **SystemD management** - native Linux service management
- ⚡ **Direct network access** - no container networking layer
- ⚡ **VM-level isolation** - stronger security boundaries than containers

---

## 🎯 **SUCCESS CRITERIA**

**✅ Native Deployment Successful When:**
1. All 5 VMs respond to `ansible all -m ping --ask-pass`
2. Frontend loads at http://172.16.168.21 (native Nginx + Vue.js)
3. Backend API on host responds at http://localhost:8001/api/health
4. All native services show as `active (running)` in `systemctl status`
5. No errors in `/tmp/autobot-native-deployment/` logs
6. Redis accessible at 172.16.168.23:6379
7. Ollama responding at 172.16.168.24:11434
8. Browser service active at 172.16.168.25:3000

**🎉 You're Ready!** AutoBot is now running with **native performance** on enterprise-grade VM infrastructure - **no Docker overhead**, maximum speed and efficiency!

---

*Need help? Check the logs in `/tmp/autobot-native-deployment/` or run `./deploy-native.sh --validate --ask-pass` for detailed status.*