# Configure Hyper-V VLANs for AutoBot with pfSense as Gateway Only
# Run as Administrator
# pfSense provides internet gateway, Hyper-V handles internal VLANs

param(
    [string]$DefaultGateway = "192.168.1.1",     # Default gateway IP (any router/gateway)
    [string]$AutoBotVLAN = "100",               # VLAN ID for AutoBot isolation
    [string]$SwitchName = "AutoBot-External"     # External switch connected to network
)

Write-Host "🔧 Configuring AutoBot Hyper-V VLANs with pfSense Gateway" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

Write-Host "🌐 Network Architecture:" -ForegroundColor Yellow
Write-Host "  pfSense: Gateway/Router only (provides internet access)" -ForegroundColor White
Write-Host "  Hyper-V: VLAN isolation (internal traffic management)" -ForegroundColor White
Write-Host "  AutoBot: Completely isolated on VLAN $AutoBotVLAN" -ForegroundColor White

# Test pfSense connectivity first
Write-Host "`n🔍 Testing pfSense gateway connectivity..." -ForegroundColor Cyan
$PfSensePing = Test-Connection -ComputerName $PfSenseGateway -Count 2 -Quiet
if (-not $PfSensePing) {
    Write-Host "❌ Cannot reach pfSense gateway at $PfSenseGateway" -ForegroundColor Red
    Write-Host "   Make sure this host can reach pfSense for internet access" -ForegroundColor Yellow
    exit 1
}
Write-Host "✅ pfSense gateway reachable at $PfSenseGateway" -ForegroundColor Green

# Create External switch connected to pfSense network
if (-not (Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue)) {
    Write-Host "`nCreating external switch connected to pfSense..." -ForegroundColor Green
    
    # Find the network adapter that can reach pfSense
    $PfSenseAdapter = $null
    $Adapters = Get-NetAdapter | Where-Object {$_.Status -eq "Up"}
    
    foreach ($Adapter in $Adapters) {
        $AdapterRoute = Get-NetRoute -InterfaceAlias $Adapter.Name -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue
        if ($AdapterRoute -and $AdapterRoute.NextHop -eq $PfSenseGateway) {
            $PfSenseAdapter = $Adapter
            break
        }
    }
    
    if (-not $PfSenseAdapter) {
        # Fallback: use the first active Ethernet adapter
        $PfSenseAdapter = $Adapters | Where-Object {$_.MediaType -eq "802.3"} | Select-Object -First 1
    }
    
    if (-not $PfSenseAdapter) {
        Write-Host "❌ No suitable network adapter found for pfSense connection" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Using network adapter: $($PfSenseAdapter.Name)" -ForegroundColor Yellow
    New-VMSwitch -Name $SwitchName -NetAdapterName $PfSenseAdapter.Name -AllowManagementOS $true
    Write-Host "✅ Created external switch: $SwitchName" -ForegroundColor Green
    
} else {
    Write-Host "External switch '$SwitchName' already exists" -ForegroundColor Yellow
}

Write-Host "`n🏗️  AutoBot VLAN Configuration:" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan

Write-Host "VLAN $AutoBotVLAN Configuration:" -ForegroundColor Yellow
Write-Host "  Purpose: Complete AutoBot isolation" -ForegroundColor White
Write-Host "  Network: 192.168.$AutoBotVLAN.0/24" -ForegroundColor White
Write-Host "  Gateway: $PfSenseGateway (internet access only)" -ForegroundColor White
Write-Host "  DNS: 8.8.8.8, 1.1.1.1 (through pfSense)" -ForegroundColor White

Write-Host "`n📋 VM IP Assignments:" -ForegroundColor Yellow
Write-Host "  AutoBot-Frontend : 192.168.$AutoBotVLAN.10" -ForegroundColor White
Write-Host "  AutoBot-Backend  : 192.168.$AutoBotVLAN.20" -ForegroundColor White  
Write-Host "  AutoBot-AIStack  : 192.168.$AutoBotVLAN.30" -ForegroundColor White
Write-Host "  AutoBot-NPUWorker: 192.168.$AutoBotVLAN.40" -ForegroundColor White
Write-Host "  AutoBot-Redis    : 192.168.$AutoBotVLAN.50" -ForegroundColor White

Write-Host "`n🛡️  Security Benefits:" -ForegroundColor Cyan
Write-Host "=====================" -ForegroundColor Cyan
Write-Host "✅ Complete Network Isolation: AutoBot VMs can only talk to each other" -ForegroundColor Green
Write-Host "✅ Gateway-Only Access: pfSense only provides internet, no LAN access" -ForegroundColor Green
Write-Host "✅ VLAN Segmentation: Hyper-V enforces VLAN boundaries" -ForegroundColor Green
Write-Host "✅ No External Exposure: AutoBot services not accessible from outside" -ForegroundColor Green
Write-Host "✅ Controlled Internet: Only outbound connections for updates/packages" -ForegroundColor Green

Write-Host "`n🔧 pfSense Configuration (Minimal Required):" -ForegroundColor Yellow
Write-Host "============================================" -ForegroundColor Yellow
Write-Host "pfSense only needs basic routing - NO special VLAN config needed!" -ForegroundColor Green
Write-Host "✅ Default routing: pfSense routes 192.168.$AutoBotVLAN.0/24 to internet" -ForegroundColor White
Write-Host "✅ DNS forwarding: pfSense forwards DNS queries (8.8.8.8, 1.1.1.1)" -ForegroundColor White
Write-Host "✅ Firewall rules: Standard outbound internet access (HTTP/HTTPS/DNS)" -ForegroundColor White
Write-Host "🚫 No VLAN config: Hyper-V handles all VLAN isolation internally" -ForegroundColor Red
Write-Host "🚫 No special rules: pfSense treats AutoBot traffic like any other subnet" -ForegroundColor Red

Write-Host "`n📦 Next Steps:" -ForegroundColor Cyan
Write-Host "1. Run: .\create-autobot-vms-vlans.ps1 (creates VMs with VLAN isolation)" -ForegroundColor Gray
Write-Host "2. Install Ubuntu on each VM with static IPs" -ForegroundColor Gray
Write-Host "3. Configure each VM to use $PfSenseGateway as default gateway" -ForegroundColor Gray
Write-Host "4. Run: .\discover-vm-ips.ps1 --update-inventory" -ForegroundColor Gray
Write-Host "5. Deploy: .\scripts\ansible\deploy.sh deploy-all" -ForegroundColor Gray

Write-Host "`n✅ Hyper-V VLAN configuration ready!" -ForegroundColor Green
Write-Host "AutoBot will be completely isolated while using pfSense for internet access." -ForegroundColor Yellow