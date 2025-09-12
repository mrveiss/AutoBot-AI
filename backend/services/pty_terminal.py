"""
Real PTY Terminal Implementation
Provides actual shell interaction with the host system
"""

import asyncio
import json
import logging
import os
import pty
import select
import signal
import subprocess
import threading
import time
from typing import Dict, Optional, Callable

logger = logging.getLogger(__name__)


class PTYTerminal:
    """Real PTY terminal that executes commands on the host system"""
    
    def __init__(self, session_id: str, initial_cwd: str = None):
        self.session_id = session_id
        self.initial_cwd = initial_cwd or os.getcwd()
        self.master_fd = None
        self.slave_fd = None
        self.process = None
        self.read_thread = None
        self.is_active = False
        self.output_callback = None
        self.close_callback = None
        
    async def start(self, output_callback: Callable, close_callback: Callable = None):
        """Start the PTY terminal"""
        self.output_callback = output_callback
        self.close_callback = close_callback
        
        try:
            # Create PTY
            self.master_fd, self.slave_fd = pty.openpty()
            
            # Set up shell environment
            env = os.environ.copy()
            env['TERM'] = 'xterm-256color'
            env['PS1'] = r'\u@\h:\w\$ '  # Standard bash prompt
            
            # Start bash process
            logger.info(f"Starting bash process for session {self.session_id}")
            self.process = subprocess.Popen(
                ['/bin/bash', '--login'],
                stdin=self.slave_fd,
                stdout=self.slave_fd,
                stderr=self.slave_fd,
                env=env,
                cwd=self.initial_cwd,
                preexec_fn=os.setsid,  # Create new session
                close_fds=True
            )
            logger.info(f"Bash process started with PID {self.process.pid}")
            
            # Close slave fd in parent process
            os.close(self.slave_fd)
            self.slave_fd = None
            
            # Set non-blocking mode
            os.set_blocking(self.master_fd, False)
            
            # Start reading thread
            self.is_active = True
            self.read_thread = threading.Thread(target=self._read_output, daemon=True)
            self.read_thread.start()
            
            # Send initial commands to set up environment
            await self._send_initial_setup()
            
            logger.info(f"PTY terminal started for session {self.session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start PTY terminal: {e}")
            await self.cleanup()
            return False
    
    async def _send_initial_setup(self):
        """Send initial setup commands"""
        try:
            # Change to initial directory
            if self.initial_cwd != os.getcwd():
                self.write_input(f"cd '{self.initial_cwd}'\n")
            
            # Set terminal size
            self.resize(24, 80)
            
        except Exception as e:
            logger.error(f"Error in initial setup: {e}")
    
    def _read_output(self):
        """Read output from PTY in background thread"""
        logger.info(f"Starting PTY read loop for session {self.session_id}")
        while self.is_active and self.master_fd:
            try:
                # Use select with timeout to check for data
                ready, _, _ = select.select([self.master_fd], [], [], 0.1)
                
                if ready:
                    try:
                        data = os.read(self.master_fd, 4096)
                        if data:
                            # Decode and send to callback
                            output = data.decode('utf-8', errors='replace')
                            if self.output_callback:
                                try:
                                    # Get the current event loop
                                    loop = asyncio.get_event_loop()
                                    asyncio.run_coroutine_threadsafe(
                                        self.output_callback(output),
                                        loop
                                    )
                                except Exception as e:
                                    logger.error(f"Error in output callback: {e}")
                        else:
                            # EOF - process terminated
                            break
                    except OSError:
                        # PTY closed
                        break
                        
            except Exception as e:
                logger.error(f"Error reading PTY output: {e}")
                break
        
        # Notify close if callback exists
        if self.close_callback:
            try:
                asyncio.run_coroutine_threadsafe(
                    self.close_callback(),
                    asyncio.get_event_loop()
                )
            except Exception as e:
                logger.error(f"Error in close callback: {e}")
    
    def write_input(self, text: str):
        """Write input to the PTY"""
        if not self.is_active or not self.master_fd:
            logger.warning(f"Cannot write to PTY - not active or no master_fd")
            return False
        
        try:
            # Convert to bytes and write
            data = text.encode('utf-8')
            logger.info(f"Writing to PTY: {repr(text)}")
            os.write(self.master_fd, data)
            return True
        except Exception as e:
            logger.error(f"Error writing to PTY: {e}")
            return False
    
    def resize(self, rows: int, cols: int):
        """Resize the PTY terminal"""
        if not self.is_active or not self.master_fd:
            return False
        
        try:
            import struct, fcntl, termios
            
            # Set window size
            winsize = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            
            # Send SIGWINCH to notify process
            if self.process and self.process.pid:
                os.killpg(os.getpgid(self.process.pid), signal.SIGWINCH)
            
            return True
        except Exception as e:
            logger.error(f"Error resizing PTY: {e}")
            return False
    
    def send_signal(self, sig: int):
        """Send signal to the terminal process"""
        if not self.process or not self.process.pid:
            return False
        
        try:
            # Send signal to process group
            os.killpg(os.getpgid(self.process.pid), sig)
            return True
        except Exception as e:
            logger.error(f"Error sending signal {sig}: {e}")
            return False
    
    async def cleanup(self):
        """Clean up PTY resources"""
        self.is_active = False
        
        # Close file descriptors
        if self.master_fd:
            try:
                os.close(self.master_fd)
            except:
                pass
            self.master_fd = None
            
        if self.slave_fd:
            try:
                os.close(self.slave_fd)
            except:
                pass
            self.slave_fd = None
        
        # Terminate process
        if self.process:
            try:
                # Try graceful termination first
                self.process.terminate()
                # Give process a moment to terminate gracefully
                import time
                time.sleep(0.1)
                if self.process.poll() is None:
                    # Process didn't terminate, force kill
                    self.process.kill()
                    # Wait without timeout for kill to complete
                    self.process.wait()
            except Exception as e:
                logger.error(f"Error terminating process: {e}")
            finally:
                self.process = None
        
        # Signal read thread to finish naturally
        if self.read_thread and self.read_thread.is_alive():
            # Thread will exit when is_active=False
            pass
        
        logger.info(f"PTY terminal cleaned up for session {self.session_id}")
    
    def is_alive(self):
        """Check if the PTY terminal is alive"""
        return (self.is_active and 
                self.process and 
                self.process.poll() is None and 
                self.master_fd is not None)


class PTYManager:
    """Manager for multiple PTY terminal sessions"""
    
    def __init__(self):
        self.sessions: Dict[str, PTYTerminal] = {}
    
    async def create_session(self, session_id: str, initial_cwd: str = None) -> PTYTerminal:
        """Create a new PTY terminal session"""
        if session_id in self.sessions:
            await self.close_session(session_id)
        
        terminal = PTYTerminal(session_id, initial_cwd)
        self.sessions[session_id] = terminal
        return terminal
    
    def get_session(self, session_id: str) -> Optional[PTYTerminal]:
        """Get existing PTY session"""
        return self.sessions.get(session_id)
    
    async def close_session(self, session_id: str):
        """Close and clean up a PTY session"""
        if session_id in self.sessions:
            terminal = self.sessions[session_id]
            await terminal.cleanup()
            del self.sessions[session_id]
    
    async def close_all_sessions(self):
        """Close all PTY sessions"""
        for session_id in list(self.sessions.keys()):
            await self.close_session(session_id)


# Global PTY manager instance
pty_manager = PTYManager()