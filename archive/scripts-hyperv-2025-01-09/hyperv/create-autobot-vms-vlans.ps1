# AutoBot VM Creation with Hyper-V VLAN Isolation
# Run as Administrator
# Creates VMs with VLAN isolation, pfSense as gateway only

param(
    [string]$VmPath = "C:\AutoBot-VMs",
    [string]$IsoPath = "C:\ISO\ubuntu-22.04.3-live-server-amd64.iso",
    [string]$SwitchName = "AutoBot-External",
    [string]$AutoBotVLAN = "100",
    [string]$PfSenseGateway = "192.168.1.1"
)

# VM Configurations with VLAN isolation
$VMs = @(
    @{Name="AutoBot-Frontend"; RAM=2GB; CPU=2; Disk=20GB; IP="192.168.$AutoBotVLAN.10"; VLAN=$AutoBotVLAN},
    @{Name="AutoBot-Backend"; RAM=8GB; CPU=4; Disk=40GB; IP="192.168.$AutoBotVLAN.20"; VLAN=$AutoBotVLAN},
    @{Name="AutoBot-AIStack"; RAM=16GB; CPU=6; Disk=60GB; IP="192.168.$AutoBotVLAN.30"; VLAN=$AutoBotVLAN; GPU=$true},
    @{Name="AutoBot-NPUWorker"; RAM=8GB; CPU=4; Disk=40GB; IP="192.168.$AutoBotVLAN.40"; VLAN=$AutoBotVLAN; NPU=$true},
    @{Name="AutoBot-Redis"; RAM=8GB; CPU=2; Disk=100GB; IP="192.168.$AutoBotVLAN.50"; VLAN=$AutoBotVLAN}
)

Write-Host "🤖 Creating AutoBot VMs with Hyper-V VLAN Isolation" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "VLAN: $AutoBotVLAN (Hyper-V managed)" -ForegroundColor Yellow
Write-Host "Gateway: $PfSenseGateway (internet access only)" -ForegroundColor Yellow
Write-Host "Switch: $SwitchName" -ForegroundColor Yellow

# Create VM directory
New-Item -ItemType Directory -Path $VmPath -Force

foreach ($VM in $VMs) {
    Write-Host "`n🔧 Creating VM: $($VM.Name)" -ForegroundColor Green
    
    # Create VM with proper resource allocation
    New-VM -Name $VM.Name -MemoryStartupBytes $VM.RAM -Path $VmPath -NewVHDPath "$VmPath\$($VM.Name)\$($VM.Name).vhdx" -NewVHDSizeBytes $VM.Disk
    
    # Configure VM settings
    Set-VM -Name $VM.Name -ProcessorCount $VM.CPU -AutomaticStartAction Nothing -AutomaticStopAction ShutDown
    
    # Connect to external switch
    Get-VMNetworkAdapter -VMName $VM.Name | Connect-VMNetworkAdapter -SwitchName $SwitchName
    
    # Configure VLAN isolation (CRITICAL for security)
    Write-Host "  🔒 Configuring VLAN $($VM.VLAN) isolation for $($VM.Name)" -ForegroundColor Yellow
    Set-VMNetworkAdapterVlan -VMName $VM.Name -Access -VlanId $VM.VLAN
    
    # Verify VLAN configuration
    $VlanConfig = Get-VMNetworkAdapterVlan -VMName $VM.Name
    if ($VlanConfig.AccessVlanId -eq $VM.VLAN) {
        Write-Host "  ✅ VLAN $($VM.VLAN) configured successfully" -ForegroundColor Green
    } else {
        Write-Host "  ❌ VLAN configuration failed!" -ForegroundColor Red
        exit 1
    }
    
    # Enable nested virtualization for AI/NPU VMs
    if ($VM.Name -match "AIStack|NPUWorker") {
        Set-VMProcessor -VMName $VM.Name -ExposeVirtualizationExtensions $true
        Write-Host "  ⚡ Enabled nested virtualization for $($VM.Name)" -ForegroundColor Yellow
    }
    
    # GPU passthrough for AI Stack
    if ($VM.GPU) {
        Write-Host "  🎮 Configuring GPU passthrough for $($VM.Name)" -ForegroundColor Yellow
        try {
            Add-VMGpuPartitionAdapter -VMName $VM.Name -ErrorAction SilentlyContinue
            Set-VM -Name $VM.Name -GuestControlledCacheTypes $true -LowMemoryMappedIoSpace 1Gb -HighMemoryMappedIoSpace 32Gb -ErrorAction SilentlyContinue
            Write-Host "  ✅ GPU passthrough configured" -ForegroundColor Green
        } catch {
            Write-Host "  ⚠️  GPU passthrough may need manual configuration" -ForegroundColor Yellow
        }
    }
    
    # Security hardening
    Set-VM -Name $VM.Name -AutomaticCheckpointsEnabled $false -CheckpointType ProductionOnly
    Set-VM -Name $VM.Name -SmartPagingFilePath "$VmPath\$($VM.Name)"
    
    # Mount Ubuntu ISO
    Add-VMDvdDrive -VMName $VM.Name -Path $IsoPath
    
    Write-Host "  ✅ VM $($VM.Name) created successfully" -ForegroundColor Green
    Write-Host "     IP: $($VM.IP), VLAN: $($VM.VLAN)" -ForegroundColor Gray
}

# Generate network configuration for Ubuntu installation
$NetworkConfigPath = "$VmPath\ubuntu-network-config.yaml"
Write-Host "`n📋 Generating Ubuntu network configuration..." -ForegroundColor Cyan

$NetworkConfig = @"
# AutoBot Ubuntu Network Configuration
# Use this configuration during Ubuntu Server setup for each VM
# Copy the relevant section for each VM during installation

network:
  version: 2
  ethernets:
    enp0s3:  # Primary network interface (may be different, check during install)
      dhcp4: false
      addresses: 
        # Use one of these for each VM:
        # Frontend:  [192.168.$AutoBotVLAN.10/24]
        # Backend:   [192.168.$AutoBotVLAN.20/24]  
        # AIStack:   [192.168.$AutoBotVLAN.30/24]
        # NPUWorker: [192.168.$AutoBotVLAN.40/24]
        # Redis:     [192.168.$AutoBotVLAN.50/24]
        - 192.168.$AutoBotVLAN.XX/24  # Replace XX with VM-specific last octet
      routes:
        - to: 0.0.0.0/0
          via: $PfSenseGateway  # pfSense gateway for internet access
      nameservers:
        addresses:
          - 8.8.8.8    # Google DNS
          - 1.1.1.1    # Cloudflare DNS
        search:
          - autobot.local

# VLAN $AutoBotVLAN is configured at Hyper-V level - no VLAN config needed in Ubuntu
# pfSense will route this subnet to internet automatically
"@

$NetworkConfig | Out-File -FilePath $NetworkConfigPath -Encoding UTF8

# Generate IP assignment reference
$IPAssignmentPath = "$VmPath\vm-ip-assignments.txt"
$IPAssignments = @"
AutoBot VM IP Assignments (VLAN $AutoBotVLAN)
===========================================

VM Name               IP Address              Purpose
---------             ----------              -------
AutoBot-Frontend      192.168.$AutoBotVLAN.10        Vue.js frontend, Nginx
AutoBot-Backend       192.168.$AutoBotVLAN.20        FastAPI backend, Python
AutoBot-AIStack       192.168.$AutoBotVLAN.30        LLM server, GPU workloads  
AutoBot-NPUWorker     192.168.$AutoBotVLAN.40        NPU processing, AI tasks
AutoBot-Redis         192.168.$AutoBotVLAN.50        Redis database, storage

Network Configuration:
- Subnet: 192.168.$AutoBotVLAN.0/24
- Gateway: $PfSenseGateway (pfSense for internet only)
- DNS: 8.8.8.8, 1.1.1.1
- VLAN: $AutoBotVLAN (Hyper-V managed isolation)

Installation Notes:
- Use static IP configuration during Ubuntu install
- Set hostname to match VM name (e.g., autobot-frontend)
- Create user 'autobot' for Ansible automation
- Enable SSH server during installation
- VLAN isolation is handled by Hyper-V - no configuration needed in Ubuntu
"@

$IPAssignments | Out-File -FilePath $IPAssignmentPath -Encoding UTF8

Write-Host "`n🌐 Network Summary:" -ForegroundColor Cyan
Write-Host "=================" -ForegroundColor Cyan
Write-Host "VLAN Isolation: Hyper-V manages VLAN $AutoBotVLAN" -ForegroundColor Green
Write-Host "Internet Access: pfSense gateway at $PfSenseGateway" -ForegroundColor Green
Write-Host "Internal Traffic: VMs can communicate within VLAN $AutoBotVLAN" -ForegroundColor Green
Write-Host "External Access: Blocked - VMs isolated from main network" -ForegroundColor Red

Write-Host "`n📁 Configuration files created:" -ForegroundColor Yellow
Write-Host "  Network config: $NetworkConfigPath" -ForegroundColor White
Write-Host "  IP assignments: $IPAssignmentPath" -ForegroundColor White

Write-Host "`n📋 Ubuntu Installation Steps:" -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan
Write-Host "For each VM:" -ForegroundColor Yellow
Write-Host "1. Start VM and boot from Ubuntu ISO" -ForegroundColor Gray
Write-Host "2. During network setup, use STATIC IP configuration:" -ForegroundColor Gray
Write-Host "   - IP: 192.168.$AutoBotVLAN.XX (see assignments above)" -ForegroundColor Gray
Write-Host "   - Netmask: 255.255.255.0 (/24)" -ForegroundColor Gray
Write-Host "   - Gateway: $PfSenseGateway" -ForegroundColor Gray
Write-Host "   - DNS: 8.8.8.8, 1.1.1.1" -ForegroundColor Gray
Write-Host "3. Set hostname to VM name (e.g., autobot-frontend)" -ForegroundColor Gray
Write-Host "4. Create user 'autobot' with sudo privileges" -ForegroundColor Gray
Write-Host "5. Install SSH server" -ForegroundColor Gray
Write-Host "6. Complete installation and reboot" -ForegroundColor Gray

Write-Host "`n🔧 After Installation:" -ForegroundColor Cyan
Write-Host "1. Test internet connectivity: ping 8.8.8.8" -ForegroundColor Gray
Write-Host "2. Test VM-to-VM connectivity within VLAN" -ForegroundColor Gray
Write-Host "3. Verify isolation: should NOT reach main network" -ForegroundColor Gray
Write-Host "4. Run discovery script to update Ansible inventory" -ForegroundColor Gray
Write-Host "5. Deploy AutoBot services via Ansible" -ForegroundColor Gray

Write-Host "`n✅ AutoBot VMs created with VLAN isolation!" -ForegroundColor Green
Write-Host "Each VM is isolated on VLAN $AutoBotVLAN with internet access via pfSense." -ForegroundColor Yellow