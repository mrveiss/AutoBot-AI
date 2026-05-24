# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC domain exceptions (GH#8215)."""


class BudgetExhausted(Exception):
    """Raised when an agent's budget_spent exceeds budget_limit."""

    def __init__(self, agent_id: str, spent: float, limit: float) -> None:
        self.agent_id = agent_id
        self.spent = spent
        self.limit = limit
        super().__init__(f"Agent {agent_id} budget exhausted: spent={spent:.6f} limit={limit:.6f}")


class ApiKeyNotFound(Exception):
    """Raised when an API key is not found or not owned by the requesting agent."""


class WipLimitExceeded(Exception):
    """Raised when moving a work item into a column would exceed its WIP limit."""

    def __init__(self, column_name: str, wip_limit: int, current_count: int) -> None:
        self.column_name = column_name
        self.wip_limit = wip_limit
        self.current_count = current_count
        super().__init__(
            f"Column '{column_name}' is at WIP limit ({wip_limit}); " f"currently has {current_count} item(s)."
        )
