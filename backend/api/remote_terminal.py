"""
Remote Terminal API
Provides REST API and WebSocket endpoints for remote SSH terminal access

Features:
- Multi-host SSH terminal sessions
- Remote command execution with security validation
- Real-time WebSocket streaming
- Connection pool management
- Audit logging for all operations
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

import yaml
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel

from backend.services.ssh_manager import SSHManager, RemoteCommandResult

logger = logging.getLogger(__name__)

# Create router for remote terminal API
router = APIRouter(tags=["remote-terminal"], prefix="/api/remote-terminal")


class RemoteSessionType(Enum):
    """Remote session types"""
    COMMAND = "command"  # Single command execution
    INTERACTIVE = "interactive"  # Interactive PTY session
    BATCH = "batch"  # Batch command execution


# Request/Response Models
class RemoteCommandRequest(BaseModel):
    host: str
    command: str
    timeout: Optional[int] = 30
    validate: Optional[bool] = True
    use_pty: Optional[bool] = False


class BatchCommandRequest(BaseModel):
    hosts: List[str]
    command: str
    timeout: Optional[int] = 30
    validate: Optional[bool] = True
    parallel: Optional[bool] = True


class RemoteSessionRequest(BaseModel):
    host: str
    session_type: RemoteSessionType = RemoteSessionType.INTERACTIVE
    initial_directory: Optional[str] = None
    enable_audit: Optional[bool] = True


class RemoteInputRequest(BaseModel):
    text: str


# Global SSH manager instance
_ssh_manager: Optional[SSHManager] = None


async def get_ssh_manager() -> SSHManager:
    """Dependency to get SSH manager instance"""
    global _ssh_manager

    if _ssh_manager is None:
        # Load configuration
        try:
            with open('config/config.yaml', 'r') as f:
                config = yaml.safe_load(f)
                ssh_config = config.get('ssh', {})

            _ssh_manager = SSHManager(
                ssh_key_path=ssh_config.get('key_path', '~/.ssh/autobot_key'),
                config_path='config/config.yaml',
                enable_audit_logging=True,
                audit_log_file='logs/audit.log'
            )

            # Start the manager
            await _ssh_manager.start()
            logger.info("SSH Manager initialized and started")

        except Exception as e:
            logger.error(f"Failed to initialize SSH Manager: {e}")
            # Fallback to default configuration
            _ssh_manager = SSHManager()
            await _ssh_manager.start()

    return _ssh_manager


# Remote session manager for WebSocket connections
class RemoteSessionManager:
    """Manager for remote terminal WebSocket sessions"""

    def __init__(self):
        self.sessions: Dict[str, Dict] = {}

    def create_session(
        self,
        session_id: str,
        host: str,
        session_type: RemoteSessionType,
        websocket: WebSocket
    ):
        """Create a new remote session"""
        self.sessions[session_id] = {
            'session_id': session_id,
            'host': host,
            'session_type': session_type,
            'websocket': websocket,
            'created_at': datetime.now(),
            'last_activity': datetime.now(),
            'active': True
        }
        logger.info(f"Remote session created: {session_id} for host {host}")

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session information"""
        return self.sessions.get(session_id)

    def remove_session(self, session_id: str):
        """Remove a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Remote session removed: {session_id}")

    def update_activity(self, session_id: str):
        """Update last activity timestamp"""
        if session_id in self.sessions:
            self.sessions[session_id]['last_activity'] = datetime.now()

    def list_sessions(self) -> List[Dict]:
        """List all active sessions"""
        return [
            {
                'session_id': s['session_id'],
                'host': s['host'],
                'session_type': s['session_type'].value,
                'created_at': s['created_at'].isoformat(),
                'last_activity': s['last_activity'].isoformat()
            }
            for s in self.sessions.values()
        ]


# Global session manager
session_manager = RemoteSessionManager()


# REST API Endpoints

@router.get("/")
async def remote_terminal_info():
    """Get information about the remote terminal API"""
    return {
        "name": "Remote Terminal API",
        "version": "1.0.0",
        "description": "Multi-host SSH terminal access and remote command execution",
        "features": [
            "Remote command execution with security validation",
            "Multi-host batch command execution",
            "Interactive SSH terminal sessions via WebSocket",
            "Connection pooling and health monitoring",
            "Comprehensive audit logging"
        ],
        "endpoints": {
            "hosts": "/api/remote-terminal/hosts",
            "execute": "/api/remote-terminal/execute",
            "batch": "/api/remote-terminal/batch",
            "sessions": "/api/remote-terminal/sessions",
            "websocket": "/api/remote-terminal/ws/{session_id}"
        }
    }


@router.get("/hosts")
async def list_hosts(ssh_manager: SSHManager = Depends(get_ssh_manager)):
    """List all configured SSH hosts"""
    try:
        hosts = ssh_manager.list_hosts()

        return {
            "hosts": [
                {
                    "name": h.name,
                    "ip": h.ip,
                    "port": h.port,
                    "username": h.username,
                    "description": h.description,
                    "enabled": h.enabled
                }
                for h in hosts
            ],
            "total": len(hosts),
            "enabled": len([h for h in hosts if h.enabled])
        }

    except Exception as e:
        logger.error(f"Error listing hosts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hosts/{host}")
async def get_host_info(
    host: str,
    ssh_manager: SSHManager = Depends(get_ssh_manager)
):
    """Get information about a specific host"""
    try:
        host_config = ssh_manager.get_host_config(host)
        if not host_config:
            raise HTTPException(status_code=404, detail=f"Host not found: {host}")

        return {
            "name": host_config.name,
            "ip": host_config.ip,
            "port": host_config.port,
            "username": host_config.username,
            "description": host_config.description,
            "enabled": host_config.enabled
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting host info for {host}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute")
async def execute_remote_command(
    request: RemoteCommandRequest,
    ssh_manager: SSHManager = Depends(get_ssh_manager)
):
    """Execute a command on a remote host"""
    try:
        result = await ssh_manager.execute_command(
            host=request.host,
            command=request.command,
            timeout=request.timeout,
            validate=request.validate,
            use_pty=request.use_pty
        )

        return {
            "host": result.host,
            "command": result.command,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "success": result.success,
            "execution_time": result.execution_time,
            "timestamp": result.timestamp.isoformat(),
            "security_info": result.security_info
        }

    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        logger.error(f"Error executing command on {request.host}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch")
async def execute_batch_command(
    request: BatchCommandRequest,
    ssh_manager: SSHManager = Depends(get_ssh_manager)
):
    """Execute a command on multiple hosts"""
    try:
        # Validate hosts
        for host in request.hosts:
            if not ssh_manager.get_host_config(host):
                raise HTTPException(status_code=400, detail=f"Unknown host: {host}")

        # Execute on all hosts
        if request.hosts[0] == 'all':
            results = await ssh_manager.execute_command_all_hosts(
                command=request.command,
                timeout=request.timeout,
                validate=request.validate,
                parallel=request.parallel
            )
        else:
            # Execute on specified hosts
            if request.parallel:
                tasks = [
                    ssh_manager.execute_command(
                        host=host,
                        command=request.command,
                        timeout=request.timeout,
                        validate=request.validate
                    )
                    for host in request.hosts
                ]
                results_list = await asyncio.gather(*tasks, return_exceptions=True)
                results = {
                    host: result if not isinstance(result, Exception) else {'error': str(result)}
                    for host, result in zip(request.hosts, results_list)
                }
            else:
                results = {}
                for host in request.hosts:
                    try:
                        results[host] = await ssh_manager.execute_command(
                            host=host,
                            command=request.command,
                            timeout=request.timeout,
                            validate=request.validate
                        )
                    except Exception as e:
                        results[host] = {'error': str(e)}

        # Format response
        formatted_results = {}
        for host, result in results.items():
            if isinstance(result, RemoteCommandResult):
                formatted_results[host] = {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                    "success": result.success,
                    "execution_time": result.execution_time
                }
            else:
                formatted_results[host] = result

        return {
            "command": request.command,
            "hosts": request.hosts,
            "parallel": request.parallel,
            "results": formatted_results,
            "total_hosts": len(request.hosts),
            "successful": len([r for r in formatted_results.values() if isinstance(r, dict) and r.get('success', False)])
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing batch command: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def check_all_hosts_health(ssh_manager: SSHManager = Depends(get_ssh_manager)):
    """Check health of all configured hosts"""
    try:
        health_status = await ssh_manager.health_check_all_hosts()

        return {
            "timestamp": datetime.now().isoformat(),
            "hosts": health_status,
            "total": len(health_status),
            "healthy": len([v for v in health_status.values() if v is True]),
            "unhealthy": len([v for v in health_status.values() if v is False]),
            "disabled": len([v for v in health_status.values() if v is None])
        }

    except Exception as e:
        logger.error(f"Error checking host health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_connection_pool_stats(ssh_manager: SSHManager = Depends(get_ssh_manager)):
    """Get connection pool statistics"""
    try:
        stats = await ssh_manager.get_pool_stats()

        return {
            "timestamp": datetime.now().isoformat(),
            "pools": stats,
            "total_connections": sum(s.get('total', 0) for s in stats.values()),
            "active_connections": sum(s.get('active', 0) for s in stats.values()),
            "idle_connections": sum(s.get('idle', 0) for s in stats.values())
        }

    except Exception as e:
        logger.error(f"Error getting pool stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions")
async def create_remote_session(request: RemoteSessionRequest):
    """Create a new remote terminal session"""
    try:
        session_id = str(uuid.uuid4())

        return {
            "session_id": session_id,
            "host": request.host,
            "session_type": request.session_type.value,
            "websocket_url": f"/api/remote-terminal/ws/{session_id}",
            "created_at": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error creating remote session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_remote_sessions():
    """List all active remote sessions"""
    try:
        sessions = session_manager.list_sessions()

        return {
            "sessions": sessions,
            "total": len(sessions)
        }

    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket Endpoints

@router.websocket("/ws/{session_id}")
async def remote_terminal_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for interactive remote terminal sessions

    Provides real-time SSH terminal access to remote hosts
    """
    await websocket.accept()

    # Get SSH manager
    ssh_manager = await get_ssh_manager()

    try:
        # Receive initial configuration
        init_data = await websocket.receive_text()
        init_message = json.loads(init_data)

        host = init_message.get('host')
        if not host:
            await websocket.send_text(json.dumps({
                'type': 'error',
                'content': 'Host not specified',
                'timestamp': time.time()
            }))
            await websocket.close()
            return

        # Validate host
        host_config = ssh_manager.get_host_config(host)
        if not host_config:
            await websocket.send_text(json.dumps({
                'type': 'error',
                'content': f'Unknown host: {host}',
                'timestamp': time.time()
            }))
            await websocket.close()
            return

        # Create session
        session_manager.create_session(
            session_id=session_id,
            host=host,
            session_type=RemoteSessionType.INTERACTIVE,
            websocket=websocket
        )

        # Send connection established message
        await websocket.send_text(json.dumps({
            'type': 'connected',
            'host': host,
            'session_id': session_id,
            'timestamp': time.time()
        }))

        logger.info(f"Remote terminal WebSocket established for {session_id} to {host}")

        # Handle WebSocket communication
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)

                message_type = message.get('type')

                if message_type == 'input':
                    # Execute command on remote host
                    command = message.get('text', '')

                    result = await ssh_manager.execute_command(
                        host=host,
                        command=command,
                        timeout=30,
                        validate=True,
                        use_pty=True
                    )

                    # Send output back
                    await websocket.send_text(json.dumps({
                        'type': 'output',
                        'content': result.stdout,
                        'exit_code': result.exit_code,
                        'timestamp': time.time()
                    }))

                    # Send stderr if present
                    if result.stderr:
                        await websocket.send_text(json.dumps({
                            'type': 'error_output',
                            'content': result.stderr,
                            'timestamp': time.time()
                        }))

                    session_manager.update_activity(session_id)

                elif message_type == 'ping':
                    await websocket.send_text(json.dumps({
                        'type': 'pong',
                        'timestamp': time.time()
                    }))

                else:
                    logger.warning(f"Unknown message type: {message_type}")

            except WebSocketDisconnect:
                logger.info(f"Remote terminal WebSocket disconnected for {session_id}")
                break
            except Exception as e:
                logger.error(f"Error in remote terminal WebSocket: {e}")
                await websocket.send_text(json.dumps({
                    'type': 'error',
                    'content': str(e),
                    'timestamp': time.time()
                }))

    except Exception as e:
        logger.error(f"Error establishing remote terminal WebSocket: {e}")
    finally:
        # Clean up session
        session_manager.remove_session(session_id)
