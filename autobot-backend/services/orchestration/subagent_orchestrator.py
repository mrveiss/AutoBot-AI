"""Autonomous subagent spawning for parallel workstreams."""
import asyncio
import logging
from typing import Any, Callable, List, Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class SubagentTask:
    """Definition of a task for subagent execution."""
    task_id: str
    func: Callable
    args: tuple = ()
    kwargs: dict = None
    timeout: int = 300
    
    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}

class SubagentOrchestrator:
    """Orchestrates autonomous subagent spawning for parallel workstreams."""
    
    def __init__(self, max_parallel: int = 10):
        self.max_parallel = max_parallel
        self.active_subagents: Dict[str, asyncio.Task] = {}
    
    async def spawn_parallel_tasks(self, tasks: List[SubagentTask]) -> Dict[str, Any]:
<<<<<<< HEAD
        """
        Spawn multiple subagents for parallel execution.
        
        Args:
            tasks: List of SubagentTask objects
            
        Returns:
            Dictionary with results keyed by task_id
        """
        results = {}
        
        # Create tasks with timeouts
        pending = []
=======
        """Spawn multiple subagents for parallel execution."""
        results = {}
        pending = []
        
>>>>>>> origin/issue-4348
        for task in tasks[:self.max_parallel]:
            try:
                coro = asyncio.wait_for(
                    self._execute_task(task),
                    timeout=task.timeout
                )
                pending.append((task.task_id, coro))
            except Exception as e:
                logger.error(f"Error creating task {task.task_id}: {e}")
                results[task.task_id] = {"error": str(e)}
        
<<<<<<< HEAD
        # Execute all pending tasks concurrently
        if pending:
            task_ids, coros = zip(*pending) if pending else ([], [])
            task_results = await asyncio.gather(*coros, return_exceptions=True)
            
=======
        if pending:
            task_ids, coros = zip(*pending)
            task_results = await asyncio.gather(*coros, return_exceptions=True)
>>>>>>> origin/issue-4348
            for task_id, result in zip(task_ids, task_results):
                results[task_id] = result
        
        return results
    
    async def _execute_task(self, task: SubagentTask) -> Any:
        """Execute a single subagent task."""
        try:
            if asyncio.iscoroutinefunction(task.func):
                return await task.func(*task.args, **task.kwargs)
            else:
                return task.func(*task.args, **task.kwargs)
        except Exception as e:
            logger.error(f"Task {task.task_id} failed: {e}")
            raise

_orchestrator_instance: Optional[SubagentOrchestrator] = None

def get_subagent_orchestrator(max_parallel: int = 10) -> SubagentOrchestrator:
    """Get or create global orchestrator instance."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = SubagentOrchestrator(max_parallel=max_parallel)
    return _orchestrator_instance
