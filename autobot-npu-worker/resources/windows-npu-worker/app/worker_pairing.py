# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pairing with the main host (#641, #15642).

The one flow that changes persisted worker state: ``/pair`` accepts an ID and a
configuration from the main host, ``/pairing-status`` reports it and
``/unpair`` clears it. Applying the configuration that arrives with a pairing —
including the model preload it can request — belongs to the same flow and lives
here with it.

This module ships inside the standalone Windows package: PyInstaller's
``installer/npu_worker.spec`` analyses ``app/npu_worker.py`` with
``pathex=[app]``, and ``scripts/install.ps1`` copies only this tree. Nothing
here may import ``autobot_shared`` — it is not on the worker's disk.
"""

import logging
from typing import Any, Dict

from api_schemas import PairRequest, PairResponse
from fastapi import HTTPException
from worker_identity import PAIRING_STATUS_FILE, WORKER_ID_FILE, get_pairing_status, save_pairing_status, save_worker_id

from async_compat import fire_and_forget

logger = logging.getLogger(__name__)


class WorkerPairingMixin:
    """Pairing routes and main-host configuration for :class:`WindowsNPUWorker`."""

    def _register_pairing_routes(self):
        """Register /pair, /pairing-status, and /unpair routes (Issue #641)."""

        @self.app.post("/pair", response_model=PairResponse)
        async def pair_with_main_host(request: PairRequest):
            """Issue #641: Assign worker ID and establish pairing with main host."""
            return await self._handle_pair(request)

        @self.app.get("/pairing-status")
        async def get_pairing_status_endpoint():
            """Issue #641: Get current pairing status."""
            return self._handle_pairing_status()

        @self.app.post("/unpair")
        async def unpair_from_main_host():
            """Issue #641: Unpair from main host, allowing re-pairing."""
            return self._handle_unpair()

    async def _handle_pair(self, request: PairRequest) -> PairResponse:
        """
        Handle POST /pair — main host assigns a permanent worker ID.

        Issue #641: This is the ONLY way a worker gets its ID.
        Workers do NOT self-register; main host controls registration via /pair.

        Args:
            request: PairRequest containing worker_id, main_host, and optional config.

        Returns:
            PairResponse indicating success or failure.
        """
        try:
            # Reject if already paired with a different host
            if self.worker_id and self.worker_id != request.worker_id:
                if self.pairing_status.get("main_host") != request.main_host:
                    return PairResponse(
                        success=False,
                        worker_id=self.worker_id,
                        message=(
                            f"Worker already paired with different host: " f"{self.pairing_status.get('main_host')}"
                        ),
                    )

            if not save_worker_id(request.worker_id):
                return PairResponse(
                    success=False,
                    worker_id=request.worker_id,
                    message="Failed to save worker ID",
                )

            self.worker_id = request.worker_id
            save_pairing_status(request.main_host, request.worker_id)
            self.pairing_status = get_pairing_status()

            if request.config:
                self._apply_main_host_config(request.config)

            logger.info(f"Successfully paired with main host {request.main_host}")

            device_info = None
            if self._model_manager:
                try:
                    device_info = self._model_manager.get_device_info()
                except Exception:
                    logger.debug("Suppressed exception in try block", exc_info=True)

            return PairResponse(
                success=True,
                worker_id=self.worker_id,
                message=f"Successfully paired with main host {request.main_host}",
                device_info=device_info,
            )

        except Exception as e:
            logger.error(f"Pairing failed: {e}")
            raise HTTPException(status_code=500, detail="Pairing failed")

    def _handle_pairing_status(self) -> Dict[str, Any]:
        """Return current pairing status for GET /pairing-status (Issue #641)."""
        return {
            "paired": self.pairing_status.get("paired", False),
            "worker_id": self.worker_id,
            "main_host": self.pairing_status.get("main_host"),
            "paired_at": self.pairing_status.get("paired_at"),
            "npu_available": self.npu_available,
            "platform": "windows",
        }

    def _handle_unpair(self) -> Dict[str, Any]:
        """
        Remove worker ID and pairing status for POST /unpair (Issue #641).

        Returns:
            Dict with success flag and message.
        """
        try:
            if WORKER_ID_FILE.exists():
                WORKER_ID_FILE.unlink()
            if PAIRING_STATUS_FILE.exists():
                PAIRING_STATUS_FILE.unlink()

            old_id = self.worker_id
            self.worker_id = None
            self.pairing_status = {
                "paired": False,
                "main_host": None,
                "paired_at": None,
            }

            logger.info(f"Unpaired worker (was: {old_id})")
            return {"success": True, "message": f"Worker unpaired (was: {old_id})"}

        except Exception as e:
            logger.error(f"Unpair failed: {e}")
            raise HTTPException(status_code=500, detail="Unpair failed")

    def _apply_main_host_config(self, host_config: Dict[str, Any]) -> None:
        """
        Apply configuration received from main host during pairing.

        Issue #641: Main host sends configuration when pairing with worker.
        This allows centralized configuration management.

        Args:
            host_config: Configuration dictionary from main host
        """
        try:
            logger.info("Applying configuration from main host")

            # Apply Redis config if provided
            if "redis" in host_config:
                redis_cfg = host_config["redis"]
                logger.info(f"Received Redis config from main host: {redis_cfg.get('host', 'N/A')}")
                # Store for use by initialize_redis on next restart
                self._bootstrap_config = {"redis": redis_cfg}

            # Apply NPU optimization settings if provided
            if "npu" in host_config:
                npu_cfg = host_config["npu"]
                if "optimization" in npu_cfg:
                    self.npu_optimization.update(npu_cfg["optimization"])
                    logger.info(f"Updated NPU optimization: {self.npu_optimization}")

            # Apply model preload settings if provided
            if "models" in host_config:
                models_cfg = host_config["models"]
                if models_cfg.get("preload"):
                    # Schedule model loading (don't block pairing response).
                    # #15522: retained by fire_and_forget — the loop keeps only
                    # a weak reference, so a discarded preload could be
                    # collected before it ran, silently.
                    fire_and_forget(
                        self._preload_models_from_config(models_cfg),
                        name="npu-preload-models-from-pairing",
                    )

            logger.info("Main host configuration applied successfully")

        except Exception as e:
            logger.error(f"Failed to apply main host config: {e}")

    async def _preload_models_from_config(self, models_config: Dict[str, Any]) -> None:
        """Preload models specified in main host configuration."""
        try:
            for model_name in models_config.get("preload", []):
                logger.info(f"Preloading model from main host config: {model_name}")
                await self.load_and_optimize_model(model_name)
        except Exception as e:
            logger.warning(f"Failed to preload models: {e}")
