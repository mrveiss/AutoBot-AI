# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Advanced Workflow Models

Enums, dataclasses, and constants for the advanced workflow system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from services.workflow_automation import WorkflowStep
from type_defs.common import Metadata

# Performance optimization: O(1) lookup for dangerous command patterns (Issue #326)
CRITICAL_RISK_PATTERNS = {"rm -r", "dd ", "mkfs"}
HIGH_RISK_PATTERNS = {"sudo rm", "chmod 777", "killall"}
MODERATE_RISK_PATTERNS = {"sudo", "systemctl", "apt install"}


class WorkflowComplexity(Enum):
    """Workflow complexity levels"""

    SIMPLE = "simple"  # 1-3 steps, no dependencies
    MODERATE = "moderate"  # 4-10 steps, simple dependencies
    COMPLEX = "complex"  # 11-25 steps, complex dependencies
    ENTERPRISE = "enterprise"  # 25+ steps, multi-system integration


class AdaptiveMode(Enum):
    """Adaptive learning modes for workflows"""

    STATIC = "static"  # Fixed workflow, no adaptation
    LEARNING = "learning"  # Learns from user preferences
    PREDICTIVE = "predictive"  # Predicts user needs
    AUTONOMOUS = "autonomous"  # Self-optimizing workflows


class WorkflowIntent(Enum):
    """Workflow intent categories"""

    INSTALLATION = "installation"
    CONFIGURATION = "configuration"
    DEPLOYMENT = "deployment"
    MAINTENANCE = "maintenance"
    SECURITY = "security"
    DEVELOPMENT = "development"
    ANALYSIS = "analysis"
    BACKUP = "backup"
    MONITORING = "monitoring"
    OPTIMIZATION = "optimization"


@dataclass
class WorkflowIntelligence:
    """AI-driven workflow intelligence and optimization"""

    workflow_id: str
    user_behavior_patterns: Metadata = field(default_factory=dict)
    success_predictions: Dict[str, float] = field(default_factory=dict)
    optimization_suggestions: List[str] = field(default_factory=list)
    risk_mitigation_strategies: List[str] = field(default_factory=list)
    estimated_completion_time: float = 0.0
    confidence_score: float = 0.0
    learning_data: Metadata = field(default_factory=dict)


@dataclass
class SmartWorkflowStep(WorkflowStep):
    """Enhanced workflow step with AI intelligence"""

    intent: WorkflowIntent = WorkflowIntent.CONFIGURATION
    confidence_score: float = 0.0
    alternative_commands: List[str] = field(default_factory=list)
    success_probability: float = 0.0
    rollback_command: Optional[str] = None
    validation_command: Optional[str] = None
    learning_metadata: Metadata = field(default_factory=dict)
    ai_generated: bool = True
    user_customizations: List[str] = field(default_factory=list)


@dataclass
class WorkflowTemplate:
    """Intelligent workflow template"""

    template_id: str
    name: str
    description: str
    intent: WorkflowIntent
    complexity: WorkflowComplexity
    steps: List[SmartWorkflowStep]
    prerequisites: List[str] = field(default_factory=list)
    success_rate: float = 0.0
    usage_count: int = 0
    last_updated: datetime = field(default_factory=datetime.now)
    user_ratings: List[float] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_summary_dict(self) -> dict:
        """Convert to summary dictionary for API response (Issue #372 - reduces feature envy)."""
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "intent": self.intent.value,
            "complexity": self.complexity.value,
            "steps_count": len(self.steps),
            "prerequisites": self.prerequisites,
            "success_rate": self.success_rate,
            "usage_count": self.usage_count,
            "tags": self.tags,
            "last_updated": self.last_updated.isoformat(),
        }
