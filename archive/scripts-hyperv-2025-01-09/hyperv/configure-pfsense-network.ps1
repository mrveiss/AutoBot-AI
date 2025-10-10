# Configure Hyper-V with pfSense Integration for AutoBot
# Run as Administrator
# Assumes pfSense VM is already configured and running

param(
    [string]$PfSenseIP = "192.168.1.1",  # Your pfSense LAN IP
    [string]$AutoBotVLAN = "100",        # VLAN ID for AutoBot network
    [string]$SwitchName = "AutoBot-pfSense"
)

Write-Host "🔥 Configuring AutoBot with pfSense Integration" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# Create External switch connected to pfSense network
if (-not (Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue)) {
    Write-Host "Creating pfSense-connected virtual switch..." -ForegroundColor Green
    
    # Get the network adapter connected to pfSense
    $PhysicalAdapter = Get-NetAdapter | Where-Object {$_.Status -eq "Up" -and $_.MediaType -eq "802.3"} | Select-Object -First 1
    
    if (-not $PhysicalAdapter) {
        Write-Host "❌ No suitable network adapter found" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Using network adapter: $($PhysicalAdapter.Name)" -ForegroundColor Yellow
    New-VMSwitch -Name $SwitchName -NetAdapterName $PhysicalAdapter.Name -AllowManagementOS $true
} else {
    Write-Host "pfSense virtual switch already exists" -ForegroundColor Yellow
}

# Configure VLAN for AutoBot VMs if specified
if ($AutoBotVLAN -ne "0") {
    Write-Host "Configuring VLAN $AutoBotVLAN for AutoBot isolation..." -ForegroundColor Green
    
    # Note: VLAN configuration will be done per-VM
    Write-Host "VLAN $AutoBotVLAN will be configured on each AutoBot VM" -ForegroundColor Yellow
}

Write-Host "`n🌐 pfSense Network Architecture:" -ForegroundColor Cyan
Write-Host "  pfSense IP: $PfSenseIP" -ForegroundColor White
Write-Host "  AutoBot VLAN: $AutoBotVLAN (if configured)" -ForegroundColor White
Write-Host "  Switch: $SwitchName" -ForegroundColor White
Write-Host "  VM Range: 192.168.$AutoBotVLAN.10-192.168.$AutoBotVLAN.50" -ForegroundColor White

Write-Host "`n🔧 Next Steps for pfSense Configuration:" -ForegroundColor Cyan
Write-Host "1. Create VLAN $AutoBotVLAN interface in pfSense" -ForegroundColor Gray
Write-Host "2. Configure DHCP scope for AutoBot VMs" -ForegroundColor Gray
Write-Host "3. Set up firewall rules for AutoBot network" -ForegroundColor Gray
Write-Host "4. Configure traffic shaping if needed" -ForegroundColor Gray

Write-Host "`n🛡️ Recommended pfSense Rules for AutoBot:" -ForegroundColor Yellow
Write-Host "ALLOW: AutoBot VLAN -> AutoBot VLAN (internal traffic)" -ForegroundColor Green
Write-Host "ALLOW: AutoBot VLAN -> Internet:80,443,53 (updates)" -ForegroundColor Green
Write-Host "ALLOW: LAN -> AutoBot VLAN:22,8000-8081 (management)" -ForegroundColor Green
Write-Host "BLOCK: AutoBot VLAN -> LAN (except management)" -ForegroundColor Red
Write-Host "BLOCK: Internet -> AutoBot VLAN (no inbound)" -ForegroundColor Red

Write-Host "`n✅ Hyper-V configuration complete!" -ForegroundColor Green
Write-Host "Configure pfSense VLAN and rules, then run create-autobot-vms-pfsense.ps1" -ForegroundColor Yellow