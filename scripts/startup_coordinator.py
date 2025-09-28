#!/usr/bin/env python3
"""
AutoBot Startup Coordinator

Manages startup sequence with proper state reporting and dependencies.
Each component reports its state before dependent components can start.
"""
import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set
import requests
import psutil

# Import centralized Redis client
sys.path.append(str(Path(__file__).parent.parent))
from src.utils.redis_client import get_redis_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/startup_coordinator.log')
    ]
)
logger = logging.getLogger(__name__)

class ComponentState(Enum):
    """States a component can be in during startup"""
    PENDING = "pending"
    STARTING = "starting" 
    READY = "ready"
    FAILED = "failed"
    STOPPED = "stopped"

class HealthStatus(Enum):
    """Health check results"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

@dataclass
class ComponentInfo:
    """Information about a startup component"""
    name: str
    state: ComponentState = ComponentState.PENDING
    pid: Optional[int] = None
    port: Optional[int] = None
    health_url: Optional[str] = None
    dependencies: List[str] = None
    start_command: Optional[str] = None
    health_status: HealthStatus = HealthStatus.UNKNOWN
    start_time: Optional[float] = None
    ready_time: Optional[float] = None
    error_message: Optional[str] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []

class StartupCoordinator:
    """Coordinates the startup of AutoBot components with proper dependency management"""
    
    def __init__(self):
        self.components: Dict[str, ComponentInfo] = {}
        self.processes: Dict[str, subprocess.Popen] = {}
        self.startup_state_file = Path("data/startup_state.json")
        self.max_startup_time = 300  # 5 minutes max for any component
        self.health_check_timeout = 5  # 5 seconds for health checks
        
        # Define component startup order and dependencies
        self._define_components()
        
    def _define_components(self):
        """Define all components and their dependencies"""
        
        # Core infrastructure (no dependencies)
        self.components['redis'] = ComponentInfo(
            name='redis',
            port=6379,
            health_url='redis://127.0.0.1:6379',
            dependencies=[]
        )
        
        self.components['logging'] = ComponentInfo(
            name='logging',
            dependencies=[]
        )
        
        # Configuration (no dependencies - just loads config files)
        self.components['config'] = ComponentInfo(
            name='config',
            dependencies=[]
        )
        
        # Backend API (depends on redis and config)
        self.components['backend'] = ComponentInfo(
            name='backend',
            port=8001,
            health_url='http://127.0.0.3:8001/api/system/health',
            dependencies=['redis', 'config'],
            start_command='uvicorn main:app --host 0.0.0.0 --port 8001 --log-level info'
        )
        
        # Frontend (depends on backend being ready)
        self.components['frontend'] = ComponentInfo(
            name='frontend',
            port=5173,
            health_url='http://127.0.0.1:5173',
            dependencies=['backend'],
            start_command='npm run dev'
        )
        
        # Optional components
        self.components['ai_stack'] = ComponentInfo(
            name='ai_stack',
            dependencies=['redis', 'config']
        )
        
    def save_state(self):
        """Save current startup state to file"""
        try:
            state_data = {
                name: asdict(comp) for name, comp in self.components.items()
            }
            self.startup_state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.startup_state_file, 'w') as f:
                json.dump(state_data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save startup state: {e}")
    
    def load_state(self):
        """Load startup state from file if it exists"""
        try:
            if self.startup_state_file.exists():
                with open(self.startup_state_file, 'r') as f:
                    state_data = json.load(f)
                    for name, data in state_data.items():
                        if name in self.components:
                            # Restore component state
                            comp = self.components[name]
                            comp.state = ComponentState(data.get('state', 'pending'))
                            comp.pid = data.get('pid')
                            comp.health_status = HealthStatus(data.get('health_status', 'unknown'))
                logger.info("Loaded previous startup state")
        except Exception as e:
            logger.warning(f"Could not load previous startup state: {e}")
    
    async def check_health(self, component: ComponentInfo) -> bool:
        """Check if a component is healthy"""
        if not component.health_url:
            # If no health URL, just check if process is running
            return component.pid and psutil.pid_exists(component.pid)
        
        try:
            if component.health_url.startswith('http'):
                # HTTP health check
                response = requests.get(
                    component.health_url, 
                    timeout=self.health_check_timeout
                )
                healthy = response.status_code == 200
                component.health_status = HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY
                return healthy
            elif component.health_url.startswith('redis'):
                # Redis health check using centralized client
                async def check_redis():
                    try:
                        redis_client = await get_redis_client('main')
                        if redis_client:
                            await redis_client.ping()
                            return True
                        return False
                    except Exception:
                        return False
                
                # Run async check
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                healthy = loop.run_until_complete(check_redis())
                loop.close()
                component.health_status = HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY
                return healthy
        except Exception as e:
            logger.debug(f"Health check failed for {component.name}: {e}")
            component.health_status = HealthStatus.UNHEALTHY
            return False
        
        return False
    
    def check_dependencies_ready(self, component: ComponentInfo) -> bool:
        """Check if all dependencies of a component are ready"""
        for dep_name in component.dependencies:
            if dep_name not in self.components:
                logger.error(f"Unknown dependency '{dep_name}' for component '{component.name}'")
                return False
            
            dep = self.components[dep_name]
            if dep.state != ComponentState.READY:
                logger.debug(f"Dependency '{dep_name}' not ready for '{component.name}' (state: {dep.state})")
                return False
        
        return True
    
    async def start_component(self, component: ComponentInfo) -> bool:
        """Start a single component"""
        logger.info(f"🚀 Starting component: {component.name}")
        component.state = ComponentState.STARTING
        component.start_time = time.time()
        self.save_state()
        
        try:
            if component.start_command:
                # Start external process
                logger.info(f"Executing: {component.start_command}")
                
                # Set up environment and working directory
                env = os.environ.copy()
                cwd = None
                
                if component.name == 'backend':
                    cwd = 'backend'  # Run from backend directory
                    env['PYTHONPATH'] = os.path.abspath('.') + ':' + env.get('PYTHONPATH', '')
                elif component.name == 'frontend':
                    cwd = 'autobot-vue'
                
                # Start process
                process = subprocess.Popen(
                    component.start_command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    cwd=cwd
                )
                
                self.processes[component.name] = process
                component.pid = process.pid
                
                logger.info(f"Started {component.name} with PID {component.pid}")
                
                # Wait for component to become healthy
                max_wait = self.max_startup_time
                check_interval = 2  # Check every 2 seconds
                
                for attempt in range(0, max_wait, check_interval):
                    # Check if process died
                    if process.poll() is not None:
                        stdout, stderr = process.communicate()
                        error_msg = f"Process died: {stderr.decode()}"
                        logger.error(f"❌ {component.name} failed: {error_msg}")
                        component.error_message = error_msg
                        component.state = ComponentState.FAILED
                        self.save_state()
                        return False
                    
                    # Check health
                    if await self.check_health(component):
                        component.state = ComponentState.READY
                        component.ready_time = time.time()
                        startup_duration = component.ready_time - component.start_time
                        logger.info(f"✅ {component.name} is ready (took {startup_duration:.1f}s)")
                        self.save_state()
                        return True
                    
                    # Progress feedback
                    if attempt % 10 == 0 and attempt > 0:
                        logger.info(f"⏳ Waiting for {component.name} to be ready... ({attempt}s elapsed)")
                    
                    await asyncio.sleep(check_interval)
                
                # Timeout reached
                logger.error(f"❌ {component.name} did not become ready within {max_wait}s")
                component.error_message = f"Startup timeout ({max_wait}s)"
                component.state = ComponentState.FAILED
                self.save_state()
                return False
            else:
                # Built-in component (no external process)
                logger.info(f"✅ {component.name} is ready (built-in)")
                component.state = ComponentState.READY
                component.ready_time = time.time()
                self.save_state()
                return True
                
        except Exception as e:
            error_msg = f"Failed to start: {str(e)}"
            logger.error(f"❌ {component.name} failed: {error_msg}")
            component.error_message = error_msg
            component.state = ComponentState.FAILED
            self.save_state()
            return False
    
    async def startup_sequence(self, target_components: Optional[Set[str]] = None) -> bool:
        """Execute the complete startup sequence"""
        if target_components is None:
            target_components = set(self.components.keys())
        
        logger.info("🎯 Starting AutoBot with state-based startup coordination")
        logger.info(f"Target components: {', '.join(sorted(target_components))}")
        
        # Load any previous state
        self.load_state()
        
        started_components = set()
        failed_components = set()
        
        while True:
            # Find components that are ready to start
            ready_to_start = []
            
            for name, component in self.components.items():
                if (name in target_components and 
                    name not in started_components and 
                    name not in failed_components and
                    component.state == ComponentState.PENDING and
                    self.check_dependencies_ready(component)):
                    ready_to_start.append(component)
            
            if not ready_to_start:
                # Check if we're done
                remaining = target_components - started_components - failed_components
                if not remaining:
                    break
                
                # Check if we're stuck (all remaining components have failed dependencies)
                all_stuck = True
                for name in remaining:
                    component = self.components[name]
                    if self.check_dependencies_ready(component):
                        all_stuck = False
                        break
                
                if all_stuck:
                    logger.error(f"❌ Startup stuck! Remaining components have failed dependencies: {remaining}")
                    return False
                
                # Wait a bit and try again
                logger.info("⏳ Waiting for dependencies...")
                await asyncio.sleep(2)
                continue
            
            # Start components in parallel if they don't depend on each other
            tasks = []
            for component in ready_to_start:
                task = asyncio.create_task(self.start_component(component))
                tasks.append((component.name, task))
            
            # Wait for all to complete
            for name, task in tasks:
                success = await task
                if success:
                    started_components.add(name)
                    logger.info(f"✅ Component '{name}' started successfully")
                else:
                    failed_components.add(name)
                    logger.error(f"❌ Component '{name}' failed to start")
        
        # Final status
        total_target = len(target_components)
        successful = len(started_components)
        failed = len(failed_components)
        
        logger.info(f"🎯 Startup completed: {successful}/{total_target} components started")
        
        if failed_components:
            logger.error(f"❌ Failed components: {', '.join(failed_components)}")
            return False
        
        logger.info("🎉 All components started successfully!")
        return True
    
    def stop_all(self):
        """Stop all running processes"""
        logger.info("🛑 Stopping all components...")
        
        for name, process in self.processes.items():
            try:
                if process.poll() is None:  # Process still running
                    logger.info(f"Stopping {name} (PID: {process.pid})")
                    process.terminate()
                    
                    # Give it 5 seconds to terminate gracefully
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logger.warning(f"Force killing {name}")
                        process.kill()
                        process.wait()
                    
                    logger.info(f"✅ {name} stopped")
                    self.components[name].state = ComponentState.STOPPED
            except Exception as e:
                logger.error(f"Error stopping {name}: {e}")
        
        self.save_state()
        
        # Clean up state file
        if self.startup_state_file.exists():
            self.startup_state_file.unlink()

async def main():
    """Main startup coordinator entry point"""
    coordinator = StartupCoordinator()
    
    # Set up signal handling
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        coordinator.stop_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='AutoBot Startup Coordinator')
    parser.add_argument('--components', nargs='*', 
                       help='Specific components to start (default: all)')
    parser.add_argument('--status', action='store_true',
                       help='Show current component status')
    parser.add_argument('--stop', action='store_true',
                       help='Stop all components')
    
    args = parser.parse_args()
    
    if args.status:
        coordinator.load_state()
        print("\n🔍 Component Status:")
        for name, comp in coordinator.components.items():
            status_icon = {
                ComponentState.PENDING: "⏳",
                ComponentState.STARTING: "🚀", 
                ComponentState.READY: "✅",
                ComponentState.FAILED: "❌",
                ComponentState.STOPPED: "🛑"
            }.get(comp.state, "❓")
            
            print(f"  {status_icon} {name:<12} {comp.state.value:<8} "
                  f"PID: {comp.pid or 'N/A':<6} "
                  f"Health: {comp.health_status.value}")
        return
    
    if args.stop:
        coordinator.stop_all()
        return
    
    # Start components
    target_components = None
    if args.components:
        target_components = set(args.components)
        # Validate component names
        invalid = target_components - set(coordinator.components.keys())
        if invalid:
            logger.error(f"Invalid component names: {invalid}")
            logger.info(f"Available: {', '.join(coordinator.components.keys())}")
            return
    
    success = await coordinator.startup_sequence(target_components)
    if not success:
        logger.error("❌ Startup failed!")
        sys.exit(1)
    
    logger.info("✅ AutoBot is ready!")
    
    # Keep running until interrupted
    try:
        while True:
            await asyncio.sleep(10)
            
            # Periodic health checks
            for name, component in coordinator.components.items():
                if component.state == ComponentState.READY:
                    healthy = await coordinator.check_health(component)
                    if not healthy:
                        logger.warning(f"⚠️ Component {name} health check failed")
    except KeyboardInterrupt:
        pass
    finally:
        coordinator.stop_all()

if __name__ == "__main__":
    asyncio.run(main())