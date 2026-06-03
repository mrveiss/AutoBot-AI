---
tags:
  - getting-started
  - installation
  - vm
  - virtualbox
  - vmware
  - wsl2
aliases:
  - VM Installation
  - Virtual Machine Setup
---

# Installing AutoBot in a Virtual Machine

This guide covers running AutoBot AI inside a virtual machine (VM), including hypervisor-specific networking, file sharing, and verification steps.

---

## Prerequisites

### VM Minimum Specifications

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 8 GB | 16 GB |
| vCPUs | 4 | 8 |
| Disk | 40 GB | 80 GB (SSD-backed) |
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |

### Supported Hypervisors

- **VirtualBox** 7.0+
- **VMware Workstation / Fusion** 17+
- **Hyper-V** (Windows 10/11 Pro, Server 2019+)
- **KVM/QEMU** with libvirt
- **WSL2** (Windows Subsystem for Linux 2)

---

## Networking

AutoBot exposes several ports that must be reachable from your host or LAN.

### Default Ports

| Service | Port |
|---------|------|
| AutoBot API | 8000 |
| Frontend (Vite dev) | 5173 |
| Redis | 6379 |
| Ollama | 11434 |

### NAT vs. Bridged Adapter

**NAT (default)** — the VM shares the host's IP. Ports are only reachable from the host. Use NAT for development on a single machine.

**Bridged** — the VM gets its own IP on the LAN. Use bridged mode when other machines on the network need to reach AutoBot.

### Port Forwarding (NAT mode)

Configure port forwarding in your hypervisor so host ports map to VM ports.

**VirtualBox** (via GUI or command line):

```bash
VBoxManage modifyvm "AutoBot-VM" --natpf1 "autobot-api,tcp,,8000,,8000"
VBoxManage modifyvm "AutoBot-VM" --natpf1 "autobot-frontend,tcp,,5173,,5173"
VBoxManage modifyvm "AutoBot-VM" --natpf1 "ollama,tcp,,11434,,11434"
```

**VMware** — in the VM settings, go to **Network Adapter → Advanced → Port Forwarding** and add the same mappings.

**KVM/QEMU** with user-mode networking:

```bash
qemu-system-x86_64 \
  -netdev user,id=net0,hostfwd=tcp::8000-:8000,hostfwd=tcp::5173-:5173 \
  -device virtio-net-pci,netdev=net0 \
  ...
```

---

## File Sharing

If the AutoBot repository lives on your host machine and is mounted into the VM, observe the following:

### Permissions

Shared folders often map as root-owned or with restrictive umask. Run inside the VM:

```bash
sudo chown -R $USER:$USER /path/to/mounted/AutoBot-AI
```

### Symlinks

VirtualBox shared folders **do not support symlinks** by default. Enable symlink creation:

```bash
# On the host, before starting the VM:
VBoxManage setextradata "AutoBot-VM" \
  VBoxInternal2/SharedFoldersEnableSymlinksCreate/AutoBot-AI 1
```

VMware and KVM/virtio-fs support symlinks natively.

### inotify Limits

Node.js and Python watch tools require enough inotify watches. If you see `ENOSPC` errors from file watchers:

```bash
echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### Best Practices

- Prefer cloning the repo **inside** the VM for best performance — shared folders add significant I/O latency.
- If you must use a shared folder, mount it with `dmode=775,fmode=664` to avoid permission issues.
- Use `virtio-fs` (KVM) or VMware HGFS for better performance than VirtualBox shared folders.

---

## WSL2 Specifics

WSL2 runs as a lightweight VM managed by Hyper-V. It has unique networking and resource constraints.

### Port Exclusion Ranges

Windows reserves certain TCP ports. If AutoBot fails to bind, check for conflicts:

```powershell
# Run in PowerShell (elevated)
netsh int ipv4 show excludedportrange protocol=tcp
```

If a required port (e.g., 8000) is in an excluded range, restart the WinNAT service to reset the ranges:

```powershell
net stop winnat
net start winnat
```

### `.wslconfig` Settings

Create or edit `%USERPROFILE%\.wslconfig` on the Windows host:

```ini
[wsl2]
memory=12GB
swap=4GB
processors=6
localhostForwarding=true
```

Apply the changes:

```powershell
wsl --shutdown
# Then reopen WSL2
```

### Service Startup with systemd

WSL2 on Windows 11 (and recent Windows 10 builds) supports systemd. Enable it in `/etc/wsl.conf` inside the distro:

```ini
[boot]
systemd=true
```

Then restart the WSL instance (`wsl --shutdown`). After that, AutoBot services can be managed with `systemctl`.

### WSL2 Networking Quirks

- The WSL2 VM gets a private IP (`172.x.x.x`). Windows forwards `localhost` automatically when `localhostForwarding=true`.
- Other LAN machines cannot reach WSL2 services via NAT by default — you need a port proxy:

```powershell
# On Windows host (elevated PowerShell), replace <wsl-ip> with the output of `wsl hostname -I`
netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=<wsl-ip>
```

---

## GPU / CPU Passthrough

### NVIDIA GPU (KVM/QEMU — VFIO passthrough)

Full GPU passthrough requires IOMMU enabled in BIOS and a dedicated GPU for the VM. This is an advanced topic; see the [Architecture docs](../architecture/) for ML component requirements.

For most users, the CPU-only Ollama backend is sufficient. To confirm:

```bash
# Inside VM
ollama run llama3.2 "hello"
```

### VMware / VirtualBox GPU

These hypervisors support virtual GPU acceleration (VMSVGA/VBoxVGA) for display only — not for CUDA/ROCm compute. ML inference runs on CPU inside these VMs.

### WSL2 GPU

WSL2 supports GPU compute via the Windows GPU-PV driver. NVIDIA CUDA works out of the box on supported Windows + driver versions:

```bash
# Verify inside WSL2
nvidia-smi
```

---

## Clipboard / Copy-Paste

### VirtualBox

Install **VirtualBox Guest Additions** inside the VM:

```bash
sudo apt-get install -y virtualbox-guest-utils virtualbox-guest-x11
sudo reboot
```

Then enable bidirectional clipboard in **Devices → Shared Clipboard → Bidirectional**.

### VMware

Install **Open VM Tools**:

```bash
sudo apt-get install -y open-vm-tools open-vm-tools-desktop
sudo reboot
```

### Headless / Server VMs

For headless VMs (no desktop), clipboard integration is not applicable. Use `ssh` and standard terminal copy-paste, or access the AutoBot web UI from the host browser via forwarded ports.

---

## Verifying the Install

After completing setup, run the following inside the VM to confirm everything is working.

### 1. Check service health

```bash
cd /path/to/AutoBot-AI
docker compose ps          # all services should be "Up"
# or, if running natively:
curl -s http://localhost:8000/health | python3 -m json.tool
```

Expected output:

```json
{
  "status": "ok",
  "version": "...",
  "agents": {...}
}
```

### 2. Verify Ollama

```bash
curl http://localhost:11434/api/tags
```

Expected: JSON list of available models.

### 3. Verify frontend

Open `http://localhost:5173` in the host browser (port forwarding must be configured). You should see the AutoBot dashboard.

### 4. Verify Redis

```bash
redis-cli ping
# Expected: PONG
```

---

## Troubleshooting Common VM Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `EADDRINUSE` on port 8000 | Windows reserved port range | Restart WinNAT or change port |
| Frontend loads but API calls fail | Port forwarding missing for 8000 | Add NAT rule for port 8000 |
| File watcher `ENOSPC` | inotify limit too low | Increase `fs.inotify.max_user_watches` |
| Symlink errors in shared folder | VirtualBox symlink not enabled | Run `VBoxManage setextradata` command above |
| `nvidia-smi` not found in WSL2 | Driver not installed or old | Update Windows GPU driver to latest |
| Services fail to start | Not enough RAM | Increase VM RAM to ≥ 8 GB |
| `docker: command not found` | Docker not installed in VM | Follow [Installation guide](../user-guide/01-installation.md) |

---

## Next Steps

- [[01-installation]] — Full bare-metal installation guide
- [[02-quickstart]] — Get AutoBot running in 5 minutes
- [[CONFIGURATION_GUIDE]] — Tune AutoBot for your environment
- [Architecture Overview](../architecture/) — Understand the system design
