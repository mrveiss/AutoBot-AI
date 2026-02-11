# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pipeline Runner - Orchestrator for ECL pipeline execution.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from .base import PipelineContext, PipelineResult
from .registry import TaskRegistry

logger = logging.getLogger(__name__)


class PipelineRunner:
    """
    Orchestrates Extract → Cognify → Load pipeline execution.

    Loads task configurations, instantiates tasks from registry,
    executes stages in sequence with batching, and tracks metrics.
    """

    def __init__(self, pipeline_config: Dict[str, Any]):
        """
        Initialize pipeline runner with configuration.

        Args:
            pipeline_config: Pipeline configuration dict with stages
        """
        self.config = pipeline_config
        self.batch_size = pipeline_config.get("batch_size", 10)

    async def run(self, input_data: Any, context: PipelineContext) -> PipelineResult:
        """
        Execute complete ECL pipeline.

        Args:
            input_data: Raw input data (document text, file path, etc.)
            context: Pipeline execution context

        Returns:
            Pipeline execution result with metrics
        """
        start_time = datetime.utcnow()
        result = PipelineResult(document_id=context.document_id, started_at=start_time)

        try:
            extracted_data = await self._run_extract_stage(input_data, context)
            result.chunks_processed = len(extracted_data)

            cognified_data = await self._run_cognify_stage(extracted_data, context)
            self._update_result_counts(result, cognified_data)

            await self._run_load_stage(cognified_data, context)

        except Exception as e:
            logger.error("Pipeline error for doc %s: %s", context.document_id, e)
            result.errors.append(str(e))

        end_time = datetime.utcnow()
        result.completed_at = end_time
        result.duration_seconds = (end_time - start_time).total_seconds()

        return result

    async def _run_extract_stage(
        self, input_data: Any, context: PipelineContext
    ) -> List[Any]:
        """
        Run Extract stage tasks. Helper for run (Issue #665).

        Args:
            input_data: Raw input data
            context: Pipeline context

        Returns:
            List of extracted data objects
        """
        extract_config = self.config.get("extract", [])
        extracted_data = []

        for task_config in extract_config:
            task_name = task_config["task"]
            task_class = TaskRegistry.get_task("extract", task_name)
            task_instance = task_class(**task_config.get("params", {}))

            async for item in task_instance.process(input_data, context):
                extracted_data.append(item)

        logger.info("Extract stage: %d items", len(extracted_data))
        return extracted_data

    async def _run_cognify_stage(
        self, extracted_data: List[Any], context: PipelineContext
    ) -> Dict[str, List[Any]]:
        """
        Run Cognify stage tasks. Helper for run (Issue #665).

        Args:
            extracted_data: Extracted data from previous stage
            context: Pipeline context

        Returns:
            Dict of cognified data by category (entities, relationships, etc.)
        """
        cognify_config = self.config.get("cognify", [])
        cognified_data: Dict[str, List[Any]] = {
            "entities": [],
            "relationships": [],
            "events": [],
            "summaries": [],
        }

        for task_config in cognify_config:
            task_name = task_config["task"]
            output_type = task_config.get("output_type", "entities")
            task_class = TaskRegistry.get_task("cognify", task_name)
            task_instance = task_class(**task_config.get("params", {}))

            results = await task_instance.process(extracted_data, context)
            cognified_data[output_type].extend(results)

        self._log_cognify_stats(cognified_data)
        return cognified_data

    def _log_cognify_stats(self, cognified_data: Dict[str, List[Any]]) -> None:
        """
        Log cognify stage statistics. Helper for _run_cognify_stage (Issue #665).

        Args:
            cognified_data: Cognified data dict
        """
        logger.info(
            "Cognify stage: %d entities, %d relationships, %d events, %d summaries",
            len(cognified_data["entities"]),
            len(cognified_data["relationships"]),
            len(cognified_data["events"]),
            len(cognified_data["summaries"]),
        )

    async def _run_load_stage(
        self, cognified_data: Dict[str, List[Any]], context: PipelineContext
    ) -> None:
        """
        Run Load stage tasks. Helper for run (Issue #665).

        Args:
            cognified_data: Cognified data to persist
            context: Pipeline context
        """
        load_config = self.config.get("load", [])

        for task_config in load_config:
            task_name = task_config["task"]
            data_type = task_config.get("data_type", "entities")
            task_class = TaskRegistry.get_task("load", task_name)
            task_instance = task_class(**task_config.get("params", {}))

            data_to_load = cognified_data.get(data_type, [])
            if data_to_load:
                await task_instance.load(data_to_load, context)

        logger.info("Load stage: persisted all data")

    def _update_result_counts(
        self, result: PipelineResult, cognified_data: Dict[str, List[Any]]
    ) -> None:
        """
        Update result with cognified data counts. Helper for run (Issue #665).

        Args:
            result: Pipeline result to update
            cognified_data: Cognified data dict
        """
        result.entities_extracted = len(cognified_data.get("entities", []))
        result.relationships_extracted = len(cognified_data.get("relationships", []))
        result.events_extracted = len(cognified_data.get("events", []))
        result.summaries_generated = len(cognified_data.get("summaries", []))
