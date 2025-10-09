#!/usr/bin/env python3
"""
AutoBot NPU Worker GUI - Main Entry Point
Windows desktop application for NPU worker management
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from gui.windows.main_window import MainWindow
from gui.utils.app_config import AppConfig


def main():
    """Main application entry point"""
    # Enable High DPI scaling for Windows 11
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("AutoBot NPU Worker")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("AutoBot")

    # Load application configuration
    config = AppConfig()

    # Set application icon
    icon_path = Path(__file__).parent / "resources" / "icons" / "app_icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Create and show main window
    main_window = MainWindow(config)
    main_window.show()

    # Start event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
