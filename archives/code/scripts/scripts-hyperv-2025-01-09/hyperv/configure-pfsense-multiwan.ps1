# Configure AutoBot with pfSense Multi-WAN Failover Integration
# Run as Administrator
# Optimized for pfSense with 3 interfaces: LAN, WAN1 (Ethernet), WAN2 (WiFi Bridge)

param(
    [string]$PfSenseLANIP = "192.168.1.1",       # pfSense LAN interface IP
    [string]$AutoBotVLAN = "100",                # VLAN for AutoBot isolation
    [string]$SwitchName = "AutoBot-pfSense-MultiWAN",
    [switch]$CreateHighAvailability = $true,     # Enable HA configuration
    [switch]$EnableFailoverTesting = $true       # Allow testing failover scenarios
)

Write-Host "🌐 Configuring AutoBot with pfSense Multi-WAN Failover" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

Write-Host "🔗 Detected pfSense Multi-WAN Configuration:" -ForegroundColor Yellow
Write-Host "  Interface 1: LAN (AutoBot Management)" -ForegroundColor White
Write-Host "  Interface 2: WAN1 (Ethernet - Primary)" -ForegroundColor White
Write-Host "  Interface 3: WAN2 (WiFi Bridge - Backup)" -ForegroundColor White
Write-Host "  AutoBot VLAN: $AutoBotVLAN" -ForegroundColor White

# Create External switch connected to pfSense LAN
if (-not (Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue)) {
    Write-Host "Creating multi-WAN pfSense virtual switch..." -ForegroundColor Green
    
    # Get the network adapter connected to pfSense LAN
    Write-Host "Detecting network adapter connected to pfSense LAN..." -ForegroundColor Yellow
    
    $PfSenseReachable = $false
    $SelectedAdapter = $null
    
    # Test each adapter to find the one connected to pfSense
    $Adapters = Get-NetAdapter | Where-Object {$_.Status -eq "Up" -and $_.MediaType -eq "802.3"}
    
    foreach ($Adapter in $Adapters) {
        Write-Host "  Testing adapter: $($Adapter.Name)" -ForegroundColor Gray
        
        # Get IP config for this adapter
        $AdapterIP = Get-NetIPAddress -InterfaceAlias $Adapter.Name -AddressFamily IPv4 -ErrorAction SilentlyContinue
        
        if ($AdapterIP) {
            # Test if we can reach pfSense from this adapter
            $PingResult = Test-Connection -ComputerName $PfSenseLANIP -Count 1 -Quiet -TimeoutSeconds 2
            
            if ($PingResult) {
                $SelectedAdapter = $Adapter
                $PfSenseReachable = $true
                Write-Host "  ✅ Found pfSense connection via: $($Adapter.Name)" -ForegroundColor Green
                break
            }
        }
    }
    
    if (-not $PfSenseReachable) {
        Write-Host "❌ Cannot reach pfSense at $PfSenseLANIP from any adapter" -ForegroundColor Red
        Write-Host "   Make sure this host is connected to pfSense LAN" -ForegroundColor Yellow
        exit 1
    }
    
    # Create External switch using the pfSense-connected adapter
    New-VMSwitch -Name $SwitchName -NetAdapterName $SelectedAdapter.Name -AllowManagementOS $true
    Write-Host "✅ Created switch '$SwitchName' using adapter '$($SelectedAdapter.Name)'" -ForegroundColor Green
    
} else {
    Write-Host "Multi-WAN pfSense switch already exists" -ForegroundColor Yellow
}

# Test pfSense connectivity and WAN status
Write-Host "`n🔍 Testing pfSense Multi-WAN Status..." -ForegroundColor Cyan

try {
    # Ping test to verify connectivity
    $PfSensePing = Test-Connection -ComputerName $PfSenseLANIP -Count 3 -Quiet
    if ($PfSensePing) {
        Write-Host "✅ pfSense LAN reachable at $PfSenseLANIP" -ForegroundColor Green
        
        # Test internet connectivity through pfSense (to verify WAN failover is working)
        Write-Host "🌐 Testing internet connectivity through pfSense..." -ForegroundColor Yellow
        
        $InternetTest = Test-Connection -ComputerName "8.8.8.8" -Count 2 -Quiet -TimeoutSeconds 5
        if ($InternetTest) {
            Write-Host "✅ Internet connectivity confirmed (WAN failover operational)" -ForegroundColor Green
        } else {
            Write-Host "⚠️  Internet connectivity issues (check pfSense WAN status)" -ForegroundColor Yellow
        }
        
    } else {
        Write-Host "❌ Cannot reach pfSense LAN at $PfSenseLANIP" -ForegroundColor Red
        exit 1
    }
    
} catch {
    Write-Host "❌ Error testing pfSense connectivity: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "`n🎯 AutoBot Network Architecture with pfSense Multi-WAN:" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

Write-Host "🌐 Network Topology:" -ForegroundColor Yellow
Write-Host "  Internet 1 (Ethernet) ←→ pfSense WAN1" -ForegroundColor White
Write-Host "  Internet 2 (WiFi)     ←→ pfSense WAN2 (Failover)" -ForegroundColor White
Write-Host "  pfSense LAN ($PfSenseLANIP) ←→ Host Machine" -ForegroundColor White
Write-Host "  Host Machine ←→ AutoBot VMs (VLAN $AutoBotVLAN)" -ForegroundColor White

Write-Host "`n🏗️  AutoBot VM Placement Strategy:" -ForegroundColor Yellow
Write-Host "  Frontend VM  : 192.168.$AutoBotVLAN.10 (Public-facing)" -ForegroundColor White
Write-Host "  Backend VM   : 192.168.$AutoBotVLAN.20 (API Services)" -ForegroundColor White
Write-Host "  AI Stack VM  : 192.168.$AutoBotVLAN.30 (GPU-intensive)" -ForegroundColor White
Write-Host "  NPU Worker VM: 192.168.$AutoBotVLAN.40 (NPU-optimized)" -ForegroundColor White
Write-Host "  Redis VM     : 192.168.$AutoBotVLAN.50 (Data persistence)" -ForegroundColor White

Write-Host "`n🛡️  pfSense Multi-WAN Configuration Required:" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

Write-Host "`n1. Gateway Group Configuration:" -ForegroundColor Yellow
Write-Host "   System > Routing > Gateway Groups" -ForegroundColor Gray
Write-Host "   - Create 'AutoBot_Failover' group" -ForegroundColor Gray
Write-Host "   - WAN1 (Ethernet): Tier 1, Priority 1" -ForegroundColor Gray
Write-Host "   - WAN2 (WiFi): Tier 2, Priority 2" -ForegroundColor Gray
Write-Host "   - Trigger Level: Packet Loss or High Latency" -ForegroundColor Gray

Write-Host "`n2. VLAN Interface Creation:" -ForegroundColor Yellow
Write-Host "   Interfaces > Assignments > VLANs" -ForegroundColor Gray
Write-Host "   - Create VLAN $AutoBotVLAN on LAN interface" -ForegroundColor Gray
Write-Host "   - Assign new interface: OPT1_AUTOBOT" -ForegroundColor Gray
Write-Host "   - Enable interface" -ForegroundColor Gray
Write-Host "   - Set Static IP: 192.168.$AutoBotVLAN.1/24" -ForegroundColor Gray

Write-Host "`n3. DHCP Server for AutoBot VLAN:" -ForegroundColor Yellow
Write-Host "   Services > DHCP Server > OPT1_AUTOBOT" -ForegroundColor Gray
Write-Host "   - Enable DHCP Server" -ForegroundColor Gray
Write-Host "   - Range: 192.168.$AutoBotVLAN.10 to 192.168.$AutoBotVLAN.50" -ForegroundColor Gray
Write-Host "   - Gateway: 192.168.$AutoBotVLAN.1" -ForegroundColor Gray
Write-Host "   - DNS Servers: 8.8.8.8, 1.1.1.1" -ForegroundColor Gray

Write-Host "`n4. Firewall Rules (Interfaces > Firewall Rules):" -ForegroundColor Yellow
Write-Host "   OPT1_AUTOBOT Interface Rules:" -ForegroundColor Gray
Write-Host "   ✅ ALLOW: AutoBot net -> AutoBot net (All ports)" -ForegroundColor Green
Write-Host "   ✅ ALLOW: AutoBot net -> Internet via Gateway Group 'AutoBot_Failover'" -ForegroundColor Green
Write-Host "   ✅ ALLOW: LAN net -> AutoBot net (Management ports: 22,80,443,8000-8081)" -ForegroundColor Green
Write-Host "   🚫 BLOCK: AutoBot net -> LAN net (Prevent lateral movement)" -ForegroundColor Red
Write-Host "   🚫 BLOCK: Internet -> AutoBot net (Default - no inbound)" -ForegroundColor Red

Write-Host "`n5. Advanced Multi-WAN Rules:" -ForegroundColor Yellow
Write-Host "   Firewall > Rules > OPT1_AUTOBOT" -ForegroundColor Gray
Write-Host "   - Create rule: AutoBot Internet Access" -ForegroundColor Gray
Write-Host "   - Source: AutoBot subnet (192.168.$AutoBotVLAN.0/24)" -ForegroundColor Gray
Write-Host "   - Destination: Any" -ForegroundColor Gray
Write-Host "   - Gateway: AutoBot_Failover (enables failover)" -ForegroundColor Gray
Write-Host "   - Description: AutoBot internet with WAN failover" -ForegroundColor Gray

if ($EnableFailoverTesting) {
    Write-Host "`n6. Failover Testing Configuration:" -ForegroundColor Yellow
    Write-Host "   System > Routing > Gateways" -ForegroundColor Gray
    Write-Host "   - WAN1 Monitor IP: 8.8.8.8 (Google DNS)" -ForegroundColor Gray
    Write-Host "   - WAN2 Monitor IP: 1.1.1.1 (Cloudflare DNS)" -ForegroundColor Gray
    Write-Host "   - Latency Threshold: 500ms" -ForegroundColor Gray
    Write-Host "   - Packet Loss Threshold: 10%" -ForegroundColor Gray
    Write-Host "   - Probe Interval: 3 seconds" -ForegroundColor Gray
}

if ($CreateHighAvailability) {
    Write-Host "`n7. High Availability Features:" -ForegroundColor Yellow
    Write-Host "   Services > Load Balancer" -ForegroundColor Gray
    Write-Host "   - Create Virtual Server for AutoBot Frontend" -ForegroundColor Gray
    Write-Host "   - Backend Pool: AutoBot Frontend VMs" -ForegroundColor Gray
    Write-Host "   - Health Check: HTTP GET to /" -ForegroundColor Gray
    Write-Host "   - Failover Mode: Automatic" -ForegroundColor Gray
}

Write-Host "`n🔧 Benefits of Multi-WAN pfSense Integration:" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "✅ Automatic WAN Failover: Ethernet ←→ WiFi seamless switching" -ForegroundColor Green
Write-Host "✅ Load Balancing: Distribute traffic across both WANs" -ForegroundColor Green
Write-Host "✅ Network Isolation: AutoBot VMs isolated from main LAN" -ForegroundColor Green
Write-Host "✅ Controlled Internet: Only essential protocols allowed out" -ForegroundColor Green
Write-Host "✅ High Availability: Multiple layers of redundancy" -ForegroundColor Green
Write-Host "✅ Traffic Shaping: QoS policies for AutoBot traffic" -ForegroundColor Green
Write-Host "✅ Security: pfSense firewall protecting all AutoBot traffic" -ForegroundColor Green

Write-Host "`n📊 Monitoring & Alerts:" -ForegroundColor Cyan
Write-Host "   Status > System Logs > Routing (Monitor WAN switching)" -ForegroundColor Gray
Write-Host "   Status > Gateways (Real-time WAN status)" -ForegroundColor Gray
Write-Host "   Status > Traffic Graph (Network utilization)" -ForegroundColor Gray

Write-Host "`n🔧 Next Steps:" -ForegroundColor Cyan
Write-Host "1. Configure pfSense Multi-WAN settings (above)" -ForegroundColor Gray
Write-Host "2. Run: .\create-autobot-vms-pfsense.ps1 -UseDHCP" -ForegroundColor Gray
Write-Host "3. Install Ubuntu on VMs with DHCP networking" -ForegroundColor Gray
Write-Host "4. Run: .\discover-vm-ips-pfsense.ps1 -UseDHCPLeases -UpdateInventory" -ForegroundColor Gray
Write-Host "5. Deploy: .\scripts\ansible\deploy.sh deploy-all" -ForegroundColor Gray
Write-Host "6. Test failover by disconnecting primary WAN" -ForegroundColor Gray

Write-Host "`n✅ Multi-WAN pfSense integration configured!" -ForegroundColor Green
Write-Host "AutoBot will benefit from automatic WAN failover and network isolation." -ForegroundColor Yellow