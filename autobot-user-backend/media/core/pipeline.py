# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Base Media Pipeline
# Issue #735: Organize media processing into dedicated pipelines

"""Base abstract class for media processing pipelines."""

import logging
import time
from abc import ABC, abstractmethod
from typing import List

from media.core.types import MediaInput, MediaType, PipelineMetrics, ProcessingResult


class MediaPipeline(ABC):
    """
    Abstract base class for media processing pipelines.

    Each media type (image, audio, video, etc.) should implement this
    interface to provide consistent processing capabilities.
    """

    def __init__(self, pipeline_name: str):
        """
        Initialize pipeline.

        Args:
            pipeline_name: Name identifier for this pipeline
        """
        self.pipeline_name = pipeline_name
        self.logger = logging.getLogger(f"{__name__}.{pipeline_name}")
        self.metrics = PipelineMetrics()
        self._enabled = True

    @abstractmethod
    def supports(self, media_type: MediaType) -> bool:
        """
        Check if this pipeline supports the given media type.

        Args:
            media_type: The media type to check

        Returns:
            True if supported, False otherwise
        """
        raise NotImplementedError

    @abstractmethod
    async def process(self, media_input: MediaInput) -> ProcessingResult:
        """
        Process media input and return result.

        Args:
            media_input: Input data to process

        Returns:
            Processing result with data and metadata
        """
        raise NotImplementedError

    def enable(self) -> None:
        """Enable this pipeline for processing."""
        self._enabled = True
        self.logger.info("Pipeline '%s' enabled", self.pipeline_name)

    def disable(self) -> None:
        """Disable this pipeline from processing."""
        self._enabled = False
        self.logger.info("Pipeline '%s' disabled", self.pipeline_name)

    def is_enabled(self) -> bool:
        """Check if pipeline is enabled."""
        return self._enabled

    def get_metrics(self) -> PipelineMetrics:
        """Get current pipeline metrics."""
        return self.metrics

    def reset_metrics(self) -> None:
        """Reset pipeline metrics to zero."""
        self.metrics = PipelineMetrics()
        self.logger.debug("Pipeline '%s' metrics reset", self.pipeline_name)

    def _update_metrics(self, result: ProcessingResult) -> None:
        """Update pipeline metrics based on result. Helper for process()."""
        self.metrics.total_processed += 1

        if result.success:
            self.metrics.successful += 1
            # Update average confidence
            total_confidence = (
                self.metrics.average_confidence * (self.metrics.successful - 1)
                + result.confidence
            )
            self.metrics.average_confidence = total_confidence / self.metrics.successful
        else:
            self.metrics.failed += 1

        # Update average processing time
        total_time = (
            self.metrics.average_time * (self.metrics.total_processed - 1)
            + result.processing_time
        )
        self.metrics.average_time = total_time / self.metrics.total_processed


class BasePipeline(MediaPipeline):
    """
    Base implementation of MediaPipeline with common functionality.

    Subclasses can override specific methods while inheriting shared logic.
    """

    def __init__(self, pipeline_name: str, supported_types: List[MediaType]):
        """
        Initialize base pipeline.

        Args:
            pipeline_name: Name identifier for this pipeline
            supported_types: List of media types this pipeline supports
        """
        super().__init__(pipeline_name)
        self.supported_types = supported_types

    def supports(self, media_type: MediaType) -> bool:
        """Check if media type is in supported types list."""
        return media_type in self.supported_types

    async def process(self, media_input: MediaInput) -> ProcessingResult:
        """
        Process media with error handling and metrics tracking.

        Args:
            media_input: Input to process

        Returns:
            Processing result
        """
        if not self.is_enabled():
            return ProcessingResult(
                result_id=f"{self.pipeline_name}_{media_input.media_id}",
                media_id=media_input.media_id,
                media_type=media_input.media_type,
                intent=media_input.intent,
                success=False,
                confidence=0.0,
                result_data=None,
                processing_time=0.0,
                error_message=f"Pipeline '{self.pipeline_name}' is disabled",
            )

        if not self.supports(media_input.media_type):
            return ProcessingResult(
                result_id=f"{self.pipeline_name}_{media_input.media_id}",
                media_id=media_input.media_id,
                media_type=media_input.media_type,
                intent=media_input.intent,
                success=False,
                confidence=0.0,
                result_data=None,
                processing_time=0.0,
                error_message=(
                    f"Media type {media_input.media_type.value} "
                    f"not supported by {self.pipeline_name}"
                ),
            )

        start_time = time.time()
        try:
            result = await self._process_impl(media_input)
            result.processing_time = time.time() - start_time
            self._update_metrics(result)
            return result

        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error(
                "Pipeline '%s' processing failed: %s", self.pipeline_name, e
            )
            result = ProcessingResult(
                result_id=f"{self.pipeline_name}_{media_input.media_id}",
                media_id=media_input.media_id,
                media_type=media_input.media_type,
                intent=media_input.intent,
                success=False,
                confidence=0.0,
                result_data=None,
                processing_time=processing_time,
                error_message=str(e),
            )
            self._update_metrics(result)
            return result

    @abstractmethod
    async def _process_impl(self, media_input: MediaInput) -> ProcessingResult:
        """
        Actual processing implementation (override in subclasses).

        Args:
            media_input: Input to process

        Returns:
            Processing result
        """
        raise NotImplementedError
