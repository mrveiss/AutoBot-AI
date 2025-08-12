"""
Base Terminal WebSocket Handler
Provides common terminal functionality for websocket handlers
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any

logger = logging.getLogger(__name__)


class BaseTerminalWebSocket(ABC):
    """Base class for terminal WebSocket handlers"""
    
    def __init__(self):
        self.websocket = None
        self.pty_process = None
        self.active_sessions = {}
        
    @abstractmethod
    async def send_input(self, command: str):
        """Send input to the PTY process"""
        pass
        
    @abstractmethod  
    async def send_message(self, message: dict):
        """Send message to WebSocket client"""
        pass
        
    @property
    @abstractmethod
    def terminal_type(self) -> str:
        """Get terminal type for logging"""
        pass
    
    async def execute_command(self, command: str) -> bool:
        """Send command to PTY shell with common handling"""
        if not command.strip():
            return False

        logger.info(f"{self.terminal_type} executing: {command}")

        try:
            # Send command to PTY shell
            await self.send_input(command + "\n")
            return True

        except Exception as e:
            logger.error(f"{self.terminal_type} command error: {e}")
            await self.send_message(
                {"type": "error", "message": f"{self.terminal_type} error: {str(e)}"}
            )
            return False
            
    async def validate_command(self, command: str) -> bool:
        """Validate command before execution (override in subclasses)"""
        return True
        
    async def audit_command(self, command: str, result: bool):
        """Audit command execution (override in subclasses)"""
        pass