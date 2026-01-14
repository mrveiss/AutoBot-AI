# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Node Agent Package

Lightweight agent deployed to each managed node for:
- Health data collection
- Heartbeat sending
- Command receiving
"""

from slm.agent.health_collector import HealthCollector
from slm.agent.agent import SLMAgent

__all__ = ["HealthCollector", "SLMAgent"]
