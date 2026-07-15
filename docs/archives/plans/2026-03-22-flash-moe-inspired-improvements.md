# Flash-MoE-Inspired Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Adopt key patterns from [flash-moe](https://github.com/danveloper/flash-moe) — explicit memory budgeting, multi-vendor GPU detection, experiment tracking, cache validation, and pipeline optimization — to make AutoBot's model selection, hardware awareness, and performance workflows production-grade.

**Architecture:** Seven independent work streams, each touching a focused area of the codebase. Tasks 1-3 are high priority (fix real bugs). Tasks 4-7 are medium priority (improve performance workflows). All tasks are independent and can be parallelized.

**Tech Stack:** Python 3.14, psutil, pynvml, pytest, Redis, asyncio

**Source:** Research comparison of [danveloper/flash-moe](https://github.com/danveloper/flash-moe) against AutoBot codebase (2026-03-22).

**Umbrella Issue:** #1988
**Related Issues:** #1959 (GPU detection), #1966 (ModelSelector OOM), #1950 (hardware-aware scoring), #1961 (cost tracker pricing)

---

## Task 1: Multi-Vendor GPU Detection (#1959)

**Problem:** `check_gpu_availability()` returns `False` for any non-RTX NVIDIA card (GTX, Tesla, A100) and all AMD/Intel/Apple GPUs. Flash-MoE demonstrated hardware-specific detection with graceful fallback.

**Files:**
- Modify: `autobot-backend/utils/gpu_optimization/gpu_detection.py`
- Modify: `autobot-backend/utils/gpu_optimization/types.py`
- Create: `autobot-backend/tests/utils/gpu_optimization/__init__.py`
- Create: `autobot-backend/tests/utils/gpu_optimization/test_gpu_detection.py`
- Create: `autobot-backend/tests/utils/__init__.py`

**Step 1: Write failing tests for multi-vendor detection**

Test file: `autobot-backend/tests/utils/gpu_optimization/test_gpu_detection.py`

Tests cover: NVIDIA RTX/GTX/Tesla/A100 detection, AMD via rocm-smi mock, Intel via sysfs mock, fallback to NONE when no GPU, check_gpu_availability accepts all NVIDIA (not just RTX), capabilities include vendor field, tensor_cores false for GTX.

**Step 2:** Run: `cd autobot-backend && python -m pytest tests/utils/gpu_optimization/test_gpu_detection.py -v` — Expected: FAIL

**Step 3:** Add `GPUVendor` enum to types.py, add `vendor` field to `GPUCapabilities`

**Step 4:** Rewrite gpu_detection.py:
- Remove `and "RTX" in result.stdout` from `check_gpu_availability()`
- Add `detect_gpu_vendor()`: NVIDIA > AMD (rocm-smi) > Intel (sysfs 0x8086) > NONE
- Add `_check_amd_gpu()`: Query rocm-smi for product name and VRAM
- Add `_check_intel_gpu()`: Check /sys/class/drm/card*/device/vendor
- Update `detect_gpu_capabilities()`: Set vendor, fix tensor_cores (RTX/A100/H100/L40 only)

**Step 5:** Run tests — Expected: ALL PASS

**Step 6:** Commit: `feat(gpu): multi-vendor GPU detection — NVIDIA/AMD/Intel (#1959, #1988)`

---

## Task 2: VRAM-Aware Model Selection (#1966)

**Problem:** `ModelSelector.filter_by_resources` uses rough RAM heuristics — never checks GPU VRAM. Flash-MoE's explicit memory budgeting is the pattern to follow.

**Files:**
- Modify: `autobot-backend/utils/model_optimization/types.py`
- Modify: `autobot-backend/utils/model_optimization/system_resources.py`
- Create: `autobot-backend/tests/utils/model_optimization/__init__.py`
- Create: `autobot-backend/tests/utils/model_optimization/test_vram_estimation.py`

**Step 1: Write failing tests**

Tests cover: 7B Q4 VRAM estimate ~4.4GB, 70B Q4 >35GB, 13B FP16 >24GB, unknown quant fallback to size_gb, SystemResources has gpu_vram_gb field (default 0.0), model exceeding VRAM rejected, small model fits.

**Step 2:** Run tests — Expected: FAIL

**Step 3:** Implementation:
- Add `gpu_vram_gb: float = 0.0` to `SystemResources`
- Add module-level `_QUANT_BYTES` lookup table and `_KV_CACHE_OVERHEAD = 1.25`
- Add `estimate_vram_gb()` to ModelInfo: params x bytes_per_param x overhead
- Add `_parse_param_count()` to ModelInfo: parse "7B" -> 7.0, "3800M" -> 3.8
- Update `fits_resource_constraints()`: check VRAM when gpu_vram_gb > 0
- Add `_get_gpu_vram()` to SystemResourceAnalyzer using pynvml

**Step 4:** Run tests — Expected: ALL PASS

**Step 5:** Commit: `feat(models): VRAM-aware model selection — prevent OOM (#1966, #1988)`

---

## Task 3: Hardware-Aware Model Scoring (#1950)

**Problem:** `HardwareDetector` unconditionally adds "intel_arc" and "openvino" regardless of hardware.

**Files:**
- Modify: `autobot-backend/llm_interface_pkg/hardware.py`
- Create: `autobot-backend/tests/llm_interface_pkg/__init__.py`
- Create: `autobot-backend/tests/llm_interface_pkg/test_hardware.py`

**Step 1:** Write tests: no false-positive openvino without library, cuda when torch available, always has cpu

**Step 2:** Run tests — Expected: FAIL (false positive test)

**Step 3:** Replace placeholder block with real `import openvino` + `core.available_devices` check

**Step 4:** Run tests — Expected: ALL PASS

**Step 5:** Commit: `fix(hardware): replace placeholder Intel detection with real OpenVINO check (#1950, #1988)`

---

## Task 4: Experiment Tracking System (New)

**Problem:** No structured way to track performance experiments.

**Files:**
- Create: `autobot-backend/utils/experiment_tracker.py`
- Create: `autobot-backend/tests/utils/test_experiment_tracker.py`

**Step 1:** Write tests for ExperimentRecord creation/serialization and ExperimentTracker Redis storage/retrieval/filtering

**Step 2:** Run tests — Expected: FAIL

**Step 3:** Implement ExperimentRecord dataclass + ExperimentTracker with Redis list storage in analytics DB

**Step 4:** Run tests — Expected: ALL PASS

**Step 5:** Commit: `feat(perf): experiment tracking system for performance work (#1988)`

---

## Task 5: Cost Tracker Pricing Update (#1961)

**Problem:** MODEL_PRICING missing 2025-2026 models.

**Files:**
- Modify: `autobot-backend/services/llm_cost_tracker.py`
- Create: `autobot-backend/tests/services/test_llm_cost_tracker.py`

**Step 1:** Write parametrized tests requiring Claude 4.x, GPT-4.1, Gemini 2.5 entries

**Step 2:** Run tests — Expected: FAIL

**Step 3:** Add missing entries to MODEL_PRICING dict

**Step 4:** Run tests — Expected: ALL PASS

**Step 5:** Commit: `fix(costs): update MODEL_PRICING with 2025-2026 models (#1961, #1988)`

---

## Task 6: L1 Cache Benchmark Harness (New)

**Problem:** Need data on whether L1 in-memory LRU adds value over Redis L2 alone.

**Files:**
- Create: `autobot-backend/benchmarks/__init__.py`
- Create: `autobot-backend/benchmarks/cache_benchmark.py`

**Step 1:** Write benchmark script measuring L1 vs L2 hit latencies with decision guide

**Step 2:** Commit: `feat(perf): L1 vs L2 cache benchmark harness (#1988)`

---

## Task 7: RAG Pipeline Profiler (New)

**Problem:** No timing instrumentation in RAG pipeline.

**Files:**
- Create: `autobot-backend/utils/pipeline_profiler.py`
- Create: `autobot-backend/tests/utils/test_pipeline_profiler.py`

**Step 1:** Write tests for async context manager stage timing, total duration, empty report, exception handling

**Step 2:** Run tests — Expected: FAIL

**Step 3:** Implement PipelineProfiler with perf_counter_ns timing and async context manager

**Step 4:** Run tests — Expected: ALL PASS

**Step 5:** Commit: `feat(perf): pipeline profiler for stage-by-stage latency analysis (#1988)`

---

## Summary

| Task | Issue | Priority | Effort | What it does |
|------|-------|----------|--------|--------------|
| 1. Multi-vendor GPU detection | #1959 | High | Moderate | Detect NVIDIA (all), AMD, Intel GPUs |
| 2. VRAM-aware model selection | #1966 | High | Moderate | Prevent OOM by estimating model VRAM needs |
| 3. Hardware-aware scoring | #1950 | High | Small | Replace placeholder OpenVINO detection |
| 4. Experiment tracker | #1988 | Medium | Small | Structured logging for perf experiments |
| 5. Cost tracker pricing | #1961 | Medium | Small | Add 2025-2026 model pricing |
| 6. Cache benchmark harness | #1988 | Medium | Small | Validate L1 cache value (trust-the-OS test) |
| 7. Pipeline profiler | #1988 | Medium | Small | Per-stage timing for RAG pipeline |

**Dependency order:** All tasks are independent. Maximum parallelism: all 7 at once.

**Total new test files:** 5 (covering all modified/created modules)
