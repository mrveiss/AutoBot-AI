# AutoBot Hyper-V Internal Network Deployment

## Overview

This deployment approach uses Hyper-V Internal Switch with Windows NAT and firewall rules to create a secure, isolated network for AutoBot VMs while allowing controlled internet access.

## Network Architecture

```
Host Machine (Windows)
├── AutoBot-Internal Switch (192.168.100.1)
├── Windows NAT (controlled internet access)
├── Windows Firewall (traffic filtering)
└── AutoBot VMs:
    ├── Frontend VM      (192.168.100.10)
    ├── Backend VM       (192.168.100.20)  
    ├── AI Stack VM      (192.168.100.30)
    ├── NPU Worker VM    (192.168.100.40)
    └── Redis VM         (192.168.100.50)
```

## Security Features

### ✅ **Internal VM Traffic**
- **VM-to-VM communication**: Fully allowed on 192.168.100.0/24
- **Host-to-VM management**: SSH (22) and API ports (80,443,8000-8081) open
- **No external interference**: Traffic never leaves the host machine

### 🛡️ **Controlled Internet Access**
- **Allowed**: HTTP (80), HTTPS (443), DNS (53) for package updates
- **Blocked**: All other protocols and ports
- **Monitored**: All traffic goes through Windows Firewall rules

### 🔒 **Security Benefits**
- **Zero external attack surface**: No direct internet connectivity
- **Controlled updates**: Only essential package repositories accessible
- **Internal communication**: High-speed VM-to-VM without network latency
- **Firewall protection**: Windows Advanced Firewall monitors all traffic

## Deployment Steps

### 1. Configure Hyper-V Internal Network

Run as Administrator in PowerShell:

```powershell
# Configure the internal network with firewall
.\scripts\hyperv\configure-network.ps1
```

This creates:
- AutoBot-Internal switch (Internal type)
- Windows host IP: 192.168.100.1
- NAT for controlled internet access
- Firewall rules for traffic filtering

### 2. Create AutoBot VMs

```powershell
# Create all 5 AutoBot VMs with proper resource allocation
.\scripts\hyperv\create-autobot-vms.ps1
```

This creates:
- 5 VMs with allocated RAM, CPU, and disk space
- Connection to AutoBot-Internal switch
- GPU passthrough for AI Stack VM
- NPU configuration for NPU Worker VM

### 3. Install Ubuntu Server on Each VM

1. Download Ubuntu Server 22.04 LTS ISO
2. Mount ISO on each VM
3. Install with these network settings:
   - **Use static IP configuration**
   - **Gateway**: 192.168.100.1
   - **DNS**: 8.8.8.8, 1.1.1.1
   - **Create 'autobot' user** for Ansible automation

### 4. Discover VM IPs

From Windows PowerShell:
```powershell
# Discover and map all AutoBot VMs
.\scripts\hyperv\discover-vm-ips.ps1 -UpdateInventory
```

From Linux/WSL:
```bash
# Alternative discovery method
./scripts/network/discover-vms.sh --update-inventory
```

### 5. Set Up SSH Keys for Ansible

```bash
# Generate SSH key for Ansible automation
ssh-keygen -t rsa -b 4096 -f ~/.ssh/autobot_key -N ""

# Copy key to all VMs (replace IPs with discovered ones)
for ip in 192.168.100.10 192.168.100.20 192.168.100.30 192.168.100.40 192.168.100.50; do
    ssh-copy-id -i ~/.ssh/autobot_key.pub autobot@$ip
done
```

### 6. Deploy AutoBot Services with Ansible

```bash
# Test connectivity to all VMs
ansible all -m ping

# Deploy complete AutoBot infrastructure
./scripts/ansible/deploy.sh deploy-all
```

## Network Configuration Details

### Firewall Rules Created

| Rule | Direction | Protocol | Source | Destination | Port | Action |
|------|-----------|----------|---------|-------------|------|--------|
| Internal VM Traffic | Both | Any | 192.168.100.0/24 | 192.168.100.0/24 | Any | Allow |
| VM Updates HTTP | Outbound | TCP | 192.168.100.0/24 | Any | 80 | Allow |
| VM Updates HTTPS | Outbound | TCP | 192.168.100.0/24 | Any | 443 | Allow |
| VM DNS | Outbound | UDP | 192.168.100.0/24 | Any | 53 | Allow |
| Host SSH Management | Inbound | TCP | 192.168.100.1 | 192.168.100.0/24 | 22 | Allow |
| Host API Management | Inbound | TCP | 192.168.100.1 | 192.168.100.0/24 | 80,443,8000-8081 | Allow |
| Block All Other | Outbound | Any | 192.168.100.0/24 | Any | Any | Block |

### VM IP Assignments

| VM | IP Address | RAM | CPU | Disk | Special Features |
|----|------------|-----|-----|------|------------------|
| Frontend | 192.168.100.10 | 2GB | 2 | 20GB | Vue.js, Nginx |
| Backend | 192.168.100.20 | 8GB | 4 | 40GB | FastAPI, Python |
| AI Stack | 192.168.100.30 | 16GB | 6 | 60GB | GPU Passthrough |
| NPU Worker | 192.168.100.40 | 8GB | 4 | 40GB | NPU Access |
| Redis | 192.168.100.50 | 8GB | 2 | 100GB | Redis Stack |

## Advantages of This Approach

### 🚀 **Performance**
- **No Docker overhead**: Direct VM execution
- **Dedicated resources**: Each service has guaranteed RAM/CPU
- **Native networking**: VM-to-VM at memory speeds
- **GPU acceleration**: Direct hardware access for AI workloads

### 🔧 **Scalability**
- **Independent scaling**: Scale each service separately
- **Resource isolation**: One service can't starve others
- **Future expansion**: Easy migration to separate physical machines
- **Load balancing**: Can add multiple instances of any service

### 🛡️ **Security**
- **Network isolation**: Internal traffic never leaves host
- **Controlled internet**: Only essential protocols allowed
- **Firewall protection**: All traffic monitored and filtered
- **Zero attack surface**: No direct external connectivity

### 🔧 **Management**
- **Ansible automation**: Infrastructure as Code approach
- **Service discovery**: Automatic VM detection and inventory updates
- **Health monitoring**: Built-in service health checks
- **Backup/restore**: VM-level snapshots and backups

## Troubleshooting

### VM Discovery Issues

```bash
# Check AutoBot network configuration
Get-NetAdapter | Where-Object Name -like "*AutoBot-Internal*"
Get-NetIPAddress -InterfaceAlias "*AutoBot-Internal*"

# Test VM connectivity
ping 192.168.100.10  # Frontend
ping 192.168.100.20  # Backend
# ... etc
```

### Firewall Issues

```powershell
# Check firewall rules
Get-NetFirewallRule -DisplayName "*AutoBot*" | Select-Object DisplayName,Enabled,Action

# Temporarily disable for testing (NOT RECOMMENDED for production)
Set-NetFirewallRule -DisplayName "AutoBot VM Block Others" -Enabled False
```

### Internet Access Issues

```bash
# Test from inside VM
curl -I http://archive.ubuntu.com  # Should work (HTTP)
curl -I https://packages.ubuntu.com  # Should work (HTTPS)
nslookup google.com  # Should work (DNS)
ping google.com  # Should be blocked (ICMP)
```

## Next Steps

1. **Monitor Performance**: Set up monitoring dashboards
2. **Backup Strategy**: Configure automated VM backups
3. **Load Testing**: Validate performance under load
4. **Security Audit**: Review firewall logs and access patterns
5. **Documentation**: Update operational procedures

## Comparison: Internal Network vs Docker

| Aspect | Internal Network + VMs | Docker Containers |
|--------|------------------------|-------------------|
| **Performance** | ⭐⭐⭐⭐⭐ Native VM speed | ⭐⭐⭐ Container overhead |
| **Security** | ⭐⭐⭐⭐⭐ Complete isolation | ⭐⭐⭐ Shared kernel |
| **Scalability** | ⭐⭐⭐⭐⭐ Independent scaling | ⭐⭐⭐ Resource sharing |
| **Management** | ⭐⭐⭐⭐ Ansible automation | ⭐⭐⭐⭐⭐ Docker Compose |
| **Resource Usage** | ⭐⭐⭐ Higher RAM usage | ⭐⭐⭐⭐⭐ Efficient sharing |
| **Network Issues** | ⭐⭐⭐⭐⭐ Eliminated | ⭐ Frequent problems |

The Internal Network approach provides superior performance, security, and eliminates the Docker networking issues that were causing 4-6 hour build times.