"""
Status Panel - NPU Worker Status Display
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox,
    QLabel, QProgressBar, QGridLayout
)
from PySide6.QtCore import Slot


class StatusPanel(QWidget):
    """Panel displaying NPU worker status and metrics"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        """Initialize user interface"""
        layout = QVBoxLayout(self)

        # NPU Status Group
        npu_group = QGroupBox("NPU Status")
        npu_layout = QGridLayout(npu_group)

        # NPU Available
        npu_layout.addWidget(QLabel("NPU Available:"), 0, 0)
        self.npu_available_label = QLabel("Unknown")
        self.npu_available_label.setStyleSheet("font-weight: bold;")
        self.npu_available_label.setWordWrap(True)
        self.npu_available_label.setMinimumWidth(150)
        npu_layout.addWidget(self.npu_available_label, 0, 1)

        # NPU Utilization
        npu_layout.addWidget(QLabel("NPU Utilization:"), 1, 0)
        self.npu_utilization = QProgressBar()
        self.npu_utilization.setRange(0, 100)
        self.npu_utilization.setValue(0)
        self.npu_utilization.setFormat("%v%")
        npu_layout.addWidget(self.npu_utilization, 1, 1)

        # Temperature
        npu_layout.addWidget(QLabel("Temperature:"), 2, 0)
        self.npu_temperature = QLabel("-- °C")
        npu_layout.addWidget(self.npu_temperature, 2, 1)

        # Power Usage
        npu_layout.addWidget(QLabel("Power Usage:"), 3, 0)
        self.npu_power = QLabel("-- W")
        npu_layout.addWidget(self.npu_power, 3, 1)

        layout.addWidget(npu_group)

        # Task Statistics Group
        task_group = QGroupBox("Task Statistics")
        task_layout = QGridLayout(task_group)

        # Tasks Completed
        task_layout.addWidget(QLabel("Tasks Completed:"), 0, 0)
        self.tasks_completed = QLabel("0")
        self.tasks_completed.setStyleSheet("color: green; font-weight: bold;")
        task_layout.addWidget(self.tasks_completed, 0, 1)

        # Tasks Failed
        task_layout.addWidget(QLabel("Tasks Failed:"), 1, 0)
        self.tasks_failed = QLabel("0")
        self.tasks_failed.setStyleSheet("color: red; font-weight: bold;")
        task_layout.addWidget(self.tasks_failed, 1, 1)

        # Average Response Time
        task_layout.addWidget(QLabel("Avg Response Time:"), 2, 0)
        self.avg_response_time = QLabel("-- ms")
        task_layout.addWidget(self.avg_response_time, 2, 1)

        # Embedding Generations
        task_layout.addWidget(QLabel("Embeddings Generated:"), 3, 0)
        self.embeddings_generated = QLabel("0")
        task_layout.addWidget(self.embeddings_generated, 3, 1)

        # Semantic Searches
        task_layout.addWidget(QLabel("Semantic Searches:"), 4, 0)
        self.semantic_searches = QLabel("0")
        task_layout.addWidget(self.semantic_searches, 4, 1)

        layout.addWidget(task_group)

        # Loaded Models Group
        model_group = QGroupBox("Loaded Models")
        model_layout = QVBoxLayout(model_group)

        self.loaded_models_label = QLabel("No models loaded")
        self.loaded_models_label.setWordWrap(True)
        model_layout.addWidget(self.loaded_models_label)

        layout.addWidget(model_group)

        layout.addStretch()

    @Slot(dict)
    def update_status(self, metrics: dict):
        """Update status display with new metrics"""
        # Update NPU status
        npu_available = metrics.get('npu_available', False)
        if npu_available:
            self.npu_available_label.setText("✓ Yes")
            self.npu_available_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.npu_available_label.setText("✗ No (CPU Fallback)")
            self.npu_available_label.setStyleSheet("color: orange; font-weight: bold;")

        # Update NPU metrics
        npu_metrics = metrics.get('npu_metrics', {})
        utilization = npu_metrics.get('utilization_percent', 0)
        self.npu_utilization.setValue(int(utilization))

        temperature = npu_metrics.get('temperature_c', 0)
        self.npu_temperature.setText(f"{temperature:.1f} °C")

        power = npu_metrics.get('power_usage_w', 0)
        self.npu_power.setText(f"{power:.1f} W")

        # Update task statistics
        stats = metrics.get('stats', {})
        self.tasks_completed.setText(str(stats.get('tasks_completed', 0)))
        self.tasks_failed.setText(str(stats.get('tasks_failed', 0)))

        avg_time = stats.get('average_response_time_ms', 0)
        self.avg_response_time.setText(f"{avg_time:.2f} ms")

        self.embeddings_generated.setText(str(stats.get('embedding_generations', 0)))
        self.semantic_searches.setText(str(stats.get('semantic_searches', 0)))

        # Update loaded models
        loaded_models = metrics.get('loaded_models', [])
        if loaded_models:
            models_text = "\n".join([f"• {model}" for model in loaded_models])
            self.loaded_models_label.setText(models_text)
        else:
            self.loaded_models_label.setText("No models loaded")
