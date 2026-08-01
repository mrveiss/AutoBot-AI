#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# NPU Environment Configuration for AutoBot

export OLLAMA_DEVICE="npu"
export OPENVINO_DEVICE="NPU"
export INTEL_NPU_ENABLED="1"
export OPENVINO_DEVICE_PRIORITIES="NPU,GPU,CPU"
