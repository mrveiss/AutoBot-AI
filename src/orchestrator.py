import asyncio
import json
import logging
import time
import uuid
from typing import Dict, Any, List, Optional, Callable
import yaml
import os
from datetime import datetime

# LLM and knowledge base imports
from src.llm_interface import LLMInterface
from src.knowledge_base import KnowledgeBase
from src.worker_node import WorkerNode
from src.event_manager import event_manager
from src.chat_history_manager import ChatHistoryManager

# Import LangChain agent orchestrator
from src.langchain_agent_orchestrator import LangChainAgentOrchestrator

# Import system integrations
from src.system_integration import SystemIntegration
from src.diagnostics import Diagnostics
from src.security_layer import SecurityLayer

# Memory and transport backends
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logging.warning("Redis not available. Using local transport only.")

class TaskOrchestrator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_interface = None
        self.knowledge_base = None
        self.worker_node = None
        self.langchain_orchestrator = None
        self.system_integration = None
        self.diagnostics = None
        self.security_layer = None
        self.chat_history_manager = None
        
        # Task management
        self.active_tasks = {}
        self.task_queue = asyncio.Queue()
        self.worker_pool = []
        self.task_results = {}
        
        # State management
        self.is_running = False
        self.transport_type = config.get('transport_type', 'local')
        
        # Redis connection (if configured)
        if self.transport_type == 'redis' and REDIS_AVAILABLE:
            redis_config = config.get('memory', {}).get('redis', {})
            self.redis_client = redis.Redis(
                host=redis_config.get('host', 'localhost'),
                port=redis_config.get('port', 6379),
                password=redis_config.get('password'),
                db=redis_config.get('db', 0),
                decode_responses=True
            )
        else:
            self.redis_client = None
            
        # Initialize logging
        self.logger = logging.getLogger(__name__)
        
    async def initialize(self):
        """Initialize all components of the orchestrator"""
        try:
            self.logger.info("Initializing Task Orchestrator...")
            
            # Initialize LLM interface
            self.llm_interface = LLMInterface()
            await self.llm_interface.check_ollama_connection()
            
            # Initialize knowledge base
            self.knowledge_base = KnowledgeBase()
            await self.knowledge_base.ainit(self.config.get('llm_config', {}))
            
            # Initialize worker node
            self.worker_node = WorkerNode(self.config)
            await self.worker_node.initialize()
            
            # Initialize LangChain orchestrator
            self.langchain_orchestrator = LangChainAgentOrchestrator(
                self.config, self.worker_node, self.knowledge_base
            )
            
            # Initialize system integration
            self.system_integration = SystemIntegration(self.config)
            await self.system_integration.initialize()
            
            # Initialize diagnostics
            self.diagnostics = Diagnostics(self.config)
            await self.diagnostics.initialize()
            
            # Initialize security layer
            self.security_layer = SecurityLayer(self.config)
            await self.security_layer.initialize()
            
            # Initialize chat history manager
            self.chat_history_manager = ChatHistoryManager(self.config)
            
            # Set up event subscriptions
            await self._setup_event_subscriptions()
            
            # Initialize worker pool
            await self._initialize_worker_pool()
            
            self.is_running = True
            self.logger.info("Task Orchestrator initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Task Orchestrator: {e}")
            raise
    
    async def _setup_event_subscriptions(self):
        """Set up event subscriptions for orchestrator"""
        await event_manager.subscribe("task_completed", self._handle_task_completion)
        await event_manager.subscribe("task_failed", self._handle_task_failure)
        await event_manager.subscribe("user_input", self._handle_user_input)
        await event_manager.subscribe("system_alert", self._handle_system_alert)
        
    async def _initialize_worker_pool(self):
        """Initialize the worker pool"""
        worker_count = self.config.get('worker_pool_size', 3)
        for i in range(worker_count):
            worker_task = asyncio.create_task(self._worker_loop(f"worker-{i}"))
            self.worker_pool.append(worker_task)
        self.logger.info(f"Initialized worker pool with {worker_count} workers")
    
    async def _worker_loop(self, worker_id: str):
        """Main worker loop for processing tasks"""
        self.logger.info(f"Worker {worker_id} started")
        
        while self.is_running:
            try:
                # Get task from queue with timeout
                task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                
                self.logger.info(f"Worker {worker_id} processing task {task.get('task_id')}")
                
                # Process the task
                result = await self._process_task(task, worker_id)
                
                # Store result
                task_id = task.get('task_id')
                if task_id:
                    self.task_results[task_id] = result
                
                # Mark task as done
                self.task_queue.task_done()
                
                # Publish completion event
                await event_manager.publish("task_completed", {
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "result": result
                })
                
            except asyncio.TimeoutError:
                # No tasks available, continue
                continue
            except Exception as e:
                self.logger.error(f"Worker {worker_id} error: {e}")
                await event_manager.publish("task_failed", {
                    "worker_id": worker_id,
                    "error": str(e)
                })
    
    async def _process_task(self, task: Dict[str, Any], worker_id: str) -> Dict[str, Any]:
        """Process a single task"""
        task_type = task.get('type')
        task_id = task.get('task_id')
        
        try:
            # Log task start
            await event_manager.publish("log_message", {
                "level": "INFO",
                "message": f"Processing task {task_id} of type {task_type}"
            })
            
            # Route task based on type
            if task_type == 'chat_completion':
                result = await self._handle_chat_completion(task)
            elif task_type == 'system_command':
                result = await self._handle_system_command(task)
            elif task_type == 'knowledge_query':
                result = await self._handle_knowledge_query(task)
            elif task_type == 'file_operation':
                result = await self._handle_file_operation(task)
            elif task_type == 'langchain_goal':
                result = await self._handle_langchain_goal(task)
            else:
                # Delegate to worker node
                result = await self.worker_node.execute_task(task)
            
            return {
                "status": "success",
                "task_id": task_id,
                "worker_id": worker_id,
                "result": result,
                "timestamp": time.time()
            }
            
        except Exception as e:
            self.logger.error(f"Task {task_id} failed: {e}")
            return {
                "status": "error",
                "task_id": task_id,
                "worker_id": worker_id,
                "error": str(e),
                "timestamp": time.time()
            }
    
    async def _handle_chat_completion(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Handle chat completion tasks"""
        messages = task.get('messages', [])
        llm_type = task.get('llm_type', 'orchestrator')
        
        response = await self.llm_interface.chat_completion(
            messages=messages,
            llm_type=llm_type,
            **task.get('params', {})
        )
        
        return {"response": response}
    
    async def _handle_system_command(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Handle system command tasks"""
        command = task.get('command')
        if not command:
            raise ValueError("No command specified")
        
        result = await self.system_integration.execute_command(
            command,
            task.get('working_dir'),
            task.get('timeout', 30)
        )
        
        return result
    
    async def _handle_knowledge_query(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Handle knowledge base queries"""
        query = task.get('query')
        if not query:
            raise ValueError("No query specified")
        
        results = await self.knowledge_base.search(
            query,
            n_results=task.get('n_results', 5)
        )
        
        return {"results": results}
    
    async def _handle_file_operation(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Handle file operations"""
        operation = task.get('operation')
        file_path = task.get('file_path')
        
        if operation == 'add_to_kb':
            file_type = task.get('file_type', 'txt')
            result = await self.knowledge_base.add_file(file_path, file_type)
        else:
            raise ValueError(f"Unknown file operation: {operation}")
        
        return result
    
    async def _handle_langchain_goal(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Handle LangChain agent goals"""
        if not self.langchain_orchestrator or not self.langchain_orchestrator.available:
            raise ValueError("LangChain orchestrator not available")
        
        goal = task.get('goal')
        conversation_history = task.get('conversation_history', [])
        
        result = await self.langchain_orchestrator.execute_goal(
            goal,
            conversation_history
        )
        
        return result
    
    async def _handle_task_completion(self, event_data: Dict[str, Any]):
        """Handle task completion events"""
        task_id = event_data.get('task_id')
        if task_id in self.active_tasks:
            del self.active_tasks[task_id]
        
        # Update metrics
        await self.diagnostics.update_task_metrics(event_data)
    
    async def _handle_task_failure(self, event_data: Dict[str, Any]):
        """Handle task failure events"""
        task_id = event_data.get('task_id')
        if task_id in self.active_tasks:
            del self.active_tasks[task_id]
        
        # Log failure
        self.logger.error(f"Task failed: {event_data}")
        
        # Update metrics
        await self.diagnostics.update_failure_metrics(event_data)
    
    async def _handle_user_input(self, event_data: Dict[str, Any]):
        """Handle user input events"""
        user_input = event_data.get('input')
        session_id = event_data.get('session_id')
        
        # Create task for user input processing
        task = {
            "task_id": str(uuid.uuid4()),
            "type": "user_input",
            "input": user_input,
            "session_id": session_id,
            "timestamp": time.time()
        }
        
        await self.submit_task(task)
    
    async def _handle_system_alert(self, event_data: Dict[str, Any]):
        """Handle system alerts"""
        alert_type = event_data.get('type')
        severity = event_data.get('severity', 'info')
        
        self.logger.info(f"System alert [{severity}]: {alert_type}")
        
        # Create response task if needed
        if severity in ['warning', 'error', 'critical']:
            task = {
                "task_id": str(uuid.uuid4()),
                "type": "system_response",
                "alert_data": event_data,
                "timestamp": time.time()
            }
            await self.submit_task(task)
    
    async def submit_task(self, task: Dict[str, Any]) -> str:
        """Submit a task for processing"""
        task_id = task.get('task_id') or str(uuid.uuid4())
        task['task_id'] = task_id
        
        # Add to active tasks
        self.active_tasks[task_id] = task
        
        # Add to queue
        await self.task_queue.put(task)
        
        self.logger.info(f"Task {task_id} submitted")
        return task_id
    
    async def get_task_result(self, task_id: str, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """Get the result of a completed task"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if task_id in self.task_results:
                return self.task_results.pop(task_id)
            
            await asyncio.sleep(0.1)
        
        return None
    
    async def execute_goal(self, goal: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a high-level goal"""
        self.logger.info(f"Executing goal: {goal}")
        
        # Choose orchestration strategy
        if self.langchain_orchestrator and self.langchain_orchestrator.available:
            # Use LangChain agent
            task = {
                "task_id": str(uuid.uuid4()),
                "type": "langchain_goal",
                "goal": goal,
                "conversation_history": context.get('conversation_history', []) if context else [],
                "timestamp": time.time()
            }
        else:
            # Use traditional orchestration
            task = {
                "task_id": str(uuid.uuid4()),
                "type": "traditional_goal",
                "goal": goal,
                "context": context or {},
                "timestamp": time.time()
            }
        
        # Submit and wait for result
        task_id = await self.submit_task(task)
        result = await self.get_task_result(task_id, timeout=60.0)
        
        if result is None:
            return {
                "status": "timeout",
                "message": "Goal execution timed out"
            }
        
        return result
    
    async def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status"""
        return {
            "is_running": self.is_running,
            "active_tasks": len(self.active_tasks),
            "queue_size": self.task_queue.qsize(),
            "worker_count": len(self.worker_pool),
            "transport_type": self.transport_type,
            "components": {
                "llm_interface": self.llm_interface is not None,
                "knowledge_base": self.knowledge_base is not None,
                "worker_node": self.worker_node is not None,
                "langchain_orchestrator": self.langchain_orchestrator is not None and self.langchain_orchestrator.available,
                "system_integration": self.system_integration is not None,
                "diagnostics": self.diagnostics is not None,
                "security_layer": self.security_layer is not None,
                "redis_client": self.redis_client is not None
            }
        }
    
    async def shutdown(self):
        """Shutdown the orchestrator"""
        self.logger.info("Shutting down Task Orchestrator...")
        
        self.is_running = False
        
        # Wait for tasks to complete
        await self.task_queue.join()
        
        # Cancel worker tasks
        for worker_task in self.worker_pool:
            worker_task.cancel()
        
        # Wait for workers to finish
        await asyncio.gather(*self.worker_pool, return_exceptions=True)
        
        # Close Redis connection
        if self.redis_client:
            await self.redis_client.close()
        
        # Shutdown components
        if self.system_integration:
            await self.system_integration.shutdown()
        
        if self.diagnostics:
            await self.diagnostics.shutdown()
        
        if self.security_layer:
            await self.security_layer.shutdown()
        
        self.logger.info("Task Orchestrator shutdown complete")

# Factory function for creating orchestrator
async def create_orchestrator(config_path: str = "config/config.yaml") -> TaskOrchestrator:
    """Create and initialize a task orchestrator"""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    orchestrator = TaskOrchestrator(config)
    await orchestrator.initialize()
    
    return orchestrator
