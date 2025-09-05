# Create Simple AutoBot Network - Development Environment
# Run as Administrator
# Creates basic internal virtual ethernet for host + VMs

param(
    [string]$SwitchName = "AutoBot-Internal",
    [string]$HostIP = "192.168.100.1",
    [string]$NetworkRange = "192.168.100.0/24"
)

Write-Host "🔧 Creating Simple AutoBot Network for Development" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

# Create Internal virtual switch (Host + VMs can communicate)
if (-not (Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue)) {
    Write-Host "Creating internal virtual switch: $SwitchName" -ForegroundColor Green
    New-VMSwitch -Name $SwitchName -SwitchType Internal
    Write-Host "✅ Internal switch created successfully" -ForegroundColor Green
} else {
    Write-Host "✅ Internal switch '$SwitchName' already exists" -ForegroundColor Yellow
}

# Configure host IP on the virtual adapter
Write-Host "`nConfiguring host networking..." -ForegroundColor Green
$VirtualAdapter = Get-NetAdapter | Where-Object Name -like "*$SwitchName*"

if ($VirtualAdapter) {
    Write-Host "Found virtual adapter: $($VirtualAdapter.Name)" -ForegroundColor Yellow
    
    # Remove existing IP configuration
    Remove-NetIPAddress -InterfaceAlias $VirtualAdapter.Name -ErrorAction SilentlyContinue -Confirm:$false
    Remove-NetRoute -InterfaceAlias $VirtualAdapter.Name -ErrorAction SilentlyContinue -Confirm:$false
    
    # Set host IP
    New-NetIPAddress -InterfaceAlias $VirtualAdapter.Name -IPAddress $HostIP -PrefixLength 24
    Write-Host "✅ Host IP configured: $HostIP" -ForegroundColor Green
    
} else {
    Write-Host "❌ Could not find virtual adapter for $SwitchName" -ForegroundColor Red
    exit 1
}

Write-Host "`n🌐 AutoBot Development Network:" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan
Write-Host "Switch Type: Internal (Host + VMs)" -ForegroundColor White
Write-Host "Host IP: $HostIP" -ForegroundColor White
Write-Host "VM Range: 192.168.100.10-50" -ForegroundColor White
Write-Host "Internet: Via firewall adapter (separate)" -ForegroundColor White

Write-Host "`n📋 Planned VM IPs:" -ForegroundColor Yellow
Write-Host "  Host (Hyper-V)      : $HostIP" -ForegroundColor White
Write-Host "  AutoBot-Frontend    : 192.168.100.10" -ForegroundColor White
Write-Host "  AutoBot-Backend     : 192.168.100.20" -ForegroundColor White
Write-Host "  AutoBot-AIStack     : 192.168.100.30" -ForegroundColor White
Write-Host "  AutoBot-NPUWorker   : 192.168.100.40" -ForegroundColor White
Write-Host "  AutoBot-Redis       : 192.168.100.50" -ForegroundColor White

Write-Host "`n🔧 Network Characteristics:" -ForegroundColor Cyan
Write-Host "✅ Host can reach all VMs directly" -ForegroundColor Green
Write-Host "✅ VMs can reach each other directly" -ForegroundColor Green
Write-Host "✅ VMs can reach host for services" -ForegroundColor Green
Write-Host "📡 Internet access: Configure via firewall adapter routing" -ForegroundColor Yellow
Write-Host "🔒 External access: VMs not directly accessible from outside" -ForegroundColor Green

Write-Host "`n🔧 Next Steps:" -ForegroundColor Cyan
Write-Host "1. Run: .\create-autobot-vms-simple.ps1" -ForegroundColor Gray
Write-Host "2. Install Ubuntu on VMs with static IPs (192.168.100.10-50)" -ForegroundColor Gray
Write-Host "3. Configure internet access via firewall routing (if needed)" -ForegroundColor Gray
Write-Host "4. Run: .\discover-vms-simple.ps1 --update-inventory" -ForegroundColor Gray
Write-Host "5. Deploy: .\scripts\ansible\deploy.sh deploy-all" -ForegroundColor Gray

Write-Host "`n✅ Simple AutoBot network ready!" -ForegroundColor Green
Write-Host "Internal virtual ethernet created - host and VMs can communicate." -ForegroundColor Yellow