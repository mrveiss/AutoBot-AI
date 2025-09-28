# AutoBot Development Instructions & Project Reference

This document contains development guidelines, project setup instructions, and architectural rules for the AutoBot platform.

> **📋 For system status updates and fixes, see:** [`docs/system-state.md`](docs/system-state.md)

---

## 🚨 STANDARDIZED PROCEDURES

**ONLY PERMITTED SETUP AND RUN METHODS:**

### Setup (Required First Time)
```bash
bash setup.sh [--full|--minimal|--distributed]
```

### Startup (Daily Use)
```bash
bash run_autobot.sh [--dev|--prod] [--build|--no-build] [--desktop|--no-desktop]
```

**❌ OBSOLETE METHODS (DO NOT USE):**
- ~~`run_agent_unified.sh`~~ → Use `run_autobot.sh`
- ~~`setup_agent.sh`~~ → Use `setup.sh`
- ~~Any other run scripts~~ → ALL archived in `scripts/archive/`

---

## 🧹 REPOSITORY CLEANLINESS STANDARDS

**MANDATORY: Keep root directory clean and organized**

### **File Placement Rules:**
- **❌ NEVER place in root directory:**
  - Test files (`test_*.py`, `*_test.py`)
  - Report files (`*REPORT*.md`, `*_report.*`)
  - Log files (`*.log`, `*.log.*`, `*.bak`)
  - Analysis outputs (`analysis_*.json`, `*_analysis.*`)
  - Temporary files (`*.tmp`, `*.temp`)
  - Backup files (`*.backup`, `*.old`)

### **Proper Directory Structure:**
```
/
├── tests/           # All test files go here
│   ├── results/     # Test results and validation reports
│   └── temp/        # Temporary test files
├── logs/            # Application logs (gitignored)
├── reports/         # Generated reports (gitignored)
├── temp/            # Temporary files (gitignored)
├── analysis/        # Analysis outputs (gitignored)
└── backups/         # Backup files (gitignored)
```

### **Agent and Script Guidelines:**
- **All agents MUST**: Use proper output directories for their files
- **All scripts MUST**: Create organized output in designated folders
- **Test systems MUST**: Place results in `tests/results/` directory
- **Report generators MUST**: Output to `reports/` directory (gitignored)
- **Monitoring systems MUST**: Log to `logs/` directory (gitignored)

---

## ⚠️ **CRITICAL: Single Frontend Server Architecture**

**MANDATORY FRONTEND SERVER RULES:**

### **✅ CORRECT: Single Frontend Server**
- **ONLY** `172.16.168.21:5173` runs the frontend (Frontend VM)
- **NO** frontend servers on main machine (`172.16.168.20`)
- **NO** local development servers (`localhost:5173`)
- **NO** multiple frontend instances permitted

### **Development Workflow:**
1. **Edit Code Locally**: Make all changes in `/home/kali/Desktop/AutoBot/autobot-vue/`
2. **Sync to Frontend VM**: Use `./sync-frontend.sh` or `./scripts/utilities/sync-to-vm.sh frontend`
3. **Frontend VM Runs**: Either dev or production mode via `run_autobot.sh`

### **❌ STRICTLY FORBIDDEN (CAUSES SYSTEM CONFLICTS):**
- Starting frontend servers on main machine (`172.16.168.20`)
- Running `npm run dev` locally
- Running `yarn dev` locally
- Running `vite dev` locally
- Running any Vite development server on main machine
- Multiple frontend instances (causes port conflicts and confusion)
- Direct editing on remote VMs
- **ANY command that starts a server on port 5173 on main machine**

---

## 🔐 CERTIFICATE-BASED SSH AUTHENTICATION

**MANDATORY: Use SSH keys instead of passwords for all operations**

#### SSH Key Configuration:
- **SSH Private Key**: `~/.ssh/autobot_key` (4096-bit RSA)
- **SSH Public Key**: `~/.ssh/autobot_key.pub`
- **All 5 VMs configured**: frontend(21), npu-worker(22), redis(23), ai-stack(24), browser(25)

#### Sync Files to Remote VMs:
```bash
# Sync specific file to specific VM
./scripts/utilities/sync-to-vm.sh frontend autobot-vue/src/components/App.vue /home/autobot/autobot-vue/src/components/

# Sync directory to specific VM
./scripts/utilities/sync-to-vm.sh frontend autobot-vue/src/components/ /home/autobot/autobot-vue/src/components/

# Sync to ALL VMs
./scripts/utilities/sync-to-vm.sh all scripts/setup.sh /home/autobot/scripts/
```

---

## 🚨 CRITICAL: Remote Host Development Rules

**🚨 MANDATORY - NEVER EDIT CODE DIRECTLY ON REMOTE HOSTS 🚨**

**This rule MUST NEVER BE BROKEN under any circumstances:**

- **You are manager and planner** you plan tasks and then delegate them to agents and subagents, you do not work on tasks on your own, you use specialised team members.
- **Allways use installed mcp servers to fulfill the task faster**
- **Allways launch multiple subagents to work on task so it is solved faster**
- **ALL code edits MUST be made locally** and then synced to remote hosts
- **NEVER use SSH to edit files directly** on remote VMs (172.16.168.21-25)
- **NEVER use remote text editors** (vim, nano, etc.) on remote hosts
- **Configuration changes MUST be made locally** and deployed via sync scripts
- **ALWAYS use sync scripts to push changes** to remote machines after local edits

**🔄 MANDATORY WORKFLOW AFTER ANY CODE CHANGES:**
1. **Edit locally** - Make ALL changes in `/home/kali/Desktop/AutoBot/`
2. **Immediately sync** - Use appropriate sync script after each edit session
3. **Never skip sync** - Remote machines must stay synchronized with local changes

**🎯 WHY THIS RULE MUST NEVER BE BROKEN:**

**💥 CRITICAL ISSUE: NO CODE TRACKING ON REMOTE MACHINES**
- **No version control** on remote VMs - changes are completely untracked
- **No backup system** - edits made remotely are never saved or recorded
- **No change history** - impossible to know what was modified, when, or by whom
- **No rollback capability** - cannot undo or revert remote changes

**⚠️ REMOTE MACHINES ARE EPHEMERAL:**
- **Can be reinstalled at any moment** without warning
- **All local changes will be PERMANENTLY LOST** during reinstallation
- **No recovery mechanism** for work done directly on remote machines
- **Complete work loss** is inevitable with direct remote editing

**🚨 ZERO TOLERANCE POLICY:**
Direct editing on remote machines (172.16.168.21-25) **GUARANTEES WORK LOSS** when machines are reinstalled. We cannot track remote changes and cannot recover lost work.

---

## 🌐 CRITICAL NETWORKING RULES

**🚨 MANDATORY: Remote Machine Accessibility**

**❌ NEVER use `localhost` or `127.0.0.1` for services accessed by remote machines:**
- **localhost/127.0.0.1 are NOT accessible from remote VMs**
- **ALWAYS use `0.0.0.0` to bind services accessible from network**
- **ALWAYS use actual IP addresses (172.16.168.x) for inter-VM communication**

**✅ CORRECT Network Configuration:**
- Backend binding: `0.0.0.0:8001` (accessible from all network interfaces)
- Frontend URLs: `172.16.168.20:8001` (actual IP for remote access)
- Inter-VM communication: Use specific VM IPs (172.16.168.21-25)

---

## Architecture Notes

### Service Layout - Distributed VM Infrastructure

**Infrastructure Overview:**
- 📡 **Main Machine (WSL)**: `172.16.168.20` - Backend API (port 8001) + Desktop/Terminal VNC (port 6080)
- 🌐 **Remote VMs:**
  - **VM1 Frontend**: `172.16.168.21:5173` - Web interface (SINGLE FRONTEND SERVER)
  - **VM2 NPU Worker**: `172.16.168.22:8081` - Hardware AI acceleration
  - **VM3 Redis**: `172.16.168.23:6379` - Data layer
  - **VM4 AI Stack**: `172.16.168.24:8080` - AI processing
  - **VM5 Browser**: `172.16.168.25:3000` - Web automation (Playwright)

### Key Files

- `setup.sh`: Standardized setup and installation script
- `run_autobot.sh`: Main startup script (replaces all other run methods)
- `backend/fast_app_factory_fix.py`: Fast backend with Redis timeout fix
- `compose.yml`: Distributed VM configuration
- `.env`: Main environment configuration for distributed infrastructure
- `config/config.yaml`: Central configuration file

---

## Development Guidelines

**CRITICAL**:

- Ignore any assumptions and reason from facts only.
- launch multiple agents in parallel to handle the different aspects of task
- use subagents in parallel and available mcp's to find the solutions.
- work on one problem at a time, it could be that problem you are working on  is caused by another problem, leave no stone unturned.
- If something is not working, look into logs for clues, check all logs.
- Timeout is not a solution to problem.
- Temporary function disable is not a solution, all it does is cause more problems and we forget that it was disabled.
- Missing api endpoint, look for existing before creating new.
- Avoid Hardcodes at all costs.
- Do not restart any processes without user consent, allways ask user to do restart, restarts are service disruptions.
- When you receive error or warning, you fix it properly untill it is gone forever. investigate all logs, not only the one error appeared, but related also components until you track down the line where it happened and all related functions that could have caused it.
- Allways trace  all errors full way, if its a frontend error, trace it all the way to backend, if backend all the way to frontend, allways look in to logs.
- when installing dependency allways update the install scripts for the fresh deployments.

---

## 📋 Status Updates & System State

**For all system status updates, fixes, and improvements:**

👉 **See:** [`docs/system-state.md`](docs/system-state.md)

This includes:
- Critical fixes and resolutions
- System status changes
- Performance improvements
- Architecture updates
- Error resolutions
- Hardware optimization notes
- Service health status

---

## How to Run AutoBot

### Standard Startup (Recommended)

```bash
bash run_autobot.sh --dev
```

**Available Options:**
```bash
bash run_autobot.sh [OPTIONS]

OPTIONS:
  --dev              Development mode with auto-reload and debugging
  --prod             Production mode (default)
  --no-build         Skip builds (fastest restart)
  --build            Force build even if images exist
  --rebuild          Force rebuild everything (clean slate)
  --no-desktop       Disable VNC desktop access
  --desktop          Enable VNC desktop access (default)
  --help             Show this help message
```

### Common Usage Examples

**Development Mode (Daily Use):**
```bash
bash run_autobot.sh --dev --no-build
```
- Fastest startup for development
- Uses existing services
- Auto-reload and debugging enabled

**Fresh Development Setup:**
```bash
bash run_autobot.sh --dev --build
```
- Builds/rebuilds all services
- Development mode with debugging
- VNC desktop enabled by default

### Desktop Access (VNC)

Desktop access is **enabled by default** on all modes:
- **Access URL**: `http://127.0.0.1:6080/vnc.html`
- **Disable**: Add `--no-desktop` flag
- **Distributed Setup**: VNC runs on main machine (WSL)

---

## Monitoring & Debugging

### Check Service Health

```bash
# Backend health
curl http://localhost:8001/api/health

# Redis connection
redis-cli -h 172.16.168.23 ping

# View logs
tail -f logs/backend.log
```

### Frontend Debugging

Browser DevTools automatically open in dev mode to monitor:

- API calls and timeouts
- RUM (Real User Monitoring) events
- Console errors

**🚨 CRITICAL: Browser Debugging on Kali Linux**

- **❌ NEVER install Playwright locally on Kali Linux** - incompatible environment
- **✅ ALWAYS use AutoBot's dedicated Browser VM** (`172.16.168.25:3000`)
- **✅ Playwright is pre-installed and ready on Browser VM** - Claude can use it directly
- **✅ Use Browser VM for all web automation and debugging tasks**
- **✅ Access frontend via Browser VM's Playwright instance for console debugging**
- **Browser VM Services:**
  - Playwright automation: `172.16.168.25:3000`
  - VNC access for visual debugging when needed
  - Full browser compatibility and tool support

---

## Documentation Structure

**Complete documentation available in:**

```
docs/
├── api/                    # API documentation (518+ endpoints)
├── architecture/          # System architecture and design
├── developer/             # Developer setup and onboarding
├── features/              # Feature documentation
├── security/              # Security implementation
├── troubleshooting/       # Problem resolution guides
└── system-state.md        # System status and updates
```

**Key Documents:**
- [`docs/developer/PHASE_5_DEVELOPER_SETUP.md`](docs/developer/PHASE_5_DEVELOPER_SETUP.md) - 25-minute developer setup
- [`docs/api/COMPREHENSIVE_API_DOCUMENTATION.md`](docs/api/COMPREHENSIVE_API_DOCUMENTATION.md) - Complete API reference
- [`docs/architecture/PHASE_5_DISTRIBUTED_ARCHITECTURE.md`](docs/architecture/PHASE_5_DISTRIBUTED_ARCHITECTURE.md) - Architecture overview
- [`docs/troubleshooting/COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md`](docs/troubleshooting/COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md) - Problem resolution
- [`docs/system-state.md`](docs/system-state.md) - **System status and updates**