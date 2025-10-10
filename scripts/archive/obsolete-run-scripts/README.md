# Obsolete Run Scripts Archive

This directory contains run scripts that have been superseded by standardized procedures defined in CLAUDE.md.

## Archived Scripts

### start-frontend-dev.sh (Archived: 2025-10-10)

**Status**: ❌ **OBSOLETE - DO NOT USE**

**Replacement**: Use `bash run_autobot.sh --dev` instead

**Reason**: Violates CLAUDE.md STANDARDIZED PROCEDURES policy. All startup operations must use:
- **Setup**: `bash setup.sh [--full|--minimal|--distributed]`
- **Startup**: `bash run_autobot.sh [--dev|--prod] [--desktop|--no-desktop] [--no-browser]`

**Historical Context**:
This script was used to start the frontend development server on VM1 (172.16.168.21:5173) before the unified `run_autobot.sh` system was established. It performed:
- Backend health check on 172.16.168.20:8001
- Frontend code sync to VM1
- Vite dev server startup on remote VM

**Why It's Obsolete**:
- Duplicates functionality now in `run_autobot.sh --dev`
- Not part of standardized procedures
- Listed under "OBSOLETE METHODS (DO NOT USE)" in CLAUDE.md
- Creates confusion about proper startup method

**Preserved for**: Reference and historical documentation only.

---

## Policy Reference

From CLAUDE.md section **"STANDARDIZED PROCEDURES"**:

> **ONLY PERMITTED SETUP AND RUN METHODS:**
>
> ### Setup (Required First Time)
> ```bash
> bash setup.sh [--full|--minimal|--distributed]
> ```
>
> ### Startup (Daily Use)
> ```bash
> bash run_autobot.sh [--dev|--prod] [--desktop|--no-desktop] [--no-browser]
> ```
>
> **❌ OBSOLETE METHODS (DO NOT USE):**
> - ~~Any other run scripts~~ → ALL archived in `scripts/archive/`

All scripts in this archive directory violate this policy and have been replaced by the standardized methods above.
