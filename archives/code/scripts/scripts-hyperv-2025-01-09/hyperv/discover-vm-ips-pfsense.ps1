# AutoBot VM Discovery Script for pfSense Integration
# Discovers AutoBot VMs on pfSense VLAN and updates Ansible inventory
# Run as Administrator

param(
    [string]$PfSenseIP = "192.168.1.1",           # pfSense web interface IP
    [string]$AutoBotVLAN = "100",                 # VLAN ID for AutoBot
    [string]$NetworkRange = "192.168.100.0/24",   # AutoBot network range
    [string]$InventoryPath = "../../ansible/inventory/hosts-pfsense.yml",
    [switch]$UpdateInventory,
    [switch]$ShowAll,
    [switch]$UseDHCPLeases,                       # Query pfSense DHCP leases
    [string]$PfSenseUser = "admin",               # pfSense admin username  
    [string]$PfSensePass = ""                     # pfSense admin password (will prompt if empty)
)

# Import required modules
Add-Type -AssemblyName System.Web

function Get-PfSenseDHCPLeases {
    param($PfSenseIP, $Username, $Password)
    
    Write-Host "🔍 Querying pfSense DHCP leases at $PfSenseIP..." -ForegroundColor Yellow
    
    try {
        # Create web session for pfSense
        $LoginUri = "https://$PfSenseIP/index.php"
        $DHCPUri = "https://$PfSenseIP/status_dhcp_leases.php"
        
        # Skip SSL certificate validation (self-signed pfSense cert)
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}
        
        $WebSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
        
        # Get login page to extract CSRF token
        $LoginPage = Invoke-WebRequest -Uri $LoginUri -SessionVariable WebSession -UseBasicParsing
        $CSRFToken = ($LoginPage.Content | Select-String -Pattern '__csrf_magic.*?value="([^"]+)"').Matches[0].Groups[1].Value
        
        # Login to pfSense
        $LoginData = @{
            '__csrf_magic' = $CSRFToken
            'usernamefld' = $Username
            'passwordfld' = $Password
            'login' = 'Sign In'
        }
        
        $LoginResponse = Invoke-WebRequest -Uri $LoginUri -Method POST -Body $LoginData -WebSession $WebSession -UseBasicParsing
        
        if ($LoginResponse.Content -like "*Dashboard*") {
            Write-Host "✅ Successfully logged into pfSense" -ForegroundColor Green
            
            # Get DHCP leases page
            $DHCPPage = Invoke-WebRequest -Uri $DHCPUri -WebSession $WebSession -UseBasicParsing
            
            # Parse DHCP leases (basic HTML parsing)
            $Leases = @()
            $DHCPMatches = [regex]::Matches($DHCPPage.Content, '<tr[^>]*>.*?<td[^>]*>(\d+\.\d+\.\d+\.\d+)</td>.*?<td[^>]*>([^<]+)</td>.*?<td[^>]*>([^<]+)</td>')
            
            foreach ($Match in $DHCPMatches) {
                $IP = $Match.Groups[1].Value
                $MAC = $Match.Groups[2].Value
                $Hostname = $Match.Groups[3].Value
                
                # Filter for AutoBot VLAN range
                if ($IP -match "^192\.168\.$AutoBotVLAN\.") {
                    $Leases += [PSCustomObject]@{
                        IP = $IP
                        MAC = $MAC
                        Hostname = $Hostname
                        Source = "pfSense DHCP"
                    }
                }
            }
            
            return $Leases
            
        } else {
            Write-Host "❌ Failed to login to pfSense" -ForegroundColor Red
            return @()
        }
        
    } catch {
        Write-Host "❌ Error querying pfSense: $($_.Exception.Message)" -ForegroundColor Red
        return @()
    }
}

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
    param($NetworkRange, $DHCPLeases)
    
    Write-Host "🔍 Scanning AutoBot pfSense VLAN: $NetworkRange" -ForegroundColor Cyan
    Write-Host "This may take 30-60 seconds..." -ForegroundColor Yellow
    
    $DiscoveredVMs = @()
    
    # If we have DHCP leases, use those first
    if ($DHCPLeases -and $DHCPLeases.Count -gt 0) {
        Write-Host "📋 Processing DHCP leases from pfSense..." -ForegroundColor Green
        
        foreach ($Lease in $DHCPLeases) {
            $IP = $Lease.IP
            Write-Host "  Testing DHCP lease: $IP ($($Lease.Hostname))" -ForegroundColor Gray
            
            # Test if host is actually reachable
            $PingResult = Test-Connection -ComputerName $IP -Count 1 -Quiet -TimeoutSeconds 2
            
            if ($PingResult) {
                $Services = Test-VMConnection -IP $IP
                $VMType = "Unknown"
                
                # Identify VM type based on services or hostname
                if ($Lease.Hostname -match "frontend" -or $Services -match "Vue Frontend") { $VMType = "Frontend" }
                elseif ($Lease.Hostname -match "backend" -or $Services -match "FastAPI Backend") { $VMType = "Backend" }
                elseif ($Lease.Hostname -match "aistack" -or $Services -match "AI Stack") { $VMType = "AI Stack" }
                elseif ($Lease.Hostname -match "npu" -or $Services -match "NPU Worker") { $VMType = "NPU Worker" }
                elseif ($Lease.Hostname -match "redis" -or $Services -match "Redis") { $VMType = "Redis" }
                elseif ($Services -match "SSH") { $VMType = "Generic Linux" }
                
                $DiscoveredVMs += [PSCustomObject]@{
                    IP = $IP
                    Hostname = $Lease.Hostname
                    Type = $VMType
                    Services = ($Services -join ", ")
                    Status = "Active (DHCP)"
                    MAC = $Lease.MAC
                }
            }
        }
    }
    
    # Also do manual network scan to catch any missed VMs
    Write-Host "🔍 Performing network scan for additional VMs..." -ForegroundColor Cyan
    
    # Parse network range
    $Network = $NetworkRange.Split('/')[0]
    $NetworkBase = $Network.Substring(0, $Network.LastIndexOf('.'))
    
    # Scan IP range (avoid duplicates from DHCP leases)
    $ExistingIPs = $DiscoveredVMs | ForEach-Object { $_.IP }
    
    for ($i = 10; $i -le 50; $i++) {
        $IP = "$NetworkBase.$i"
        
        if ($IP -in $ExistingIPs) {
            continue  # Already found via DHCP
        }
        
        Write-Progress -Activity "Scanning pfSense AutoBot Network" -Status "Testing $IP" -PercentComplete (($i-9)/41*100)
        
        # Quick ping test first
        $PingResult = Test-Connection -ComputerName $IP -Count 1 -Quiet -TimeoutSeconds 1
        
        if ($PingResult) {
            Write-Host "✅ Found additional VM: $IP" -ForegroundColor Green
            
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
                Status = "Active (Static)"
                MAC = "Unknown"
            }
        }
    }
    
    Write-Progress -Completed -Activity "Scanning pfSense AutoBot Network"
    return $DiscoveredVMs
}

function Update-AnsibleInventory {
    param($VMs, $InventoryPath)
    
    Write-Host "📝 Creating pfSense Ansible inventory at: $InventoryPath" -ForegroundColor Yellow
    
    # Create pfSense-specific inventory
    $InventoryContent = @"
# AutoBot Ansible Inventory for pfSense Integration
all:
  vars:
    ansible_user: autobot
    ansible_ssh_private_key_file: ~/.ssh/autobot_key
    python_interpreter: /usr/bin/python3
    
  children:
    autobot_cluster:
      vars:
        # pfSense VLAN $AutoBotVLAN network configuration
        network_subnet: "192.168.$AutoBotVLAN.0/24"
        network_gateway: "192.168.$AutoBotVLAN.1"  # pfSense VLAN interface
        dns_servers: 
          - "8.8.8.8"
          - "1.1.1.1"
        pfsense_integration: true
        vlan_id: $AutoBotVLAN
        
      children:
        frontend:
          hosts:
"@

    # Add discovered VMs to inventory
    foreach ($VM in $VMs) {
        $ServiceName = switch ($VM.Type) {
            "Frontend" { "autobot-frontend" }
            "Backend" { "autobot-backend" }
            "AI Stack" { "autobot-aistack" }
            "NPU Worker" { "autobot-npu" }
            "Redis" { "autobot-redis" }
            default { continue }  # Skip unknown VMs
        }
        
        $ServiceConfig = switch ($VM.Type) {
            "Frontend" {
@"
            $ServiceName:
              ansible_host: $($VM.IP)
              services:
                - { name: "vue-dev", port: 5173, command: "npm run dev" }
                - { name: "nginx", port: 80, command: "nginx -g 'daemon off;'" }
              mac_address: "$($VM.MAC)"
"@
            }
            "Backend" {
@"
        backend:
          hosts:
            $ServiceName:
              ansible_host: $($VM.IP)
              services:
                - { name: "fastapi", port: 8001, command: "uvicorn backend.fast_app_factory_fix:app --host 0.0.0.0 --port 8001" }
              environment:
                REDIS_HOST: "$(($VMs | Where-Object {$_.Type -eq "Redis"}).IP)"
                AI_STACK_HOST: "$(($VMs | Where-Object {$_.Type -eq "AI Stack"}).IP)"
                NPU_WORKER_HOST: "$(($VMs | Where-Object {$_.Type -eq "NPU Worker"}).IP)"
              mac_address: "$($VM.MAC)"
"@
            }
            "AI Stack" {
@"
        ai_stack:
          hosts:
            $ServiceName:
              ansible_host: $($VM.IP)
              services:
                - { name: "llm-server", port: 8080, command: "python -m src.ai_stack_main" }
              gpu_enabled: true
              memory_gb: 16
              mac_address: "$($VM.MAC)"
"@
            }
            "NPU Worker" {
@"
        npu_workers:
          hosts:
            $ServiceName:
              ansible_host: $($VM.IP)
              services:
                - { name: "npu-service", port: 8081, command: "python -m src.npu_worker_main" }
              npu_enabled: true
              memory_gb: 8
              mac_address: "$($VM.MAC)"
"@
            }
            "Redis" {
@"
        database:
          hosts:
            $ServiceName:
              ansible_host: $($VM.IP)
              services:
                - { name: "redis-stack", port: 6379, command: "redis-stack-server --bind 0.0.0.0" }
              storage_gb: 100
              mac_address: "$($VM.MAC)"
"@
            }
        }
        
        if ($VM.Type -eq "Frontend") {
            $InventoryContent += "`n$ServiceConfig"
        } else {
            $InventoryContent += "`n$ServiceConfig"
        }
    }
    
    # Ensure directory exists
    $InventoryDir = Split-Path $InventoryPath -Parent
    if (-not (Test-Path $InventoryDir)) {
        New-Item -ItemType Directory -Path $InventoryDir -Force
    }
    
    # Write inventory file
    $InventoryContent | Out-File -FilePath $InventoryPath -Encoding UTF8
    Write-Host "📝 pfSense Ansible inventory created successfully!" -ForegroundColor Green
}

# Main execution
Write-Host "🔥 AutoBot VM Discovery Tool (pfSense Integration)" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

Write-Host "🌐 Configuration:" -ForegroundColor Yellow
Write-Host "  pfSense IP: $PfSenseIP" -ForegroundColor White
Write-Host "  AutoBot VLAN: $AutoBotVLAN" -ForegroundColor White
Write-Host "  Network Range: $NetworkRange" -ForegroundColor White

# Get pfSense credentials if using DHCP leases
$DHCPLeases = @()
if ($UseDHCPLeases) {
    if (-not $PfSensePass) {
        $SecurePass = Read-Host "Enter pfSense admin password" -AsSecureString
        $PfSensePass = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePass))
    }
    
    $DHCPLeases = Get-PfSenseDHCPLeases -PfSenseIP $PfSenseIP -Username $PfSenseUser -Password $PfSensePass
    
    if ($DHCPLeases.Count -gt 0) {
        Write-Host "📋 Found $($DHCPLeases.Count) DHCP leases for AutoBot VLAN" -ForegroundColor Green
    }
}

# Scan network
$DiscoveredVMs = Scan-AutoBotNetwork -NetworkRange $NetworkRange -DHCPLeases $DHCPLeases

if ($DiscoveredVMs.Count -eq 0) {
    Write-Host "❌ No AutoBot VMs discovered on pfSense VLAN $AutoBotVLAN" -ForegroundColor Red
    Write-Host "   Make sure VMs are running and pfSense VLAN is configured correctly." -ForegroundColor Yellow
} else {
    Write-Host "`n🎯 Discovered AutoBot VMs on pfSense:" -ForegroundColor Cyan
    Write-Host "===================================" -ForegroundColor Cyan
    
    $DiscoveredVMs | Format-Table -Property IP, Hostname, Type, Services, Status -AutoSize
    
    if ($ShowAll) {
        Write-Host "`n📋 Detailed VM Information:" -ForegroundColor Cyan
        foreach ($VM in $DiscoveredVMs) {
            Write-Host "  IP: $($VM.IP)" -ForegroundColor White
            Write-Host "  Hostname: $($VM.Hostname)" -ForegroundColor Gray
            Write-Host "  MAC: $($VM.MAC)" -ForegroundColor Gray
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
    Write-Host "  1. Review pfSense firewall rules for VLAN $AutoBotVLAN" -ForegroundColor Gray
    Write-Host "  2. Test connectivity: ansible all -i $InventoryPath -m ping" -ForegroundColor Gray
    Write-Host "  3. Deploy services: ./scripts/ansible/deploy.sh deploy-all" -ForegroundColor Gray
}

Write-Host "`n✅ pfSense discovery complete!" -ForegroundColor Green