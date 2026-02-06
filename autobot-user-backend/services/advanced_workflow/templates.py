# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Template Manager

Handles creation and management of workflow templates.
"""

import logging
from typing import Dict, List, Optional

from .models import (
    SmartWorkflowStep,
    WorkflowComplexity,
    WorkflowIntent,
    WorkflowTemplate,
)

logger = logging.getLogger(__name__)


class TemplateManager:
    """Manages intelligent workflow templates"""

    def __init__(self):
        """Initialize template manager with built-in workflow templates."""
        self.templates: Dict[str, WorkflowTemplate] = {}
        self._initialize_templates()

    def _initialize_templates(self):
        """Initialize built-in workflow templates"""
        templates = [
            self._create_smart_development_environment_template(),
            self._create_intelligent_security_hardening_template(),
            self._create_adaptive_deployment_template(),
            self._create_predictive_maintenance_template(),
            self._create_ai_backup_strategy_template(),
        ]

        for template in templates:
            self.templates[template.template_id] = template

        logger.info("Initialized %s intelligent workflow templates", len(templates))

    def get_template(self, template_id: str) -> Optional[WorkflowTemplate]:
        """Get a template by ID"""
        return self.templates.get(template_id)

    def list_templates(self) -> List[WorkflowTemplate]:
        """List all available templates"""
        return list(self.templates.values())

    def _create_smart_development_environment_template(self) -> WorkflowTemplate:
        """Create intelligent development environment setup template"""
        steps = [
            SmartWorkflowStep(
                step_id="dev_env_1",
                command="sudo apt update",
                description="Update package repositories",
                explanation=(
                    "Update system package lists before installing development tools"
                ),
                intent=WorkflowIntent.INSTALLATION,
                confidence_score=0.95,
                requires_confirmation=True,
                validation_command="apt list --upgradable | head -5",
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="dev_env_2",
                command=(
                    "sudo apt install -y git curl wget nodejs npm python3 python3-pip"
                ),
                description="Install essential development tools",
                explanation=(
                    "Install Git, Node.js, Python, and common development utilities"
                ),
                intent=WorkflowIntent.INSTALLATION,
                confidence_score=0.9,
                requires_confirmation=True,
                validation_command=(
                    "git --version && node --version && python3 --version"
                ),
                rollback_command=(
                    "sudo apt remove -y git curl wget nodejs npm python3-pip"
                ),
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="dev_env_3",
                command="git config --global init.defaultBranch main",
                description="Configure Git default branch",
                explanation="Set default branch name to 'main' for new repositories",
                intent=WorkflowIntent.CONFIGURATION,
                confidence_score=0.85,
                requires_confirmation=False,
                ai_generated=True,
            ),
        ]

        return WorkflowTemplate(
            template_id="smart_dev_environment",
            name="Smart Development Environment",
            description="AI-optimized setup of complete development environment",
            intent=WorkflowIntent.DEVELOPMENT,
            complexity=WorkflowComplexity.MODERATE,
            steps=steps,
            prerequisites=["sudo access", "internet connection"],
            success_rate=0.92,
            tags=["development", "git", "nodejs", "python", "tools"],
        )

    def _create_intelligent_security_hardening_template(self) -> WorkflowTemplate:
        """Create intelligent security hardening template"""
        steps = [
            SmartWorkflowStep(
                step_id="sec_1",
                command="sudo ufw --force enable",
                description="Enable UFW firewall",
                explanation=(
                    "Activate Ubuntu's uncomplicated firewall for basic protection"
                ),
                intent=WorkflowIntent.SECURITY,
                confidence_score=0.9,
                requires_confirmation=True,
                validation_command="sudo ufw status",
                rollback_command="sudo ufw disable",
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="sec_2",
                command="sudo ufw default deny incoming",
                description="Block incoming connections by default",
                explanation="Set default policy to deny all incoming connections",
                intent=WorkflowIntent.SECURITY,
                confidence_score=0.95,
                requires_confirmation=True,
                validation_command="sudo ufw status verbose",
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="sec_3",
                command="sudo ufw allow ssh",
                description="Allow SSH connections",
                explanation="Keep SSH access open for remote administration",
                intent=WorkflowIntent.SECURITY,
                confidence_score=0.8,
                requires_confirmation=True,
                validation_command="sudo ufw status | grep 22",
                rollback_command="sudo ufw delete allow ssh",
                ai_generated=True,
            ),
        ]

        return WorkflowTemplate(
            template_id="intelligent_security_hardening",
            name="Intelligent Security Hardening",
            description=(
                "AI-driven system security hardening with firewall configuration"
            ),
            intent=WorkflowIntent.SECURITY,
            complexity=WorkflowComplexity.MODERATE,
            steps=steps,
            prerequisites=["sudo access", "UFW installed"],
            success_rate=0.88,
            tags=["security", "firewall", "hardening", "ufw"],
        )

    def _create_adaptive_deployment_template(self) -> WorkflowTemplate:
        """Create adaptive application deployment template"""
        steps = [
            SmartWorkflowStep(
                step_id="deploy_1",
                command="docker --version",
                description="Verify Docker installation",
                explanation="Check if Docker is installed and accessible",
                intent=WorkflowIntent.ANALYSIS,
                confidence_score=0.95,
                requires_confirmation=False,
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="deploy_2",
                command="sudo systemctl start docker",
                description="Start Docker service",
                explanation="Ensure Docker daemon is running for container operations",
                intent=WorkflowIntent.DEPLOYMENT,
                confidence_score=0.9,
                requires_confirmation=True,
                validation_command="sudo systemctl is-active docker",
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="deploy_3",
                command="sudo usermod -aG docker $USER",
                description="Add user to docker group",
                explanation="Allow current user to run Docker commands without sudo",
                intent=WorkflowIntent.CONFIGURATION,
                confidence_score=0.85,
                requires_confirmation=True,
                validation_command="groups $USER | grep docker",
                ai_generated=True,
            ),
        ]

        return WorkflowTemplate(
            template_id="adaptive_deployment",
            name="Adaptive Application Deployment",
            description="Smart deployment workflow that adapts to system configuration",
            intent=WorkflowIntent.DEPLOYMENT,
            complexity=WorkflowComplexity.COMPLEX,
            steps=steps,
            prerequisites=["Docker installed", "sudo access"],
            success_rate=0.85,
            tags=["deployment", "docker", "containers", "automation"],
        )

    def _create_predictive_maintenance_template(self) -> WorkflowTemplate:
        """Create predictive system maintenance template"""
        steps = [
            SmartWorkflowStep(
                step_id="maint_1",
                command="df -h",
                description="Check disk space usage",
                explanation="Monitor disk usage to identify potential storage issues",
                intent=WorkflowIntent.MONITORING,
                confidence_score=0.98,
                requires_confirmation=False,
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="maint_2",
                command="sudo apt autoremove -y",
                description="Remove unnecessary packages",
                explanation=(
                    "Clean up automatically installed packages that are no "
                    "longer needed"
                ),
                intent=WorkflowIntent.MAINTENANCE,
                confidence_score=0.85,
                requires_confirmation=True,
                validation_command="apt list --installed | wc -l",
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="maint_3",
                command="sudo journalctl --vacuum-time=7d",
                description="Clean old system logs",
                explanation="Remove system logs older than 7 days to free space",
                intent=WorkflowIntent.MAINTENANCE,
                confidence_score=0.9,
                requires_confirmation=True,
                validation_command="sudo journalctl --disk-usage",
                ai_generated=True,
            ),
        ]

        return WorkflowTemplate(
            template_id="predictive_maintenance",
            name="Predictive System Maintenance",
            description="AI-powered system maintenance with predictive cleanup",
            intent=WorkflowIntent.MAINTENANCE,
            complexity=WorkflowComplexity.MODERATE,
            steps=steps,
            prerequisites=["sudo access"],
            success_rate=0.93,
            tags=["maintenance", "cleanup", "monitoring", "system"],
        )

    def _create_ai_backup_strategy_template(self) -> WorkflowTemplate:
        """Create AI-driven backup strategy template"""
        steps = [
            SmartWorkflowStep(
                step_id="backup_1",
                command="mkdir -p ~/backups/$(date +%Y-%m-%d)",
                description="Create dated backup directory",
                explanation="Create a new backup directory with today's date",
                intent=WorkflowIntent.BACKUP,
                confidence_score=0.95,
                requires_confirmation=False,
                validation_command="ls -la ~/backups/",
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="backup_2",
                command=(
                    "tar -czf ~/backups/$(date +%Y-%m-%d)/home_backup.tar.gz "
                    "~/Documents ~/Downloads ~/Desktop"
                ),
                description="Backup user documents",
                explanation="Create compressed archive of important user directories",
                intent=WorkflowIntent.BACKUP,
                confidence_score=0.8,
                requires_confirmation=True,
                validation_command=(
                    "ls -lh ~/backups/$(date +%Y-%m-%d)/home_backup.tar.gz"
                ),
                ai_generated=True,
            ),
            SmartWorkflowStep(
                step_id="backup_3",
                command="echo 'Backup completed successfully at $(date)'",
                description="Confirm backup completion",
                explanation="Display backup completion confirmation with timestamp",
                intent=WorkflowIntent.BACKUP,
                confidence_score=0.99,
                requires_confirmation=False,
                ai_generated=True,
            ),
        ]

        return WorkflowTemplate(
            template_id="ai_backup_strategy",
            name="AI Backup Strategy",
            description="Intelligent backup workflow with automated organization",
            intent=WorkflowIntent.BACKUP,
            complexity=WorkflowComplexity.SIMPLE,
            steps=steps,
            prerequisites=["sufficient disk space", "read access to user directories"],
            success_rate=0.95,
            tags=["backup", "archive", "data protection", "automation"],
        )
