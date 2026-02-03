"""
Main Window - NPU Worker Dashboard
"""

import logging

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTabWidget, QStatusBar,
    QMessageBox, QSystemTrayIcon, QMenu
)
from PySide6.QtCore import QTimer, Slot
from PySide6.QtGui import QIcon, QAction

logger = logging.getLogger(__name__)

# Import widgets with error handling
try:
    logger.debug("Importing StatusPanel")
    from gui.widgets.status_panel import StatusPanel
except Exception as e:
    logger.error("Failed to import StatusPanel: %s", e, exc_info=True)
    raise

try:
    logger.debug("Importing MetricsDisplay")
    from gui.widgets.metrics_display import MetricsDisplay
except Exception as e:
    logger.error("Failed to import MetricsDisplay: %s", e, exc_info=True)
    raise

try:
    logger.debug("Importing ConnectionInfoWidget")
    from gui.widgets.connection_info import ConnectionInfoWidget
except Exception as e:
    logger.error("Failed to import ConnectionInfoWidget: %s", e, exc_info=True)
    raise

try:
    logger.debug("Importing SettingsDialog")
    from gui.windows.settings_dialog import SettingsDialog
except Exception as e:
    logger.error("Failed to import SettingsDialog: %s", e, exc_info=True)
    raise

try:
    logger.debug("Importing LogViewer")
    from gui.windows.log_viewer import LogViewer
except Exception as e:
    logger.error("Failed to import LogViewer: %s", e, exc_info=True)
    raise

try:
    logger.debug("Importing BenchmarkWidget")
    from gui.widgets.benchmark_widget import BenchmarkWidget
except Exception as e:
    logger.error("Failed to import BenchmarkWidget: %s", e, exc_info=True)
    raise

try:
    logger.debug("Importing WorkerController")
    from gui.controllers.worker_controller import WorkerController
except Exception as e:
    logger.error("Failed to import WorkerController: %s", e, exc_info=True)
    raise

try:
    logger.debug("Importing ConfigManager")
    from gui.controllers.config_manager import ConfigManager
except Exception as e:
    logger.error("Failed to import ConfigManager: %s", e, exc_info=True)
    raise


class MainWindow(QMainWindow):
    """Main application window with NPU worker dashboard"""

    def __init__(self, app_config):
        super().__init__()
        logger.debug("MainWindow.__init__ starting")
        self.app_config = app_config

        try:
            logger.debug("Creating WorkerController")
            self.worker_controller = WorkerController()
        except Exception as e:
            logger.error("Failed to create WorkerController: %s", e, exc_info=True)
            raise

        try:
            logger.debug("Creating ConfigManager")
            self.config_manager = ConfigManager()
        except Exception as e:
            logger.error("Failed to create ConfigManager: %s", e, exc_info=True)
            raise

        try:
            logger.debug("Initializing UI")
            self.init_ui()
        except Exception as e:
            logger.error("Failed to init_ui: %s", e, exc_info=True)
            raise

        try:
            logger.debug("Initializing system tray")
            self.init_system_tray()
        except Exception as e:
            logger.error("Failed to init_system_tray: %s", e, exc_info=True)
            raise

        try:
            logger.debug("Initializing timers")
            self.init_timers()
        except Exception as e:
            logger.error("Failed to init_timers: %s", e, exc_info=True)
            raise

        try:
            logger.debug("Connecting signals")
            self.connect_signals()
        except Exception as e:
            logger.error("Failed to connect_signals: %s", e, exc_info=True)
            raise

        # Initial status update
        logger.debug("Initial status update")
        self.update_status()
        logger.debug("MainWindow.__init__ complete")

    def init_ui(self):
        """Initialize user interface"""
        self.setWindowTitle("AutoBot NPU Worker - Dashboard")
        self.setMinimumSize(900, 650)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Header with service controls
        header_layout = self.create_header()
        main_layout.addLayout(header_layout)

        # Tab widget for different views
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Dashboard tab
        dashboard_tab = self.create_dashboard_tab()
        self.tabs.addTab(dashboard_tab, "Dashboard")

        # Benchmark tab (Issue #640)
        self.benchmark_widget = BenchmarkWidget()
        self.tabs.addTab(self.benchmark_widget, "Benchmark")

        # Connection Info tab
        self.connection_info = ConnectionInfoWidget()
        self.tabs.addTab(self.connection_info, "Connection Info")

        # Logs tab
        self.log_viewer = LogViewer(self.app_config)
        self.tabs.addTab(self.log_viewer, "Logs")

        # Status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.status_label = QLabel("Ready")
        self.statusBar.addPermanentWidget(self.status_label)

        # Menu bar
        self.create_menu_bar()

    def create_header(self):
        """Create header with service controls"""
        header_layout = QHBoxLayout()

        # Service status indicator
        self.service_status = QLabel("⚫ Service Stopped")
        self.service_status.setStyleSheet("font-size: 14px; font-weight: bold;")
        header_layout.addWidget(self.service_status)

        header_layout.addStretch()

        # Control buttons
        self.start_btn = QPushButton("▶ Start")
        self.start_btn.clicked.connect(self.start_service)
        self.start_btn.setMinimumWidth(100)
        header_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.clicked.connect(self.stop_service)
        self.stop_btn.setMinimumWidth(100)
        self.stop_btn.setEnabled(False)
        header_layout.addWidget(self.stop_btn)

        self.restart_btn = QPushButton("🔄 Restart")
        self.restart_btn.clicked.connect(self.restart_service)
        self.restart_btn.setMinimumWidth(100)
        self.restart_btn.setEnabled(False)
        header_layout.addWidget(self.restart_btn)

        return header_layout

    def create_dashboard_tab(self):
        """Create main dashboard tab"""
        dashboard = QWidget()
        layout = QVBoxLayout(dashboard)

        # Status panels
        self.status_panel = StatusPanel()
        layout.addWidget(self.status_panel)

        # Metrics display
        self.metrics_display = MetricsDisplay()
        layout.addWidget(self.metrics_display)

        return dashboard

    def create_menu_bar(self):
        """Create application menu bar"""
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("&File")

        settings_action = QAction("&Settings", self)
        settings_action.setShortcut("Ctrl+S")
        settings_action.triggered.connect(self.show_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Service menu
        service_menu = menu_bar.addMenu("&Service")

        start_action = QAction("&Start Service", self)
        start_action.triggered.connect(self.start_service)
        service_menu.addAction(start_action)

        stop_action = QAction("S&top Service", self)
        stop_action.triggered.connect(self.stop_service)
        service_menu.addAction(stop_action)

        restart_action = QAction("&Restart Service", self)
        restart_action.triggered.connect(self.restart_service)
        service_menu.addAction(restart_action)

        service_menu.addSeparator()

        # Issue #640: Re-pair action
        repair_action = QAction("Re-&pair with Master...", self)
        repair_action.setShortcut("Ctrl+R")
        repair_action.triggered.connect(self.show_repair_dialog)
        service_menu.addAction(repair_action)

        # Help menu
        help_menu = menu_bar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def init_system_tray(self):
        """Initialize system tray icon"""
        self.tray_icon = QSystemTrayIcon(self)

        # Set tray icon
        icon_path = self.app_config.get_icon_path("app_icon.png")
        if icon_path and icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        else:
            self.tray_icon.setIcon(self.style().standardIcon(
                self.style().StandardPixmap.SP_ComputerIcon
            ))

        # Tray menu
        tray_menu = QMenu()

        show_action = tray_menu.addAction("Show Dashboard")
        show_action.triggered.connect(self.show)

        tray_menu.addSeparator()

        start_action = tray_menu.addAction("Start Service")
        start_action.triggered.connect(self.start_service)

        stop_action = tray_menu.addAction("Stop Service")
        stop_action.triggered.connect(self.stop_service)

        tray_menu.addSeparator()

        exit_action = tray_menu.addAction("Exit")
        exit_action.triggered.connect(self.quit_application)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()

    def init_timers(self):
        """Initialize update timers"""
        # Status update timer (every 2 seconds)
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(2000)

        # Metrics update timer (every 5 seconds)
        self.metrics_timer = QTimer(self)
        self.metrics_timer.timeout.connect(self.update_metrics)
        self.metrics_timer.start(5000)

    def connect_signals(self):
        """Connect controller signals to slots"""
        self.worker_controller.status_changed.connect(self.on_status_changed)
        self.worker_controller.error_occurred.connect(self.on_error)
        self.worker_controller.metrics_updated.connect(self.on_metrics_updated)

    @Slot()
    def start_service(self):
        """Start NPU worker service"""
        self.status_label.setText("Starting service...")
        self.worker_controller.start_worker()

    @Slot()
    def stop_service(self):
        """Stop NPU worker service"""
        self.status_label.setText("Stopping service...")
        self.worker_controller.stop_worker()

    @Slot()
    def restart_service(self):
        """Restart NPU worker service"""
        self.status_label.setText("Restarting service...")
        self.worker_controller.restart_worker()

    @Slot()
    def update_status(self):
        """Update service status display (non-blocking)"""
        # Trigger async status check - result comes via on_status_changed signal
        self.worker_controller.check_status_async()
        # Also update UI with cached status immediately for responsiveness
        status = self.worker_controller.get_status()
        self.update_ui_for_status(status)

    @Slot()
    def update_metrics(self):
        """Update metrics display"""
        self.worker_controller.fetch_metrics()

    @Slot(str)
    def on_status_changed(self, status: str):
        """Handle status change"""
        self.update_ui_for_status(status)

        # Show tray notification
        if status == "running":
            self.tray_icon.showMessage(
                "NPU Worker",
                "Service started successfully",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        elif status == "stopped":
            self.tray_icon.showMessage(
                "NPU Worker",
                "Service stopped",
                QSystemTrayIcon.MessageIcon.Warning,
                2000
            )

    @Slot(str)
    def on_error(self, error_msg: str):
        """Handle error from controller"""
        self.status_label.setText(f"Error: {error_msg}")
        QMessageBox.critical(self, "Error", error_msg)

    @Slot(dict)
    def on_metrics_updated(self, metrics: dict):
        """Handle updated metrics"""
        self.status_panel.update_status(metrics)
        self.metrics_display.update_metrics(metrics)

        # Update connection info with worker ID and port
        worker_id = metrics.get('worker_id', 'N/A')
        port = metrics.get('port', 8082)
        self.connection_info.set_worker_id(worker_id)
        self.connection_info.set_port(port)

        # Issue #640: Update benchmark widget with correct API URL
        if port:
            self.benchmark_widget.set_api_url(f"http://localhost:{port}")

    def update_ui_for_status(self, status: str):
        """Update UI elements based on service status"""
        if status == "running":
            self.service_status.setText("🟢 Service Running")
            self.service_status.setStyleSheet(
                "color: green; font-size: 14px; font-weight: bold;"
            )
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.restart_btn.setEnabled(True)
            self.status_label.setText("Service is running")
        else:
            self.service_status.setText("⚫ Service Stopped")
            self.service_status.setStyleSheet(
                "color: gray; font-size: 14px; font-weight: bold;"
            )
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.restart_btn.setEnabled(False)
            self.status_label.setText("Service is stopped")

    @Slot()
    def show_settings(self):
        """Show settings dialog"""
        dialog = SettingsDialog(self.config_manager, self)
        if dialog.exec():
            # Settings saved, restart if service is running
            if self.worker_controller.get_status() == "running":
                reply = QMessageBox.question(
                    self,
                    "Restart Required",
                    "Settings have been changed. Restart the service to apply?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.restart_service()

    @Slot()
    def show_about(self):
        """Show about dialog"""
        # Get network info for display
        from gui.utils.network_info import get_network_interfaces, get_primary_ip

        interfaces = get_network_interfaces()
        primary_ip = get_primary_ip() or "N/A"

        network_info_html = ""
        if interfaces:
            network_info_html = "<p><strong>Network Interfaces:</strong></p><ul>"
            for iface in interfaces[:3]:  # Show max 3 interfaces
                primary_mark = " ★" if iface.get('is_primary') else ""
                network_info_html += f"<li>{iface['type']}: {iface['ip']}{primary_mark}</li>"
            network_info_html += "</ul>"

        QMessageBox.about(
            self,
            "About AutoBot NPU Worker",
            "<h3>AutoBot NPU Worker GUI</h3>"
            "<p>Version 1.0.0</p>"
            "<p>Windows desktop application for managing the NPU worker service.</p>"
            "<p>Features:</p>"
            "<ul>"
            "<li>Real-time NPU metrics monitoring</li>"
            "<li>Service control (start/stop/restart)</li>"
            "<li>Network connection information display</li>"
            "<li>Live log viewing</li>"
            "<li>Configuration management</li>"
            "</ul>"
            f"{network_info_html}"
            f"<p><strong>Primary IP:</strong> {primary_ip}</p>"
            "<p>© 2025 AutoBot Development Team</p>"
        )

    @Slot()
    def show_repair_dialog(self):
        """Show re-pair dialog (Issue #640)

        Allows user to clear pairing data and re-pair with master.
        This removes the worker ID, bootstrap cache, and backend/redis config.
        """
        # Get current pairing status
        status = self.config_manager.get_pairing_status()

        if not status['paired']:
            QMessageBox.information(
                self,
                "Not Paired",
                "This worker is not currently paired with a master.\n\n"
                "Start the service to initiate pairing with a master backend.",
                QMessageBox.StandardButton.Ok
            )
            return

        # Show confirmation dialog with current pairing info
        worker_id = status.get('worker_id', 'Unknown')
        backend_host = status.get('backend_host', 'Unknown')

        reply = QMessageBox.warning(
            self,
            "Re-pair with Master",
            f"<b>Current Pairing:</b><br><br>"
            f"Worker ID: <code>{worker_id}</code><br>"
            f"Master Host: <code>{backend_host}</code><br><br>"
            f"<b>This action will:</b><br>"
            f"• Remove the worker ID<br>"
            f"• Clear cached bootstrap configuration<br>"
            f"• Clear backend and Redis host settings<br><br>"
            f"The worker will need to re-pair with a master on next start.<br><br>"
            f"<b>Continue?</b>",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Stop service if running
        was_running = self.worker_controller.get_status() == "running"
        if was_running:
            self.status_label.setText("Stopping service for re-pair...")
            self.worker_controller.stop_worker()
            # Give it a moment to stop
            QTimer.singleShot(1000, lambda: self._complete_repair(was_running))
        else:
            self._complete_repair(was_running)

    def _complete_repair(self, was_running: bool):
        """Complete the re-pair process after service is stopped"""
        # Clear pairing data
        result = self.config_manager.clear_pairing()

        if result['success']:
            cleared_items = "\n• ".join(result['cleared']) if result['cleared'] else "No items to clear"

            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("Re-pair Complete")
            msg.setText("Pairing data has been cleared successfully.")
            msg.setInformativeText(
                f"<b>Cleared:</b><br>• {cleared_items}<br><br>"
                "The worker will re-pair with the master on next start."
            )

            if was_running:
                msg.setStandardButtons(
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                msg.button(QMessageBox.StandardButton.Yes).setText("Start Service Now")
                msg.button(QMessageBox.StandardButton.No).setText("Start Later")
                msg.setDefaultButton(QMessageBox.StandardButton.Yes)

                if msg.exec() == QMessageBox.StandardButton.Yes:
                    self.status_label.setText("Starting service for re-pairing...")
                    self.start_service()
            else:
                msg.setStandardButtons(QMessageBox.StandardButton.Ok)
                msg.exec()

            # Update connection info to show unpaired status
            self.connection_info.set_worker_id("Not paired")
        else:
            errors = "\n• ".join(result['errors']) if result['errors'] else "Unknown error"
            QMessageBox.critical(
                self,
                "Re-pair Failed",
                f"Failed to clear pairing data:\n\n• {errors}",
                QMessageBox.StandardButton.Ok
            )

        self.status_label.setText("Ready")

    @Slot(QSystemTrayIcon.ActivationReason)
    def tray_icon_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.activateWindow()

    def closeEvent(self, event):
        """Handle window close event"""
        # Minimize to tray instead of closing
        if self.tray_icon.isVisible():
            self.hide()
            event.ignore()
            self.tray_icon.showMessage(
                "AutoBot NPU Worker",
                "Application minimized to tray",
                QSystemTrayIcon.MessageIcon.Information,
                1000
            )

    def quit_application(self):
        """Quit application completely"""
        # Stop service if running
        if self.worker_controller.get_status() == "running":
            reply = QMessageBox.question(
                self,
                "Service Running",
                "The NPU worker service is still running. Stop it before exiting?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Cancel:
                return
            elif reply == QMessageBox.StandardButton.Yes:
                self.worker_controller.stop_worker()

        # Cleanup
        self.tray_icon.hide()
        self.close()
        QApplication.quit()
