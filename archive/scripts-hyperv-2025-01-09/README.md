# Hyper-V Scripts Archive

**Archived Date**: 2025-01-09
**Reason**: Not applicable to current infrastructure

## Original Purpose

These PowerShell scripts were designed for setting up AutoBot infrastructure using Microsoft Hyper-V virtualization with pfSense networking.

## Current Infrastructure

AutoBot now uses:
- **Main Machine**: WSL (Windows Subsystem for Linux) at 172.16.168.20
- **Remote VMs**: 5 separate VMs (172.16.168.21-25) managed independently

## Archive Contents

- `configure-hyper-v-vlans.ps1` - Hyper-V VLAN configuration
- `configure-network.ps1` - Network setup for Hyper-V
- `configure-pfsense-multiwan.ps1` - pfSense multi-WAN configuration
- `configure-pfsense-network.ps1` - pfSense network configuration
- `create-autobot-vms-pfsense.ps1` - VM creation with pfSense
- `create-autobot-vms.ps1` - Basic VM creation
- `create-autobot-vms-simple.ps1` - Simplified VM creation
- `create-autobot-vms-vlans.ps1` - VM creation with VLANs
- `create-simple-network.ps1` - Simple network setup
- `discover-vm-ips-pfsense.ps1` - IP discovery with pfSense
- `discover-vm-ips.ps1` - Basic IP discovery

## Status

These scripts are preserved for historical reference but are not part of the active AutoBot deployment workflow.

## References in Documentation

These scripts are referenced in archived documentation:
- `docs/archives/processed_20250910/security_deployment/deployment/hyper-v-internal-network.md`
- `docs/deployment/hyper-v-internal-network.md`

If you need to deploy AutoBot using Hyper-V in the future, these scripts may serve as a starting point.
