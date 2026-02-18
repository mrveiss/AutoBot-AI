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

from .agent import SLMAgent
from .health_collector import HealthCollector
from .version import AgentVersion, get_agent_version

__all__ = ["HealthCollector", "SLMAgent", "AgentVersion", "get_agent_version"]
