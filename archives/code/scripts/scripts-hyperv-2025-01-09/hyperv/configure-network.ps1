# Configure Hyper-V Internal Switch for AutoBot
# Run as Administrator
# Internal switch keeps all VM traffic on the host - no external network access

$SwitchName = "AutoBot-Internal"

# Create Internal virtual switch (VM-to-VM + Host-to-VM only)
if (-not (Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue)) {
    Write-Host "Creating AutoBot Internal virtual switch..." -ForegroundColor Green
    New-VMSwitch -Name $SwitchName -SwitchType Internal
} else {
    Write-Host "AutoBot Internal switch already exists" -ForegroundColor Yellow
}

# Configure internal network with NAT and firewall
Write-Host "Configuring internal network with firewall..." -ForegroundColor Green

# Get the virtual adapter created by the Internal switch
$VirtualAdapter = Get-NetAdapter | Where-Object Name -like "*$SwitchName*"

if ($VirtualAdapter) {
    Write-Host "Found internal virtual adapter: $($VirtualAdapter.Name)" -ForegroundColor Yellow
    
    # Configure Windows host as gateway for internal VMs
    Remove-NetIPAddress -InterfaceAlias $VirtualAdapter.Name -ErrorAction SilentlyContinue -Confirm:$false
    Remove-NetRoute -InterfaceAlias $VirtualAdapter.Name -ErrorAction SilentlyContinue -Confirm:$false
    
    # Set host IP on internal network (VMs will use this as gateway)
    New-NetIPAddress -InterfaceAlias $VirtualAdapter.Name -IPAddress "192.168.100.1" -PrefixLength 24
    
    # Create NAT for controlled internet access
    Write-Host "Creating NAT for controlled internet access..." -ForegroundColor Yellow
    Remove-NetNat -Name "AutoBot-NAT" -ErrorAction SilentlyContinue -Confirm:$false
    New-NetNat -Name "AutoBot-NAT" -InternalIPInterfaceAddressPrefix "192.168.100.0/24"
    
    # Configure Windows Firewall rules for AutoBot internal network
    Write-Host "Configuring firewall rules..." -ForegroundColor Yellow
    
    # Allow internal VM-to-VM traffic
    New-NetFirewallRule -DisplayName "AutoBot Internal VM Traffic" -Direction Inbound -Protocol Any -LocalAddress "192.168.100.0/24" -RemoteAddress "192.168.100.0/24" -Action Allow -Profile Any -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName "AutoBot Internal VM Traffic" -Direction Outbound -Protocol Any -LocalAddress "192.168.100.0/24" -RemoteAddress "192.168.100.0/24" -Action Allow -Profile Any -ErrorAction SilentlyContinue
    
    # Allow specific outbound for package updates (HTTP/HTTPS/DNS)
    New-NetFirewallRule -DisplayName "AutoBot VM Updates HTTP" -Direction Outbound -Protocol TCP -LocalAddress "192.168.100.0/24" -LocalPort Any -RemotePort 80 -Action Allow -Profile Any -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName "AutoBot VM Updates HTTPS" -Direction Outbound -Protocol TCP -LocalAddress "192.168.100.0/24" -LocalPort Any -RemotePort 443 -Action Allow -Profile Any -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName "AutoBot VM DNS" -Direction Outbound -Protocol UDP -LocalAddress "192.168.100.0/24" -LocalPort Any -RemotePort 53 -Action Allow -Profile Any -ErrorAction SilentlyContinue
    
    # Block all other outbound from VMs (default deny)
    New-NetFirewallRule -DisplayName "AutoBot VM Block Others" -Direction Outbound -LocalAddress "192.168.100.0/24" -Action Block -Profile Any -ErrorAction SilentlyContinue
    
    # Allow host-to-VM management traffic (SSH, HTTP APIs)
    New-NetFirewallRule -DisplayName "AutoBot Host to VM SSH" -Direction Inbound -Protocol TCP -LocalAddress "192.168.100.1" -RemoteAddress "192.168.100.0/24" -RemotePort 22 -Action Allow -Profile Any -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName "AutoBot Host to VM HTTP" -Direction Inbound -Protocol TCP -LocalAddress "192.168.100.1" -RemoteAddress "192.168.100.0/24" -RemotePort @(80,443,8000,8001,8080,8081) -Action Allow -Profile Any -ErrorAction SilentlyContinue
    
    Write-Host "Network with firewall configured:" -ForegroundColor Cyan
    Write-Host "  Windows Host IP: 192.168.100.1" -ForegroundColor White
    Write-Host "  VM Range: 192.168.100.10-192.168.100.50" -ForegroundColor White
    Write-Host "  Internal Traffic: ALLOWED (VM-to-VM)" -ForegroundColor Green
    Write-Host "  Internet Access: CONTROLLED (HTTP/HTTPS/DNS only)" -ForegroundColor Yellow
    Write-Host "  Management: SSH and API ports open to host" -ForegroundColor Cyan
    Write-Host "  Security: All other traffic blocked" -ForegroundColor Red
} else {
    Write-Host "Could not find internal virtual adapter" -ForegroundColor Red
    exit 1
}

Write-Host "`nNetwork configuration complete!" -ForegroundColor Green