# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Media Pipeline Manager
# Issue #735: Organize media processing into dedicated pipelines

"""Centralized manager for all media processing pipelines."""

import logging
from typing import Dict, List, Optional

from media.audio.pipeline import AudioPipeline
from media.core.pipeline import MediaPipeline
from media.core.types import MediaInput, MediaType, ProcessingResult
from media.document.pipeline import DocumentPipeline
from media.image.pipeline import ImagePipeline
from media.link.pipeline import LinkPipeline
from media.video.pipeline import VideoPipeline

logger = logging.getLogger(__name__)


class MediaPipelineManager:
    """
    Central manager for coordinating media processing pipelines.

    Automatically routes media inputs to the appropriate pipeline
    based on media type.
    """

    def __init__(self):
        """Initialize all media pipelines."""
        self.pipelines: Dict[str, MediaPipeline] = {
            "image": ImagePipeline(),
            "audio": AudioPipeline(),
            "video": VideoPipeline(),
            "document": DocumentPipeline(),
            "link": LinkPipeline(),
        }

    def get_pipeline(self, media_type: MediaType) -> Optional[MediaPipeline]:
        """
        Get appropriate pipeline for media type.

        Args:
            media_type: Type of media to process

        Returns:
            Pipeline instance or None if not found
        """
        for pipeline in self.pipelines.values():
            if pipeline.supports(media_type):
                return pipeline
        return None

    async def process(self, media_input: MediaInput) -> ProcessingResult:
        """
        Process media input through appropriate pipeline.

        Args:
            media_input: Input to process

        Returns:
            Processing result from pipeline
        """
        pipeline = self.get_pipeline(media_input.media_type)

        if pipeline is None:
            logger.error("No pipeline found for media type: %s", media_input.media_type)
            return ProcessingResult(
                result_id=f"no_pipeline_{media_input.media_id}",
                media_id=media_input.media_id,
                media_type=media_input.media_type,
                intent=media_input.intent,
                success=False,
                confidence=0.0,
                result_data=None,
                processing_time=0.0,
                error_message=(
                    f"No pipeline supports media type: "
                    f"{media_input.media_type.value}"
                ),
            )

        return await pipeline.process(media_input)

    def list_pipelines(self) -> List[str]:
        """
        List all available pipeline names.

        Returns:
            List of pipeline names
        """
        return list(self.pipelines.keys())

    def get_pipeline_by_name(self, name: str) -> Optional[MediaPipeline]:
        """
        Get pipeline by name.

        Args:
            name: Pipeline name

        Returns:
            Pipeline instance or None if not found
        """
        return self.pipelines.get(name)

    def get_all_metrics(self) -> Dict[str, Dict]:
        """
        Get metrics from all pipelines.

        Returns:
            Dictionary mapping pipeline name to metrics
        """
        return {
            name: {
                "total_processed": pipeline.metrics.total_processed,
                "successful": pipeline.metrics.successful,
                "failed": pipeline.metrics.failed,
                "average_time": pipeline.metrics.average_time,
                "average_confidence": pipeline.metrics.average_confidence,
                "enabled": pipeline.is_enabled(),
            }
            for name, pipeline in self.pipelines.items()
        }

    def reset_all_metrics(self) -> None:
        """Reset metrics for all pipelines."""
        for pipeline in self.pipelines.values():
            pipeline.reset_metrics()
        logger.info("All pipeline metrics reset")


# Singleton instance for global access
_manager_instance: Optional[MediaPipelineManager] = None


def get_media_pipeline_manager() -> MediaPipelineManager:
    """
    Get singleton media pipeline manager instance.

    Returns:
        MediaPipelineManager singleton
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = MediaPipelineManager()
    return _manager_instance
