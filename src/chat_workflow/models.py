# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Data models for chat workflow management.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class WorkflowSession:
    """Represents an active chat workflow session"""

    session_id: str
    workflow: Any  # AsyncChatWorkflow instance
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    message_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    conversation_history: List[Dict[str, str]] = field(
        default_factory=list
    )  # Track conversation context
