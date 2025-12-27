"""
Log Viewer - Real-time Log Display
"""

import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QComboBox, QLabel, QCheckBox,
    QFileDialog
)
from PySide6.QtCore import Signal, Slot, QThread, QTimer
from PySide6.QtGui import QFont, QTextCursor

logger = logging.getLogger(__name__)


class LogWatcher(QThread):
    """Thread for watching log file changes"""

    log_updated = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, log_file_path):
        super().__init__()
        self.log_file_path = Path(log_file_path)
        self.running = True
        self.last_position = 0
        logger.debug("LogWatcher created for: %s", self.log_file_path)

    def run(self):
        """Watch log file for changes"""
        logger.debug("LogWatcher.run() starting for: %s", self.log_file_path)
        while self.running:
            try:
                if self.log_file_path.exists():
                    with open(self.log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                        f.seek(self.last_position)
                        new_content = f.read()
                        if new_content:
                            self.log_updated.emit(new_content)
                            self.last_position = f.tell()
            except Exception as e:
                logger.error("LogWatcher error reading %s: %s", self.log_file_path, e)
                self.error_occurred.emit(str(e))

            self.msleep(500)  # Check every 500ms
        logger.debug("LogWatcher.run() finished for: %s", self.log_file_path)

    def stop(self):
        """Stop watching"""
        logger.debug("LogWatcher.stop() called")
        self.running = False


class LogViewer(QWidget):
    """Real-time log viewer widget"""

    def __init__(self, app_config, parent=None):
        super().__init__(parent)
        logger.debug("LogViewer.__init__ starting")
        self.app_config = app_config
        self.log_watcher = None
        self._initialized = False
        self.init_ui()
        logger.debug("LogViewer.__init__ complete")

    def init_ui(self):
        """Initialize user interface"""
        logger.debug("LogViewer.init_ui starting")
        layout = QVBoxLayout(self)

        # Controls
        controls = QHBoxLayout()

        # Log file selector
        controls.addWidget(QLabel("Log File:"))

        self.log_file_combo = QComboBox()
        self.log_file_combo.addItems([
            "app.log",
            "service.log",
            "error.log",
            "gui_crash.log"
        ])
        controls.addWidget(self.log_file_combo)

        controls.addStretch()

        # Auto-scroll checkbox
        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)
        controls.addWidget(self.auto_scroll)

        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_log_display)
        controls.addWidget(clear_btn)

        # Export button
        export_btn = QPushButton("Export...")
        export_btn.clicked.connect(self.export_logs)
        controls.addWidget(export_btn)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_logs)
        controls.addWidget(refresh_btn)

        layout.addLayout(controls)

        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Courier New", 9))
        self.log_display.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.log_display)

        # Status bar
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Ready")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        self.line_count_label = QLabel("Lines: 0")
        status_layout.addWidget(self.line_count_label)
        layout.addLayout(status_layout)

        # Connect signal AFTER UI is set up (avoid race condition)
        self.log_file_combo.currentTextChanged.connect(self.change_log_file)

        # Delay log watcher start to avoid crash during init
        # Use QTimer.singleShot to start after event loop is running
        QTimer.singleShot(100, self._delayed_init)
        logger.debug("LogViewer.init_ui complete")

    def _delayed_init(self):
        """Delayed initialization after event loop starts"""
        logger.debug("LogViewer._delayed_init starting")
        try:
            self._initialized = True
            self.start_watching("app.log")
            self.load_log_file("app.log")
        except Exception as e:
            logger.error("LogViewer._delayed_init failed: %s", e, exc_info=True)
            self.log_display.setPlainText(f"Error initializing log viewer: {e}")
        logger.debug("LogViewer._delayed_init complete")

    def get_log_path(self, log_filename):
        """Get full path to log file"""
        log_dir = self.app_config.get_log_directory()
        return log_dir / log_filename

    @Slot(str)
    def change_log_file(self, log_filename):
        """Change the log file being watched"""
        if not self._initialized:
            logger.debug("change_log_file called before init, ignoring")
            return
        logger.debug("Changing log file to: %s", log_filename)
        try:
            self.start_watching(log_filename)
            self.load_log_file(log_filename)
        except Exception as e:
            logger.error("Failed to change log file: %s", e, exc_info=True)
            self.log_display.setPlainText(f"Error loading log: {e}")

    def start_watching(self, log_filename):
        """Start watching a log file"""
        # Stop existing watcher
        if self.log_watcher:
            self.log_watcher.stop()
            self.log_watcher.wait()

        # Start new watcher
        log_path = self.get_log_path(log_filename)
        self.log_watcher = LogWatcher(log_path)
        self.log_watcher.log_updated.connect(self.append_log_content)
        self.log_watcher.start()

        self.status_label.setText(f"Watching: {log_filename}")

    def load_log_file(self, log_filename):
        """Load entire log file"""
        try:
            log_path = self.get_log_path(log_filename)

            if not log_path.exists():
                self.log_display.setPlainText(f"Log file not found: {log_path}")
                return

            with open(log_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.log_display.setPlainText(content)
                self.update_line_count()

                # Scroll to bottom if auto-scroll enabled
                if self.auto_scroll.isChecked():
                    self.scroll_to_bottom()

        except Exception as e:
            self.log_display.setPlainText(f"Error loading log: {e}")

    @Slot(str)
    def append_log_content(self, content):
        """Append new log content"""
        self.log_display.moveCursor(QTextCursor.MoveOperation.End)
        self.log_display.insertPlainText(content)
        self.update_line_count()

        # Auto-scroll to bottom if enabled
        if self.auto_scroll.isChecked():
            self.scroll_to_bottom()

    @Slot()
    def clear_log_display(self):
        """Clear log display"""
        self.log_display.clear()
        self.update_line_count()

    @Slot()
    def refresh_logs(self):
        """Refresh log display"""
        log_filename = self.log_file_combo.currentText()
        self.load_log_file(log_filename)

    @Slot()
    def export_logs(self):
        """Export logs to file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Logs",
            "",
            "Text Files (*.txt);;Log Files (*.log);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_display.toPlainText())
                self.status_label.setText(f"Exported to: {file_path}")
            except Exception as e:
                self.status_label.setText(f"Export failed: {e}")

    def scroll_to_bottom(self):
        """Scroll to bottom of log display"""
        scrollbar = self.log_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def update_line_count(self):
        """Update line count display"""
        line_count = self.log_display.document().lineCount()
        self.line_count_label.setText(f"Lines: {line_count}")

    def closeEvent(self, event):
        """Handle widget close"""
        if self.log_watcher:
            self.log_watcher.stop()
            self.log_watcher.wait()
        event.accept()
