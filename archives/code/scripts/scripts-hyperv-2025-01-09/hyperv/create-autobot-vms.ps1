# AutoBot Hyper-V VM Creation Script
# Run as Administrator in PowerShell

$VmPath = "C:\AutoBot-VMs"
$IsoPath = "C:\ISO\ubuntu-22.04.3-live-server-amd64.iso"  # Download Ubuntu Server ISO
$SwitchName = "AutoBot-Internal"

# Create VM directory
New-Item -ItemType Directory -Path $VmPath -Force

# VM Configurations
$VMs = @(
    @{Name="AutoBot-Frontend"; RAM=2GB; CPU=2; Disk=20GB; IP="192.168.100.10"},
    @{Name="AutoBot-Backend"; RAM=8GB; CPU=4; Disk=40GB; IP="192.168.100.20"},
    @{Name="AutoBot-AIStack"; RAM=16GB; CPU=6; Disk=60GB; IP="192.168.100.30"; GPU=$true},
    @{Name="AutoBot-NPUWorker"; RAM=8GB; CPU=4; Disk=40GB; IP="192.168.100.40"; NPU=$true},
    @{Name="AutoBot-Redis"; RAM=8GB; CPU=2; Disk=100GB; IP="192.168.100.50"}
)

foreach ($VM in $VMs) {
    Write-Host "Creating VM: $($VM.Name)" -ForegroundColor Green
    
    # Create VM
    New-VM -Name $VM.Name -MemoryStartupBytes $VM.RAM -Path $VmPath -NewVHDPath "$VmPath\$($VM.Name)\$($VM.Name).vhdx" -NewVHDSizeBytes $VM.Disk
    
    # Configure VM
    Set-VM -Name $VM.Name -ProcessorCount $VM.CPU -AutomaticStartAction Start -AutomaticStopAction ShutDown
    
    # Connect to AutoBot Internal switch
    Get-VMNetworkAdapter -VMName $VM.Name | Connect-VMNetworkAdapter -SwitchName $SwitchName
    
    # Enable nested virtualization for AI/NPU VMs
    if ($VM.Name -match "AIStack|NPUWorker") {
        Set-VMProcessor -VMName $VM.Name -ExposeVirtualizationExtensions $true
    }
    
    # GPU passthrough for AI Stack
    if ($VM.GPU) {
        Write-Host "Configuring GPU passthrough for $($VM.Name)" -ForegroundColor Yellow
        Add-VMGpuPartitionAdapter -VMName $VM.Name
        Set-VM -Name $VM.Name -GuestControlledCacheTypes $true -LowMemoryMappedIoSpace 1Gb -HighMemoryMappedIoSpace 32Gb
    }
    
    # Mount Ubuntu ISO
    Add-VMDvdDrive -VMName $VM.Name -Path $IsoPath
    
    Write-Host "VM $($VM.Name) created successfully" -ForegroundColor Green
}

Write-Host "`nAll AutoBot VMs created!" -ForegroundColor Cyan
Write-Host "Network: AutoBot-Internal (192.168.100.0/24)" -ForegroundColor Yellow
Write-Host "Next steps:" -ForegroundColor White
Write-Host "1. Install Ubuntu Server on each VM" -ForegroundColor Gray
Write-Host "2. Configure static IPs" -ForegroundColor Gray
Write-Host "3. Install AutoBot services" -ForegroundColor Gray