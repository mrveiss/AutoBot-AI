# Interactive Command Support (Issue #33)

**Status:** ✅ Complete
**Version:** 1.0.0
**Date:** 2025-11-15

## Overview

Interactive command support enables AutoBot's approval workflow to handle commands that require user input (stdin) such as password prompts, SSH confirmations, and interactive scripts. Previously, these commands would hang or fail because they couldn't receive user input.

## Features

### 1. **Automatic Detection** (Backend)
- 16 regex patterns detect interactive commands
- Patterns cover: sudo, ssh, mysql, passwd, apt, docker login, git clone, etc.
- Detection runs during command risk assessment
- Results stored in approval metadata

### 2. **User Notification** (Frontend)
- Blue info box in approval UI shows interactive command warning
- Lists specific input requirements (e.g., "sudo commands (password)")
- Clear message: "This command requires user input (stdin). You'll be prompted after approval."

### 3. **Stdin Input Handling** (Full Stack)
- **Backend:** WebSocket `terminal_stdin` message handler
- **Frontend:** `sendStdin()` method in TerminalService
- **PTY:** Direct input to SimplePTY via `write_input()`
- **Security:** 4KB message size limit, session validation

### 4. **Password Protection** (Security)
- `is_password` flag disables terminal echo
- Passwords never logged
- Echo automatically re-enabled after input
- Failsafe: Echo re-enabled on error

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       INTERACTIVE COMMAND FLOW                   │
└─────────────────────────────────────────────────────────────────┘

1. DETECTION (Backend - agent_terminal_service.py)
   ┌──────────────────────────────────────────────────────┐
   │ Agent executes command                                │
   │   ↓                                                   │
   │ is_interactive_command(command) runs                  │
   │   ↓                                                   │
   │ Returns: (is_interactive=True, reasons=[...])         │
   │   ↓                                                   │
   │ Metadata added to CommandExecution                    │
   │   ↓                                                   │
   │ Approval response includes: is_interactive, reasons   │
   └──────────────────────────────────────────────────────┘

2. USER NOTIFICATION (Frontend - ChatMessages.vue)
   ┌──────────────────────────────────────────────────────┐
   │ Approval card displays interactive warning:          │
   │   [🎹] Interactive Command                           │
   │   This command requires user input (stdin).          │
   │   Input required for:                                │
   │     • sudo commands (password)                       │
   │     • SSH connections (host verification)            │
   └──────────────────────────────────────────────────────┘

3. APPROVAL & EXECUTION
   ┌──────────────────────────────────────────────────────┐
   │ User approves command                                 │
   │   ↓                                                   │
   │ Command executes in PTY                              │
   │   ↓                                                   │
   │ PTY outputs password prompt: "Password: "            │
   │   ↓                                                   │
   │ Terminal displays prompt to user                     │
   └──────────────────────────────────────────────────────┘

4. STDIN INPUT (Full Stack)
   ┌──────────────────────────────────────────────────────┐
   │ User types password in terminal                       │
   │   ↓                                                   │
   │ Frontend: terminalService.sendStdin(sessionId,        │
   │           content, isPassword=true, commandId)        │
   │   ↓                                                   │
   │ WebSocket sends: { type: "terminal_stdin",           │
   │                    content: "password\\n",            │
   │                    is_password: true }                │
   │   ↓                                                   │
   │ Backend handler: _handle_terminal_stdin()            │
   │   • Validates size (max 4KB)                         │
   │   • Disables echo (if is_password=true)              │
   │   • Calls PTY.write_input(content)                   │
   │   • Re-enables echo                                  │
   │   ↓                                                   │
   │ PTY receives input → Command processes → Continues   │
   └──────────────────────────────────────────────────────┘
```

## Implementation Details

### Detection Patterns

**File:** `backend/services/agent_terminal_service.py` (lines 137-157)

```python
INTERACTIVE_COMMAND_PATTERNS = [
    r'^\s*sudo\s+',              # sudo commands (password)
    r'^\s*ssh\s+',               # SSH connections
    r'\bmysql\s+.*-p\b',         # MySQL with password
    r'^\s*passwd\b',             # Password change
    r'\b--interactive\b',        # Explicit interactive flag
    r'^\s*python.*input\(',      # Python scripts with input()
    r'^\s*read\s+',              # Bash read command
    r'^\s*apt\s+install\b',      # APT confirmations
    r'^\s*docker\s+login\b',     # Docker login
    # ... 16 total patterns
]
```

### WebSocket Protocol

**Message Type:** `terminal_stdin`

**Request Format:**
```json
{
  "type": "terminal_stdin",
  "content": "user input text\\n",
  "is_password": false,
  "command_id": "cmd-uuid-optional"
}
```

**Response:** None (input forwarded directly to PTY)

**Error Response:**
```json
{
  "type": "error",
  "content": "Error message",
  "timestamp": 1234567890.123
}
```

### Security Controls

**Size Limit:**
- Maximum 4KB per stdin message
- Prevents abuse and buffer overflow

**Session Validation:**
- Requires active PTY session
- WebSocket connection must be OPEN state

**Password Protection:**
- `is_password=true` → `pty.set_echo(False)`
- Disables terminal echo (no visible characters)
- Automatically re-enabled after input processed
- Failsafe: Always re-enable on error

**Logging:**
- Regular stdin: Logged with byte count
- Password stdin: Logged as "password input" (content never logged)
- Format: `[STDIN] Sent 10 bytes to PTY (password: true, command: cmd-123)`

## Usage Examples

### Example 1: Sudo Command

**User executes:** `sudo apt update`

**Detection:**
- Pattern matched: `r'^\s*sudo\s+'`
- `is_interactive = true`
- `interactive_reasons = ["sudo commands (password)"]`

**Approval UI shows:**
```
⚠️  Command Approval Required
Command: sudo apt update
Risk Level: HIGH

[🎹] Interactive Command
This command requires user input (stdin). You'll be prompted after approval.
Input required for:
  • sudo commands (password)
```

**After approval:**
1. Command executes in PTY
2. PTY outputs: `[sudo] password for user: `
3. User types password in terminal
4. Frontend calls: `terminalService.sendStdin(sessionId, "password\\n", isPassword=true)`
5. Backend disables echo, sends to PTY, re-enables echo
6. Command continues execution

### Example 2: SSH Connection

**User executes:** `ssh user@host.com`

**Detection:**
- Pattern matched: `r'^\s*ssh\s+'`
- `is_interactive = true`
- `interactive_reasons = ["SSH connections (host verification, password)"]`

**After approval:**
1. PTY outputs: `The authenticity of host 'host.com' can't be established. Continue? (yes/no)`
2. User types: `yes`
3. PTY outputs: `user@host.com's password: `
4. User types password (echo disabled automatically)
5. SSH connection established

### Example 3: MySQL Password

**User executes:** `mysql -u root -p`

**Detection:**
- Pattern matched: `r'\bmysql\s+.*-p\b'`
- `is_interactive = true`
- `interactive_reasons = ["MySQL with password flag"]`

**After approval:**
1. PTY outputs: `Enter password: `
2. User types password (echo disabled)
3. MySQL client starts

## API Reference

### Backend

#### `is_interactive_command(command: str) -> tuple[bool, list[str]]`

**Location:** `backend/services/agent_terminal_service.py:163-210`

**Purpose:** Detect if command requires stdin input

**Parameters:**
- `command` (str): Shell command to analyze

**Returns:**
- Tuple of `(is_interactive, matched_patterns)`
- `is_interactive` (bool): True if command requires stdin
- `matched_patterns` (list[str]): Descriptions of why (e.g., "sudo commands (password)")

**Example:**
```python
is_interactive, reasons = is_interactive_command("sudo apt update")
# Returns: (True, ["sudo commands (password)"])
```

#### `_handle_terminal_stdin(message: dict)`

**Location:** `backend/api/terminal.py:688-784`

**Purpose:** WebSocket handler for interactive stdin messages

**Message Format:** See WebSocket Protocol above

**Security:**
- Size validation (4KB max)
- Session validation
- Echo control for passwords
- Error handling with failsafe

### Frontend

#### `terminalService.sendStdin(sessionId, content, isPassword, commandId)`

**Location:** `autobot-vue/src/services/TerminalService.js:397-420`

**Purpose:** Send stdin input to interactive command

**Parameters:**
- `sessionId` (string): Terminal session ID
- `content` (string): Input text to send (include `\\n` for newline)
- `isPassword` (boolean): Disable echo for password input
- `commandId` (string | null): Optional command ID for tracking

**Returns:** `boolean` - True if sent successfully, false otherwise

**Example:**
```javascript
const success = terminalService.sendStdin(
  'session-123',
  'mypassword\\n',
  true,  // isPassword
  'cmd-456'
)
```

## Testing

### Manual Test Checklist

- [ ] **Sudo command:**
  - Execute: `sudo ls /root`
  - Verify: Blue interactive warning shows in approval UI
  - Approve command
  - Verify: Password prompt appears in terminal
  - Type password (verify no echo)
  - Verify: Command executes successfully
  - Verify: Password not in logs

- [ ] **SSH connection:**
  - Execute: `ssh user@testhost`
  - Verify: Interactive warning shows
  - Approve command
  - Verify: Host verification prompt appears
  - Type `yes` + Enter
  - Verify: Password prompt appears
  - Type password (verify no echo)
  - Verify: Connection established or proper error

- [ ] **MySQL password:**
  - Execute: `mysql -u root -p`
  - Verify: Interactive warning shows
  - Approve command
  - Verify: "Enter password:" prompt appears
  - Type password (verify no echo)
  - Verify: MySQL client starts or proper error

- [ ] **Python input():**
  - Execute: `python3 -c "name = input('Enter name: '); print(f'Hello {name}')"`
  - Verify: Interactive warning shows
  - Approve command
  - Verify: "Enter name:" prompt appears
  - Type name + Enter
  - Verify: Output shows "Hello {name}"

- [ ] **APT install:**
  - Execute: `sudo apt install curl`
  - Verify: Interactive warning shows
  - Approve command
  - Verify: sudo password prompt
  - Type password
  - Verify: APT confirmation prompt (Y/n)
  - Type `Y` + Enter
  - Verify: Package installs

## Troubleshooting

### Issue: Command hangs after approval

**Symptom:** Command shows password prompt but doesn't accept input

**Solution:**
1. Check WebSocket connection is active: Browser DevTools → Network → WS
2. Verify terminal session ID matches approval
3. Check backend logs for `[STDIN]` messages
4. Ensure SimplePTY session exists for the terminal

### Issue: Password visible when typing

**Symptom:** Password characters appear in terminal

**Solution:**
1. Verify `isPassword=true` in sendStdin call
2. Check backend logs for "Disabling echo for password input"
3. Ensure SimplePTY `set_echo(False)` working
4. Check for errors re-enabling echo (check logs)

### Issue: Interactive warning not showing

**Symptom:** Interactive command approved but no warning displayed

**Solution:**
1. Check approval response includes `is_interactive: true`
2. Verify `message.metadata.is_interactive` in Vue component
3. Check detection patterns match your command
4. Review backend logs for "Interactive command detected"

### Issue: Size limit error

**Symptom:** Large input rejected with "Input too large" error

**Solution:**
- Current limit: 4KB per message
- For large inputs, split into multiple messages
- Or use file upload + redirect: `command < largefile.txt`

## Future Enhancements

**Potential improvements (not implemented):**

1. **Visual stdin input field**
   - Dedicated input box for interactive commands
   - Auto-focus when prompt detected
   - Password type="password" for masked input

2. **Prompt detection**
   - Regex patterns to detect password prompts
   - Auto-enable password masking
   - Highlight prompts in terminal output

3. **Command templates**
   - Pre-defined responses for common prompts
   - Example: "yes" for SSH host verification
   - User configurable templates

4. **Input history**
   - Save non-password inputs for replay
   - Command-specific input suggestions

5. **Multi-line input support**
   - Heredoc-style input
   - Editor popup for large inputs

## Related Documentation

- **API Documentation:** `docs/api/AGENT_TERMINAL_API.md`
- **WebSocket Protocol:** `docs/api/WEBSOCKET_PROTOCOL.md`
- **Security Guide:** `docs/security/COMMAND_APPROVAL_SECURITY.md`
- **PTY Implementation:** `backend/services/simple_pty.py` (docstrings)

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-11-15 | Initial implementation (Issue #33) |

## References

- **GitHub Issue:** #33 - Interactive command support for approval workflow
- **Implementation PRs:**
  - Backend: Commit `ed883c8`
  - Frontend: Commit `1231f75`
