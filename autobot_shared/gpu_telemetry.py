# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GPU telemetry: one nvidia-smi / rocm-smi parser for every caller (#16280).

The main backend and the SLM agent on every node read GPUs from the same vendor
tools. Before #16280 each caller split nvidia-smi's CSV itself, each with its own
idea of a missing value. This module owns the parsing; callers own only what they
do with the numbers.

``probe_gpus`` reports the host in one of two shapes, and a caller that never
probed omits the result entirely -- three states the SLM shows as-is (#15226):

* ``[]`` -- probed, and no NVIDIA or AMD GPU is present;
* a list of devices -- each measured when its vendor tool answered, or marked
  ``monitored: False`` with null metrics when sysfs shows the card but the tool
  is missing or failed.

``device_type`` uses the SLM's ``NPUDeviceType`` values (``nvidia-gpu``,
``amd-gpu``); this module cannot import the SLM's models, so the strings are
repeated here and the SLM validates them on the way in.
"""

import json
import logging
import re
import shutil
import subprocess  # nosec B404  # fixed vendor-tool argv, no user input
from pathlib import Path
from typing import Any, Dict, List, Sequence

from autobot_shared.env_utils import env_float

logger = logging.getLogger(__name__)

GPU_PROBE_TIMEOUT_S = env_float("AUTOBOT_GPU_PROBE_TIMEOUT_S", 5.0)

NVIDIA_GPU = "nvidia-gpu"
AMD_GPU = "amd-gpu"
_VENDOR_DEVICE_TYPE = {"0x10de": NVIDIA_GPU, "0x1002": AMD_GPU}

# What nvidia-smi prints in place of a value it cannot read.
_NVIDIA_UNREADABLE = frozenset({"[N/A]", "[Not Supported]", "N/A", ""})

# The fields a node reports in its heartbeat, in nvidia-smi's query names.
NODE_QUERY_FIELDS = (
    "index",
    "name",
    "utilization.gpu",
    "memory.used",
    "memory.total",
    "temperature.gpu",
    "power.draw",
)

ROCM_SMI_ARGV = [
    "rocm-smi",
    "--showproductname",
    "--showuse",
    "--showmeminfo",
    "vram",
    "--showtemp",
    "--showpower",
    "--json",
]

# rocm-smi's JSON keys drift between ROCm releases; the first key present wins.
_ROCM_KEYS: Dict[str, Sequence[str]] = {
    "name": ("Card series", "Card model", "Device Name"),
    "utilization_percent": ("GPU use (%)",),
    "memory_used_b": ("VRAM Total Used Memory (B)",),
    "memory_total_b": ("VRAM Total Memory (B)",),
    "temperature_celsius": ("Temperature (Sensor edge) (C)", "Temperature (Sensor junction) (C)"),
    "power_watts": ("Average Graphics Package Power (W)", "Current Socket Graphics Package Power (W)"),
}

_BYTES_PER_MB = 1024 * 1024
_DRM_CARD = re.compile(r"card\d+")


def nvidia_smi_argv(fields: Sequence[str]) -> List[str]:
    """The nvidia-smi command that reports *fields*, one CSV row per GPU."""
    return ["nvidia-smi", f"--query-gpu={','.join(fields)}", "--format=csv,noheader,nounits"]


def parse_nvidia_value(raw: str) -> float | None:
    """One nvidia-smi cell as a number, or None when the tool could not read it."""
    value = raw.strip()
    if value in _NVIDIA_UNREADABLE:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_nvidia_smi_csv(output: str, fields: Sequence[str]) -> List[Dict[str, str]]:
    """Split ``--format=csv,noheader`` output into one row per GPU, keyed by *fields*.

    Cells stay strings -- ``parse_nvidia_value`` turns them into numbers. A line
    whose cell count differs from *fields* is skipped rather than mis-keyed.
    """
    rows = []
    for line in output.splitlines():
        if not line.strip():
            continue
        cells = [cell.strip() for cell in line.split(",")]
        if len(cells) != len(fields):
            logger.debug("Skipping nvidia-smi row with %d cells, expected %d", len(cells), len(fields))
            continue
        rows.append(dict(zip(fields, cells)))
    return rows


def run_vendor_tool(argv: Sequence[str]) -> str | None:
    """A vendor tool's stdout, or None when it is missing, fails or hangs."""
    if shutil.which(argv[0]) is None:
        return None
    try:
        result = subprocess.run(  # nosec B603  # fixed vendor-tool argv, no user input
            list(argv), capture_output=True, text=True, timeout=GPU_PROBE_TIMEOUT_S, check=False
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("%s unavailable: %s", argv[0], exc)
        return None
    if result.returncode != 0:
        logger.debug("%s exited %d", argv[0], result.returncode)
        return None
    return result.stdout


def query_nvidia_gpus(fields: Sequence[str]) -> List[Dict[str, str]] | None:
    """nvidia-smi's rows for *fields*, or None when nvidia-smi could not be asked."""
    output = run_vendor_tool(nvidia_smi_argv(fields))
    return None if output is None else parse_nvidia_smi_csv(output, fields)


def _nvidia_device(row: Dict[str, str]) -> Dict[str, Any]:
    """One heartbeat device from a ``NODE_QUERY_FIELDS`` row."""
    index = parse_nvidia_value(row["index"])
    return {
        "device_type": NVIDIA_GPU,
        "index": None if index is None else int(index),
        "name": row["name"],
        "monitored": True,
        "utilization_percent": parse_nvidia_value(row["utilization.gpu"]),
        "memory_used_mb": parse_nvidia_value(row["memory.used"]),
        "memory_total_mb": parse_nvidia_value(row["memory.total"]),
        "temperature_celsius": parse_nvidia_value(row["temperature.gpu"]),
        "power_watts": parse_nvidia_value(row["power.draw"]),
    }


def _rocm_value(card: Dict[str, Any], field: str) -> Any:
    """The first of *field*'s known rocm-smi keys that *card* carries, else None."""
    for key in _ROCM_KEYS[field]:
        if key in card:
            return card[key]
    return None


def _rocm_number(card: Dict[str, Any], field: str) -> float | None:
    """A numeric rocm-smi field, or None when absent or unreadable."""
    try:
        return float(_rocm_value(card, field))
    except (TypeError, ValueError):
        return None


def _rocm_device(index: int, card: Dict[str, Any]) -> Dict[str, Any]:
    """One heartbeat device from a rocm-smi ``cardN`` object."""
    used_b, total_b = _rocm_number(card, "memory_used_b"), _rocm_number(card, "memory_total_b")
    return {
        "device_type": AMD_GPU,
        "index": index,
        "name": _rocm_value(card, "name"),
        "monitored": True,
        "utilization_percent": _rocm_number(card, "utilization_percent"),
        "memory_used_mb": None if used_b is None else round(used_b / _BYTES_PER_MB, 1),
        "memory_total_mb": None if total_b is None else round(total_b / _BYTES_PER_MB, 1),
        "temperature_celsius": _rocm_number(card, "temperature_celsius"),
        "power_watts": _rocm_number(card, "power_watts"),
    }


def parse_rocm_smi_json(output: str) -> List[Dict[str, Any]]:
    """Devices from ``rocm-smi --json``. Raises ValueError on output that is not JSON."""
    data = json.loads(output)
    cards = sorted(
        (int(key[4:]), value) for key, value in data.items() if _DRM_CARD.fullmatch(key) and isinstance(value, dict)
    )
    return [_rocm_device(index, card) for index, card in cards]


def sysfs_gpu_vendors(drm_root: Path = Path("/sys/class/drm")) -> List[str]:
    """The PCI vendor id of every DRM card sysfs shows -- presence without a vendor tool."""
    vendors = []
    try:
        for card in sorted(drm_root.iterdir()):
            vendor_file = card / "device" / "vendor"
            if _DRM_CARD.fullmatch(card.name) and vendor_file.is_file():
                vendors.append(vendor_file.read_text(encoding="utf-8").strip())
    except OSError as exc:
        logger.debug("sysfs DRM scan failed: %s", exc)
    return vendors


def _unmonitored(device_type: str) -> Dict[str, Any]:
    """A card sysfs shows but no vendor tool measured."""
    return {
        "device_type": device_type,
        "index": None,
        "name": None,
        "monitored": False,
        "utilization_percent": None,
        "memory_used_mb": None,
        "memory_total_mb": None,
        "temperature_celsius": None,
        "power_watts": None,
    }


def _measured_amd() -> List[Dict[str, Any]]:
    """AMD devices from rocm-smi; empty when it is missing, fails or prints no JSON."""
    output = run_vendor_tool(ROCM_SMI_ARGV)
    if output is None:
        return []
    try:
        return parse_rocm_smi_json(output)
    except ValueError as exc:
        logger.debug("rocm-smi output was not JSON: %s", exc)
        return []


def probe_gpus() -> List[Dict[str, Any]]:
    """Every NVIDIA and AMD GPU on this host, measured where its tool answers (#16280)."""
    rows = query_nvidia_gpus(NODE_QUERY_FIELDS) or []
    devices = [_nvidia_device(row) for row in rows] + _measured_amd()
    measured = {device["device_type"] for device in devices}
    for vendor in sysfs_gpu_vendors():
        device_type = _VENDOR_DEVICE_TYPE.get(vendor)
        if device_type is not None and device_type not in measured:
            devices.append(_unmonitored(device_type))
    return devices
