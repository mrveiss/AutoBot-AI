# Terminal Architecture for Distributed Deployment

## Current Architecture (Co-located with Backend)

### Overview
Currently, the terminal functionality runs on the main machine (`172.16.168.20`) alongside the backend API. This provides optimal performance and minimal latency for terminal operations.

### Current Setup
- **Location**: Main machine (WSL) at `172.16.168.20`
- **Backend API**: Port 8001
- **Terminal Endpoints**: `/api/terminal/*`
- **WebSocket Endpoints**: `/ws/terminal/*`, `/ws/simple/*`, `/ws/secure/*`
- **Security**: Enhanced security layer with audit logging

### Key Components

#### 1. Terminal API Router (`autobot-user-backend/api/terminal.py`)
**22 REST API Endpoints**:
- **Session Management**: CREATE, READ, LIST, DELETE operations
- **Command Execution**: Single commands and interactive sessions
- **Tool Management**: Install, check, validate tools
- **Control Operations**: Take/return control, send signals
- **WebSocket Integration**: 3 WebSocket endpoint types

**Core Endpoints**:
```
POST   /api/terminal/sessions          # Create terminal session
GET    /api/terminal/sessions          # List active sessions
GET    /api/terminal/sessions/{id}     # Get session info
DELETE /api/terminal/sessions/{id}     # Close session
POST   /api/terminal/command           # Execute single command
POST   /api/terminal/{id}/input        # Send input to session
POST   /api/terminal/{id}/control/take # Take user control
POST   /api/terminal/{id}/control/return # Return to agent
```

#### 2. WebSocket Handlers
**Three WebSocket Types**:
- **Standard**: `/ws/terminal/{chat_id}` - Basic terminal communication
- **Simple**: `/ws/simple/{session_id}` - Lightweight sessions
- **Secure**: `/ws/secure/{session_id}` - Enhanced security with auditing

#### 3. System Command Agent (`autobot-user-backend/agents/system_command_agent.py`)
**Core Terminal Engine**:
- PTY (pseudo-terminal) management
- Command execution with security validation
- Session state management
- Tool installation automation
- Package manager detection

#### 4. Security Features
- **Command Validation**: Safety checks before execution
- **Audit Logging**: Complete command history with timestamps
- **Enhanced Security Layer**: PII detection and redaction
- **Access Control**: Session-based permissions

## Future Architecture (Separate Terminal Machine)

### Motivation for Separation
- **Hardware Optimization**: Dedicated terminal processing machine
- **Security Isolation**: Terminal operations in sandboxed environment
- **Scalability**: Multiple terminal machines for load balancing
- **Fault Tolerance**: Terminal failures don't affect main backend

### Proposed Distributed Architecture

```
Main Backend Machine (172.16.168.20)
├── FastAPI Backend (Port 8001)
├── Terminal Proxy API
└── WebSocket Proxy

↓ Network Communication ↓

Terminal Machine (172.16.168.26) [Future]
├── Terminal Service (Port 8002)
├── PTY Manager
├── Security Auditor
└── Session Manager
```

### API Contract for Remote Terminal

#### Terminal Service API (Port 8002)
**Core Endpoints** (Mirror current API):
```
POST   /terminal/sessions             # Create session
GET    /terminal/sessions             # List sessions
POST   /terminal/execute              # Execute command
WS     /ws/terminal/{session_id}      # WebSocket connection
```

#### Backend Proxy API (Port 8001)
**Proxy Endpoints** (Transparent to frontend):
```
POST   /api/terminal/sessions         # Proxies to terminal machine
GET    /api/terminal/sessions         # Proxies to terminal machine
POST   /api/terminal/command          # Proxies to terminal machine
WS     /api/terminal/ws/{id}          # WebSocket proxy
```

### Implementation Strategy

#### Phase 1: API Abstraction
1. **Create Terminal Client Interface**:
   ```python
   class TerminalClient:
       async def create_session(self, config: SessionConfig) -> Session
       async def execute_command(self, session_id: str, command: str) -> Result
       async def get_sessions(self) -> List[Session]
   ```

2. **Implement Local Client** (Current behavior):
   ```python
   class LocalTerminalClient(TerminalClient):
       # Direct calls to system_command_agent
   ```

3. **Implement Remote Client** (Future):
   ```python
   class RemoteTerminalClient(TerminalClient):
       # HTTP/WebSocket calls to remote terminal machine
   ```

#### Phase 2: Configuration-Based Switching
```yaml
# config/terminal.yaml
terminal:
  mode: "local"  # or "remote"
  remote:
    host: "172.16.168.26"
    port: 8002
    auth:
      method: "ssh_key"
      key_path: "~/.ssh/autobot_terminal_key"
```

#### Phase 3: WebSocket Proxying
```python
@app.websocket("/api/terminal/ws/{session_id}")
async def terminal_websocket_proxy(websocket: WebSocket, session_id: str):
    if config.terminal.mode == "local":
        await handle_local_terminal_websocket(websocket, session_id)
    else:
        await handle_remote_terminal_websocket(websocket, session_id)
```

### Security Considerations

#### Authentication Between Machines
- **SSH Key Authentication**: Dedicated key for terminal communication
- **Certificate-Based**: TLS certificates for API authentication
- **Token-Based**: JWT tokens for session authentication

#### Network Security
- **Firewall Rules**: Only backend machine can access terminal machine port 8002
- **VPN/Tunnel**: Encrypted communication channel
- **Rate Limiting**: Prevent abuse of terminal resources

#### Audit Trail Preservation
- **Centralized Logging**: Forward all audit logs to main machine
- **Event Streaming**: Real-time security events to monitoring system
- **Command History**: Maintain complete command history across machines

### Migration Path

#### Step 1: Code Refactoring
1. Extract terminal operations into service interface
2. Create local implementation using existing code
3. Update all callers to use interface instead of direct calls

#### Step 2: Remote Implementation
1. Create standalone terminal service application
2. Implement HTTP API matching current endpoints
3. Add WebSocket support for real-time communication
4. Implement security and auditing features

#### Step 3: Deployment Strategy
1. **Blue-Green Deployment**: Run both local and remote simultaneously
2. **Feature Flags**: Switch individual sessions between local/remote
3. **Gradual Migration**: Move sessions one by one to remote
4. **Fallback Capability**: Return to local if remote fails

### Performance Considerations

#### Latency Impact
- **Current**: Direct function calls (~0.1ms)
- **Remote**: HTTP API calls (~5-10ms)
- **WebSocket**: Real-time streaming (~2-5ms latency)

#### Optimization Strategies
- **Connection Pooling**: Reuse HTTP connections
- **WebSocket Persistence**: Keep connections alive
- **Compression**: gzip compression for large outputs
- **Buffering**: Batch small commands for efficiency

### Configuration Management

#### Environment Variables
```bash
# Terminal configuration
AUTOBOT_TERMINAL_MODE=remote
AUTOBOT_TERMINAL_HOST=172.16.168.26
AUTOBOT_TERMINAL_PORT=8002
AUTOBOT_TERMINAL_AUTH_KEY=/home/autobot/.ssh/terminal_key
```

#### Service Discovery
```python
class TerminalServiceDiscovery:
    def discover_terminal_services(self) -> List[TerminalService]:
        # Auto-discover available terminal machines
        # Health check and load balancing
```

### Monitoring and Observability

#### Health Checks
- **Terminal Service Health**: `/health` endpoint on terminal machine
- **Connection Status**: Backend monitors terminal machine connectivity
- **Session Health**: Track active sessions and their status

#### Metrics Collection
- **Request Latency**: Time for commands to execute
- **Session Duration**: How long sessions remain active
- **Error Rates**: Failed commands and connection issues
- **Resource Usage**: CPU/Memory on terminal machine

### Error Handling and Fallback

#### Connection Failures
1. **Retry Logic**: Exponential backoff for temporary failures
2. **Circuit Breaker**: Temporarily disable remote terminals if unhealthy
3. **Local Fallback**: Switch to local terminal if remote unavailable
4. **Graceful Degradation**: Inform users of reduced functionality

#### Session Recovery
1. **Session State Persistence**: Save session state for recovery
2. **Command Replay**: Replay commands to restore session state
3. **User Notification**: Inform users when sessions are recovered

### Testing Strategy

#### Integration Testing
```python
@pytest.mark.asyncio
async def test_remote_terminal_command_execution():
    client = RemoteTerminalClient("172.16.168.26:8002")
    session = await client.create_session()
    result = await client.execute_command(session.id, "pwd")
    assert result.exit_code == 0
```

#### Load Testing
- **Concurrent Sessions**: Test multiple terminal sessions
- **Command Throughput**: Measure commands per second
- **WebSocket Stress**: Test WebSocket connection limits

### Documentation Updates Required

When implementing remote terminal:

1. **API Documentation**: Update endpoint documentation
2. **Deployment Guide**: Add terminal machine setup
3. **Security Guide**: Document new security considerations
4. **Troubleshooting**: Add remote terminal debugging guide
5. **Configuration Reference**: Document all new config options

### Implementation Timeline

#### Phase 1 (2 weeks): Abstraction Layer
- Create terminal client interface
- Implement local client
- Update all callers to use interface

#### Phase 2 (3 weeks): Remote Service
- Build standalone terminal service
- Implement HTTP API
- Add WebSocket support
- Security and authentication

#### Phase 3 (2 weeks): Integration
- Backend proxy implementation
- Configuration management
- Testing and validation

#### Phase 4 (1 week): Deployment
- Production deployment
- Monitoring setup
- Documentation updates

### Conclusion

The current co-located terminal architecture provides excellent performance and simplicity. The future distributed architecture will enable better scalability, security isolation, and fault tolerance while maintaining API compatibility. The migration path ensures zero downtime and gradual transition to the new architecture.

The key success factors are:
1. **API Compatibility**: Frontend code requires no changes
2. **Configuration-Driven**: Easy switching between local/remote
3. **Robust Error Handling**: Graceful fallback to local terminal
4. **Security Preservation**: Maintain all current security features
5. **Performance Monitoring**: Ensure remote performance is acceptable
