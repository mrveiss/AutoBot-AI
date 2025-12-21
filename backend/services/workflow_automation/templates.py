# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Templates Module

Pre-defined workflow templates for common automation tasks.
"""

import logging
from typing import Callable, Dict, List

from .models import WorkflowStep

logger = logging.getLogger(__name__)


class WorkflowTemplateManager:
    """Manages workflow templates for common automation tasks"""

    def __init__(self):
        """Initialize template manager with default workflow templates."""
        self.templates: Dict[str, Callable[[str], List[WorkflowStep]]] = {
            "system_update": self._create_system_update_workflow,
            "dev_environment": self._create_dev_environment_workflow,
            "security_scan": self._create_security_scan_workflow,
            "backup_creation": self._create_backup_workflow,
        }

    def get_template(self, template_name: str, session_id: str) -> List[WorkflowStep]:
        """Get workflow steps from a template"""
        if template_name not in self.templates:
            logger.warning("Template '%s' not found", template_name)
            return []
        return self.templates[template_name](session_id)

    def list_templates(self) -> List[str]:
        """List available template names"""
        return list(self.templates.keys())

    def _create_system_update_workflow(self, session_id: str) -> List[WorkflowStep]:
        """Create system update workflow"""
        return [
            WorkflowStep(
                step_id="update_repos",
                command="sudo apt update",
                description="Update package repositories",
            ),
            WorkflowStep(
                step_id="upgrade_packages",
                command="sudo apt upgrade -y",
                description="Upgrade installed packages",
            ),
            WorkflowStep(
                step_id="autoremove",
                command="sudo apt autoremove -y",
                description="Remove unnecessary packages",
            ),
            WorkflowStep(
                step_id="verify",
                command="apt list --upgradable",
                description="Check for remaining updates",
            ),
        ]

    def _create_dev_environment_workflow(self, session_id: str) -> List[WorkflowStep]:
        """Create development environment setup workflow"""
        return [
            WorkflowStep(
                step_id="update_system",
                command="sudo apt update",
                description="Update system packages",
            ),
            WorkflowStep(
                step_id="install_git",
                command="sudo apt install -y git",
                description="Install Git version control",
            ),
            WorkflowStep(
                step_id="install_nodejs",
                command="curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -",
                description="Setup Node.js repository",
            ),
            WorkflowStep(
                step_id="install_nodejs_pkg",
                command="sudo apt install -y nodejs",
                description="Install Node.js and npm",
            ),
            WorkflowStep(
                step_id="install_python",
                command="sudo apt install -y python3 python3-pip",
                description="Install Python 3 and pip",
            ),
            WorkflowStep(
                step_id="verify_installs",
                command="git --version && node --version && python3 --version",
                description="Verify installations",
            ),
        ]

    def _create_security_scan_workflow(self, session_id: str) -> List[WorkflowStep]:
        """Create security scanning workflow"""
        return [
            WorkflowStep(
                step_id="update_db",
                command="sudo apt update",
                description="Update package database",
            ),
            WorkflowStep(
                step_id="install_scanner",
                command="sudo apt install -y nmap lynis",
                description="Install security scanning tools",
            ),
            WorkflowStep(
                step_id="scan_ports",
                command="sudo nmap -sS -O localhost",
                description="Scan local ports and services",
            ),
            WorkflowStep(
                step_id="system_audit",
                command="sudo lynis audit system",
                description="Run system security audit",
            ),
            WorkflowStep(
                step_id="check_permissions",
                command="find /etc -perm -o=w -type f 2>/dev/null",
                description="Check for world-writable files in /etc",
            ),
        ]

    def _create_backup_workflow(self, session_id: str) -> List[WorkflowStep]:
        """Create backup creation workflow"""
        return [
            WorkflowStep(
                step_id="create_backup_dir",
                command="mkdir -p ~/backups/$(date +%Y%m%d)",
                description="Create dated backup directory",
            ),
            WorkflowStep(
                step_id="backup_config",
                command="tar -czf ~/backups/$(date +%Y%m%d)/config_backup.tar.gz ~/.bashrc ~/.profile /etc/hosts",
                description="Backup configuration files",
            ),
            WorkflowStep(
                step_id="backup_documents",
                command="tar -czf ~/backups/$(date +%Y%m%d)/docs_backup.tar.gz ~/Documents",
                description="Backup documents directory",
            ),
            WorkflowStep(
                step_id="verify_backups",
                command="ls -la ~/backups/$(date +%Y%m%d)/",
                description="Verify backup files created",
            ),
            WorkflowStep(
                step_id="cleanup_old",
                command="find ~/backups -type d -mtime +30 -exec rm -rf {} +",
                description="Clean up backups older than 30 days",
            ),
        ]
