"""
Metrics Display - Performance Metrics Visualization
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Slot
from PySide6.QtGui import QFont
from collections import deque
from datetime import datetime


class MetricsDisplay(QWidget):
    """Widget for displaying performance metrics"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.metrics_history = deque(maxlen=100)
        self.init_ui()

    def init_ui(self):
        """Initialize user interface"""
        layout = QVBoxLayout(self)

        # Performance Summary Group
        summary_group = QGroupBox("Performance Summary")
        summary_layout = QHBoxLayout(summary_group)

        # Cache statistics
        cache_box = QVBoxLayout()
        cache_box.addWidget(QLabel("Cache Statistics"))
        self.cache_size_label = QLabel("Size: 0")
        cache_box.addWidget(self.cache_size_label)
        self.cache_hits_label = QLabel("Hits: 0")
        cache_box.addWidget(self.cache_hits_label)
        self.cache_hit_rate_label = QLabel("Hit Rate: 0%")
        cache_box.addWidget(self.cache_hit_rate_label)
        summary_layout.addLayout(cache_box)

        # Worker info
        worker_box = QVBoxLayout()
        worker_box.addWidget(QLabel("Worker Information"))
        self.worker_id_label = QLabel("ID: Unknown")
        self.worker_id_label.setFont(QFont("Courier New", 9))
        worker_box.addWidget(self.worker_id_label)
        self.platform_label = QLabel("Platform: Unknown")
        worker_box.addWidget(self.platform_label)
        self.port_label = QLabel("Port: Unknown")
        worker_box.addWidget(self.port_label)
        summary_layout.addLayout(worker_box)

        layout.addWidget(summary_group)

        # Model Details Group
        model_group = QGroupBox("Model Details")
        model_layout = QVBoxLayout(model_group)

        self.model_table = QTableWidget()
        self.model_table.setColumnCount(5)
        self.model_table.setHorizontalHeaderLabels([
            "Model Name",
            "Device",
            "Size (MB)",
            "Precision",
            "Last Used"
        ])
        self.model_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.model_table.setAlternatingRowColors(True)
        model_layout.addWidget(self.model_table)

        layout.addWidget(model_group)

        # Recent Metrics Group
        metrics_group = QGroupBox("Recent Metrics History")
        metrics_layout = QVBoxLayout(metrics_group)

        self.metrics_table = QTableWidget()
        self.metrics_table.setColumnCount(5)
        self.metrics_table.setHorizontalHeaderLabels([
            "Time",
            "NPU %",
            "Temp °C",
            "Power W",
            "Tasks"
        ])
        self.metrics_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.metrics_table.setAlternatingRowColors(True)
        metrics_layout.addWidget(self.metrics_table)

        layout.addWidget(metrics_group)

    @Slot(dict)
    def update_metrics(self, metrics: dict):
        """Update metrics display"""
        # Update cache statistics
        cache_stats = metrics.get('cache_stats', {})
        cache_size = cache_stats.get('embedding_cache_size', 0)
        self.cache_size_label.setText(f"Size: {cache_size}")

        cache_hits = cache_stats.get('cache_hits', 0)
        self.cache_hits_label.setText(f"Hits: {cache_hits}")

        cache_hit_rate = cache_stats.get('cache_hit_rate', 0)
        self.cache_hit_rate_label.setText(f"Hit Rate: {cache_hit_rate:.1f}%")

        # Update worker info
        worker_id = metrics.get('worker_id', 'Unknown')
        self.worker_id_label.setText(f"ID: {worker_id}")

        platform = metrics.get('platform', 'Unknown')
        self.platform_label.setText(f"Platform: {platform}")

        port = metrics.get('port', 'Unknown')
        self.port_label.setText(f"Port: {port}")

        # Update model details table
        loaded_models = metrics.get('loaded_models', {})
        self.model_table.setRowCount(len(loaded_models))

        for row, (model_name, model_info) in enumerate(loaded_models.items()):
            self.model_table.setItem(row, 0, QTableWidgetItem(model_name))
            self.model_table.setItem(row, 1, QTableWidgetItem(
                model_info.get('device', 'Unknown')
            ))
            self.model_table.setItem(row, 2, QTableWidgetItem(
                str(model_info.get('size_mb', 0))
            ))
            self.model_table.setItem(row, 3, QTableWidgetItem(
                model_info.get('precision', 'Unknown')
            ))
            self.model_table.setItem(row, 4, QTableWidgetItem(
                model_info.get('last_used', 'Never')
            ))

        # Add to metrics history
        npu_metrics = metrics.get('npu_metrics', {})
        stats = metrics.get('stats', {})

        self.metrics_history.append({
            'time': datetime.now(),
            'npu_utilization': npu_metrics.get('utilization_percent', 0),
            'temperature': npu_metrics.get('temperature_c', 0),
            'power': npu_metrics.get('power_usage_w', 0),
            'tasks_completed': stats.get('tasks_completed', 0)
        })

        # Update metrics history table
        self.update_metrics_history_table()

    def update_metrics_history_table(self):
        """Update metrics history table"""
        history = list(self.metrics_history)
        history.reverse()  # Show most recent first

        self.metrics_table.setRowCount(min(len(history), 20))  # Show last 20

        for row, metrics in enumerate(history[:20]):
            time_str = metrics['time'].strftime("%H:%M:%S")
            self.metrics_table.setItem(row, 0, QTableWidgetItem(time_str))
            self.metrics_table.setItem(row, 1, QTableWidgetItem(
                f"{metrics['npu_utilization']:.1f}"
            ))
            self.metrics_table.setItem(row, 2, QTableWidgetItem(
                f"{metrics['temperature']:.1f}"
            ))
            self.metrics_table.setItem(row, 3, QTableWidgetItem(
                f"{metrics['power']:.1f}"
            ))
            self.metrics_table.setItem(row, 4, QTableWidgetItem(
                str(metrics['tasks_completed'])
            ))
