#!/usr/bin/env python3
"""
AutoBot NPU Worker GUI - Main Entry Point
Windows desktop application for NPU worker management
"""

import logging
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup crash logging before any imports that might fail
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)
crash_log = log_dir / "gui_crash.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(crash_log, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def exception_hook(exc_type, exc_value, exc_tb):
    """Global exception handler for uncaught exceptions"""
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical("Uncaught exception:\n%s", error_msg)

    # Try to show message box if Qt is available
    try:
        if QApplication.instance():
            QMessageBox.critical(
                None,
                "Critical Error",
                f"An unexpected error occurred:\n\n{exc_value}\n\nCheck gui_crash.log for details.",
            )
    except Exception:
        logger.debug("Suppressed exception in try block", exc_info=True)

    # Call the default handler
    sys.__excepthook__(exc_type, exc_value, exc_tb)


# Install global exception hook
sys.excepthook = exception_hook


def main():
    """Main application entry point"""
    logger.info("=== AutoBot NPU Worker GUI Starting ===")

    try:
        # Enable High DPI scaling for Windows 11
        logger.debug("Setting High DPI scaling policy")
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

        logger.debug("Creating QApplication")
        app = QApplication(sys.argv)
        app.setApplicationName("AutoBot NPU Worker")
        app.setApplicationVersion("1.0.0")
        app.setOrganizationName("AutoBot")

        # Load application configuration
        logger.debug("Loading AppConfig")
        from gui.utils.app_config import AppConfig

        config = AppConfig()

        # Set application icon
        icon_path = Path(__file__).parent / "resources" / "icons" / "app_icon.png"
        if icon_path.exists():
            logger.debug("Setting application icon: %s", icon_path)
            app.setWindowIcon(QIcon(str(icon_path)))

        # Create and show main window
        logger.debug("Creating MainWindow")
        from gui.windows.main_window import MainWindow

        main_window = MainWindow(config)

        logger.debug("Showing MainWindow")
        main_window.show()

        logger.info("GUI initialized successfully, starting event loop")
        # Start event loop
        sys.exit(app.exec())

    except Exception as e:
        logger.critical("Failed to start GUI: %s", e, exc_info=True)
        try:
            QMessageBox.critical(
                None,
                "Startup Error",
                f"Failed to start NPU Worker GUI:\n\n{e}\n\nCheck gui_crash.log for details.",
            )
        except Exception:
            logger.debug("Suppressed exception in try block", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
