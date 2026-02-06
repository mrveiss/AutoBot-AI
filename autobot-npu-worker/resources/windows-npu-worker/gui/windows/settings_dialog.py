"""
Settings Dialog - Configuration Management
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QTextEdit, QLabel, QMessageBox,
    QFileDialog, QGroupBox, QFormLayout, QLineEdit,
    QSpinBox, QComboBox, QCheckBox
)
from PySide6.QtCore import Slot
from PySide6.QtGui import QFont


class SettingsDialog(QDialog):
    """Settings dialog for NPU worker configuration"""

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.init_ui()
        self.load_configuration()

    def init_ui(self):
        """Initialize user interface"""
        self.setWindowTitle("NPU Worker Settings")
        self.setMinimumSize(700, 500)

        layout = QVBoxLayout(self)

        # Tab widget for different settings categories
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # YAML editor tab
        yaml_tab = self.create_yaml_editor_tab()
        self.tabs.addTab(yaml_tab, "YAML Editor")

        # Service settings tab
        service_tab = self.create_service_settings_tab()
        self.tabs.addTab(service_tab, "Service")

        # NPU settings tab
        npu_tab = self.create_npu_settings_tab()
        self.tabs.addTab(npu_tab, "NPU Configuration")

        # Logging settings tab
        logging_tab = self.create_logging_settings_tab()
        self.tabs.addTab(logging_tab, "Logging")

        # Button box
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save_configuration)
        button_layout.addWidget(self.save_btn)

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self.apply_configuration)
        button_layout.addWidget(self.apply_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def create_yaml_editor_tab(self):
        """Create YAML editor tab"""
        tab = QGroupBox()
        layout = QVBoxLayout(tab)

        # Info label
        info_label = QLabel(
            "⚠️ Advanced: Direct YAML configuration editing. "
            "Use the other tabs for guided configuration."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # YAML text editor
        self.yaml_editor = QTextEdit()
        self.yaml_editor.setFont(QFont("Courier New", 10))
        layout.addWidget(self.yaml_editor)

        # Editor controls
        editor_controls = QHBoxLayout()

        load_btn = QPushButton("Load from File")
        load_btn.clicked.connect(self.load_yaml_file)
        editor_controls.addWidget(load_btn)

        validate_btn = QPushButton("Validate YAML")
        validate_btn.clicked.connect(self.validate_yaml)
        editor_controls.addWidget(validate_btn)

        editor_controls.addStretch()

        layout.addLayout(editor_controls)

        return tab

    def create_service_settings_tab(self):
        """Create service settings tab"""
        tab = QGroupBox()
        layout = QFormLayout(tab)

        # Host
        self.service_host = QLineEdit()
        layout.addRow("Host:", self.service_host)

        # Port
        self.service_port = QSpinBox()
        self.service_port.setRange(1024, 65535)
        self.service_port.setValue(8082)
        layout.addRow("Port:", self.service_port)

        # Workers
        self.service_workers = QSpinBox()
        self.service_workers.setRange(1, 8)
        self.service_workers.setValue(1)
        layout.addRow("Workers:", self.service_workers)

        # Backend host
        self.backend_host = QLineEdit()
        layout.addRow("Backend Host:", self.backend_host)

        # Backend port
        self.backend_port = QSpinBox()
        self.backend_port.setRange(1024, 65535)
        self.backend_port.setValue(8001)
        layout.addRow("Backend Port:", self.backend_port)

        # Redis host
        self.redis_host = QLineEdit()
        layout.addRow("Redis Host:", self.redis_host)

        # Redis port
        self.redis_port = QSpinBox()
        self.redis_port.setRange(1024, 65535)
        self.redis_port.setValue(6379)
        layout.addRow("Redis Port:", self.redis_port)

        return tab

    def create_npu_settings_tab(self):
        """Create NPU settings tab"""
        tab = QGroupBox()
        layout = QFormLayout(tab)

        # NPU enabled
        self.npu_enabled = QCheckBox("Enable NPU Acceleration")
        self.npu_enabled.setChecked(True)
        layout.addRow("NPU:", self.npu_enabled)

        # CPU fallback
        self.npu_fallback = QCheckBox("Fallback to CPU if NPU unavailable")
        self.npu_fallback.setChecked(True)
        layout.addRow("Fallback:", self.npu_fallback)

        # Precision
        self.npu_precision = QComboBox()
        self.npu_precision.addItems(["INT8", "FP16", "FP32"])
        layout.addRow("Precision:", self.npu_precision)

        # Batch size
        self.npu_batch_size = QSpinBox()
        self.npu_batch_size.setRange(1, 128)
        self.npu_batch_size.setValue(32)
        layout.addRow("Batch Size:", self.npu_batch_size)

        # Streams
        self.npu_streams = QSpinBox()
        self.npu_streams.setRange(1, 8)
        self.npu_streams.setValue(2)
        layout.addRow("Streams:", self.npu_streams)

        # Threads
        self.npu_threads = QSpinBox()
        self.npu_threads.setRange(1, 16)
        self.npu_threads.setValue(4)
        layout.addRow("Threads:", self.npu_threads)

        return tab

    def create_logging_settings_tab(self):
        """Create logging settings tab"""
        tab = QGroupBox()
        layout = QFormLayout(tab)

        # Log level
        self.log_level = QComboBox()
        self.log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.log_level.setCurrentText("INFO")
        layout.addRow("Log Level:", self.log_level)

        # Log directory
        log_dir_layout = QHBoxLayout()
        self.log_directory = QLineEdit()
        log_dir_layout.addWidget(self.log_directory)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_log_directory)
        log_dir_layout.addWidget(browse_btn)

        layout.addRow("Log Directory:", log_dir_layout)

        # Max log size
        self.log_max_size = QSpinBox()
        self.log_max_size.setRange(1, 1000)
        self.log_max_size.setValue(100)
        self.log_max_size.setSuffix(" MB")
        layout.addRow("Max Log Size:", self.log_max_size)

        # Backup count
        self.log_backup_count = QSpinBox()
        self.log_backup_count.setRange(1, 20)
        self.log_backup_count.setValue(5)
        layout.addRow("Backup Count:", self.log_backup_count)

        return tab

    @Slot()
    def load_configuration(self):
        """Load configuration from file"""
        try:
            config = self.config_manager.load_config()

            # Load YAML editor
            self.yaml_editor.setPlainText(self.config_manager.get_yaml_text())

            # Load service settings
            service = config.get('service', {})
            self.service_host.setText(service.get('host', '0.0.0.0'))
            self.service_port.setValue(service.get('port', 8082))
            self.service_workers.setValue(service.get('workers', 1))

            backend = config.get('backend', {})
            self.backend_host.setText(backend.get('host', ''))
            self.backend_port.setValue(backend.get('port', 8001))

            redis = config.get('redis', {})
            self.redis_host.setText(redis.get('host', ''))
            self.redis_port.setValue(redis.get('port', 6379))

            # Load NPU settings
            npu = config.get('npu', {})
            self.npu_enabled.setChecked(npu.get('enabled', True))
            self.npu_fallback.setChecked(npu.get('fallback_to_cpu', True))

            optimization = npu.get('optimization', {})
            precision = optimization.get('precision', 'INT8')
            self.npu_precision.setCurrentText(precision)
            self.npu_batch_size.setValue(optimization.get('batch_size', 32))
            self.npu_streams.setValue(optimization.get('num_streams', 2))
            self.npu_threads.setValue(optimization.get('num_threads', 4))

            # Load logging settings
            logging = config.get('logging', {})
            self.log_level.setCurrentText(logging.get('level', 'INFO'))
            self.log_directory.setText(logging.get('directory', 'logs'))
            self.log_max_size.setValue(logging.get('max_size_mb', 100))
            self.log_backup_count.setValue(logging.get('backup_count', 5))

        except Exception as e:
            QMessageBox.warning(
                self,
                "Load Error",
                f"Failed to load configuration: {e}"
            )

    @Slot()
    def save_configuration(self):
        """Save configuration and close dialog"""
        if self.apply_configuration():
            self.accept()

    @Slot()
    def apply_configuration(self):
        """Apply configuration changes"""
        try:
            # Get current tab
            current_tab = self.tabs.currentIndex()

            if current_tab == 0:
                # YAML editor - save raw YAML
                yaml_text = self.yaml_editor.toPlainText()
                if not self.config_manager.validate_yaml(yaml_text):
                    QMessageBox.warning(
                        self,
                        "Invalid YAML",
                        "The YAML configuration is invalid. Please fix errors before saving."
                    )
                    return False

                self.config_manager.save_yaml(yaml_text)
            else:
                # Form-based settings - build config dict
                config = self.build_config_from_forms()
                self.config_manager.save_config(config)

            QMessageBox.information(
                self,
                "Success",
                "Configuration saved successfully."
            )
            return True

        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save configuration: {e}"
            )
            return False

    def build_config_from_forms(self):
        """Build configuration dictionary from form inputs"""
        config = {}

        # Service settings
        config['service'] = {
            'host': self.service_host.text(),
            'port': self.service_port.value(),
            'workers': self.service_workers.value(),
        }

        config['backend'] = {
            'host': self.backend_host.text(),
            'port': self.backend_port.value(),
        }

        config['redis'] = {
            'host': self.redis_host.text(),
            'port': self.redis_port.value(),
        }

        # NPU settings
        config['npu'] = {
            'enabled': self.npu_enabled.isChecked(),
            'fallback_to_cpu': self.npu_fallback.isChecked(),
            'optimization': {
                'precision': self.npu_precision.currentText(),
                'batch_size': self.npu_batch_size.value(),
                'num_streams': self.npu_streams.value(),
                'num_threads': self.npu_threads.value(),
            }
        }

        # Logging settings
        config['logging'] = {
            'level': self.log_level.currentText(),
            'directory': self.log_directory.text(),
            'max_size_mb': self.log_max_size.value(),
            'backup_count': self.log_backup_count.value(),
        }

        return config

    @Slot()
    def load_yaml_file(self):
        """Load YAML from file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load YAML Configuration",
            "",
            "YAML Files (*.yaml *.yml);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    yaml_text = f.read()
                self.yaml_editor.setPlainText(yaml_text)
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Load Error",
                    f"Failed to load file: {e}"
                )

    @Slot()
    def validate_yaml(self):
        """Validate YAML content"""
        yaml_text = self.yaml_editor.toPlainText()
        if self.config_manager.validate_yaml(yaml_text):
            QMessageBox.information(
                self,
                "Valid YAML",
                "The YAML configuration is valid."
            )
        else:
            QMessageBox.warning(
                self,
                "Invalid YAML",
                "The YAML configuration contains errors."
            )

    @Slot()
    def browse_log_directory(self):
        """Browse for log directory"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Log Directory",
            self.log_directory.text()
        )

        if directory:
            self.log_directory.setText(directory)
