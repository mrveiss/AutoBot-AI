# Terminal Services Archive

**Date Archived**: 2025-01-09
**Reason**: Terminal consolidation - Phase 2

This directory contains archived PTY (pseudo-terminal) implementations that have been superseded by the SimplePTY implementation.

---

## Archived Files

### 1. `pty_terminal.py.unused`

**Status**: ❌ Unused - Functionality duplicates `simple_pty.py`

**Original Purpose**: Real PTY implementation with async callbacks

**Why Archived**:
- Duplicate of `simple_pty.py` with overlapping features
- `simple_pty.py` is actively used by both Tools and Chat terminals
- Unique features migrated to `simple_pty.py` in Phase 1

**Overlapping Features** (both had these):
- PTY creation with `pty.openpty()`
- Signal handling with `send_signal()`
- Terminal resize with SIGWINCH
- Process group management (`os.setsid`)
- `is_alive()` health check
- PTYManager session management

**Unique Features** (migrated to simple_pty.py):
- ✅ Login shell option (`use_login_shell` parameter)
  - Starts bash with `--login` flag to load profile files
- ✅ Custom PS1 prompt (`custom_ps1` parameter)
  - Sets custom prompt via environment variable

**Active Implementation**: Use `backend/services/simple_pty.py` (SimplePTY class)

---

## Active PTY Implementation

The active PTY implementation is **`simple_pty.py`**, which provides:

### Core Features
- Synchronous PTY with queue-based I/O
- Terminal echo configuration (enable/disable)
- Dynamic echo control for password input
- Separate reader/writer threads
- Non-blocking output retrieval via `get_output()`
- EOF/close signaling
- Race condition prevention

### Enhanced Features (Added in Phase 1)
- **Login shell support**: `SimplePTY(session_id, use_login_shell=True)`
- **Custom PS1 prompt**: `SimplePTY(session_id, custom_ps1=r'\u@\h:\w\$ ')`

### Usage Example

```python
from backend.services.simple_pty import SimplePTY

# Create PTY with login shell and custom prompt
pty = SimplePTY(
    session_id="my-session",
    use_login_shell=True,  # Loads ~/.bash_profile
    custom_ps1=r"[AutoBot] \w\$ "  # Custom prompt
)

# Start the PTY
pty.start(initial_cwd="/home/user/project")

# Send input
pty.send_input("ls -la\n")

# Get output (non-blocking)
output = pty.get_output()

# Check if process is alive
if pty.is_alive():
    print("PTY is running")

# Cleanup
pty.close()
```

---

## Re-enablement

**Not recommended** - `simple_pty.py` provides all functionality.

If you absolutely need to restore `pty_terminal.py`:

1. **Move file back**:
   ```bash
   mv backend/services/archive/pty_terminal.py.unused backend/services/pty_terminal.py
   ```

2. **Update imports** (not recommended):
   ```python
   # Instead of this:
   from backend.services.simple_pty import SimplePTY

   # You would use:
   from backend.services.pty_terminal import PTYTerminal
   ```

3. **Why this is not recommended**:
   - Duplicate functionality
   - `simple_pty.py` is actively maintained
   - `simple_pty.py` has all features from `pty_terminal.py`
   - No benefit to maintaining two PTY implementations

---

## Documentation

See also:
- `docs/architecture/TERMINAL_CONSOLIDATION_ANALYSIS.md` - Full consolidation analysis
- `backend/services/simple_pty.py` - Active PTY implementation
- `backend/api/terminal.py` - Terminal API using SimplePTY

---

## Support

If you need specific PTY features not available in `simple_pty.py`, please:
1. Check if `simple_pty.py` already has the feature
2. Consider adding the feature to `simple_pty.py` instead of restoring archived files
3. Consult terminal consolidation documentation
