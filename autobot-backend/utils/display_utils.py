# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Display Utilities for Dynamic Resolution Detection

Provides cross-platform display resolution detection for optimal
Playwright viewport configuration based on the current environment.
"""

import logging
import os
import subprocess
import sys
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def _parse_resolution_from_part(
    part: str, delimiter: str = "x"
) -> Optional[Tuple[int, int]]:
    """Parse resolution from a string part like '1920x1080' (Issue #315 - extracted helper)."""
    if delimiter not in part:
        return None
    try:
        width_str, height_str = part.split(delimiter)
        # Handle trailing decimals (e.g., '1920x1080.00')
        height_str = height_str.split(".")[0]
        return (int(width_str), int(height_str))
    except (ValueError, IndexError):
        return None


def _find_resolution_in_output(
    output: str,
    line_filter: callable,
    part_filter: callable,
) -> Optional[Tuple[int, int]]:
    """Find resolution in subprocess output (Issue #315 - extracted helper)."""
    for line in output.split("\n"):
        if not line_filter(line):
            continue
        parts = line.strip().split()
        for part in parts:
            if part_filter(part):
                resolution = _parse_resolution_from_part(part)
                if resolution:
                    return resolution
    return None


class DisplayDetector:
    """Detects current display resolution across different platforms"""

    def __init__(self):
        """Initialize display detector with cache and fallback resolution."""
        self.cached_resolution: Optional[Tuple[int, int]] = None
        self.fallback_resolution = (1920, 1080)

    def get_primary_display_resolution(self) -> Tuple[int, int]:
        """
        Get the primary display resolution.

        Returns:
            Tuple[int, int]: (width, height) of primary display
        """
        if self.cached_resolution:
            return self.cached_resolution

        try:
            resolution = self._detect_resolution()
            self.cached_resolution = resolution
            logger.info(
                "Detected display resolution: %sx%s", resolution[0], resolution[1]
            )
            return resolution
        except Exception as e:
            logger.warning("Failed to detect display resolution: %s", e)
            logger.info(
                f"Using fallback resolution: {self.fallback_resolution[0]}x{self.fallback_resolution[1]}"
            )
            return self.fallback_resolution

    def _detect_resolution(self) -> Tuple[int, int]:
        """Detect resolution based on platform"""
        platform = sys.platform.lower()

        if platform.startswith("linux"):
            return self._detect_linux_resolution()
        elif platform.startswith("darwin"):  # macOS
            return self._detect_macos_resolution()
        elif platform.startswith("win"):
            return self._detect_windows_resolution()
        else:
            logger.warning("Unsupported platform: %s", platform)
            return self.fallback_resolution

    def _detect_linux_resolution(self) -> Tuple[int, int]:
        """Detect resolution on Linux systems"""
        methods = [
            self._try_xrandr,
            self._try_xdpyinfo,
            self._try_wayland_resolution,
            self._try_framebuffer_resolution,
            self._try_environment_vars,
        ]

        for method in methods:
            try:
                resolution = method()
                if resolution and resolution[0] > 0 and resolution[1] > 0:
                    return resolution
            except Exception as e:
                logger.debug(
                    f"Resolution detection method failed: {method.__name__}: {e}"
                )
                continue

        return self.fallback_resolution

    def _try_xrandr(self) -> Optional[Tuple[int, int]]:
        """Try to get resolution using xrandr (X11) (Issue #315 - refactored)."""
        try:
            result = subprocess.run(
                ["xrandr", "--query"], capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return None

            return _find_resolution_in_output(
                result.stdout,
                line_filter=lambda line: "*" in line and "+" in line,
                part_filter=lambda part: "x" in part
                and part.replace("x", "").replace(".", "").isdigit(),
            )
        except (
            subprocess.TimeoutExpired,
            subprocess.SubprocessError,
            FileNotFoundError,
        ):
            return None

    def _try_xdpyinfo(self) -> Optional[Tuple[int, int]]:
        """Try to get resolution using xdpyinfo (X11) (Issue #315 - refactored)."""
        try:
            result = subprocess.run(
                ["xdpyinfo"], capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return None

            # Example: "  dimensions:    1920x1080 pixels (508x285 millimeters)"
            return _find_resolution_in_output(
                result.stdout,
                line_filter=lambda line: "dimensions:" in line,
                part_filter=lambda part: "x" in part and "pixels" not in part,
            )
        except (
            subprocess.TimeoutExpired,
            subprocess.SubprocessError,
            FileNotFoundError,
        ):
            return None

    def _try_wayland_resolution(self) -> Optional[Tuple[int, int]]:
        """Try to get resolution on Wayland (Issue #315 - refactored)."""
        try:
            # Try wlr-randr (for wlroots-based compositors)
            result = subprocess.run(
                ["wlr-randr"], capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return None

            return _find_resolution_in_output(
                result.stdout,
                line_filter=lambda line: "current" in line.lower(),
                part_filter=lambda part: "x" in part and "@" not in part,
            )
        except (
            subprocess.TimeoutExpired,
            subprocess.SubprocessError,
            FileNotFoundError,
        ):
            return None

    def _try_framebuffer_resolution(self) -> Optional[Tuple[int, int]]:
        """Try to get resolution from framebuffer info"""
        try:
            with open("/sys/class/graphics/fb0/virtual_size", "r") as f:
                size = f.read().strip()
                if "," in size:
                    width, height = size.split(",")
                    return (int(width), int(height))
            return None
        except (IOError, ValueError, FileNotFoundError):
            return None

    def _try_environment_vars(self) -> Optional[Tuple[int, int]]:
        """Try to get resolution from environment variables"""
        # Check for VNC or remote desktop environment variables
        if "DISPLAY_WIDTH" in os.environ and "DISPLAY_HEIGHT" in os.environ:
            try:
                width = int(os.environ["DISPLAY_WIDTH"])
                height = int(os.environ["DISPLAY_HEIGHT"])
                return (width, height)
            except ValueError as e:
                logger.debug("Invalid DISPLAY_WIDTH/HEIGHT values: %s", e)

        # Check for common VNC variables
        if "VNC_RESOLUTION" in os.environ:
            try:
                resolution = os.environ["VNC_RESOLUTION"]
                if "x" in resolution:
                    width, height = resolution.split("x")
                    return (int(width), int(height))
            except ValueError as e:
                logger.debug("Invalid VNC_RESOLUTION format: %s", e)

        return None

    def _detect_macos_resolution(self) -> Tuple[int, int]:
        """Detect resolution on macOS (Issue #315 - refactored)."""
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return self.fallback_resolution

            # Example: "          Resolution: 1920 x 1080"
            resolution = self._parse_macos_resolution_output(result.stdout)
            return resolution if resolution else self.fallback_resolution
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, ValueError):
            return self.fallback_resolution

    def _parse_macos_resolution_output(self, output: str) -> Optional[Tuple[int, int]]:
        """Parse macOS system_profiler output for resolution (Issue #315 - extracted)."""
        for line in output.split("\n"):
            if "Resolution:" not in line:
                continue
            parts = line.split()
            if len(parts) >= 4:
                try:
                    return (int(parts[-3]), int(parts[-1]))
                except ValueError:
                    continue
        return None

    def _detect_windows_resolution(self) -> Tuple[int, int]:
        """Detect resolution on Windows"""
        try:
            # Try using PowerShell
            powershell_cmd = [
                "powershell",
                "-Command",
                "Add-Type -AssemblyName System.Windows.Forms; "
                "[System.Windows.Forms.Screen]::PrimaryScreen.Bounds | "
                "Select-Object Width, Height | ConvertTo-Json",
            ]

            result = subprocess.run(
                powershell_cmd, capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                import json

                data = json.loads(result.stdout.strip())
                return (data["Width"], data["Height"])

            return self.fallback_resolution
        except (
            subprocess.TimeoutExpired,
            subprocess.SubprocessError,
            json.JSONDecodeError,
            ImportError,
        ):
            return self.fallback_resolution

    def get_optimal_playwright_config(self) -> Dict[str, any]:
        """
        Get optimal Playwright configuration based on detected resolution.

        Returns:
            Dict with viewport size and browser args optimized for current display
        """
        width, height = self.get_primary_display_resolution()

        # Use 90% of screen resolution to account for taskbars/docks
        optimal_width = int(width * 0.9)
        optimal_height = int(height * 0.9)

        # Ensure minimum viable size
        optimal_width = max(optimal_width, 1280)
        optimal_height = max(optimal_height, 720)

        return {
            "viewport": {"width": optimal_width, "height": optimal_height},
            "browser_args": [
                f"--window-size={optimal_width},{optimal_height}",
                "--force-device-scale-factor=1",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
            ],
            "detected_resolution": {"width": width, "height": height},
        }

    def clear_cache(self):
        """Clear cached resolution for re-detection"""
        self.cached_resolution = None


# Global instance for easy access
display_detector = DisplayDetector()


def get_current_resolution() -> Tuple[int, int]:
    """
    Convenience function to get current display resolution.

    Returns:
        Tuple[int, int]: (width, height) of primary display
    """
    return display_detector.get_primary_display_resolution()


def get_playwright_config() -> Dict[str, any]:
    """
    Convenience function to get Playwright config for current display.

    Returns:
        Dict with optimal viewport and browser configuration
    """
    return display_detector.get_optimal_playwright_config()
