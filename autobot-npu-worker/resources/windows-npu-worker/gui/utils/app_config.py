# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Application Configuration - GUI Application Settings
"""

from pathlib import Path

# The GUI's ONE home for the worker's listen port. The GUI runs without app/ on sys.path, so it
# cannot import app/utils/config_bootstrap; repo_tests/service_port_homes_test.py holds this equal to
# that copy and to ssot_config PortConfig.npu_windows (#19325).
DEFAULT_WORKER_PORT = 8082


class AppConfig:
    """Application configuration and paths"""

    def __init__(self):
        self.app_dir = Path(__file__).parent.parent.parent
        self.gui_dir = self.app_dir / "gui"
        self.config_dir = self.app_dir / "config"
        self.log_dir = self.app_dir / "logs"
        self.resources_dir = self.gui_dir / "resources"
        self.icons_dir = self.resources_dir / "icons"

        # Ensure directories exist
        self.log_dir.mkdir(exist_ok=True)
        self.resources_dir.mkdir(exist_ok=True)
        self.icons_dir.mkdir(exist_ok=True)

    def get_log_directory(self) -> Path:
        """Get log directory path"""
        return self.log_dir

    def get_config_directory(self) -> Path:
        """Get configuration directory path"""
        return self.config_dir

    def get_icon_path(self, icon_name: str) -> Path | None:
        """Get icon file path"""
        icon_path = self.icons_dir / icon_name
        if icon_path.exists():
            return icon_path
        return None

    def get_resource_path(self, resource_name: str) -> Path:
        """Get resource file path"""
        return self.resources_dir / resource_name
