# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoResearch Configuration

Issue #2597: Service-specific configuration for experiment runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from autobot_shared.ssot_config import config


@dataclass
class AutoResearchConfig:
    """Configuration for the autoresearch experiment runner."""

    # Path to the cloned autoresearch repo on the GPU node
    autoresearch_dir: Path = field(
        default_factory=lambda: Path(config.misc.autoresearch_dir or "/opt/autobot/autoresearch")
    )

    # Training defaults
    default_training_timeout: int = field(default_factory=lambda: int(config.autoresearch_timeout))
    default_max_steps: int = field(default_factory=lambda: int(config.autoresearch_max_steps))

    # Experiment evaluation
    improvement_threshold: float = field(default_factory=lambda: float(config.autoresearch_improvement_threshold))
    significant_improvement_threshold: float = field(
        default_factory=lambda: float(config.autoresearch_significant_threshold)
    )

    # Redis key prefixes
    redis_prefix: str = "autoresearch"
    redis_database: str = "main"

    # ChromaDB collection
    chromadb_collection: str = "autoresearch_experiments"

    # Runner settings
    max_concurrent_experiments: int = 1
    python_executable: str | None = None

    # Staged evaluation (cheap-first gating)
    staged_eval_fraction: float = field(default_factory=lambda: float(config.autoresearch_staged_eval_fraction))
    staged_eval_threshold: float = field(default_factory=lambda: float(config.autoresearch_staged_eval_threshold))

    # Docker isolation (issue #3223)
    # Set AUTOBOT_AUTORESEARCH_DOCKER_ENABLED=true via Ansible/env to activate.
    docker_enabled: bool = field(default_factory=lambda: bool(config.autoresearch_docker_enabled))
    docker_image: str = field(
        default_factory=lambda: config.misc.autoresearch_docker_image or "ghcr.io/mrveiss/autobot-autoresearch:latest"
    )
    docker_memory_limit: str = field(default_factory=lambda: config.autoresearch_docker_memory)
    docker_cpu_limit: float = field(default_factory=lambda: float(config.autoresearch_docker_cpus))
    docker_timeout: int = field(default_factory=lambda: int(config.autoresearch_docker_timeout))

    # Meta-agent settings (issue #3224)
    meta_agent_max_module_lines: int = field(default_factory=lambda: int(config.meta_agent_max_module_lines))
    meta_agent_llm_model: str = field(default_factory=lambda: config.meta_agent_llm_model)
    meta_agent_test_timeout: int = field(default_factory=lambda: int(config.meta_agent_test_timeout))
    meta_agent_approval_threshold: float = field(default_factory=lambda: float(config.meta_agent_approval_threshold))

    # Data directory for experiment outputs
    data_dir: Path = field(
        default_factory=lambda: Path(config.misc.autoresearch_data_dir or "/opt/autobot/autoresearch/data")
    )

    # Human-in-the-loop research checkpoints (issue #3291)
    checkpoints_enabled: bool = field(default_factory=lambda: bool(config.research_checkpoints_enabled))
    checkpoint_timeout_seconds: float = field(default_factory=lambda: float(config.research_checkpoint_timeout))

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
