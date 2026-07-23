#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# GPU Environment Configuration for AutoBot

export OLLAMA_DEVICE="gpu"
export CUDA_VISIBLE_DEVICES="0"
export NVIDIA_VISIBLE_DEVICES="0"
export OLLAMA_GPU_LAYERS="999"
export OLLAMA_PARALLEL="2"
export OLLAMA_NUM_THREAD="4"
