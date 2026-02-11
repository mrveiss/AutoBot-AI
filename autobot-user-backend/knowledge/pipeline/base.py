# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base Classes for ECL Knowledge Pipeline.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID


class PipelineContext:
    """Context object passed through pipeline stages."""

    def __init__(self) -> None:
        """Initialize pipeline context."""
        self.chunks: List[Any] = []
        self.entities: List[Any] = []
        self.relationships: List[Any] = []
        self.events: List[Any] = []
        self.summaries: List[Any] = []
        self.metadata: Dict[str, Any] = {}
        self.document_id: Optional[UUID] = None


class PipelineResult:
    """Result of a pipeline execution with metrics."""

    def __init__(
        self,
        document_id: Optional[UUID] = None,
        started_at: Optional[datetime] = None,
    ) -> None:
        """Initialize pipeline result."""
        self.document_id = document_id
        self.started_at = started_at
        self.completed_at: Optional[datetime] = None
        self.duration_seconds: float = 0.0
        self.chunks_processed: int = 0
        self.entities_extracted: int = 0
        self.relationships_extracted: int = 0
        self.events_extracted: int = 0
        self.summaries_generated: int = 0
        self.errors: List[str] = []

    @property
    def entities_count(self) -> int:
        """Alias for API compatibility."""
        return self.entities_extracted

    @property
    def relationships_count(self) -> int:
        """Alias for API compatibility."""
        return self.relationships_extracted

    @property
    def events_count(self) -> int:
        """Alias for API compatibility."""
        return self.events_extracted

    @property
    def summaries_count(self) -> int:
        """Alias for API compatibility."""
        return self.summaries_generated

    @property
    def chunks_count(self) -> int:
        """Alias for API compatibility."""
        return self.chunks_processed

    @property
    def stages_completed(self) -> List[str]:
        """Return list of completed stages."""
        stages = []
        if self.chunks_processed > 0:
            stages.append("extract")
        if self.entities_extracted > 0 or self.events_extracted > 0:
            stages.append("cognify")
        if not self.errors:
            stages.append("load")
        return stages


class BaseExtractor(ABC):
    """Base class for extractor components."""

    @abstractmethod
    async def process(self, input_data: Any, context: PipelineContext) -> Any:
        """
        Extract data from input.

        Args:
            input_data: Raw input data
            context: Pipeline execution context

        Returns:
            Extracted data (async iterator or list)
        """


class BaseCognifier(ABC):
    """Base class for cognifier components."""

    @abstractmethod
    async def process(self, context: PipelineContext) -> PipelineContext:
        """
        Process pipeline context and add cognified data.

        Args:
            context: Pipeline context with input data

        Returns:
            Updated pipeline context
        """


class BaseLoader(ABC):
    """Base class for loader components."""

    @abstractmethod
    async def load(self, context: PipelineContext) -> None:
        """
        Load processed data to target storage.

        Args:
            context: Pipeline context with processed data
        """
