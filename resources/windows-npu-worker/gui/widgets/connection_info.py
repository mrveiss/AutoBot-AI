"""
Connection Info Widget - Display network connection information with copy functionality
"""

import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QTextEdit, QMessageBox, QGridLayout
)
from PySide6.QtCore import Qt, Slot, QTimer

logger = logging.getLogger(__name__)

# Import with error handling
try:
    from gui.utils.network_info import (
        get_network_interfaces,
        get_platform_info,
        get_primary_ip,
        get_registration_config
    )
except Exception as e:
    logger.error("Failed to import network_info: %s", e, exc_info=True)
    # Provide fallback functions
    def get_network_interfaces():
        return []
    def get_platform_info():
        return {"system": "Unknown", "release": "", "npu_detected": False, "npu_devices": []}
    def get_primary_ip():
        return None
    def get_registration_config(port):
        return "# Network info unavailable"


class ConnectionInfoWidget(QWidget):
    """Widget displaying connection information with copy-to-clipboard functionality"""

    def __init__(self, worker_id: str = "N/A", port: int = 8082, parent=None):
        super().__init__(parent)
        logger.debug("ConnectionInfoWidget.__init__ starting")
        self.worker_id = worker_id
        self.port = port
        self._initialized = False
        self.init_ui()
        # Delay network info fetch to avoid crash during init
        QTimer.singleShot(200, self._delayed_init)
        logger.debug("ConnectionInfoWidget.__init__ complete")

    def _delayed_init(self):
        """Delayed initialization after event loop starts"""
        logger.debug("ConnectionInfoWidget._delayed_init starting")
        try:
            self._initialized = True
            self.update_connection_info()
        except Exception as e:
            logger.error("ConnectionInfoWidget._delayed_init failed: %s", e, exc_info=True)
            self.network_info_text.setText(f"Error loading network info: {e}")
        logger.debug("ConnectionInfoWidget._delayed_init complete")

    def init_ui(self):
        """Initialize user interface"""
        layout = QVBoxLayout(self)

        # Worker Info Group
        worker_group = QGroupBox("Worker Information")
        worker_layout = QGridLayout(worker_group)

        worker_layout.addWidget(QLabel("Worker ID:"), 0, 0)
        self.worker_id_label = QLabel(self.worker_id)
        self.worker_id_label.setStyleSheet("font-weight: bold; font-family: monospace;")
        self.worker_id_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        worker_layout.addWidget(self.worker_id_label, 0, 1)

        copy_worker_id_btn = QPushButton("Copy")
        copy_worker_id_btn.setMaximumWidth(80)
        copy_worker_id_btn.clicked.connect(lambda: self._copy_to_clipboard(self.worker_id))
        worker_layout.addWidget(copy_worker_id_btn, 0, 2)

        worker_layout.addWidget(QLabel("Port:"), 1, 0)
        self.port_label = QLabel(str(self.port))
        self.port_label.setStyleSheet("font-weight: bold;")
        worker_layout.addWidget(self.port_label, 1, 1)

        layout.addWidget(worker_group)

        # Platform Info Group
        platform_group = QGroupBox("Platform Information")
        platform_layout = QGridLayout(platform_group)

        platform_layout.addWidget(QLabel("System:"), 0, 0)
        self.system_label = QLabel("Loading...")
        platform_layout.addWidget(self.system_label, 0, 1)

        platform_layout.addWidget(QLabel("NPU Status:"), 1, 0)
        self.npu_status_label = QLabel("Detecting...")
        platform_layout.addWidget(self.npu_status_label, 1, 1)

        layout.addWidget(platform_group)

        # Network Interfaces Group
        network_group = QGroupBox("Network Interfaces")
        network_layout = QVBoxLayout(network_group)

        self.network_info_text = QTextEdit()
        self.network_info_text.setReadOnly(True)
        self.network_info_text.setMaximumHeight(120)
        self.network_info_text.setStyleSheet("font-family: monospace; font-size: 10pt;")
        network_layout.addWidget(self.network_info_text)

        copy_network_btn = QPushButton("Copy All Network Info")
        copy_network_btn.clicked.connect(self._copy_network_info)
        network_layout.addWidget(copy_network_btn)

        layout.addWidget(network_group)

        # Backend Registration Group
        registration_group = QGroupBox("Add to Backend Settings")
        registration_layout = QVBoxLayout(registration_group)

        # Primary endpoint
        endpoint_layout = QHBoxLayout()
        endpoint_layout.addWidget(QLabel("Registration URL:"))
        self.endpoint_label = QLabel("http://N/A:8082")
        self.endpoint_label.setStyleSheet("font-weight: bold; font-family: monospace;")
        self.endpoint_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        endpoint_layout.addWidget(self.endpoint_label)
        endpoint_layout.addStretch()

        copy_endpoint_btn = QPushButton("Copy URL")
        copy_endpoint_btn.clicked.connect(self._copy_endpoint)
        endpoint_layout.addWidget(copy_endpoint_btn)

        registration_layout.addLayout(endpoint_layout)

        # Health check URL
        health_layout = QHBoxLayout()
        health_layout.addWidget(QLabel("Health Check:"))
        self.health_label = QLabel("http://N/A:8082/health")
        self.health_label.setStyleSheet("font-family: monospace;")
        self.health_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        health_layout.addWidget(self.health_label)
        health_layout.addStretch()

        copy_health_btn = QPushButton("Copy URL")
        copy_health_btn.clicked.connect(self._copy_health_url)
        health_layout.addWidget(copy_health_btn)

        registration_layout.addLayout(health_layout)

        # Configuration snippet
        registration_layout.addWidget(QLabel("Configuration Snippet:"))
        self.config_text = QTextEdit()
        self.config_text.setReadOnly(True)
        self.config_text.setMaximumHeight(150)
        self.config_text.setStyleSheet("font-family: monospace; font-size: 9pt; background-color: #f5f5f5;")
        registration_layout.addWidget(self.config_text)

        copy_config_btn = QPushButton("Copy Configuration")
        copy_config_btn.clicked.connect(self._copy_config)
        registration_layout.addWidget(copy_config_btn)

        layout.addWidget(registration_group)

        # Refresh button at bottom
        refresh_layout = QHBoxLayout()
        refresh_layout.addStretch()
        refresh_btn = QPushButton("🔄 Refresh Network Info")
        refresh_btn.clicked.connect(self.update_connection_info)
        refresh_layout.addWidget(refresh_btn)
        layout.addLayout(refresh_layout)

        layout.addStretch()

    @Slot()
    def update_connection_info(self):
        """Update all connection information"""
        try:
            # Get network interfaces
            interfaces = get_network_interfaces()
            platform_info = get_platform_info()
            primary_ip = get_primary_ip()
        except Exception as e:
            # Handle errors gracefully
            QMessageBox.warning(
                self,
                "Network Info Error",
                f"Failed to retrieve network information:\n{str(e)}\n\nUsing fallback mode."
            )
            interfaces = []
            platform_info = {"system": "Unknown", "npu_detected": False}
            primary_ip = "Unknown"

        # Update worker ID if available
        if hasattr(self, 'worker_id') and self.worker_id != "N/A":
            self.worker_id_label.setText(self.worker_id)

        # Update platform info
        system = platform_info.get('system', 'Unknown')
        release = platform_info.get('release', '')
        npu_detected = platform_info.get('npu_detected', False)

        self.system_label.setText(f"{system} {release}")

        if npu_detected:
            self.npu_status_label.setText("✓ NPU Detected")
            self.npu_status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.npu_status_label.setText("✗ CPU Only")
            self.npu_status_label.setStyleSheet("color: orange; font-weight: bold;")

        # Update network interfaces
        network_text = ""
        if interfaces:
            for iface in interfaces:
                iface_type = iface['type']
                iface_name = iface['interface']
                iface_ip = iface['ip']
                primary_mark = " ★" if iface.get('is_primary') else ""
                network_text += f"• {iface_type:15} ({iface_name}): {iface_ip}{primary_mark}\n"
        else:
            network_text = "No network interfaces detected"

        self.network_info_text.setText(network_text.strip())

        # Update registration URLs
        if primary_ip:
            endpoint_url = f"http://{primary_ip}:{self.port}"
            health_url = f"{endpoint_url}/health"
            self.endpoint_label.setText(endpoint_url)
            self.health_label.setText(health_url)

            # Update configuration snippet
            config_snippet = get_registration_config(self.port)
            self.config_text.setText(config_snippet)
        else:
            self.endpoint_label.setText("http://N/A:8082")
            self.health_label.setText("http://N/A:8082/health")
            self.config_text.setText("# No network interface detected")

    def set_worker_id(self, worker_id: str):
        """Update worker ID"""
        self.worker_id = worker_id
        self.worker_id_label.setText(worker_id)

    def set_port(self, port: int):
        """Update port number"""
        self.port = port
        self.port_label.setText(str(port))
        self.update_connection_info()

    @Slot()
    def _copy_to_clipboard(self, text: str):
        """Copy text to clipboard"""
        try:
            from PySide6.QtGui import QGuiApplication
            clipboard = QGuiApplication.clipboard()
            clipboard.setText(text)
            QMessageBox.information(
                self,
                "Copied",
                "Text copied to clipboard!",
                QMessageBox.StandardButton.Ok
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Copy Failed",
                f"Failed to copy to clipboard: {e}",
                QMessageBox.StandardButton.Ok
            )

    @Slot()
    def _copy_endpoint(self):
        """Copy endpoint URL to clipboard"""
        self._copy_to_clipboard(self.endpoint_label.text())

    @Slot()
    def _copy_health_url(self):
        """Copy health check URL to clipboard"""
        self._copy_to_clipboard(self.health_label.text())

    @Slot()
    def _copy_network_info(self):
        """Copy all network info to clipboard"""
        self._copy_to_clipboard(self.network_info_text.toPlainText())

    @Slot()
    def _copy_config(self):
        """Copy configuration snippet to clipboard"""
        self._copy_to_clipboard(self.config_text.toPlainText())
