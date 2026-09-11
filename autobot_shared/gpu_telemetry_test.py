# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""autobot_shared.gpu_telemetry: one parser, three reportable states (#16280)."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from autobot_shared import gpu_telemetry as gt

# Recorded with NODE_QUERY_FIELDS on a host with an RTX 4070 Laptop GPU.
NVIDIA_ONE_GPU = "0, NVIDIA GeForce RTX 4070 Laptop GPU, 0, 141, 8188, 51, 1.92\n"
# A second card whose driver cannot read utilisation, temperature or power.
NVIDIA_TWO_GPUS = NVIDIA_ONE_GPU + "1, NVIDIA RTX A2000, [N/A], 10, 6138, [N/A], [Not Supported]\n"
# Modelled on rocm-smi's --json output; not recorded, as no AMD host was available.
ROCM_JSON = (
    '{"card0": {"Card series": "Radeon RX 7900 XTX", "GPU use (%)": "12",'
    ' "VRAM Total Memory (B)": "25753026560", "VRAM Total Used Memory (B)": "1073741824",'
    ' "Temperature (Sensor edge) (C)": "45.0", "Average Graphics Package Power (W)": "35.0"},'
    ' "system": {"Driver version": "6.7.0"}}'
)


class TestNvidiaParsing:
    def test_argv_asks_for_the_fields_as_bare_csv(self):
        assert gt.nvidia_smi_argv(("name", "memory.total")) == [
            "nvidia-smi",
            "--query-gpu=name,memory.total",
            "--format=csv,noheader,nounits",
        ]

    def test_each_gpu_is_one_row_keyed_by_field(self):
        rows = gt.parse_nvidia_smi_csv(NVIDIA_TWO_GPUS, gt.NODE_QUERY_FIELDS)

        assert [row["name"] for row in rows] == ["NVIDIA GeForce RTX 4070 Laptop GPU", "NVIDIA RTX A2000"]
        assert rows[0]["memory.total"] == "8188"

    def test_unreadable_values_become_none(self):
        assert [gt.parse_nvidia_value(v) for v in ("1.92", "[N/A]", "[Not Supported]", "", "abc")] == [
            1.92,
            None,
            None,
            None,
            None,
        ]

    def test_a_row_with_the_wrong_cell_count_is_skipped_not_mis_keyed(self):
        output = "0, Card, with, a, comma, in, its, name\n" + NVIDIA_ONE_GPU

        rows = gt.parse_nvidia_smi_csv(output, gt.NODE_QUERY_FIELDS)

        assert [row["index"] for row in rows] == ["0"]
        assert rows[0]["name"] == "NVIDIA GeForce RTX 4070 Laptop GPU"

    def test_text_cells_keep_their_value_and_unreadable_ones_become_none(self):
        assert [gt.parse_nvidia_text(v) for v in (" P2 ", "Active", "[N/A]", "[Not Supported]")] == [
            "P2",
            "Active",
            None,
            None,
        ]


class TestRunVendorTool:
    def test_a_missing_tool_is_none_and_nothing_is_spawned(self):
        with patch.object(gt.shutil, "which", return_value=None), patch.object(gt.subprocess, "run") as run:
            assert gt.run_vendor_tool(["nvidia-smi"]) is None
        run.assert_not_called()

    def test_a_failing_tool_is_none(self):
        failed = MagicMock(returncode=9, stdout="")
        with (
            patch.object(gt.shutil, "which", return_value="/usr/bin/nvidia-smi"),
            patch.object(gt.subprocess, "run", return_value=failed),
        ):
            assert gt.run_vendor_tool(["nvidia-smi"]) is None

    def test_a_hung_tool_is_none(self):
        hung = subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=gt.GPU_PROBE_TIMEOUT_S)
        with (
            patch.object(gt.shutil, "which", return_value="/usr/bin/nvidia-smi"),
            patch.object(gt.subprocess, "run", side_effect=hung),
        ):
            assert gt.run_vendor_tool(["nvidia-smi"]) is None

    def test_an_answering_tool_returns_its_stdout(self):
        answered = MagicMock(returncode=0, stdout=NVIDIA_ONE_GPU)
        with (
            patch.object(gt.shutil, "which", return_value="/usr/bin/nvidia-smi"),
            patch.object(gt.subprocess, "run", return_value=answered),
        ):
            assert gt.run_vendor_tool(["nvidia-smi"]) == NVIDIA_ONE_GPU


class TestRocmParsing:
    def test_cards_become_devices_with_memory_in_mb(self):
        [device] = gt.parse_rocm_smi_json(ROCM_JSON)

        assert device == {
            "device_type": gt.AMD_GPU,
            "index": 0,
            "name": "Radeon RX 7900 XTX",
            "monitored": True,
            "utilization_percent": 12.0,
            "memory_used_mb": 1024.0,
            "memory_total_mb": 24560.0,
            "temperature_celsius": 45.0,
            "power_watts": 35.0,
        }

    def test_keys_a_release_does_not_print_are_none(self):
        [device] = gt.parse_rocm_smi_json('{"card1": {"Card series": "Radeon"}}')

        assert device["index"] == 1
        assert device["utilization_percent"] is None
        assert device["memory_total_mb"] is None

    def test_output_that_is_not_json_raises(self):
        with pytest.raises(ValueError):
            gt.parse_rocm_smi_json("rocm-smi: command failed")


class TestSysfs:
    def test_only_card_directories_with_a_vendor_file_count(self, tmp_path):
        for name, vendor in (("card0", "0x10de"), ("renderD128", "0x10de")):
            (tmp_path / name / "device").mkdir(parents=True)
            (tmp_path / name / "device" / "vendor").write_text(vendor + "\n", encoding="utf-8")
        (tmp_path / "card0-DP-1").mkdir()

        assert gt.sysfs_gpu_vendors(tmp_path) == ["0x10de"]

    def test_a_missing_drm_root_is_empty(self, tmp_path):
        assert gt.sysfs_gpu_vendors(tmp_path / "absent") == []


class TestProbeGpus:
    @staticmethod
    def _host(monkeypatch, nvidia=None, rocm=None, vendors=()):
        monkeypatch.setattr(gt, "run_vendor_tool", lambda argv: nvidia if argv[0] == "nvidia-smi" else rocm)
        monkeypatch.setattr(gt, "sysfs_gpu_vendors", lambda: list(vendors))

    def test_a_measured_gpu_is_reported_once_even_when_sysfs_also_shows_it(self, monkeypatch):
        self._host(monkeypatch, nvidia=NVIDIA_ONE_GPU, vendors=["0x10de"])

        [device] = gt.probe_gpus()

        assert device["device_type"] == gt.NVIDIA_GPU
        assert device["monitored"] is True
        assert device["memory_total_mb"] == 8188.0
        assert device["power_watts"] == 1.92

    def test_a_card_whose_tool_is_missing_is_present_but_unmonitored(self, monkeypatch):
        self._host(monkeypatch, vendors=["0x10de"])

        [device] = gt.probe_gpus()

        assert device["device_type"] == gt.NVIDIA_GPU
        assert device["monitored"] is False
        assert device["utilization_percent"] is None

    def test_no_gpu_is_an_empty_list(self, monkeypatch):
        self._host(monkeypatch)

        assert gt.probe_gpus() == []

    def test_vendors_outside_the_vocabulary_are_not_reported(self, monkeypatch):
        self._host(monkeypatch, vendors=["0x8086"])

        assert gt.probe_gpus() == []

    def test_amd_is_measured_through_rocm_smi(self, monkeypatch):
        self._host(monkeypatch, rocm=ROCM_JSON, vendors=["0x1002"])

        [device] = gt.probe_gpus()

        assert device["device_type"] == gt.AMD_GPU
        assert device["monitored"] is True

    def test_unreadable_cells_on_a_second_gpu_do_not_hide_the_first(self, monkeypatch):
        self._host(monkeypatch, nvidia=NVIDIA_TWO_GPUS)

        first, second = gt.probe_gpus()

        assert first["temperature_celsius"] == 51.0
        assert second["name"] == "NVIDIA RTX A2000"
        assert second["temperature_celsius"] is None
