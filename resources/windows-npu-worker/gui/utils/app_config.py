"""
Application Configuration - GUI Application Settings
"""

from pathlib import Path
from typing import Optional


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

    def get_icon_path(self, icon_name: str) -> Optional[Path]:
        """Get icon file path"""
        icon_path = self.icons_dir / icon_name
        if icon_path.exists():
            return icon_path
        return None

    def get_resource_path(self, resource_name: str) -> Path:
        """Get resource file path"""
        return self.resources_dir / resource_name
