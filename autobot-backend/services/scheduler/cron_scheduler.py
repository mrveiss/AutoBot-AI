"""Cron scheduler for automation tasks."""
import logging
from typing import Callable, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class CronScheduler:
    """Manages cron-scheduled automation tasks."""
    
    def __init__(self):
        self.tasks: Dict[str, Dict] = {}
    
    def schedule(self, cron_expr: str, task_func: Callable, task_id: Optional[str] = None) -> str:
        """Schedule a task using cron expression."""
        # Basic cron validation
        parts = cron_expr.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {cron_expr}")
        
        if task_id is None:
            task_id = f"task_{len(self.tasks)}"
        
        self.tasks[task_id] = {
            "cron": cron_expr,
            "func": task_func,
            "created_at": datetime.utcnow()
        }
        
        logger.info(f"Scheduled task {task_id}: {cron_expr}")
        return task_id

_scheduler_instance: Optional[CronScheduler] = None

def get_cron_scheduler() -> CronScheduler:
    """Get or create global scheduler instance."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = CronScheduler()
    return _scheduler_instance
