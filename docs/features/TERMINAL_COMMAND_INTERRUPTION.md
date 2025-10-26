# Terminal Command Interruption Feature

**Date**: 2025-10-25
**Status**: ✅ Implemented and Active

---

## Overview

AutoBot now supports **interrupting long-running terminal commands** via SIGINT, SIGTERM, and other Unix signals. This allows users to stop commands that are taking too long or were started by mistake.

---

## Features

### Supported Signals

- **SIGINT (Ctrl+C)**: Interrupt/terminate process (graceful)
- **SIGTERM**: Terminate process (graceful)
- **SIGKILL**: Force kill process (immediate, non-graceful)
- **SIGHUP**: Hangup signal

### Access Points

1. **Frontend UI - Interrupt Button**:
   - Yellow "⚡ INT" button in terminal header
   - Sends SIGINT to current process
   - Disabled when no active process running

2. **Keyboard Shortcut**:
   - Press `Ctrl+C` in terminal input
   - Same as interrupt button (sends SIGINT)

3. **REST API Endpoint** (programmatic access):
   ```http
   POST /api/terminal/sessions/{session_id}/signal/{signal_name}
   ```

4. **WebSocket Message** (frontend integration):
   ```json
   {
     "type": "signal",
     "signal": "SIGINT"
   }
   ```

---

## Implementation Details

### Architecture Flow

```
User Action (Click/Ctrl+C)
    ↓
Frontend UI (TerminalHeader.vue / TerminalInput.vue)
    ↓
TerminalService.sendSignal(sessionId, 'SIGINT')
    ↓
WebSocket Message: {type: 'signal', signal: 'SIGINT'}
    ↓
Backend WebSocket Handler (terminal.py:373-374)
    ↓
_handle_signal_message() (terminal.py:595-660)
    ↓
Map signal name → signal number
    ↓
self.pty_process.send_signal(sig)
    ↓
SimplePTY.send_signal() (simple_pty.py:179-189)
    ↓
os.killpg(os.getpgid(process.pid), sig)
    ↓
Process receives signal and terminates
```

### Code Locations

#### Frontend

**UI Components**:
- `autobot-vue/src/components/terminal/TerminalHeader.vue:32-39` - Interrupt button
- `autobot-vue/src/components/terminal/TerminalInput.vue:136-140` - Ctrl+C handler

**Service Layer**:
- `autobot-vue/src/services/TerminalService.js:395-414` - `sendSignal()` method

#### Backend

**WebSocket Handler**:
- `backend/api/terminal.py:373-374` - Message type routing for 'signal'
- `backend/api/terminal.py:595-660` - `_handle_signal_message()` implementation

**REST Endpoint**:
- `backend/api/terminal.py:1014-1035` - `/sessions/{session_id}/signal/{signal_name}`

**Session Manager**:
- `backend/api/terminal.py:755-768` - `send_signal()` method (routes to PTY)

**PTY Implementation**:
- `backend/services/simple_pty.py:179-189` - `send_signal()` (actual process signaling)

---

## Usage Examples

### Example 1: Interrupt Long-Running Command

**Scenario**: You started a network scan that's taking too long

```bash
# In terminal:
nmap -sn 192.168.1.0/24
# Scanning 256 hosts...
```

**Action**:
1. Click the yellow "⚡ INT" button in terminal header
2. OR press `Ctrl+C` in terminal

**Result**:
```bash
^C
nmap scan interrupted
```

### Example 2: Kill Hanging Process

**Scenario**: Process not responding to SIGINT

```bash
# If SIGINT doesn't work, use REST API for SIGKILL:
curl -X POST http://172.16.168.20:8001/api/terminal/sessions/{session_id}/signal/SIGKILL
```

### Example 3: Programmatic Signal Sending

**Using WebSocket (from frontend)**:
```javascript
import { TerminalService } from '@/services/TerminalService'

// Send SIGINT
TerminalService.sendSignal(sessionId, 'SIGINT')

// Send SIGTERM
TerminalService.sendSignal(sessionId, 'SIGTERM')
```

**Using REST API (from any client)**:
```bash
# SIGINT
curl -X POST http://172.16.168.20:8001/api/terminal/sessions/abc123/signal/SIGINT

# SIGTERM
curl -X POST http://172.16.168.20:8001/api/terminal/sessions/abc123/signal/SIGTERM

# SIGKILL (force kill)
curl -X POST http://172.16.168.20:8001/api/terminal/sessions/abc123/signal/SIGKILL
```

---

## Response Messages

### Success Response (WebSocket)

```json
{
  "type": "signal_sent",
  "signal": "SIGINT",
  "timestamp": 1698765432.123
}
```

### Error Responses

**No Active Process**:
```json
{
  "type": "error",
  "content": "No active process to interrupt",
  "timestamp": 1698765432.123
}
```

**Unknown Signal**:
```json
{
  "type": "error",
  "content": "Unknown signal: SIGFOO",
  "timestamp": 1698765432.123
}
```

**Signal Failed**:
```json
{
  "type": "error",
  "content": "Failed to send signal: SIGINT",
  "timestamp": 1698765432.123
}
```

---

## Testing

### Test Long-Running Command

```bash
# Start a long-running command
sleep 100

# Click interrupt button or press Ctrl+C
# Expected: Command terminates immediately
```

### Test Network Command

```bash
# Start network scan
ping -c 1000 google.com

# Click interrupt button
# Expected: Ping stops, shows statistics
```

### Test Hanging Process

```bash
# Start process that ignores SIGINT
cat > /dev/null

# Press Ctrl+C (SIGINT)
# Expected: Process terminates

# If SIGINT fails, use SIGKILL via REST API
```

---

## Troubleshooting

### Issue: Interrupt Button Disabled

**Cause**: No active process detected in PTY session

**Solution**:
- Check if process is actually running: `ps aux | grep <process>`
- Restart terminal session if PTY state is stale

### Issue: Signal Not Terminating Process

**Cause**: Process ignoring SIGINT/SIGTERM

**Solutions**:
1. Try SIGKILL (force kill): `curl -X POST .../signal/SIGKILL`
2. Check process group: Some processes spawn children that need separate signals
3. Verify PTY process exists: Check backend logs for "No PTY process" errors

### Issue: WebSocket Not Receiving Signal Response

**Cause**: WebSocket connection closed or message handler error

**Solutions**:
1. Check browser console for WebSocket errors
2. Verify backend logs: `grep "signal" logs/backend.log`
3. Reconnect terminal session

---

## Security Considerations

### Process Group Signaling

The implementation uses **process group signaling** (`os.killpg`) to ensure:
- All child processes receive the signal
- Prevents orphaned processes
- Proper cleanup of process trees

### Signal Validation

- Only **predefined signals** are allowed (SIGINT, SIGTERM, SIGKILL, SIGHUP)
- Invalid signal names are rejected with error response
- Logged for security tracking

### Session Authorization

- Signals only sent to authenticated sessions
- Session ownership verified before signal delivery
- All signal attempts logged for audit

---

## Logging

### Backend Logs

**Signal Sent Successfully**:
```
INFO: Sent SIGINT to PTY process
```

**Signal Failed**:
```
ERROR: Failed to send SIGINT
WARNING: No PTY process to send signal to
```

**Security Tracking**:
```
INFO: [SECURITY] Signal sent: SIGINT, session=abc123, timestamp=2025-10-25T14:00:00
```

---

## API Reference

### REST Endpoint

**URL**: `/api/terminal/sessions/{session_id}/signal/{signal_name}`

**Method**: `POST`

**Parameters**:
- `session_id` (path): Terminal session ID
- `signal_name` (path): Signal name (SIGINT, SIGTERM, SIGKILL, SIGHUP)

**Response**:
```json
{
  "status": "signal_sent",
  "signal": "SIGINT",
  "session_id": "abc123",
  "timestamp": "2025-10-25T14:00:00"
}
```

**Error Response**:
```json
{
  "detail": "Session not found"
}
```

### WebSocket Message Format

**Send Signal**:
```json
{
  "type": "signal",
  "signal": "SIGINT"
}
```

**Receive Confirmation**:
```json
{
  "type": "signal_sent",
  "signal": "SIGINT",
  "timestamp": 1698765432.123
}
```

---

## Related Files

### Modified in This Implementation

1. **backend/api/terminal.py**:
   - Line 373-374: Added 'signal' message type handler
   - Line 595-660: Implemented `_handle_signal_message()`
   - Line 755-768: Fixed `send_signal()` to call PTY

2. **backend/services/simple_pty.py**:
   - Line 179-189: `send_signal()` implementation (existing)

### Existing Frontend Files

3. **autobot-vue/src/components/terminal/TerminalHeader.vue**:
   - Line 32-39: Interrupt button (existing)

4. **autobot-vue/src/components/terminal/TerminalInput.vue**:
   - Line 136-140: Ctrl+C handler (existing)

5. **autobot-vue/src/services/TerminalService.js**:
   - Line 395-414: `sendSignal()` method (existing)

---

## Future Enhancements

### Potential Improvements

1. **Signal History**:
   - Track which signals were sent to each session
   - Display in terminal status bar

2. **Custom Signals**:
   - Support user-defined signals (SIGUSR1, SIGUSR2)
   - Signal mapping configuration

3. **Batch Signal Sending**:
   - Send signals to multiple sessions at once
   - Useful for multi-terminal workflows

4. **Process Tree Visualization**:
   - Show process hierarchy before signaling
   - Confirm which processes will be affected

5. **Grace Period**:
   - Try SIGTERM first, wait N seconds
   - Escalate to SIGKILL if process doesn't terminate

---

## Changelog

### 2025-10-25 - Initial Implementation

**Added**:
- WebSocket signal message handler
- Signal name to signal number mapping
- PTY process group signaling integration
- Error handling and logging
- Security audit logging

**Fixed**:
- ConsolidatedTerminalManager.send_signal() stub implementation
- Missing 'signal' message type in WebSocket handler

**Files Modified**:
- `backend/api/terminal.py` (2 locations: message routing + handler method)

---

## Conclusion

The terminal command interruption feature provides a robust, secure way to control long-running processes in AutoBot's terminal sessions. The implementation follows Unix signal conventions while providing modern WebSocket and REST API interfaces.

**Status**: ✅ **Production Ready**

**Testing**: Ready for user testing with real-world long-running commands.
