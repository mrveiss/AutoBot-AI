# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Benchmark Widget - NPU Performance Benchmarking

Issue #640: Provides GUI interface for running NPU benchmarks
and displaying performance metrics.
"""

import logging
import time
from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QSpinBox, QComboBox,
    QProgressBar, QTextEdit, QGridLayout, QFrame
)
from PySide6.QtCore import Qt, Signal, Slot, QThread
from PySide6.QtGui import QFont

logger = logging.getLogger(__name__)


class BenchmarkWorker(QThread):
    """Background thread for running benchmarks"""

    progress_updated = Signal(int, str)  # percent, message
    result_ready = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, api_url: str, num_requests: int, batch_size: int, model_name: str):
        super().__init__()
        self.api_url = api_url
        self.num_requests = num_requests
        self.batch_size = batch_size
        self.model_name = model_name

    def run(self):
        """Run benchmark"""
        try:
            import requests

            results = {
                "total_requests": self.num_requests,
                "batch_size": self.batch_size,
                "model": self.model_name,
                "successful": 0,
                "failed": 0,
                "latencies": [],
                "start_time": time.time(),
            }

            # Test texts of varying lengths
            test_texts = [
                "Hello world",
                "The quick brown fox jumps over the lazy dog",
                "Machine learning is a subset of artificial intelligence that enables systems to learn from data",
                "OpenVINO is an open-source toolkit for optimizing and deploying deep learning models",
            ]

            for i in range(self.num_requests):
                try:
                    # Select test text (rotate through options)
                    text = test_texts[i % len(test_texts)]
                    batch = [text] * self.batch_size

                    start = time.time()
                    response = requests.post(
                        f"{self.api_url}/embedding/generate",
                        json=batch,
                        params={"model_name": self.model_name},
                        timeout=30
                    )
                    latency = (time.time() - start) * 1000

                    if response.status_code == 200:
                        results["successful"] += 1
                        results["latencies"].append(latency)
                    else:
                        results["failed"] += 1

                except Exception as e:
                    results["failed"] += 1
                    logger.warning(f"Benchmark request failed: {e}")

                # Update progress
                progress = int((i + 1) / self.num_requests * 100)
                self.progress_updated.emit(progress, f"Request {i + 1}/{self.num_requests}")

            # Calculate statistics
            results["end_time"] = time.time()
            results["total_time"] = results["end_time"] - results["start_time"]

            if results["latencies"]:
                results["avg_latency_ms"] = sum(results["latencies"]) / len(results["latencies"])
                results["min_latency_ms"] = min(results["latencies"])
                results["max_latency_ms"] = max(results["latencies"])
                results["requests_per_second"] = results["successful"] / results["total_time"]
                results["p50_latency_ms"] = sorted(results["latencies"])[len(results["latencies"]) // 2]
                results["p95_latency_ms"] = sorted(results["latencies"])[int(len(results["latencies"]) * 0.95)]
            else:
                results["avg_latency_ms"] = 0
                results["min_latency_ms"] = 0
                results["max_latency_ms"] = 0
                results["requests_per_second"] = 0
                results["p50_latency_ms"] = 0
                results["p95_latency_ms"] = 0

            self.result_ready.emit(results)

        except Exception as e:
            logger.error(f"Benchmark failed: {e}", exc_info=True)
            self.error_occurred.emit(str(e))


class BenchmarkWidget(QWidget):
    """Widget for running and displaying NPU benchmarks"""

    def __init__(self, api_url: str = "http://localhost:8082", parent=None):
        super().__init__(parent)
        self.api_url = api_url
        self._benchmark_worker: Optional[BenchmarkWorker] = None
        self._last_results: Optional[Dict] = None
        self.init_ui()

    def init_ui(self):
        """Initialize user interface"""
        layout = QVBoxLayout(self)

        # Configuration Group
        config_group = QGroupBox("Benchmark Configuration")
        config_layout = QGridLayout(config_group)

        # Number of requests
        config_layout.addWidget(QLabel("Number of Requests:"), 0, 0)
        self.num_requests_spin = QSpinBox()
        self.num_requests_spin.setRange(10, 1000)
        self.num_requests_spin.setValue(100)
        self.num_requests_spin.setSingleStep(10)
        config_layout.addWidget(self.num_requests_spin, 0, 1)

        # Batch size
        config_layout.addWidget(QLabel("Batch Size:"), 0, 2)
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(1, 32)
        self.batch_size_spin.setValue(1)
        config_layout.addWidget(self.batch_size_spin, 0, 3)

        # Model selection
        config_layout.addWidget(QLabel("Model:"), 1, 0)
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "nomic-embed-text",
            "all-MiniLM-L6-v2",
            "bge-small-en-v1.5"
        ])
        config_layout.addWidget(self.model_combo, 1, 1, 1, 3)

        layout.addWidget(config_group)

        # Control buttons
        button_layout = QHBoxLayout()

        self.run_btn = QPushButton("▶ Run Benchmark")
        self.run_btn.setMinimumWidth(150)
        self.run_btn.clicked.connect(self.run_benchmark)
        button_layout.addWidget(self.run_btn)

        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.setMinimumWidth(100)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_benchmark)
        button_layout.addWidget(self.stop_btn)

        button_layout.addStretch()

        self.refresh_device_btn = QPushButton("🔄 Refresh Device Info")
        self.refresh_device_btn.clicked.connect(self.refresh_device_info)
        button_layout.addWidget(self.refresh_device_btn)

        layout.addLayout(button_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)

        # Device Info Group
        device_group = QGroupBox("Device Information")
        device_layout = QGridLayout(device_group)

        device_layout.addWidget(QLabel("Selected Device:"), 0, 0)
        self.device_label = QLabel("Unknown")
        self.device_label.setStyleSheet("font-weight: bold;")
        self.device_label.setWordWrap(True)
        self.device_label.setMinimumWidth(200)
        device_layout.addWidget(self.device_label, 0, 1)

        device_layout.addWidget(QLabel("Available Devices:"), 1, 0)
        self.available_devices_label = QLabel("...")
        self.available_devices_label.setWordWrap(True)
        self.available_devices_label.setMinimumWidth(200)
        device_layout.addWidget(self.available_devices_label, 1, 1)

        device_layout.addWidget(QLabel("Real Inference:"), 2, 0)
        self.real_inference_label = QLabel("Unknown")
        self.real_inference_label.setWordWrap(True)
        device_layout.addWidget(self.real_inference_label, 2, 1)

        layout.addWidget(device_group)

        # Results Group
        results_group = QGroupBox("Benchmark Results")
        results_layout = QVBoxLayout(results_group)

        # Summary metrics in grid
        metrics_frame = QFrame()
        metrics_layout = QGridLayout(metrics_frame)
        metrics_layout.setSpacing(15)

        # Create metric cards
        self.metric_labels = {}
        metrics = [
            ("requests_per_second", "Requests/sec", "0.0"),
            ("avg_latency_ms", "Avg Latency", "0.0 ms"),
            ("p50_latency_ms", "P50 Latency", "0.0 ms"),
            ("p95_latency_ms", "P95 Latency", "0.0 ms"),
            ("successful", "Successful", "0"),
            ("failed", "Failed", "0"),
        ]

        for i, (key, label, default) in enumerate(metrics):
            row, col = divmod(i, 3)
            frame = QFrame()
            frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
            frame_layout = QVBoxLayout(frame)

            title = QLabel(label)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            frame_layout.addWidget(title)

            value = QLabel(default)
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setFont(QFont("", 14, QFont.Weight.Bold))
            self.metric_labels[key] = value
            frame_layout.addWidget(value)

            metrics_layout.addWidget(frame, row, col)

        results_layout.addWidget(metrics_frame)

        # Detailed output
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMaximumHeight(150)
        self.output_text.setFont(QFont("Consolas", 9))
        results_layout.addWidget(self.output_text)

        layout.addWidget(results_group)

        layout.addStretch()

        # Initial device info fetch
        self.refresh_device_info()

    def set_api_url(self, url: str):
        """Update API URL"""
        self.api_url = url

    @Slot()
    def run_benchmark(self):
        """Start benchmark"""
        if self._benchmark_worker and self._benchmark_worker.isRunning():
            return

        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setVisible(True)
        self.output_text.clear()
        self.output_text.append("Starting benchmark...\n")

        self._benchmark_worker = BenchmarkWorker(
            self.api_url,
            self.num_requests_spin.value(),
            self.batch_size_spin.value(),
            self.model_combo.currentText()
        )
        self._benchmark_worker.progress_updated.connect(self._on_progress)
        self._benchmark_worker.result_ready.connect(self._on_result)
        self._benchmark_worker.error_occurred.connect(self._on_error)
        self._benchmark_worker.start()

    @Slot()
    def stop_benchmark(self):
        """Stop running benchmark"""
        if self._benchmark_worker and self._benchmark_worker.isRunning():
            self._benchmark_worker.terminate()
            self._benchmark_worker.wait()
        self._reset_ui()

    @Slot(int, str)
    def _on_progress(self, percent: int, message: str):
        """Handle progress update"""
        self.progress_bar.setValue(percent)
        self.progress_label.setText(message)

    @Slot(dict)
    def _on_result(self, results: dict):
        """Handle benchmark results"""
        self._last_results = results
        self._reset_ui()

        # Update metric labels
        self.metric_labels["requests_per_second"].setText(f"{results.get('requests_per_second', 0):.1f}")
        self.metric_labels["avg_latency_ms"].setText(f"{results.get('avg_latency_ms', 0):.1f} ms")
        self.metric_labels["p50_latency_ms"].setText(f"{results.get('p50_latency_ms', 0):.1f} ms")
        self.metric_labels["p95_latency_ms"].setText(f"{results.get('p95_latency_ms', 0):.1f} ms")
        self.metric_labels["successful"].setText(str(results.get('successful', 0)))
        self.metric_labels["failed"].setText(str(results.get('failed', 0)))

        # Color failed count
        if results.get('failed', 0) > 0:
            self.metric_labels["failed"].setStyleSheet("color: red;")
        else:
            self.metric_labels["failed"].setStyleSheet("color: green;")

        # Detailed output
        output = f"""
Benchmark Complete
==================
Model: {results.get('model', 'N/A')}
Total Requests: {results.get('total_requests', 0)}
Batch Size: {results.get('batch_size', 1)}
Total Time: {results.get('total_time', 0):.2f}s

Performance
-----------
Requests/sec: {results.get('requests_per_second', 0):.1f}
Avg Latency: {results.get('avg_latency_ms', 0):.1f} ms
Min Latency: {results.get('min_latency_ms', 0):.1f} ms
Max Latency: {results.get('max_latency_ms', 0):.1f} ms
P50 Latency: {results.get('p50_latency_ms', 0):.1f} ms
P95 Latency: {results.get('p95_latency_ms', 0):.1f} ms

Results
-------
Successful: {results.get('successful', 0)}
Failed: {results.get('failed', 0)}
Success Rate: {results.get('successful', 0) / max(results.get('total_requests', 1), 1) * 100:.1f}%
"""
        self.output_text.setPlainText(output)

    @Slot(str)
    def _on_error(self, error: str):
        """Handle benchmark error"""
        self._reset_ui()
        self.output_text.append(f"\n❌ Benchmark Error: {error}")

    def _reset_ui(self):
        """Reset UI after benchmark"""
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)

    @Slot()
    def refresh_device_info(self):
        """Fetch and display device information"""
        try:
            import requests
            response = requests.get(f"{self.api_url}/device-info", timeout=5)
            if response.status_code == 200:
                info = response.json()
                model_manager = info.get("model_manager", {})

                # Use full device name if available, fallback to selected_device
                device = (model_manager.get("selected_device_full_name") or
                          model_manager.get("device_name") or
                          info.get("selected_device", "Unknown"))
                device_type = info.get("selected_device", "Unknown")

                # Build available devices with full names if present
                # device_full_names is inside model_manager
                device_full_names = model_manager.get("device_full_names", {})
                openvino_devices = model_manager.get("openvino_devices", [])

                if device_full_names and openvino_devices:
                    available_list = []
                    for dev in openvino_devices:
                        full_name = device_full_names.get(dev, dev)
                        available_list.append(f"{dev}: {full_name}")
                    available = "\n".join(available_list)
                else:
                    available = ", ".join(info.get("available_providers", []))

                real_inference = info.get("real_inference_enabled", False)

                self.device_label.setText(device)
                self.available_devices_label.setText(available or "None detected")

                if real_inference:
                    self.real_inference_label.setText("✅ Enabled")
                    self.real_inference_label.setStyleSheet("color: green; font-weight: bold;")
                else:
                    self.real_inference_label.setText("❌ Mock Mode")
                    self.real_inference_label.setStyleSheet("color: orange; font-weight: bold;")

                # Color device based on type
                if device_type == "NPU" or "NPU" in device:
                    self.device_label.setStyleSheet("color: green; font-weight: bold;")
                elif device_type == "GPU" or "GPU" in device:
                    self.device_label.setStyleSheet("color: blue; font-weight: bold;")
                else:
                    self.device_label.setStyleSheet("color: orange; font-weight: bold;")

            else:
                self.device_label.setText("Error fetching")
                self.available_devices_label.setText("N/A")
                self.real_inference_label.setText("N/A")

        except Exception as e:
            logger.warning(f"Failed to fetch device info: {e}")
            self.device_label.setText("Offline")
            self.available_devices_label.setText("Worker not responding")
            self.real_inference_label.setText("N/A")
