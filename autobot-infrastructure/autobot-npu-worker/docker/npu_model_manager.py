# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
NPU Model Manager
Manages AI models optimized for Intel NPU acceleration.

Issue #1944: Implements airllm-style prefetch/overlap I/O pattern using a
ThreadPoolExecutor to load the next model while the current one is executing on
the NPU, overlapping disk I/O and OpenVINO compilation with inference.
"""

import asyncio
import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import numpy as np
    from openvino.runtime import Core

    OPENVINO_AVAILABLE = True
except ImportError:
    OPENVINO_AVAILABLE = False
    np = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Number of background threads for model loading.
# One thread is sufficient: compilation is a single serialised operation per
# model and we only ever prefetch one model at a time.
_PREFETCH_THREAD_COUNT = 1


class NPUModelManager:
    """
    Manages models optimized for Intel NPU.

    Issue #1944: Overlaps OpenVINO model compilation (CPU-bound / I/O-bound)
    with NPU inference by running compilation in a background ThreadPoolExecutor
    while the current inference request executes.  This mirrors the airllm
    layer-prefetch technique but at model granularity.
    """

    def __init__(self, model_cache_dir: str = "/app/models"):
        self.model_cache_dir = Path(model_cache_dir)
        self.model_cache_dir.mkdir(exist_ok=True)

        self.loaded_models: Dict[str, Dict[str, Any]] = {}
        self.core: Optional["Core"] = None
        self.npu_available: bool = False

        # Issue #1944: Prefetch pipeline state
        self._executor = ThreadPoolExecutor(
            max_workers=_PREFETCH_THREAD_COUNT,
            thread_name_prefix="npu-prefetch",
        )
        # Maps model_id → in-flight Future from the executor
        self._prefetch_futures: Dict[str, Future] = {}
        # Maps model_id → compiled OpenVINO model cached from prefetch
        self._prefetch_cache: Dict[str, Any] = {}

        # Metrics (Issue #1944)
        self._prefetch_hits: int = 0
        self._prefetch_misses: int = 0
        self._total_load_time_saved_ms: float = 0.0

        self._initialize_openvino()

    # ------------------------------------------------------------------
    # OpenVINO initialisation
    # ------------------------------------------------------------------

    def _initialize_openvino(self) -> None:
        """Initialize OpenVINO runtime and detect available devices."""
        if not OPENVINO_AVAILABLE:
            logger.error("OpenVINO not available - NPU acceleration disabled")
            return

        try:
            self.core = Core()
            available_devices = self.core.available_devices
            logger.info("Available OpenVINO devices: %s", available_devices)

            npu_devices = [d for d in available_devices if "NPU" in d]
            if npu_devices:
                self.npu_available = True
                logger.info("NPU devices available: %s", npu_devices)
            else:
                logger.warning("No NPU devices detected - falling back to CPU")
        except Exception as e:
            logger.error("Failed to initialize OpenVINO: %s", e)

    # ------------------------------------------------------------------
    # Device selection
    # ------------------------------------------------------------------

    def get_optimal_device(self) -> str:
        """Return the best available inference device."""
        if self.npu_available:
            return "NPU"
        if self.core and "GPU" in self.core.available_devices:
            return "GPU"
        return "CPU"

    # ------------------------------------------------------------------
    # Synchronous model loading (runs in background thread)
    # Issue #1944: This is the blocking work we overlap with inference.
    # ------------------------------------------------------------------

    def _compile_model_for_device(
        self, model_id: str, model_path: Path, model_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compile an OpenVINO IR model for the target device (thread-pool helper)."""
        device = self.get_optimal_device()
        logger.debug("Compiling %s on %s from %s", model_id, device, model_path)
        compiled = self.core.compile_model(str(model_path), device)
        logger.info("Compiled model %s on %s", model_id, device)
        return {
            "config": model_config,
            "device": device,
            "compiled_model": compiled,
            "loaded_at": time.monotonic(),
            "inference_count": 0,
        }

    def _load_model_sync(self, model_id: str, model_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Load and compile a model synchronously (called from thread pool).

        Issue #1944: This is the blocking I/O+CPU work that is overlapped with
        NPU inference via the prefetch pipeline.  Delegates to
        _compile_model_for_device when an IR file is found; returns a stub
        entry otherwise so callers always get a usable dict.
        """
        if not OPENVINO_AVAILABLE or self.core is None:
            return self._make_stub_model_entry(model_id, model_config)

        model_path = self._resolve_model_path(model_id, model_config)
        if model_path is None:
            logger.debug("No IR file for %s, using stub entry", model_id)
            return self._make_stub_model_entry(model_id, model_config)

        return self._compile_model_for_device(model_id, model_path, model_config)

    def _resolve_model_path(self, model_id: str, model_config: Dict[str, Any]) -> Optional[Path]:
        """
        Locate an OpenVINO IR (.xml) file for model_id.

        Checks (in order):
          1. Explicit ``model_path`` key in model_config.
          2. <model_cache_dir>/<model_id>/model.xml
          3. <model_cache_dir>/<model_id>.xml
        """
        explicit = model_config.get("model_path")
        if explicit:
            p = Path(explicit)
            if p.exists():
                return p
            logger.warning("Explicit model_path not found: %s", p)

        candidates = [
            self.model_cache_dir / model_id / "model.xml",
            self.model_cache_dir / f"{model_id}.xml",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None

    def _make_stub_model_entry(self, model_id: str, model_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return a stub model entry used when OpenVINO is unavailable or the IR
        file is absent.  Inference will use the simulated path.
        """
        return {
            "config": model_config,
            "device": self.get_optimal_device(),
            "compiled_model": None,
            "loaded_at": time.monotonic(),
            "inference_count": 0,
        }

    # ------------------------------------------------------------------
    # Async public API
    # ------------------------------------------------------------------

    async def prefetch_model(self, model_id: str, model_config: Dict[str, Any]) -> None:
        """
        Issue #1944: Start loading model_id in the background without waiting.

        Call this at the start of the *previous* inference so that compilation
        overlaps with NPU execution time.  If the model is already loaded or a
        prefetch is in-flight, this is a no-op.
        """
        if model_id in self.loaded_models:
            logger.debug("prefetch_model: %s already loaded, skipping", model_id)
            return
        if model_id in self._prefetch_futures:
            logger.debug("prefetch_model: %s already in-flight, skipping", model_id)
            return

        logger.debug("Prefetching model %s in background", model_id)
        future = self._executor.submit(self._load_model_sync, model_id, model_config)
        self._prefetch_futures[model_id] = future

    async def load_model(self, model_id: str, model_config: Dict[str, Any]) -> bool:
        """
        Load a model for NPU inference, using prefetch cache when available.

        Issue #1944: If a background prefetch for this model is in-flight or
        complete, we await it rather than starting a new compilation.  This
        converts what would be a serial load-then-infer into an overlapped
        pipeline.
        """
        if model_id in self.loaded_models:
            logger.info("Model %s already loaded", model_id)
            return True

        try:
            entry = await self._resolve_model_entry(model_id, model_config)
            self.loaded_models[model_id] = entry
            logger.info("Loaded model %s on device %s", model_id, entry["device"])
            return True
        except Exception as e:
            logger.error("Failed to load model %s: %s", model_id, e)
            return False

    async def _await_prefetch_future(self, model_id: str, future: "Future[Dict[str, Any]]") -> Dict[str, Any]:
        """
        Await an in-flight prefetch Future without blocking the event loop.

        Issue #1944: Wraps future.result() in run_in_executor so waiting for
        an in-progress compilation does not stall the asyncio event loop.
        Returns the compiled model entry and records a prefetch hit.
        """
        if future.done():
            self._prefetch_hits += 1
            logger.debug(
                "Prefetch HIT for %s (hits=%d misses=%d)",
                model_id,
                self._prefetch_hits,
                self._prefetch_misses,
            )
            return future.result()

        t0 = time.monotonic()
        loop = asyncio.get_event_loop()
        entry = await loop.run_in_executor(None, future.result)
        wait_ms = (time.monotonic() - t0) * 1000
        self._prefetch_hits += 1
        logger.debug(
            "Prefetch PARTIAL HIT for %s (waited %.1f ms, hits=%d misses=%d)",
            model_id,
            wait_ms,
            self._prefetch_hits,
            self._prefetch_misses,
        )
        return entry

    async def _resolve_model_entry(self, model_id: str, model_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return a compiled model entry, honouring in-flight prefetch futures.

        Issue #1944: Uses the prefetch pipeline when available, otherwise falls
        back to a direct compilation in the thread pool (miss path).
        """
        if model_id in self._prefetch_futures:
            future = self._prefetch_futures.pop(model_id)
            return await self._await_prefetch_future(model_id, future)

        # Miss path: submit compilation now and wait for it
        self._prefetch_misses += 1
        t0 = time.monotonic()
        loop = asyncio.get_event_loop()
        entry = await loop.run_in_executor(self._executor, self._load_model_sync, model_id, model_config)
        load_ms = (time.monotonic() - t0) * 1000
        logger.debug(
            "Prefetch MISS for %s (load took %.1f ms, hits=%d misses=%d)",
            model_id,
            load_ms,
            self._prefetch_hits,
            self._prefetch_misses,
        )
        return entry

    async def unload_model(self, model_id: str) -> bool:
        """Unload a model and any pending prefetch to free memory."""
        try:
            # Cancel/drain any in-flight prefetch for this model
            if model_id in self._prefetch_futures:
                future = self._prefetch_futures.pop(model_id)
                # The Future cannot be cancelled once running but we discard it
                future.cancel()
                logger.debug("Discarded prefetch future for %s", model_id)

            self._prefetch_cache.pop(model_id, None)

            if model_id in self.loaded_models:
                del self.loaded_models[model_id]
                logger.info("Unloaded model %s", model_id)
                return True

            logger.warning("Model %s not loaded", model_id)
            return False
        except Exception as e:
            logger.error("Failed to unload model %s: %s", model_id, e)
            return False

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    async def inference(self, model_id: str, input_text: str, **kwargs) -> Dict[str, Any]:
        """Run inference on the NPU, returning result with timing metrics.

        Issue #1944: Callers should invoke prefetch_model() for the *next*
        model before awaiting this coroutine so compilation overlaps with
        NPU execution time.
        """
        if model_id not in self.loaded_models:
            logger.error("Model %s not loaded", model_id)
            return {"error": f"Model {model_id} not loaded"}

        model_info = self.loaded_models[model_id]
        model_info["inference_count"] += 1
        device = model_info["device"]
        compiled = model_info.get("compiled_model")
        logger.debug("Running inference on %s for model %s", device, model_id)
        t0 = time.monotonic()
        result = await self._run_inference_on_device(compiled, device, input_text, model_info, **kwargs)
        return {
            "model_id": model_id,
            "device": device,
            "response": result,
            "inference_time_ms": (time.monotonic() - t0) * 1000,
            "inference_count": model_info["inference_count"],
        }

    async def _run_inference_on_device(
        self,
        compiled: Any,
        device: str,
        input_text: str,
        model_info: Dict[str, Any],
        **kwargs,
    ) -> str:
        """
        Execute inference, dispatching real OpenVINO calls to the thread pool.

        When a real compiled model is present the blocking infer() call runs in
        the executor so the event loop remains responsive.  When only a stub is
        available (no IR file) the method simulates latency with asyncio.sleep.
        """
        if compiled is not None:
            loop = asyncio.get_event_loop()
            raw_output = await loop.run_in_executor(
                self._executor,
                self._infer_sync,
                compiled,
                input_text,
                kwargs,
            )
            return raw_output

        # Stub path: simulate device latency without blocking the loop
        simulated_ms = 100 if device == "NPU" else 300
        await asyncio.sleep(simulated_ms / 1000)
        return f"NPU inference response for: {input_text[:50]}..."

    def _infer_sync(self, compiled: Any, input_text: str, kwargs: Dict[str, Any]) -> str:
        """
        Run a single synchronous inference pass (called from thread pool).

        Builds a minimal numpy input tensor, executes the compiled model, and
        decodes the first output tensor to a Python string.  The exact input
        schema depends on the exported model; this implementation handles the
        common single-input sequence case.

        Called only when OpenVINO is available (compiled is non-None), so numpy
        is guaranteed to be importable.
        """
        if np is None:
            raise RuntimeError("numpy unavailable — OpenVINO import failed")
        try:
            infer_req = compiled.create_infer_request()
            input_tensor = np.array([[ord(c) for c in input_text[:512]]], dtype=np.int64)
            infer_req.infer({0: input_tensor})
            output = infer_req.get_output_tensor(0).data
            return str(output.flatten()[:20].tolist())
        except Exception as e:
            logger.error("OpenVINO infer_sync failed: %s", e)
            raise

    # ------------------------------------------------------------------
    # Status and metrics
    # ------------------------------------------------------------------

    def get_model_status(self) -> Dict[str, Any]:
        """Return status of all loaded models and prefetch pipeline metrics."""
        return {
            "npu_available": self.npu_available,
            "optimal_device": self.get_optimal_device(),
            "loaded_models": {
                model_id: {
                    "device": info["device"],
                    "inference_count": info["inference_count"],
                    "loaded_at": info["loaded_at"],
                }
                for model_id, info in self.loaded_models.items()
            },
            "available_devices": (self.core.available_devices if self.core else []),
            "prefetch": self._get_prefetch_metrics(),
        }

    def _get_prefetch_metrics(self) -> Dict[str, Any]:
        """Return Issue #1944 prefetch pipeline metrics."""
        total = self._prefetch_hits + self._prefetch_misses
        hit_rate = round(self._prefetch_hits / total, 3) if total > 0 else 0.0
        return {
            "hits": self._prefetch_hits,
            "misses": self._prefetch_misses,
            "hit_rate": hit_rate,
            "in_flight_prefetches": len(self._prefetch_futures),
            "total_load_time_saved_ms": round(self._total_load_time_saved_ms, 1),
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def cleanup(self) -> None:
        """Shutdown executor, drain prefetch futures, and unload all models."""
        # Drain in-flight prefetch futures so threads terminate cleanly
        for model_id, future in list(self._prefetch_futures.items()):
            future.cancel()
            logger.debug("Cancelled prefetch future for %s during cleanup", model_id)
        self._prefetch_futures.clear()
        self._prefetch_cache.clear()

        self._executor.shutdown(wait=False)
        logger.debug("ThreadPoolExecutor shut down")

        for model_id in list(self.loaded_models.keys()):
            await self.unload_model(model_id)

        logger.info("NPU Model Manager cleaned up")
