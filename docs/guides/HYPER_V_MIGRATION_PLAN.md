# 🔄 AutoBot Hyper-V Migration Plan

**GitHub Issue:** [#257](https://github.com/mrveiss/AutoBot-AI/issues/257)
**Migration Date:** Post P0 Critical Tasks Completion
**Current Architecture:** 8 Docker Containers → 5 Hyper-V VMs
**Target Infrastructure:** Hyper-V with SSH-enabled VMs

---

## 🏗️ **CURRENT CONTAINER ANALYSIS**

### **Identified Services** (8 containers):
1. **dns-cache** - DNS resolution service
2. **redis** - Redis Stack database 
3. **browser-service** - Playwright automation
4. **frontend** - Vue.js application (port 5173)
5. **ai-stack** - AI/ML processing services (port 8080)
6. **npu-worker** - NPU acceleration worker (port 8081)
7. **models** - Model storage and management
8. **autobot** - Main backend application (port 8001)

### **Consolidation Strategy** → **5 VMs**:
- **VM1**: Frontend + Static Assets + DNS Cache
- **VM2**: Backend + API Services 
- **VM3**: Database + Redis Stack + Models
- **VM4**: AI/ML Stack + NPU Worker 
- **VM5**: Browser Service + Automation Tools

---

## 🖥️ **OS RECOMMENDATIONS BY VM**

### **VM1: Frontend Services** 
**Recommended OS**: **Ubuntu Server 22.04 LTS**
- **Reasoning**: 
  - Lightweight, stable, excellent Node.js/npm support
  - Built-in systemd for service management
  - Strong community support for Vue.js deployments
  - Minimal resource usage for static content serving
- **Services**: nginx, Node.js, Vue frontend, DNS cache
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 50GB SSD

### **VM2: Backend Services**
**Recommended OS**: **Ubuntu Server 22.04 LTS** 
- **Reasoning**:
  - Excellent Python ecosystem support
  - FastAPI runs optimally on Ubuntu
  - Easy systemd integration for backend services
  - Strong Docker-to-systemd migration tools
- **Services**: Python FastAPI, backend APIs, logging
- **RAM**: 8GB minimum, 16GB recommended  
- **Storage**: 100GB SSD

### **VM3: Database & Storage**
**Recommended OS**: **Ubuntu Server 22.04 LTS**
- **Reasoning**:
  - Redis Stack official support for Ubuntu
  - Built-in tools for database backup/restoration
  - Proven stability for 24/7 database operations
  - Easy volume management and data persistence
- **Services**: Redis Stack, model storage, data persistence
- **RAM**: 16GB minimum, 32GB recommended
- **Storage**: 500GB SSD (database + models)

### **VM4: AI/ML Processing** 
**Recommended OS**: **Ubuntu Server 22.04 LTS** 
- **Reasoning**:
  - Best compatibility with Intel OpenVINO toolkit
  - CUDA/ROCm support for GPU acceleration
  - Comprehensive Python ML libraries (PyTorch, TensorFlow)
  - Intel NPU driver support via kernel updates
- **Services**: AI stack, NPU worker, model inference
- **RAM**: 32GB minimum, 64GB recommended
- **Storage**: 200GB SSD + fast scratch storage

### **VM5: Browser Automation**
**Recommended OS**: **Ubuntu Desktop 22.04 LTS** (with GUI)
- **Reasoning**:
  - Playwright requires GUI components for browser testing
  - VNC/X11 forwarding capabilities
  - Full browser compatibility (Chrome, Firefox, Safari via WebKit)
  - Desktop environment needed for UI automation
- **Services**: Playwright, browser automation, VNC server
- **RAM**: 8GB minimum, 16GB recommended
- **Storage**: 100GB SSD

---

## 🔧 **MIGRATION TECHNICAL SPECIFICATIONS**

### **Common Base Requirements** (All VMs):
- **Base OS**: Ubuntu Server 22.04 LTS (except VM5 = Desktop)
- **Architecture**: x86_64 
- **SSH**: OpenSSH server pre-installed and configured
- **User Account**: `autobot` user with sudo privileges
- **Time Sync**: NTP configured for log correlation
- **Monitoring**: Basic system monitoring (htop, iostat, nethogs)

### **Network Configuration**:
- **VM1 (Frontend)**: Port 5173, 80, 443
- **VM2 (Backend)**: Port 8001, 8000 (API)
- **VM3 (Database)**: Port 6379 (Redis), internal only
- **VM4 (AI/ML)**: Port 8080, 8081
- **VM5 (Browser)**: Port 3000, 6080 (VNC)

### **Security Hardening**:
- SSH key-based authentication (disable password login)
- UFW firewall pre-configured 
- fail2ban for intrusion prevention
- Automatic security updates enabled
- User account lockdown (no root SSH)

---

## 📦 **MIGRATION ORDER & DEPENDENCIES**

### **Phase 1**: Infrastructure VMs
1. **VM3 (Database)** - Foundation data layer
2. **VM5 (Browser)** - Independent automation service

### **Phase 2**: Core Application
3. **VM2 (Backend)** - Depends on VM3 database
4. **VM4 (AI/ML)** - Depends on VM2 for orchestration

### **Phase 3**: User Interface  
5. **VM1 (Frontend)** - Depends on VM2 backend APIs

---

## 🚀 **PREPARATION CHECKLIST**

### **For Each VM Setup**:
- [ ] **OS Installation**: Ubuntu 22.04 LTS with SSH enabled
- [ ] **User Setup**: Create `autobot` user with sudo access
- [ ] **SSH Keys**: Configure SSH key-based authentication
- [ ] **Network**: Static IP assignment and DNS configuration
- [ ] **Packages**: Install Docker (for migration scripts), Python 3.10+, Node.js 18+
- [ ] **Security**: Configure UFW firewall rules
- [ ] **Monitoring**: Install basic monitoring tools
- [ ] **Storage**: Mount additional storage for data/models as needed

### **Migration Tools Needed**:
- Docker-to-systemd service conversion scripts
- Database migration/export tools  
- Configuration template generators
- Health check and monitoring setup scripts
- Network connectivity validation tools

---

## ⚠️ **CRITICAL CONSIDERATIONS**

### **Data Migration**:
- **Redis Data**: Export/import RDB files from VM3
- **Model Files**: Rsync large model files to VM3/VM4
- **Configuration**: Convert Docker environment variables to systemd

### **Service Dependencies**:
- **Service Discovery**: Replace Docker networking with static IPs
- **Load Balancing**: Configure nginx reverse proxy on VM1
- **Health Checks**: Convert Docker health checks to systemd monitoring

### **Testing Strategy**:
- **Individual VM Testing**: Each service independently
- **Integration Testing**: Cross-VM communication validation
- **Performance Baseline**: Compare Docker vs VM performance
- **Rollback Plan**: Keep Docker environment ready for 48h

---

## 🎯 **EXPECTED BENEFITS**

### **Performance Gains**:
- **No Container Overhead**: Direct OS-level execution
- **Better Resource Allocation**: Dedicated VM resources per service
- **Network Performance**: Direct VM-to-VM communication
- **Storage Performance**: No Docker volume overhead

### **Operational Benefits**:
- **Hyper-V Integration**: Native Windows Server management
- **Backup/Snapshot**: VM-level backup and restoration
- **Resource Scaling**: Individual VM resource adjustment
- **Monitoring**: Native Windows performance counters

---

## 📋 **POST-MIGRATION VALIDATION**

### **Functional Testing**:
- [ ] Frontend loads correctly on VM1
- [ ] Backend APIs respond on VM2  
- [ ] Database queries work on VM3
- [ ] AI/ML processing functions on VM4
- [ ] Browser automation works on VM5
- [ ] Cross-VM communication validated
- [ ] Performance benchmarks meet/exceed Docker baseline

### **Success Criteria**:
- **Uptime**: All services achieve >99% uptime in first week
- **Performance**: Response times within 10% of Docker baseline
- **Reliability**: Zero data loss during migration
- **Maintainability**: SSH access and service management working

---

*This migration plan provides a solid foundation for transforming AutoBot from containerized to VM-based infrastructure while maintaining functionality and improving performance.*