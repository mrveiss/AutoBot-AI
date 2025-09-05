# Create AutoBot VMs - Simple Development Setup
# Run as Administrator
# Basic VMs connected to internal virtual ethernet

param(
    [string]$VmPath = "C:\AutoBot-VMs",
    [string]$IsoPath = "C:\ISO\ubuntu-22.04.3-live-server-amd64.iso",
    [string]$SwitchName = "AutoBot-Internal"
)

# Simple VM configurations - no VLANs, just basic networking
$VMs = @(
    @{Name="AutoBot-Frontend"; RAM=2GB; CPU=2; Disk=20GB; IP="192.168.100.10"},
    @{Name="AutoBot-Backend"; RAM=8GB; CPU=4; Disk=40GB; IP="192.168.100.20"},
    @{Name="AutoBot-AIStack"; RAM=16GB; CPU=6; Disk=60GB; IP="192.168.100.30"; GPU=$true},
    @{Name="AutoBot-NPUWorker"; RAM=8GB; CPU=4; Disk=40GB; IP="192.168.100.40"; NPU=$true},
    @{Name="AutoBot-Redis"; RAM=8GB; CPU=2; Disk=100GB; IP="192.168.100.50"}
)

Write-Host "🤖 Creating AutoBot VMs - Simple Development Setup" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "Switch: $SwitchName (Internal)" -ForegroundColor Yellow
Write-Host "Network: Simple virtual ethernet" -ForegroundColor Yellow

# Create VM directory
New-Item -ItemType Directory -Path $VmPath -Force

foreach ($VM in $VMs) {
    Write-Host "`n🔧 Creating VM: $($VM.Name)" -ForegroundColor Green
    
    # Create VM
    New-VM -Name $VM.Name -MemoryStartupBytes $VM.RAM -Path $VmPath -NewVHDPath "$VmPath\$($VM.Name)\$($VM.Name).vhdx" -NewVHDSizeBytes $VM.Disk
    
    # Basic VM configuration
    Set-VM -Name $VM.Name -ProcessorCount $VM.CPU -AutomaticStartAction Nothing -AutomaticStopAction ShutDown
    
    # Connect to internal switch - NO VLAN configuration
    Get-VMNetworkAdapter -VMName $VM.Name | Connect-VMNetworkAdapter -SwitchName $SwitchName
    Write-Host "  🔌 Connected to internal switch" -ForegroundColor Green
    
    # Enable nested virtualization for AI/NPU VMs (for Docker if needed)
    if ($VM.Name -match "AIStack|NPUWorker") {
        Set-VMProcessor -VMName $VM.Name -ExposeVirtualizationExtensions $true
        Write-Host "  ⚡ Enabled nested virtualization" -ForegroundColor Yellow
    }
    
    # GPU passthrough for AI Stack (if available)
    if ($VM.GPU) {
        Write-Host "  🎮 Configuring GPU access..." -ForegroundColor Yellow
        try {
            Add-VMGpuPartitionAdapter -VMName $VM.Name -ErrorAction SilentlyContinue
            Set-VM -Name $VM.Name -GuestControlledCacheTypes $true -LowMemoryMappedIoSpace 1Gb -HighMemoryMappedIoSpace 32Gb -ErrorAction SilentlyContinue
            Write-Host "  ✅ GPU passthrough configured" -ForegroundColor Green
        } catch {
            Write-Host "  ⚠️  GPU passthrough available after VM start" -ForegroundColor Yellow
        }
    }
    
    # Mount Ubuntu ISO
    Add-VMDvdDrive -VMName $VM.Name -Path $IsoPath
    
    Write-Host "  ✅ VM $($VM.Name) created - IP: $($VM.IP)" -ForegroundColor Green
}

# Generate Ubuntu installation guide
$InstallGuidePath = "$VmPath\ubuntu-install-guide.txt"
$InstallGuide = @"
AutoBot Ubuntu Installation Guide - Simple Setup
===============================================

Network Configuration for Each VM:
----------------------------------
Use STATIC IP configuration during Ubuntu installation:

Subnet: 192.168.100.0/24
Netmask: 255.255.255.0
Gateway: 192.168.100.1 (Hyper-V host)

VM IP Assignments:
-----------------
AutoBot-Frontend  : 192.168.100.10
AutoBot-Backend   : 192.168.100.20  
AutoBot-AIStack   : 192.168.100.30
AutoBot-NPUWorker : 192.168.100.40
AutoBot-Redis     : 192.168.100.50

DNS Settings:
------------
Primary DNS: 8.8.8.8
Secondary DNS: 1.1.1.1

Ubuntu Installation Steps:
-------------------------
1. Start VM and boot from Ubuntu Server ISO
2. Follow installation wizard
3. When prompted for network configuration:
   - Choose "Manual" network configuration
   - Set static IP from assignments above
   - Set gateway to 192.168.100.1 (host IP)
   - Set DNS to 8.8.8.8, 1.1.1.1
4. Set hostname to match VM name (e.g., autobot-frontend)
5. Create user: autobot (with sudo privileges)
6. Install SSH server: Yes
7. Complete installation and reboot

Post-Installation:
-----------------
1. Test host connectivity: ping 192.168.100.1
2. Test VM-to-VM: ping other VM IPs
3. Test internet (if firewall routing configured): ping 8.8.8.8
4. Verify SSH access from host: ssh autobot@192.168.100.XX

Notes:
-----
- No VLAN configuration needed - simple internal network
- Internet access depends on firewall adapter routing setup
- All VMs can communicate with each other directly
- Host can manage all VMs via SSH on their IPs
"@

$InstallGuide | Out-File -FilePath $InstallGuidePath -Encoding UTF8

Write-Host "`n📋 Installation Summary:" -ForegroundColor Cyan
Write-Host "========================" -ForegroundColor Cyan
Write-Host "Total VMs: $($VMs.Count)" -ForegroundColor White
Write-Host "Network: Internal virtual ethernet" -ForegroundColor White
Write-Host "Host IP: 192.168.100.1" -ForegroundColor White
Write-Host "VM Range: 192.168.100.10-50" -ForegroundColor White

Write-Host "`n📁 Installation guide created:" -ForegroundColor Yellow
Write-Host "  $InstallGuidePath" -ForegroundColor White

Write-Host "`n🔧 Next Steps:" -ForegroundColor Cyan
Write-Host "1. Install Ubuntu Server on each VM using guide above" -ForegroundColor Gray
Write-Host "2. Test basic connectivity between VMs and host" -ForegroundColor Gray
Write-Host "3. Configure internet access via firewall (if needed)" -ForegroundColor Gray
Write-Host "4. Run Ansible deployment scripts" -ForegroundColor Gray

Write-Host "`n✅ AutoBot VMs created successfully!" -ForegroundColor Green
Write-Host "Simple internal network - no VLANs, just virtual ethernet." -ForegroundColor Yellow