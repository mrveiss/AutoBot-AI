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
        super().__init__(
            f"Agent {agent_id} budget exhausted: spent={spent:.6f} limit={limit:.6f}"
        )
