# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unified MultiModal Processor

Main multi-modal processor that coordinates all modal-specific processors
with attention-based fusion.

Part of Issue #381 - God Class Refactoring
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import torch

from enhanced_memory_manager_async import (
    TaskPriority,
    get_async_enhanced_memory_manager,
)
from utils.multimodal_performance_monitor import performance_monitor

from .models import MultiModalInput, ProcessingResult
from .processors import ContextProcessor, VisionProcessor, VoiceProcessor
from .types import EMBEDDING_FIELDS, VISUAL_MODALITY_TYPES, ModalityType

# Import torch modules for attention fusion
try:
    import torch.nn as nn

    TORCH_NN_AVAILABLE = True
except ImportError:
    TORCH_NN_AVAILABLE = False

logger = logging.getLogger(__name__)


class UnifiedMultiModalProcessor:
    """
    Main multi-modal processor that coordinates all modal-specific processors
    """

    def __init__(self):
        """Initialize unified processor with all modal-specific processors."""
        self.vision_processor = VisionProcessor()
        self.voice_processor = VoiceProcessor()
        self.context_processor = ContextProcessor()
        self.memory_manager = get_async_enhanced_memory_manager()
        self.logger = logging.getLogger(__name__)

        # Performance monitoring integration
        self.performance_monitor = performance_monitor

        # Enable mixed precision for RTX 4070 optimization
        self.use_amp = self.performance_monitor.enable_mixed_precision(enable=True)
        # Use torch.amp.GradScaler('cuda') instead of deprecated torch.cuda.amp.GradScaler()
        self.scaler = torch.amp.GradScaler("cuda") if self.use_amp else None

        if self.use_amp:
            self.logger.info("Mixed precision (AMP) enabled for RTX 4070 optimization")

        # Processing statistics
        self.stats = {
            "total_processed": 0,
            "successful_processed": 0,
            "failed_processed": 0,
            "avg_processing_time": 0.0,
            "modality_counts": {modality.value: 0 for modality in ModalityType},
        }

        # Initialize GPU device for fusion
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.logger.info(
            f"UnifiedMultiModalProcessor initialized with device: {self.device}"
        )
        if torch.cuda.is_available():
            self.logger.info(
                f"GPU: {torch.cuda.get_device_name(0)}, "
                f"Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GB"
            )

        # Initialize cross-modal fusion components
        self.fusion_network = None
        self.attention_layer = None
        self._initialize_fusion_components()

    async def _route_to_processor(
        self, input_data: MultiModalInput
    ) -> ProcessingResult:
        """Route input to appropriate processor (Issue #315 - extracted method)"""
        # Use dict-based routing to reduce if-elif chain nesting
        if input_data.modality_type in VISUAL_MODALITY_TYPES:
            return await self.vision_processor.process(input_data)
        if input_data.modality_type == ModalityType.AUDIO:
            return await self.voice_processor.process(input_data)
        if input_data.modality_type == ModalityType.TEXT:
            return await self.context_processor.process(input_data)
        if input_data.modality_type == ModalityType.COMBINED:
            return await self._process_combined(input_data)
        raise ValueError(f"Unknown modality type: {input_data.modality_type}")

    def _create_error_result(
        self,
        input_data: MultiModalInput,
        processing_time: float,
        error: Exception,
        prefix: str = "unified",
    ) -> ProcessingResult:
        """Create error result for failed processing (Issue #315 - extracted method)"""
        return ProcessingResult(
            result_id=f"{prefix}_{input_data.input_id}",
            input_id=input_data.input_id,
            modality_type=input_data.modality_type,
            intent=input_data.intent,
            success=False,
            confidence=0.0,
            result_data=None,
            processing_time=processing_time,
            error_message=str(error),
        )

    async def process(self, input_data: MultiModalInput) -> ProcessingResult:
        """
        Main processing method that routes input to appropriate processor
        """
        start_time = time.time()
        self.logger.info(
            f"Processing {input_data.modality_type.value} input "
            f"with intent {input_data.intent.value}"
        )

        # Auto-optimize performance if needed
        await self.performance_monitor.auto_optimize()

        try:
            # Route to appropriate processor (Issue #315 - extracted method)
            result = await self._route_to_processor(input_data)

            # Record performance metrics
            processing_time = time.time() - start_time
            self.performance_monitor.record_processing(
                modality=input_data.modality_type.value,
                processing_time=processing_time,
                items_processed=1,
            )

            # Update statistics
            self._update_stats(result)

            # Store result in memory
            await self._store_result(result)

            return result

        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error("Multi-modal processing failed: %s", e)

            # Record failed processing
            self.performance_monitor.record_processing(
                modality=input_data.modality_type.value,
                processing_time=processing_time,
                items_processed=0,
            )

            return self._create_error_result(input_data, processing_time, e)

    def _create_modality_tasks(self, input_data: MultiModalInput) -> List:
        """
        Create processing tasks for each modality in combined input.

        Issue #620.
        """
        tasks = []

        if "image" in input_data.metadata:
            image_input = MultiModalInput(
                input_id=f"{input_data.input_id}_image",
                modality_type=ModalityType.IMAGE,
                intent=input_data.intent,
                data=input_data.metadata["image"],
            )
            tasks.append(self.vision_processor.process(image_input))

        if "audio" in input_data.metadata:
            audio_input = MultiModalInput(
                input_id=f"{input_data.input_id}_audio",
                modality_type=ModalityType.AUDIO,
                intent=input_data.intent,
                data=input_data.metadata["audio"],
            )
            tasks.append(self.voice_processor.process(audio_input))

        return tasks

    def _build_combined_result(
        self, input_data: MultiModalInput, combined_result: Dict, processing_time: float
    ) -> ProcessingResult:
        """
        Build successful processing result for combined input.

        Issue #620.
        """
        return ProcessingResult(
            result_id=f"combined_{input_data.input_id}",
            input_id=input_data.input_id,
            modality_type=input_data.modality_type,
            intent=input_data.intent,
            success=True,
            confidence=combined_result.get("confidence", 0.5),
            result_data=combined_result,
            processing_time=processing_time,
        )

    def _build_error_result(
        self, input_data: MultiModalInput, processing_time: float, error: Exception
    ) -> ProcessingResult:
        """
        Build error processing result for combined input.

        Issue #620.
        """
        return ProcessingResult(
            result_id=f"combined_{input_data.input_id}",
            input_id=input_data.input_id,
            modality_type=input_data.modality_type,
            intent=input_data.intent,
            success=False,
            confidence=0.0,
            result_data=None,
            processing_time=processing_time,
            error_message=str(error),
        )

    async def _process_combined(self, input_data: MultiModalInput) -> ProcessingResult:
        """Process combined multi-modal input."""
        start_time = time.time()

        try:
            tasks = self._create_modality_tasks(input_data)
            results = await asyncio.gather(*tasks, return_exceptions=True)
            combined_result = self._combine_results(results)
            processing_time = time.time() - start_time
            return self._build_combined_result(
                input_data, combined_result, processing_time
            )

        except Exception as e:
            processing_time = time.time() - start_time
            return self._build_error_result(input_data, processing_time, e)

    def _initialize_fusion_components(self):
        """Initialize cross-modal attention fusion components."""
        if not TORCH_NN_AVAILABLE:
            self.logger.warning("PyTorch NN modules not available for fusion")
            return

        try:
            # Cross-modal attention fusion network
            # Designed to handle variable number of modalities (1-3)
            self.fusion_network = nn.Sequential(
                nn.Linear(1536, 768),  # Max concatenated embeddings (3 * 512)
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.LayerNorm(768),
                nn.Linear(768, 512),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(512, 512),  # Final fused embedding
            ).to(self.device)

            # Multi-head attention for modality weighting
            self.attention_layer = nn.MultiheadAttention(
                embed_dim=512, num_heads=8, dropout=0.1, batch_first=True
            ).to(self.device)

            # Set to evaluation mode
            self.fusion_network.eval()

            self.logger.info(
                "Cross-modal fusion components initialized on %s", self.device
            )
        except Exception as e:
            self.logger.error("Failed to initialize fusion components: %s", e)

    def _extract_embedding_from_result(self, result: ProcessingResult) -> Optional[Any]:
        """Extract embedding from a processing result (Issue #315 - extracted method)"""
        if not result.result_data:
            return None

        # Try different embedding field names
        for field_name in EMBEDDING_FIELDS:  # Issue #380: use module constant
            if field_name in result.result_data:
                return result.result_data.get(field_name)

        return None

    def _collect_embeddings_from_results(
        self, results: List[ProcessingResult]
    ) -> tuple:
        """Collect and filter embeddings from results (Issue #315 - extracted method)"""
        embeddings = []
        modalities = []
        confidences = []
        result_data = []

        for result in results:
            # Guard clause: Skip unsuccessful or invalid results
            if not isinstance(result, ProcessingResult) or not result.success:
                continue

            # Extract embedding using helper method
            embedding = self._extract_embedding_from_result(result)
            if embedding is None:
                continue

            # Convert to tensor if needed
            if not isinstance(embedding, torch.Tensor):
                embedding = torch.tensor(embedding, dtype=torch.float32)

            # Guard clause: Skip empty embeddings
            if embedding.numel() == 0:
                continue

            # Collect valid embedding data
            embeddings.append(embedding.to(self.device))
            modalities.append(result.modality_type.value)
            confidences.append(result.confidence)
            result_data.append(result.result_data)

        return embeddings, modalities, confidences, result_data

    def _normalize_embeddings(
        self, embeddings: List[torch.Tensor]
    ) -> List[torch.Tensor]:
        """Normalize embeddings to target dimension (Issue #315 - extracted method)"""
        normalized_embeddings = []
        target_dim = 512

        for emb in embeddings:
            emb_flat = emb.flatten()
            if emb_flat.shape[0] < target_dim:
                # Pad with zeros
                padded = torch.zeros(target_dim, device=self.device)
                padded[: emb_flat.shape[0]] = emb_flat
                normalized_embeddings.append(padded)
            else:
                # Truncate or use as is
                normalized_embeddings.append(emb_flat[:target_dim])

        return normalized_embeddings

    def _apply_attention_fusion(self, stacked_embeddings: torch.Tensor) -> tuple:
        """Apply multi-head attention (Issue #315 - extracted method)"""
        use_cuda = torch.cuda.is_available()
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_cuda):
            attended_output, attention_weights = self.attention_layer(
                stacked_embeddings, stacked_embeddings, stacked_embeddings
            )
        return attended_output, attention_weights

    def _compute_fused_embedding(
        self, weighted_embeddings: torch.Tensor
    ) -> torch.Tensor:
        """Compute final fused embedding (Issue #315 - extracted method)"""
        # Prepare input for fusion network (pad to 1536 = 3 modalities * 512)
        fusion_input = torch.zeros(1536, device=self.device)
        flat_weighted = weighted_embeddings.flatten()
        fusion_input[: min(flat_weighted.shape[0], 1536)] = flat_weighted[:1536]

        # Apply fusion network with autocast if available
        use_cuda = torch.cuda.is_available()
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_cuda):
            fused_embedding = self.fusion_network(fusion_input)

        return fused_embedding

    def _extract_modality_contributions(
        self, attention_weights: Optional[Any], modalities: List[str]
    ) -> Dict[str, float]:
        """Extract modality contributions from attention weights. Issue #620."""
        if attention_weights is not None:
            attn_scores = attention_weights.mean(dim=1).squeeze().cpu().numpy()
            return dict(zip(modalities, attn_scores[: len(modalities)]))
        return {m: 1.0 / len(modalities) for m in modalities}

    def _build_fusion_result(
        self,
        fused_embedding: torch.Tensor,
        fusion_confidence: float,
        modality_contributions: Dict[str, float],
        modalities: List[str],
        embeddings: List[torch.Tensor],
        results: List[ProcessingResult],
        result_data: List[Any],
    ) -> Dict[str, Any]:
        """Build the final fusion result dictionary. Issue #620."""
        return {
            "fusion_type": "attention_based",
            "fused_embedding": fused_embedding.cpu().numpy().tolist(),
            "fusion_confidence": fusion_confidence,
            "modality_contributions": modality_contributions,
            "modalities_fused": modalities,
            "success_count": len(embeddings),
            "total_count": len(results),
            "individual_results": result_data,
        }

    def _perform_attention_fusion(
        self,
        embeddings: List[torch.Tensor],
        modalities: List[str],
        confidences: List[float],
        result_data: List[Any],
        results: List[ProcessingResult],
    ) -> Dict[str, Any]:
        """Perform attention-based fusion on embeddings. Issue #620."""
        with torch.no_grad():
            normalized_embeddings = self._normalize_embeddings(embeddings)
            stacked_embeddings = torch.stack(normalized_embeddings).unsqueeze(0)
            attended_output, attention_weights = self._apply_attention_fusion(
                stacked_embeddings
            )

            confidence_weights = torch.tensor(
                confidences, device=self.device
            ).unsqueeze(-1)
            weighted_embeddings = attended_output.squeeze(0) * confidence_weights
            fused_embedding = self._compute_fused_embedding(weighted_embeddings)
            fusion_confidence = torch.mean(confidence_weights).item()
            modality_contributions = self._extract_modality_contributions(
                attention_weights, modalities
            )

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return self._build_fusion_result(
            fused_embedding,
            fusion_confidence,
            modality_contributions,
            modalities,
            embeddings,
            results,
            result_data,
        )

    def _combine_results(self, results: List[ProcessingResult]) -> Dict[str, Any]:
        """Combine results from multiple processors with attention-based fusion."""
        if self.fusion_network is None or self.attention_layer is None:
            return self._simple_combination(results)

        (
            embeddings,
            modalities,
            confidences,
            result_data,
        ) = self._collect_embeddings_from_results(results)

        if len(embeddings) < 2:
            return self._simple_combination(results)

        try:
            return self._perform_attention_fusion(
                embeddings, modalities, confidences, result_data, results
            )
        except Exception as e:
            self.logger.error("Attention fusion failed: %s", e)
            return self._simple_combination(results)

    def _simple_combination(self, results: List[ProcessingResult]) -> Dict[str, Any]:
        """Simple fallback combination without attention fusion."""
        combined = {
            "fusion_type": "simple_average",
            "results": [],
            "confidence": 0.0,
            "success_count": 0,
            "total_count": len(results),
        }

        confidence_sum = 0.0
        for result in results:
            if isinstance(result, ProcessingResult):
                combined["results"].append(
                    {
                        "modality": result.modality_type.value,
                        "success": result.success,
                        "confidence": result.confidence,
                        "data": result.result_data,
                    }
                )
                if result.success:
                    combined["success_count"] += 1
                    confidence_sum += result.confidence

        # Calculate average confidence
        if combined["success_count"] > 0:
            combined["confidence"] = confidence_sum / combined["success_count"]

        return combined

    def _update_stats(self, result: ProcessingResult):
        """Update processing statistics"""
        self.stats["total_processed"] += 1

        if result.success:
            self.stats["successful_processed"] += 1
        else:
            self.stats["failed_processed"] += 1

        # Update modality counts
        self.stats["modality_counts"][result.modality_type.value] += 1

        # Update average processing time
        total_time = (
            self.stats["avg_processing_time"] * (self.stats["total_processed"] - 1)
            + result.processing_time
        )
        self.stats["avg_processing_time"] = total_time / self.stats["total_processed"]

    async def _store_result(self, result: ProcessingResult):
        """Store processing result in memory"""
        try:
            task_data = {
                "result_id": result.result_id,
                "modality": result.modality_type.value,
                "intent": result.intent.value,
                "success": result.success,
                "confidence": result.confidence,
                "processing_time": result.processing_time,
            }

            await self.memory_manager.store_task(
                task_id=result.result_id,
                task_type="multimodal_processing",
                description=f"Multi-modal processing: {result.modality_type.value}",
                status="completed" if result.success else "failed",
                priority=TaskPriority.MEDIUM,
                subtasks=[],
                context=task_data,
                execution_details={"result_data": result.result_data},
            )

        except Exception as e:
            self.logger.warning("Failed to store processing result: %s", e)

    def _group_inputs_by_modality(
        self, inputs: List[MultiModalInput]
    ) -> Dict[str, List[MultiModalInput]]:
        """Group inputs by modality type (Issue #315 - extracted method)"""
        modality_groups: Dict[str, List[MultiModalInput]] = {}
        for inp in inputs:
            modality = inp.modality_type.value
            if modality not in modality_groups:
                modality_groups[modality] = []
            modality_groups[modality].append(inp)
        return modality_groups

    async def _process_single_batch(
        self, batch: List[MultiModalInput], modality: str
    ) -> List[ProcessingResult]:
        """Process a single batch of inputs (Issue #315 - extracted method)"""
        # Memory optimization before processing
        if self.performance_monitor.should_optimize():
            await self.performance_monitor.optimize_gpu_memory()

        # Route to specialized batch processor or process individually
        if modality == "image" and len(batch) > 1:
            return await self._process_image_batch(batch)
        if modality == "audio" and len(batch) > 1:
            return await self._process_audio_batch(batch)

        # Process individually for other modalities or small batches
        return [await self.process(inp) for inp in batch]

    async def _process_modality_group(
        self, modality: str, group_inputs: List[MultiModalInput]
    ) -> List[ProcessingResult]:
        """Process all batches for a single modality (Issue #315 - extracted method)"""
        results = []
        batch_size = self.performance_monitor.get_optimal_batch_size(modality)

        for i in range(0, len(group_inputs), batch_size):
            batch = group_inputs[i : i + batch_size]
            self.logger.debug("Processing batch of %s %s inputs", len(batch), modality)
            batch_results = await self._process_single_batch(batch, modality)
            results.extend(batch_results)

        return results

    async def _fallback_individual_processing(
        self, inputs: List[MultiModalInput]
    ) -> List[ProcessingResult]:
        """Fallback to individual processing on batch failure (Issue #315 - extracted)"""
        results = []
        for inp in inputs:
            result = await self._process_input_with_fallback(inp)
            results.append(result)
        return results

    async def _process_input_with_fallback(
        self, inp: MultiModalInput
    ) -> ProcessingResult:
        """Process single input with error handling (Issue #315 - extracted method)"""
        try:
            return await self.process(inp)
        except Exception as individual_error:
            self.logger.error(
                f"Individual processing failed for {inp.input_id}: {individual_error}"
            )
            return self._create_error_result(inp, 0.0, individual_error, "batch_error")

    async def process_batch(
        self, inputs: List[MultiModalInput]
    ) -> List[ProcessingResult]:
        """
        Process multiple inputs efficiently using optimized batching
        """
        if not inputs:
            return []

        self.logger.info("Processing batch of %s inputs", len(inputs))
        start_time = time.time()

        # Auto-optimize performance before batch processing
        await self.performance_monitor.auto_optimize()

        try:
            # Group inputs by modality (Issue #315 - extracted method)
            modality_groups = self._group_inputs_by_modality(inputs)

            # Process each modality group (Issue #315 - extracted method)
            results = []
            for modality, group_inputs in modality_groups.items():
                group_results = await self._process_modality_group(
                    modality, group_inputs
                )
                results.extend(group_results)

            # Record batch processing performance
            total_processing_time = time.time() - start_time
            self.performance_monitor.record_processing(
                modality="batch",
                processing_time=total_processing_time,
                items_processed=len(inputs),
            )

            self.logger.info(
                f"Batch processing completed: {len(results)} results "
                f"in {total_processing_time:.2f}s"
            )
            return results

        except Exception as e:
            self.logger.error("Batch processing failed: %s", e)
            return await self._fallback_individual_processing(inputs)

    async def _process_image_batch(
        self, batch: List[MultiModalInput]
    ) -> List[ProcessingResult]:
        """Process a batch of images efficiently"""
        results = []

        try:
            # Use mixed precision if available
            if self.use_amp and torch.cuda.is_available():
                with torch.amp.autocast("cuda"):
                    for inp in batch:
                        result = await self.vision_processor.process(inp)
                        results.append(result)
            else:
                for inp in batch:
                    result = await self.vision_processor.process(inp)
                    results.append(result)

        except Exception as e:
            self.logger.error("Image batch processing failed: %s", e)
            # Fallback to individual processing
            for inp in batch:
                try:
                    result = await self.vision_processor.process(inp)
                    results.append(result)
                except Exception as individual_error:
                    error_result = ProcessingResult(
                        result_id=f"image_batch_error_{inp.input_id}",
                        input_id=inp.input_id,
                        modality_type=inp.modality_type,
                        intent=inp.intent,
                        success=False,
                        confidence=0.0,
                        result_data=None,
                        processing_time=0.0,
                        error_message=str(individual_error),
                    )
                    results.append(error_result)

        return results

    async def _process_audio_batch(
        self, batch: List[MultiModalInput]
    ) -> List[ProcessingResult]:
        """Process a batch of audio inputs efficiently"""
        results = []

        try:
            # Use mixed precision if available
            if self.use_amp and torch.cuda.is_available():
                with torch.amp.autocast("cuda"):
                    for inp in batch:
                        result = await self.voice_processor.process(inp)
                        results.append(result)
            else:
                for inp in batch:
                    result = await self.voice_processor.process(inp)
                    results.append(result)

        except Exception as e:
            self.logger.error("Audio batch processing failed: %s", e)
            # Fallback to individual processing
            for inp in batch:
                try:
                    result = await self.voice_processor.process(inp)
                    results.append(result)
                except Exception as individual_error:
                    error_result = ProcessingResult(
                        result_id=f"audio_batch_error_{inp.input_id}",
                        input_id=inp.input_id,
                        modality_type=inp.modality_type,
                        intent=inp.intent,
                        success=False,
                        confidence=0.0,
                        result_data=None,
                        processing_time=0.0,
                        error_message=str(individual_error),
                    )
                    results.append(error_result)

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics including model availability"""
        stats = self.stats.copy()
        # Issue #675: Add model availability status for frontend display
        stats["model_availability"] = {
            "vision": {
                "clip_available": self.vision_processor.clip_model is not None,
                "blip_available": self.vision_processor.blip_model is not None,
                "enabled": self.vision_processor.enabled,
            },
            "voice": {
                "whisper_available": self.voice_processor.whisper_model is not None,
                "wav2vec_available": self.voice_processor.wav2vec_model is not None
                if hasattr(self.voice_processor, "wav2vec_model")
                else False,
                "enabled": self.voice_processor.enabled,
            },
        }
        return stats

    def reset_stats(self):
        """Reset processing statistics"""
        self.stats = {
            "total_processed": 0,
            "successful_processed": 0,
            "failed_processed": 0,
            "avg_processing_time": 0.0,
            "modality_counts": {modality.value: 0 for modality in ModalityType},
        }
