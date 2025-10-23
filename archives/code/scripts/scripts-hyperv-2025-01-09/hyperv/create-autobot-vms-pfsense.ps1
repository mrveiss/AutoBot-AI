# AutoBot Hyper-V VM Creation Script with pfSense Integration
# Run as Administrator in PowerShell

param(
    [string]$VmPath = "C:\AutoBot-VMs",
    [string]$IsoPath = "C:\ISO\ubuntu-22.04.3-live-server-amd64.iso",
    [string]$SwitchName = "AutoBot-pfSense",
    [string]$AutoBotVLAN = "100",
    [switch]$UseDHCP = $false,  # Use DHCP instead of static IPs
    [switch]$CreateVLANs = $true  # Create VLAN configuration per VM
)

# Create VM directory
New-Item -ItemType Directory -Path $VmPath -Force

# VM Configurations with pfSense network
$VMs = @(
    @{Name="AutoBot-Frontend"; RAM=2GB; CPU=2; Disk=20GB; StaticIP="192.168.$AutoBotVLAN.10"; VLAN=$AutoBotVLAN},
    @{Name="AutoBot-Backend"; RAM=8GB; CPU=4; Disk=40GB; StaticIP="192.168.$AutoBotVLAN.20"; VLAN=$AutoBotVLAN},
    @{Name="AutoBot-AIStack"; RAM=16GB; CPU=6; Disk=60GB; StaticIP="192.168.$AutoBotVLAN.30"; VLAN=$AutoBotVLAN; GPU=$true},
    @{Name="AutoBot-NPUWorker"; RAM=8GB; CPU=4; Disk=40GB; StaticIP="192.168.$AutoBotVLAN.40"; VLAN=$AutoBotVLAN; NPU=$true},
    @{Name="AutoBot-Redis"; RAM=8GB; CPU=2; Disk=100GB; StaticIP="192.168.$AutoBotVLAN.50"; VLAN=$AutoBotVLAN}
)

Write-Host "🔥 Creating AutoBot VMs with pfSense Integration" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "Network Mode: $(if($UseDHCP){'DHCP from pfSense'}else{'Static IPs'})" -ForegroundColor Yellow
Write-Host "VLAN: $AutoBotVLAN" -ForegroundColor Yellow
Write-Host "Switch: $SwitchName" -ForegroundColor Yellow

foreach ($VM in $VMs) {
    Write-Host "`nCreating VM: $($VM.Name)" -ForegroundColor Green
    
    # Create VM
    New-VM -Name $VM.Name -MemoryStartupBytes $VM.RAM -Path $VmPath -NewVHDPath "$VmPath\$($VM.Name)\$($VM.Name).vhdx" -NewVHDSizeBytes $VM.Disk
    
    # Configure VM
    Set-VM -Name $VM.Name -ProcessorCount $VM.CPU -AutomaticStartAction Start -AutomaticStopAction ShutDown
    
    # Connect to pfSense switch
    Get-VMNetworkAdapter -VMName $VM.Name | Connect-VMNetworkAdapter -SwitchName $SwitchName
    
    # Configure VLAN if enabled
    if ($CreateVLANs -and $VM.VLAN) {
        Write-Host "  Configuring VLAN $($VM.VLAN) for $($VM.Name)" -ForegroundColor Yellow
        Set-VMNetworkAdapterVlan -VMName $VM.Name -Access -VlanId $VM.VLAN
    }
    
    # Enable nested virtualization for AI/NPU VMs
    if ($VM.Name -match "AIStack|NPUWorker") {
        Set-VMProcessor -VMName $VM.Name -ExposeVirtualizationExtensions $true
        Write-Host "  Enabled nested virtualization for $($VM.Name)" -ForegroundColor Yellow
    }
    
    # GPU passthrough for AI Stack
    if ($VM.GPU) {
        Write-Host "  Configuring GPU passthrough for $($VM.Name)" -ForegroundColor Yellow
        try {
            Add-VMGpuPartitionAdapter -VMName $VM.Name
            Set-VM -Name $VM.Name -GuestControlledCacheTypes $true -LowMemoryMappedIoSpace 1Gb -HighMemoryMappedIoSpace 32Gb
        } catch {
            Write-Host "  ⚠️  GPU passthrough failed - may need manual configuration" -ForegroundColor Yellow
        }
    }
    
    # Enhanced security configuration
    Set-VM -Name $VM.Name -AutomaticCheckpointsEnabled $false -CheckpointType ProductionOnly
    
    # Mount Ubuntu ISO
    Add-VMDvdDrive -VMName $VM.Name -Path $IsoPath
    
    Write-Host "  ✅ VM $($VM.Name) created successfully" -ForegroundColor Green
}

# Generate network configuration for Ubuntu installation
$NetworkConfigPath = "$VmPath\network-config.yaml"
$NetworkConfig = @"
# AutoBot Network Configuration for Ubuntu Installation
# Use this configuration during Ubuntu Server setup

network:
  version: 2
  ethernets:
    enp0s3:  # Primary network interface
      dhcp4: $(if($UseDHCP){'true'}else{'false'})
$(if(-not $UseDHCP){
$VMs | ForEach-Object {
@"
      # For $($_.Name):
      # addresses: [$($_.StaticIP)/24]
      # gateway4: 192.168.$AutoBotVLAN.1
      # nameservers:
      #   addresses: [8.8.8.8, 1.1.1.1]

"@
}
})
"@

$NetworkConfig | Out-File -FilePath $NetworkConfigPath -Encoding UTF8

Write-Host "`n🌐 pfSense Configuration Required:" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

Write-Host "`n1. Create VLAN Interface:" -ForegroundColor Yellow
Write-Host "   - Navigate to Interfaces > Assignments" -ForegroundColor Gray
Write-Host "   - Create VLAN $AutoBotVLAN on your LAN interface" -ForegroundColor Gray
Write-Host "   - Assign interface and enable" -ForegroundColor Gray
Write-Host "   - Set IP: 192.168.$AutoBotVLAN.1/24" -ForegroundColor Gray

if ($UseDHCP) {
    Write-Host "`n2. Configure DHCP Server:" -ForegroundColor Yellow
    Write-Host "   - Navigate to Services > DHCP Server" -ForegroundColor Gray
    Write-Host "   - Enable DHCP for VLAN $AutoBotVLAN" -ForegroundColor Gray
    Write-Host "   - Range: 192.168.$AutoBotVLAN.10 - 192.168.$AutoBotVLAN.50" -ForegroundColor Gray
    Write-Host "   - DNS: 8.8.8.8, 1.1.1.1" -ForegroundColor Gray
} else {
    Write-Host "`n2. Note Static IP Assignments:" -ForegroundColor Yellow
    foreach ($VM in $VMs) {
        Write-Host "   - $($VM.Name): $($VM.StaticIP)" -ForegroundColor Gray
    }
}

Write-Host "`n3. Configure Firewall Rules (Interfaces > Firewall Rules):" -ForegroundColor Yellow
Write-Host "   AutoBot_VLAN rules:" -ForegroundColor Gray
Write-Host "   ✅ ALLOW: AutoBot net -> AutoBot net (port any)" -ForegroundColor Green
Write-Host "   ✅ ALLOW: AutoBot net -> WAN (port 80,443,53)" -ForegroundColor Green
Write-Host "   ✅ ALLOW: LAN net -> AutoBot net (port 22,8000-8081)" -ForegroundColor Green
Write-Host "   🚫 BLOCK: AutoBot net -> LAN net" -ForegroundColor Red
Write-Host "   🚫 BLOCK: WAN -> AutoBot net (default)" -ForegroundColor Red

Write-Host "`n4. Optional Traffic Shaping:" -ForegroundColor Yellow
Write-Host "   - Navigate to Firewall > Traffic Shaping" -ForegroundColor Gray
Write-Host "   - Create limiter for AutoBot VLAN if needed" -ForegroundColor Gray
Write-Host "   - Recommended: Limit to 80% of available bandwidth" -ForegroundColor Gray

Write-Host "`n📋 VM Installation Steps:" -ForegroundColor Cyan
Write-Host "========================" -ForegroundColor Cyan
Write-Host "1. Start each VM and install Ubuntu Server 22.04" -ForegroundColor Gray
Write-Host "2. During network setup:" -ForegroundColor Gray
if ($UseDHCP) {
    Write-Host "   - Select 'Use DHCP' for network configuration" -ForegroundColor Gray
} else {
    Write-Host "   - Use static IP configuration from the list above" -ForegroundColor Gray
    Write-Host "   - Gateway: 192.168.$AutoBotVLAN.1" -ForegroundColor Gray
    Write-Host "   - DNS: 8.8.8.8, 1.1.1.1" -ForegroundColor Gray
}
Write-Host "3. Create user 'autobot' for Ansible automation" -ForegroundColor Gray
Write-Host "4. Install SSH server during setup" -ForegroundColor Gray

Write-Host "`n📁 Network configuration template created at:" -ForegroundColor Green
Write-Host "   $NetworkConfigPath" -ForegroundColor White

Write-Host "`n🔧 Next Steps:" -ForegroundColor Cyan
Write-Host "1. Configure pfSense VLAN and firewall rules (above)" -ForegroundColor Gray
Write-Host "2. Install Ubuntu on all VMs" -ForegroundColor Gray
Write-Host "3. Run VM discovery: .\discover-vm-ips-pfsense.ps1" -ForegroundColor Gray
Write-Host "4. Deploy with Ansible: .\scripts\ansible\deploy.sh deploy-all" -ForegroundColor Gray

Write-Host "`n✅ All AutoBot VMs created with pfSense integration!" -ForegroundColor Green