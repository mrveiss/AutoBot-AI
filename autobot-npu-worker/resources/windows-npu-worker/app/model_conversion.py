# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Getting a model onto disk in ONNX form (#640, #15642).

Downloads a supported model from HuggingFace and exports it to ONNX, which is
the only shape the OpenVINO execution provider can load. Split out of
``ONNXModelManager``, which mixes it in: this is slow, one-off, network-and-
disk work, unrelated to serving an already-converted model.

This module ships inside the standalone Windows package: PyInstaller's
``installer/npu_worker.spec`` analyses ``app/npu_worker.py`` with
``pathex=[app]``, and ``scripts/install.ps1`` copies only this tree. Nothing
here may import ``autobot_shared`` — it is not on the worker's disk.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict

from worker_settings import SUPPORTED_MODELS

logger = logging.getLogger(__name__)


class ModelConversionMixin:
    """Download and ONNX-export helpers for :class:`ONNXModelManager`."""

    async def ensure_model_downloaded(self, model_name: str) -> Path:
        """
        Ensure model is downloaded and converted to ONNX format.

        Downloads from HuggingFace if not present, then exports to ONNX.
        """
        model_config = SUPPORTED_MODELS.get(model_name)
        if not model_config:
            raise ValueError(f"Unsupported model: {model_name}. Supported: {list(SUPPORTED_MODELS.keys())}")

        model_path = self.models_dir / model_name
        onnx_model_path = model_path / "model.onnx"

        if onnx_model_path.exists():
            logger.info(f"Model {model_name} already in ONNX format")
            return model_path

        logger.info(f"Downloading and converting model: {model_name}")

        # Run blocking operations in thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._download_and_convert, model_name, model_config, model_path)

        return model_path

    def _download_and_convert(self, model_name: str, model_config: Dict, model_path: Path):
        """Download model from HuggingFace and export to ONNX (blocking)"""
        try:
            from transformers import AutoModel, AutoTokenizer

            hf_id = model_config["hf_id"]
            logger.info(f"Downloading {hf_id} from HuggingFace...")

            # Download model and tokenizer
            tokenizer = AutoTokenizer.from_pretrained(hf_id, trust_remote_code=True)
            model = AutoModel.from_pretrained(hf_id, trust_remote_code=True)
            model.eval()

            # Save tokenizer for later use
            model_path.mkdir(parents=True, exist_ok=True)
            tokenizer.save_pretrained(str(model_path))

            # Export to ONNX
            logger.info(f"Exporting {model_name} to ONNX format...")
            self._export_to_onnx(model, tokenizer, model_config, model_path)

            logger.info(f"Model {model_name} successfully exported to ONNX format")

        except Exception as e:
            logger.error(f"Failed to download/convert model {model_name}: {e}")
            raise

    def _export_to_onnx(self, model, tokenizer, model_config: Dict, model_path: Path):
        """Export PyTorch model to ONNX format"""
        try:
            import torch

            # Create dummy input for tracing
            # Use fixed sequence length for NPU compatibility (static shapes)
            max_length = min(model_config.get("max_length", 512), 512)
            dummy_input = tokenizer(
                "This is a sample text for model export.",
                padding="max_length",
                max_length=max_length,
                truncation=True,
                return_tensors="pt",
            )

            onnx_path = model_path / "model.onnx"

            # Export with static shapes for better NPU/DirectML compatibility
            # Issue #640: NPU prefers static shapes over dynamic
            logger.info(f"Exporting with static sequence length: {max_length}")

            with torch.no_grad():
                torch.onnx.export(
                    model,
                    (dummy_input["input_ids"], dummy_input["attention_mask"]),
                    str(onnx_path),
                    input_names=["input_ids", "attention_mask"],
                    output_names=["last_hidden_state"],
                    # Use static batch size but allow dynamic sequence for flexibility
                    dynamic_axes={
                        "input_ids": {0: "batch_size"},
                        "attention_mask": {0: "batch_size"},
                        "last_hidden_state": {0: "batch_size"},
                    },
                    opset_version=14,
                    do_constant_folding=True,  # Optimize constants
                )

            # Verify the ONNX model
            import onnx

            onnx_model = onnx.load(str(onnx_path))
            onnx.checker.check_model(onnx_model)
            logger.info(f"ONNX model verified and saved to {onnx_path}")

        except Exception as e:
            logger.error(f"ONNX export failed: {e}")
            raise
