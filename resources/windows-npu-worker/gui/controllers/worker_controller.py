"""
Worker Controller - NPU Worker Process Management
"""

import subprocess
import requests
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot, QThread
from typing import Optional


class MetricsWorker(QThread):
    """Background thread for fetching metrics"""

    metrics_fetched = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, api_url: str):
        super().__init__()
        self.api_url = api_url
        self.running = True

    def run(self):
        """Fetch metrics from API"""
        try:
            response = requests.get(
                f"{self.api_url}/health",
                timeout=5
            )
            if response.status_code == 200:
                self.metrics_fetched.emit(response.json())
            else:
                self.error_occurred.emit(f"API returned status {response.status_code}")
        except requests.RequestException as e:
            self.error_occurred.emit(f"Failed to fetch metrics: {e}")


class WorkerController(QObject):
    """Controller for managing NPU worker process"""

    status_changed = Signal(str)
    error_occurred = Signal(str)
    metrics_updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self.worker_process: Optional[subprocess.Popen] = None
        self.api_url = "http://localhost:8082"
        self.worker_status = "stopped"

        # Paths
        self.worker_dir = Path(__file__).parent.parent.parent
        self.worker_script = self.worker_dir / "app" / "npu_worker.py"
        self.python_exe = self.worker_dir / "venv" / "Scripts" / "python.exe"

    def get_status(self) -> str:
        """Get current worker status"""
        # Try to ping the API to confirm it's really running
        try:
            response = requests.get(f"{self.api_url}/health", timeout=2)
            if response.status_code == 200:
                self.worker_status = "running"
                return "running"
        except requests.RequestException:
            pass

        # Check if process exists
        if self.worker_process and self.worker_process.poll() is None:
            self.worker_status = "running"
            return "running"

        self.worker_status = "stopped"
        return "stopped"

    @Slot()
    def start_worker(self):
        """Start NPU worker process"""
        try:
            # Check if already running
            if self.get_status() == "running":
                self.error_occurred.emit("Worker is already running")
                return

            # Check if worker script exists
            if not self.worker_script.exists():
                self.error_occurred.emit(f"Worker script not found: {self.worker_script}")
                return

            # Check if Python executable exists
            if not self.python_exe.exists():
                # Try system Python
                python_cmd = "python"
            else:
                python_cmd = str(self.python_exe)

            # Start worker process
            self.worker_process = subprocess.Popen(
                [python_cmd, str(self.worker_script)],
                cwd=str(self.worker_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )

            # Wait a moment for startup
            import time
            time.sleep(2)

            # Verify it started
            if self.get_status() == "running":
                self.worker_status = "running"
                self.status_changed.emit("running")
            else:
                self.error_occurred.emit("Worker failed to start")

        except Exception as e:
            self.error_occurred.emit(f"Failed to start worker: {e}")

    @Slot()
    def stop_worker(self):
        """Stop NPU worker process"""
        try:
            if self.worker_process and self.worker_process.poll() is None:
                self.worker_process.terminate()
                self.worker_process.wait(timeout=5)
                self.worker_process = None

            self.worker_status = "stopped"
            self.status_changed.emit("stopped")

        except Exception as e:
            self.error_occurred.emit(f"Failed to stop worker: {e}")

    @Slot()
    def restart_worker(self):
        """Restart NPU worker process"""
        self.stop_worker()
        import time
        time.sleep(1)
        self.start_worker()

    @Slot()
    def fetch_metrics(self):
        """Fetch metrics from worker API"""
        if self.get_status() != "running":
            return

        # Create worker thread to fetch metrics
        worker = MetricsWorker(self.api_url)
        worker.metrics_fetched.connect(self._on_metrics_fetched)
        worker.error_occurred.connect(self._on_metrics_error)
        worker.start()

    @Slot(dict)
    def _on_metrics_fetched(self, metrics: dict):
        """Handle fetched metrics"""
        # Also fetch detailed stats
        try:
            response = requests.get(f"{self.api_url}/stats", timeout=5)
            if response.status_code == 200:
                stats = response.json()
                # Merge metrics and stats
                combined = {**metrics, **stats}
                self.metrics_updated.emit(combined)
            else:
                self.metrics_updated.emit(metrics)
        except Exception:
            self.metrics_updated.emit(metrics)

    @Slot(str)
    def _on_metrics_error(self, error: str):
        """Handle metrics fetch error"""
        # Silently ignore - worker might be stopped
        pass
