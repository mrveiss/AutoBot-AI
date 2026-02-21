"""
Worker Controller - NPU Worker Process Management
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

import requests
from PySide6.QtCore import QObject, QThread, Signal, Slot

logger = logging.getLogger(__name__)


class StatusChecker(QThread):
    """Background thread for checking worker status without blocking UI"""

    status_checked = Signal(str)  # "running" or "stopped"

    def __init__(self, api_url: str, timeout: float = 5.0):
        super().__init__()
        self.api_url = api_url
        self.timeout = timeout

    def run(self):
        """Check if worker API is responding"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=self.timeout)
            if response.status_code == 200:
                self.status_checked.emit("running")
                return
        except requests.RequestException:
            pass
        self.status_checked.emit("stopped")


class MetricsWorker(QThread):
    """Background thread for fetching metrics"""

    metrics_fetched = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, api_url: str):
        super().__init__()
        self.api_url = api_url

    def run(self):
        """Fetch metrics from API"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=2)
            if response.status_code == 200:
                metrics = response.json()
                # Also try to get stats
                try:
                    stats_response = requests.get(f"{self.api_url}/stats", timeout=2)
                    if stats_response.status_code == 200:
                        metrics.update(stats_response.json())
                except Exception:
                    logger.debug("Suppressed exception in try block", exc_info=True)
                self.metrics_fetched.emit(metrics)
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
        logger.debug("WorkerController.__init__")
        self.worker_process: Optional[subprocess.Popen] = None
        self.api_url = "http://localhost:8082"
        self.worker_status = "unknown"  # Start as unknown until first check
        self._status_checker: Optional[StatusChecker] = None
        self._metrics_worker: Optional[MetricsWorker] = None

        # Paths
        self.worker_dir = Path(__file__).parent.parent.parent
        self.worker_script = self.worker_dir / "app" / "npu_worker.py"
        self.python_exe = self.worker_dir / "venv" / "Scripts" / "python.exe"

    def get_status(self) -> str:
        """Get cached worker status (non-blocking)"""
        # Return cached status - actual checking done async
        return self.worker_status

    def check_status_async(self):
        """Check worker status asynchronously (non-blocking)"""
        # Don't start new check if one is already running
        if self._status_checker is not None and self._status_checker.isRunning():
            return

        self._status_checker = StatusChecker(self.api_url, timeout=5.0)
        self._status_checker.status_checked.connect(self._on_status_checked)
        self._status_checker.start()

    @Slot(str)
    def _on_status_checked(self, status: str):
        """Handle async status check result"""
        old_status = self.worker_status
        self.worker_status = status
        if old_status != status:
            logger.debug("Status changed: %s -> %s", old_status, status)
            self.status_changed.emit(status)

    @Slot()
    def start_worker(self):
        """Start NPU worker process or Windows service"""
        from PySide6.QtCore import QTimer

        try:
            # Check if already running (use cached status)
            if self.worker_status == "running":
                self.error_occurred.emit("Worker is already running")
                return

            # Try to start the Windows service first (preferred method)
            if self._start_windows_service():
                logger.info("Started AutoBotNPUWorker Windows service")
                self.worker_status = "starting"
                QTimer.singleShot(3000, self._verify_worker_started)
                return

            # Fall back to starting as subprocess if service doesn't exist
            # Check if worker script exists
            if not self.worker_script.exists():
                self.error_occurred.emit(
                    f"Worker script not found: {self.worker_script}"
                )
                return

            # Check if Python executable exists
            if not self.python_exe.exists():
                # Try system Python
                python_cmd = "python"
            else:
                python_cmd = str(self.python_exe)

            logger.info(
                "Starting worker process: %s %s", python_cmd, self.worker_script
            )

            # Start worker process
            self.worker_process = subprocess.Popen(
                [python_cmd, str(self.worker_script)],
                cwd=str(self.worker_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if hasattr(subprocess, "CREATE_NO_WINDOW")
                    else 0
                ),
            )

            # Set status to starting and trigger async check after delay
            # Don't block the GUI - use QTimer for delayed verification
            self.worker_status = "starting"
            QTimer.singleShot(2000, self._verify_worker_started)

        except Exception as e:
            logger.error("Failed to start worker: %s", e, exc_info=True)
            self.error_occurred.emit(f"Failed to start worker: {e}")

    def _verify_worker_started(self):
        """Verify worker started after delay (called by QTimer)"""
        # Trigger async status check - result will come via _on_status_checked
        self.check_status_async()

    @Slot()
    def stop_worker(self):
        """Stop NPU worker process or Windows service"""
        try:
            # First, try to stop the Windows service (if running as service)
            service_stopped = self._stop_windows_service()

            # Also terminate any subprocess we started directly
            if self.worker_process and self.worker_process.poll() is None:
                self.worker_process.terminate()
                try:
                    self.worker_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.worker_process.kill()
                self.worker_process = None

            self.worker_status = "stopped"
            self.status_changed.emit("stopped")

            if service_stopped:
                logger.info("Windows service stopped successfully")

        except Exception as e:
            logger.error("Failed to stop worker: %s", e, exc_info=True)
            self.error_occurred.emit(f"Failed to stop worker: {e}")

    def _stop_windows_service(self) -> bool:
        """Stop the Windows service if it exists and is running.

        Returns:
            True if service was stopped, False if not running or doesn't exist
        """
        try:
            # Check if service exists
            result = subprocess.run(
                ["sc", "query", "AutoBotNPUWorker"],
                capture_output=True,
                text=True,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if hasattr(subprocess, "CREATE_NO_WINDOW")
                    else 0
                ),
            )

            if result.returncode != 0:
                logger.debug("AutoBotNPUWorker service not found")
                return False

            # Check if running
            if "RUNNING" not in result.stdout:
                logger.debug("AutoBotNPUWorker service not running")
                return False

            # Stop the service
            logger.info("Stopping AutoBotNPUWorker service...")
            stop_result = subprocess.run(
                ["sc", "stop", "AutoBotNPUWorker"],
                capture_output=True,
                text=True,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if hasattr(subprocess, "CREATE_NO_WINDOW")
                    else 0
                ),
            )

            if stop_result.returncode == 0:
                # Wait a moment for service to stop
                import time

                time.sleep(2)
                return True
            else:
                logger.warning("Failed to stop service: %s", stop_result.stderr)
                return False

        except Exception as e:
            logger.warning("Error stopping Windows service: %s", e)
            return False

    def _start_windows_service(self) -> bool:
        """Start the Windows service if it exists.

        Returns:
            True if service was started, False otherwise
        """
        try:
            # Check if service exists
            result = subprocess.run(
                ["sc", "query", "AutoBotNPUWorker"],
                capture_output=True,
                text=True,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if hasattr(subprocess, "CREATE_NO_WINDOW")
                    else 0
                ),
            )

            if result.returncode != 0:
                logger.debug("AutoBotNPUWorker service not found")
                return False

            # Check if already running
            if "RUNNING" in result.stdout:
                logger.debug("AutoBotNPUWorker service already running")
                return True

            # Start the service
            logger.info("Starting AutoBotNPUWorker service...")
            start_result = subprocess.run(
                ["sc", "start", "AutoBotNPUWorker"],
                capture_output=True,
                text=True,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if hasattr(subprocess, "CREATE_NO_WINDOW")
                    else 0
                ),
            )

            if start_result.returncode == 0:
                return True
            else:
                logger.warning("Failed to start service: %s", start_result.stderr)
                return False

        except Exception as e:
            logger.warning("Error starting Windows service: %s", e)
            return False

    @Slot()
    def restart_worker(self):
        """Restart NPU worker process (non-blocking)"""
        from PySide6.QtCore import QTimer

        self.stop_worker()
        # Use QTimer instead of blocking sleep
        QTimer.singleShot(1000, self.start_worker)

    @Slot()
    def fetch_metrics(self):
        """Fetch metrics from worker API (non-blocking)"""
        if self.get_status() != "running":
            return

        # Don't start new fetch if one is already running
        if self._metrics_worker is not None and self._metrics_worker.isRunning():
            return

        # Create worker thread to fetch metrics
        self._metrics_worker = MetricsWorker(self.api_url)
        self._metrics_worker.metrics_fetched.connect(self._on_metrics_fetched)
        self._metrics_worker.error_occurred.connect(self._on_metrics_error)
        self._metrics_worker.start()

    @Slot(dict)
    def _on_metrics_fetched(self, metrics: dict):
        """Handle fetched metrics (already includes stats from MetricsWorker)"""
        # MetricsWorker already fetched stats, just emit the metrics
        self.metrics_updated.emit(metrics)

    @Slot(str)
    def _on_metrics_error(self, error: str):
        """Handle metrics fetch error"""
        # Silently ignore - worker might be stopped
        pass
