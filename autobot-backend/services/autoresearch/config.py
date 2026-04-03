# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoResearch Configuration

Issue #2597: Service-specific configuration for experiment runner.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AutoResearchConfig:
    """Configuration for the autoresearch experiment runner."""

    # Path to the cloned autoresearch repo on the GPU node
    autoresearch_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "AUTOBOT_AUTORESEARCH_DIR",
                "/opt/autobot/autoresearch",
            )
        )
    )

    # Training defaults
    default_training_timeout: int = field(
        default_factory=lambda: int(os.getenv("AUTOBOT_AUTORESEARCH_TIMEOUT", "600"))
    )
    default_max_steps: int = field(
        default_factory=lambda: int(os.getenv("AUTOBOT_AUTORESEARCH_MAX_STEPS", "5000"))
    )

    # Experiment evaluation
    improvement_threshold: float = field(
        default_factory=lambda: float(
            os.getenv("AUTOBOT_AUTORESEARCH_IMPROVEMENT_THRESHOLD", "0.01")
        )
    )
    significant_improvement_threshold: float = field(
        default_factory=lambda: float(
            os.getenv("AUTOBOT_AUTORESEARCH_SIGNIFICANT_THRESHOLD", "0.05")
        )
    )

    # Redis key prefixes
    redis_prefix: str = "autoresearch"
    redis_database: str = "main"

    # ChromaDB collection
    chromadb_collection: str = "autoresearch_experiments"

    # Runner settings
    max_concurrent_experiments: int = 1
    python_executable: Optional[str] = None

    # Staged evaluation (cheap-first gating)
    staged_eval_fraction: float = field(
        default_factory=lambda: float(
            os.getenv("AUTOBOT_AUTORESEARCH_STAGED_EVAL_FRACTION", "0.3")
        )
    )
    staged_eval_threshold: float = field(
        default_factory=lambda: float(
            os.getenv("AUTOBOT_AUTORESEARCH_STAGED_EVAL_THRESHOLD", "0.5")
        )
    )

    # Docker isolation (issue #3223)
    # Set AUTOBOT_AUTORESEARCH_DOCKER_ENABLED=true via Ansible/env to activate.
    docker_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "AUTOBOT_AUTORESEARCH_DOCKER_ENABLED", "false"
        ).lower()
        == "true"
    )
    docker_image: str = field(
        default_factory=lambda: os.getenv(
            "AUTOBOT_AUTORESEARCH_DOCKER_IMAGE",
            "ghcr.io/mrveiss/autobot-autoresearch:latest",
        )
    )
    docker_memory_limit: str = field(
        default_factory=lambda: os.getenv(
            "AUTOBOT_AUTORESEARCH_DOCKER_MEMORY", "4g"
        )
    )
    docker_cpu_limit: float = field(
        default_factory=lambda: float(
            os.getenv("AUTOBOT_AUTORESEARCH_DOCKER_CPUS", "2.0")
        )
    )
    docker_timeout: int = field(
        default_factory=lambda: int(
            os.getenv("AUTOBOT_AUTORESEARCH_DOCKER_TIMEOUT", "300")
        )
    )

    # Data directory for experiment outputs
    data_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "AUTOBOT_AUTORESEARCH_DATA_DIR",
                "/opt/autobot/autoresearch/data",
            )
        )
    )

    @property
    def train_script(self) -> Path:
        return self.autoresearch_dir / "train.py"

    @property
    def python_bin(self) -> str:
        if self.python_executable:
            return self.python_executable
        venv_python = self.autoresearch_dir / "venv" / "bin" / "python"
        if venv_python.exists():
            return str(venv_python)
        return "python3"
