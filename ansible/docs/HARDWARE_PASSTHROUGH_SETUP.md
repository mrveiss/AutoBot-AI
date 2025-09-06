# 🔧 Hardware Passthrough Setup for AutoBot Native Deployment

## NPU and GPU Access for VM2 (NPU Worker - 172.16.168.22)

The NPU Worker VM requires direct access to both NPU and GPU hardware for optimal AI inference performance. This requires configuring hardware passthrough in Hyper-V.

---

## 🚀 **Hyper-V Hardware Passthrough Configuration**

### **Prerequisites:**
- Windows 11/Windows Server with Hyper-V enabled
- Host machine with Intel NPU (Intel Core Ultra or Intel Arc)
- Host machine with dedicated GPU (NVIDIA/AMD/Intel Arc)
- VT-d/AMD-Vi enabled in BIOS
- IOMMU enabled in host system

### **Step 1: Enable GPU Passthrough (GPU-PV or DDA)**

#### **Option A: GPU-PV (Recommended for Intel Arc/Integrated Graphics)**
```powershell
# Enable GPU-PV for VM2 (NPU Worker)
Add-VMGpuPartitionAdapter -VMName "autobot-npu" -AdapterName "Intel(R) Arc(TM) Graphics"

# Configure GPU resource allocation
Set-VMGpuPartitionAdapter -VMName "autobot-npu" -MinPartitionVRAM 512MB -MaxPartitionVRAM 2GB -OptimalPartitionVRAM 1GB

# Enable GPU scheduling
Set-VMProcessor -VMName "autobot-npu" -ExposeVirtualizationExtensions $true
```

#### **Option B: Discrete Device Assignment (DDA) for Dedicated GPUs**
```powershell
# 1. Disable GPU in host (temporary for passthrough)
Disable-PnpDevice -InstanceId "PCI\VEN_10DE&DEV_XXXX&SUBSYS_XXXXXXXX&REV_XX" -Confirm:$false

# 2. Get GPU location path
$gpu = Get-PnpDevice | Where-Object {$_.Name -like "*NVIDIA*" -or $_.Name -like "*AMD*"}
$locationPath = ($gpu | Get-PnpDeviceProperty -KeyName DEVPKEY_Device_LocationPaths).Data[0]

# 3. Dismount GPU from host
Dismount-VmHostAssignableDevice -LocationPath $locationPath -Force

# 4. Assign GPU to VM
Add-VMAssignableDevice -VMName "autobot-npu" -LocationPath $locationPath
```

### **Step 2: Enable NPU Passthrough**

```powershell
# 1. Identify NPU device
Get-PnpDevice | Where-Object {$_.Name -like "*NPU*" -or $_.Name -like "*VPU*" -or $_.Name -like "*AI Boost*"}

# 2. Get NPU location path
$npu = Get-PnpDevice | Where-Object {$_.Name -like "*Intel(R) AI Boost*"}
$npuLocationPath = ($npu | Get-PnpDeviceProperty -KeyName DEVPKEY_Device_LocationPaths).Data[0]

# 3. Dismount NPU from host (if needed)
Dismount-VmHostAssignableDevice -LocationPath $npuLocationPath -Force

# 4. Assign NPU to VM
Add-VMAssignableDevice -VMName "autobot-npu" -LocationPath $npuLocationPath
```

### **Step 3: VM Configuration for Hardware Access**

```powershell
# Enable IOMMU for VM
Set-VMProcessor -VMName "autobot-npu" -ExposeVirtualizationExtensions $true

# Increase VM memory for hardware workloads
Set-VMMemory -VMName "autobot-npu" -DynamicMemoryEnabled $true -MinimumBytes 4GB -MaximumBytes 12GB -StartupBytes 8GB

# Enable enhanced session mode (for better hardware access)
Set-VM -VMName "autobot-npu" -EnhancedSessionTransportType HvSocket
```

---

## 🐧 **Linux VM Configuration (Inside NPU Worker VM)**

### **Step 1: Install Hardware Drivers**

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Intel NPU drivers
wget -qO - https://repositories.intel.com/graphics/intel-graphics.key | sudo apt-key add -
echo "deb [arch=amd64] https://repositories.intel.com/graphics/ubuntu jammy main" | sudo tee /etc/apt/sources.list.d/intel-graphics.list
sudo apt update

# Install NPU runtime and OpenVINO
sudo apt install -y intel-level-zero-gpu level-zero intel-opencl-icd
sudo apt install -y intel-media-va-driver-non-free intel-media-driver

# Install OpenVINO runtime
pip3 install openvino[pytorch,tensorflow] openvino-dev[pytorch,tensorflow]
```

### **Step 2: Verify Hardware Access**

```bash
# Check NPU device access
ls -la /dev/accel*  # Should show NPU acceleration devices

# Check GPU access  
ls -la /dev/dri/*   # Should show GPU render nodes

# Test OpenVINO device detection
python3 -c "
from openvino.runtime import Core
core = Core()
devices = core.available_devices
print('Available devices:', devices)
for device in devices:
    print(f'Device {device}: {core.get_property(device, \"FULL_DEVICE_NAME\")}')
"
```

### **Step 3: Configure NPU Worker Service**

```bash
# Create service configuration
sudo tee /opt/autobot/config/npu-worker.conf << EOF
[hardware]
enable_npu = true
enable_gpu = true
openvino_device = AUTO
npu_priority = high
gpu_fallback = true
device_cache_dir = /opt/autobot/data/device_cache

[performance]
inference_threads = 2
batch_size = 1
precision = FP16
cache_models = true

[monitoring]
log_device_usage = true
performance_metrics = true
temperature_monitoring = true
EOF
```

---

## ✅ **Verification Steps**

### **Host Verification:**
```powershell
# Check assigned devices
Get-VMAssignableDevice -VMName "autobot-npu"

# Verify VM can see hardware
Get-VM -VMName "autobot-npu" | Select-Object VMName, State, ProcessorCount, MemoryAssigned
```

### **VM Verification:**
```bash
# Run hardware detection
python3 /opt/autobot/scripts/hardware-detect.py

# Test inference performance
python3 /opt/autobot/scripts/npu-benchmark.py

# Check device temperatures and usage
python3 /opt/autobot/scripts/hardware-monitor.py
```

---

## ⚠️ **Important Considerations**

### **Performance:**
- **NPU Priority**: NPU offers best performance/watt for AI workloads
- **GPU Fallback**: GPU used for workloads NPU cannot handle  
- **CPU Fallback**: CPU used as last resort

### **Resource Management:**
- NPU and GPU share some system resources
- Monitor temperature and throttling
- Configure appropriate memory allocation

### **VM Limitations:**
- Hardware passthrough may prevent VM migration
- Backup/snapshot limitations with assigned devices
- Host hardware unavailable while assigned to VM

### **Troubleshooting:**
- Check Windows Event Logs for hardware errors
- Verify IOMMU groups don't conflict
- Ensure VM has sufficient memory allocation
- Check device driver compatibility in guest OS

---

## 📊 **Expected Performance Benefits**

| Workload | NPU | GPU | CPU | Notes |
|----------|-----|-----|-----|-------|
| LLM Inference | ⚡⚡⚡ | ⚡⚡ | ⚡ | NPU optimized for transformer models |
| Image Processing | ⚡⚡ | ⚡⚡⚡ | ⚡ | GPU excels at parallel image ops |
| General AI | ⚡⚡⚡ | ⚡⚡ | ⚡ | NPU best overall efficiency |
| Power Usage | 🔋🔋🔋 | 🔋 | 🔋🔋 | NPU most power efficient |

With proper hardware passthrough, the NPU Worker VM will have direct access to both NPU and GPU units, enabling optimal AI inference performance for AutoBot workloads.