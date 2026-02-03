"""
System Tray Icon Helper
"""

from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import QObject, Signal


class TrayIconManager(QObject):
    """Manager for system tray icon"""

    show_window = Signal()
    hide_window = Signal()
    quit_app = Signal()
    start_service = Signal()
    stop_service = Signal()

    def __init__(self, icon: QIcon, parent=None):
        super().__init__(parent)
        self.tray_icon = QSystemTrayIcon(icon, parent)
        self.init_menu()

    def init_menu(self):
        """Initialize tray icon menu"""
        menu = QMenu()

        # Show/Hide action
        show_action = QAction("Show Dashboard", self)
        show_action.triggered.connect(self.show_window.emit)
        menu.addAction(show_action)

        menu.addSeparator()

        # Service actions
        start_action = QAction("Start Service", self)
        start_action.triggered.connect(self.start_service.emit)
        menu.addAction(start_action)

        stop_action = QAction("Stop Service", self)
        stop_action.triggered.connect(self.stop_service.emit)
        menu.addAction(stop_action)

        menu.addSeparator()

        # Quit action
        quit_action = QAction("Exit", self)
        quit_action.triggered.connect(self.quit_app.emit)
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)

    def show(self):
        """Show tray icon"""
        self.tray_icon.show()

    def hide(self):
        """Hide tray icon"""
        self.tray_icon.hide()

    def show_message(self, title: str, message: str, icon=QSystemTrayIcon.MessageIcon.Information, duration: int = 2000):
        """Show tray notification"""
        self.tray_icon.showMessage(title, message, icon, duration)
