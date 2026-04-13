"""Cron scheduler for automation tasks."""
import logging
from typing import Callable, Dict, List, Optional
from croniter import croniter
from datetime import datetime

logger = logging.getLogger(__name__)

class CronScheduler:
    """Manages cron-scheduled automation tasks."""
    
    def __init__(self):
        self.tasks: Dict[str, Dict] = {}
    
    def schedule(self, cron_expr: str, task_func: Callable, task_id: Optional[str] = None) -> str:
        """
        Schedule a task using cron expression.
        
        Args:
            cron_expr: Cron expression (minute hour day month day_of_week)
            task_func: Callable to execute
            task_id: Optional task ID
            
        Returns:
            Task ID
        """
        # Validate cron expression
        if not croniter.is_valid(cron_expr):
            raise ValueError(f"Invalid cron expression: {cron_expr}")
        
        if task_id is None:
            task_id = f"task_{len(self.tasks)}"
        
        self.tasks[task_id] = {
            "cron": cron_expr,
            "func": task_func,
            "last_run": None,
            "created_at": datetime.utcnow()
        }
        
        logger.info(f"Scheduled task {task_id}: {cron_expr}")
        return task_id
    
    def get_next_run(self, task_id: str) -> Optional[datetime]:
        """Get next scheduled run time for a task."""
        if task_id not in self.tasks:
            return None
        
        cron = croniter(self.tasks[task_id]["cron"], datetime.utcnow())
        return cron.get_next(datetime)

_scheduler_instance: Optional[CronScheduler] = None

def get_cron_scheduler() -> CronScheduler:
    """Get or create global scheduler instance."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = CronScheduler()
    return _scheduler_instance
