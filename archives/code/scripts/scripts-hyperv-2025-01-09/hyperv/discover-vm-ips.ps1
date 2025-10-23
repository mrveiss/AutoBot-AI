# AutoBot VM IP Discovery Script
# Discovers AutoBot VMs on the internal network and updates Ansible inventory
# Run as Administrator

param(
    [string]$NetworkRange = "192.168.100.0/24",
    [string]$InventoryPath = "../../ansible/inventory/hosts.yml",
    [switch]$UpdateInventory,
    [switch]$ShowAll
)

function Test-VMConnection {
    param($IP)
    
    # Test multiple ports to identify service type
    $Services = @{
        22 = "SSH"
        80 = "HTTP"
        443 = "HTTPS" 
        5173 = "Vue Frontend"
        8001 = "FastAPI Backend"
        8080 = "AI Stack"
        8081 = "NPU Worker"
        6379 = "Redis"
    }
    
    $FoundServices = @()
    foreach ($Port in $Services.Keys) {
        $Connection = Test-NetConnection -ComputerName $IP -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue
        if ($Connection) {
            $FoundServices += "$($Services[$Port])($Port)"
        }
    }
    
    return $FoundServices
}

function Get-VMHostname {
    param($IP)
    
    try {
        $Hostname = [System.Net.Dns]::GetHostEntry($IP).HostName
        return $Hostname
    } catch {
        return $null
    }
}

function Scan-AutoBotNetwork {
    param($NetworkRange)
    
    Write-Host "🔍 Scanning AutoBot internal network: $NetworkRange" -ForegroundColor Cyan
    Write-Host "This may take 30-60 seconds..." -ForegroundColor Yellow
    
    # Parse network range
    $Network = $NetworkRange.Split('/')[0]
    $NetworkBase = $Network.Substring(0, $Network.LastIndexOf('.'))
    
    $DiscoveredVMs = @()
    
    # Scan IP range 192.168.100.10-50 (VM range)
    for ($i = 10; $i -le 50; $i++) {
        $IP = "$NetworkBase.$i"
        Write-Progress -Activity "Scanning AutoBot Network" -Status "Testing $IP" -PercentComplete (($i-9)/41*100)
        
        # Quick ping test first
        $PingResult = Test-Connection -ComputerName $IP -Count 1 -Quiet -TimeoutSeconds 1
        
        if ($PingResult) {
            Write-Host "✅ Found active VM: $IP" -ForegroundColor Green
            
            # Get hostname and services
            $Hostname = Get-VMHostname -IP $IP
            $Services = Test-VMConnection -IP $IP
            
            # Try to identify VM type based on services
            $VMType = "Unknown"
            if ($Services -match "Vue Frontend") { $VMType = "Frontend" }
            elseif ($Services -match "FastAPI Backend") { $VMType = "Backend" }
            elseif ($Services -match "AI Stack") { $VMType = "AI Stack" }
            elseif ($Services -match "NPU Worker") { $VMType = "NPU Worker" }
            elseif ($Services -match "Redis") { $VMType = "Redis" }
            elseif ($Services -match "SSH") { $VMType = "Generic Linux" }
            
            $DiscoveredVMs += [PSCustomObject]@{
                IP = $IP
                Hostname = $Hostname
                Type = $VMType
                Services = ($Services -join ", ")
                Status = "Active"
            }
        }
    }
    
    Write-Progress -Completed -Activity "Scanning AutoBot Network"
    return $DiscoveredVMs
}

function Update-AnsibleInventory {
    param($VMs, $InventoryPath)
    
    Write-Host "📝 Updating Ansible inventory at: $InventoryPath" -ForegroundColor Yellow
    
    if (-not (Test-Path $InventoryPath)) {
        Write-Host "❌ Inventory file not found: $InventoryPath" -ForegroundColor Red
        return
    }
    
    # Read current inventory
    $InventoryContent = Get-Content $InventoryPath -Raw
    
    # Update IPs for each discovered VM
    foreach ($VM in $VMs) {
        if ($VM.Type -ne "Unknown" -and $VM.Type -ne "Generic Linux") {
            $ServiceName = switch ($VM.Type) {
                "Frontend" { "autobot-frontend" }
                "Backend" { "autobot-backend" }
                "AI Stack" { "autobot-aistack" }
                "NPU Worker" { "autobot-npu" }
                "Redis" { "autobot-redis" }
            }
            
            # Update ansible_host line for this service
            $Pattern = "($ServiceName:.*?ansible_host:\s*)[\d\.]+(\s*)"
            $Replacement = "`${1}$($VM.IP)`${2}"
            
            if ($InventoryContent -match $ServiceName) {
                $InventoryContent = $InventoryContent -replace $Pattern, $Replacement
                Write-Host "  ✅ Updated $ServiceName -> $($VM.IP)" -ForegroundColor Green
            }
        }
    }
    
    # Write updated inventory
    $InventoryContent | Set-Content $InventoryPath -Encoding UTF8
    Write-Host "📝 Ansible inventory updated successfully!" -ForegroundColor Green
}

# Main execution
Write-Host "🤖 AutoBot VM Discovery Tool" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

# Check if we're on the AutoBot internal network
$HostIP = (Get-NetIPAddress -InterfaceAlias "*AutoBot-Internal*" -AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress
if (-not $HostIP) {
    Write-Host "❌ AutoBot Internal network not detected. Make sure configure-network.ps1 has been run." -ForegroundColor Red
    exit 1
}

Write-Host "🖥️  Host IP on AutoBot network: $HostIP" -ForegroundColor Green

# Scan network
$DiscoveredVMs = Scan-AutoBotNetwork -NetworkRange $NetworkRange

if ($DiscoveredVMs.Count -eq 0) {
    Write-Host "❌ No AutoBot VMs discovered on network $NetworkRange" -ForegroundColor Red
    Write-Host "   Make sure VMs are running and network is configured correctly." -ForegroundColor Yellow
} else {
    Write-Host "`n🎯 Discovered AutoBot VMs:" -ForegroundColor Cyan
    Write-Host "=========================" -ForegroundColor Cyan
    
    $DiscoveredVMs | Format-Table -Property IP, Hostname, Type, Services -AutoSize
    
    if ($ShowAll) {
        Write-Host "`n📋 Detailed VM Information:" -ForegroundColor Cyan
        foreach ($VM in $DiscoveredVMs) {
            Write-Host "  IP: $($VM.IP)" -ForegroundColor White
            Write-Host "  Hostname: $($VM.Hostname)" -ForegroundColor Gray
            Write-Host "  Type: $($VM.Type)" -ForegroundColor Yellow
            Write-Host "  Services: $($VM.Services)" -ForegroundColor Green
            Write-Host "  Status: $($VM.Status)" -ForegroundColor Cyan
            Write-Host "  ---"
        }
    }
    
    if ($UpdateInventory) {
        Update-AnsibleInventory -VMs $DiscoveredVMs -InventoryPath $InventoryPath
    }
    
    Write-Host "`n🔧 Next Steps:" -ForegroundColor Cyan
    Write-Host "  1. Use -UpdateInventory to update Ansible hosts.yml" -ForegroundColor Gray
    Write-Host "  2. Test connectivity: ansible all -m ping" -ForegroundColor Gray
    Write-Host "  3. Deploy services: ./scripts/ansible/deploy.sh deploy-all" -ForegroundColor Gray
}

# Export discovered VMs for scripting
$global:AutoBotVMs = $DiscoveredVMs

Write-Host "`n✅ Discovery complete!" -ForegroundColor Green