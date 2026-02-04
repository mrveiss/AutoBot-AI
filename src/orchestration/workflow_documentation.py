# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Documentation Generator

Issue #381: Extracted from enhanced_orchestrator.py god class refactoring.
Contains workflow documentation generation and knowledge extraction.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .types import AgentProfile, DocumentationType, WorkflowDocumentation

logger = logging.getLogger(__name__)


class WorkflowDocumenter:
    """
    Handles auto-documentation and knowledge extraction for workflows.

    Generates comprehensive documentation for workflow executions,
    extracts knowledge patterns, and stores insights.
    """

    def __init__(
        self,
        knowledge_base: Optional[Any] = None,
        llm_interface: Optional[Any] = None,
    ):
        """
        Initialize the workflow documenter.

        Args:
            knowledge_base: Knowledge base for storing documentation
            llm_interface: LLM interface for generating summaries
        """
        self.knowledge_base = knowledge_base
        self.llm_interface = llm_interface
        self._documentation: Dict[str, WorkflowDocumentation] = {}
        self._metrics = {
            "documentation_generated": 0,
            "knowledge_extracted": 0,
        }

    def create_workflow_doc(
        self,
        workflow_id: str,
        title: str,
        description: str,
        doc_type: DocumentationType = DocumentationType.WORKFLOW_SUMMARY,
    ) -> WorkflowDocumentation:
        """
        Create initial workflow documentation.

        Args:
            workflow_id: Unique workflow identifier
            title: Workflow title
            description: Workflow description
            doc_type: Type of documentation

        Returns:
            Created WorkflowDocumentation instance
        """
        now = datetime.now()
        doc = WorkflowDocumentation(
            workflow_id=workflow_id,
            title=title,
            description=description,
            created_at=now,
            updated_at=now,
            documentation_type=doc_type,
            content={
                "start_time": now.isoformat(),
                "steps": [],
            },
        )
        self._documentation[workflow_id] = doc
        return doc

    def get_doc(self, workflow_id: str) -> Optional[WorkflowDocumentation]:
        """Get documentation by workflow ID."""
        return self._documentation.get(workflow_id)

    def get_all_docs(self) -> Dict[str, WorkflowDocumentation]:
        """Get all documentation."""
        return self._documentation.copy()

    async def document_agent_registration(
        self,
        agent_profile: AgentProfile,
    ) -> None:
        """
        Auto-document agent registration.

        Args:
            agent_profile: The registered agent profile
        """
        doc_content = {
            "agent_id": agent_profile.agent_id,
            "agent_type": agent_profile.agent_type,
            "capabilities": [cap.value for cap in agent_profile.capabilities],
            "specializations": agent_profile.specializations,
            "max_concurrent_tasks": agent_profile.max_concurrent_tasks,
            "preferred_task_types": agent_profile.preferred_task_types,
            "registration_time": datetime.now().isoformat(),
        }

        # Store in knowledge base
        if self.knowledge_base and hasattr(self.knowledge_base, "add_document"):
            await self.knowledge_base.add_document(
                content=f"Agent Registration: {agent_profile.agent_id}",
                metadata=doc_content,
                doc_type="agent_profile",
            )

    def _update_workflow_doc_content(
        self,
        workflow_doc: WorkflowDocumentation,
        execution_result: Dict[str, Any],
    ) -> None:
        """
        Update workflow documentation with execution results.

        Issue #620.

        Args:
            workflow_doc: The workflow documentation to update
            execution_result: Results from workflow execution
        """
        workflow_doc.updated_at = datetime.now()
        workflow_doc.content.update(
            {
                "execution_result": execution_result,
                "agents_involved": execution_result.get("agents_involved", []),
                "success_rate": execution_result.get("success_rate", 0),
                "status": execution_result.get("status", "unknown"),
                "interactions": len(execution_result.get("interactions", [])),
                "end_time": datetime.now().isoformat(),
            }
        )

    async def _generate_llm_summary(
        self,
        workflow_doc: WorkflowDocumentation,
        execution_result: Dict[str, Any],
    ) -> None:
        """
        Generate and attach LLM summary to workflow documentation.

        Issue #620.

        Args:
            workflow_doc: The workflow documentation to update
            execution_result: Results from workflow execution
        """
        if not self.llm_interface:
            return

        try:
            summary_prompt = f"""
            Generate a concise summary of this workflow execution:

            Request: {workflow_doc.description}
            Status: {execution_result.get('status', 'unknown')}
            Agents Involved: {', '.join(execution_result.get('agents_involved', []))}
            Success Rate: {execution_result.get('success_rate', 0):.1%}

            Provide a brief summary of what was accomplished and any key insights.
            """

            summary_result = await self.llm_interface.chat_completion(
                model="default",
                messages=[{"role": "user", "content": summary_prompt}],
            )

            if summary_result:
                workflow_doc.content["generated_summary"] = summary_result.get(
                    "content", ""
                )

        except Exception as e:
            logger.warning("Failed to generate workflow summary: %s", e)

    async def generate_workflow_documentation(
        self,
        workflow_id: str,
        execution_result: Dict[str, Any],
    ) -> None:
        """
        Generate comprehensive workflow documentation.

        Args:
            workflow_id: Workflow identifier
            execution_result: Results from workflow execution
        """
        if workflow_id not in self._documentation:
            return

        workflow_doc = self._documentation[workflow_id]

        self._update_workflow_doc_content(workflow_doc, execution_result)
        await self._generate_llm_summary(workflow_doc, execution_result)

        self._metrics["documentation_generated"] += 1

    def _extract_success_pattern(
        self,
        user_request: str,
        execution_result: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Extract success pattern if workflow had high success rate.

        Args:
            user_request: Original user request
            execution_result: Results from execution

        Returns:
            Success pattern dict if success_rate > 0.8, else None. Issue #620.
        """
        if execution_result.get("success_rate", 0) > 0.8:
            return {
                "type": "success_pattern",
                "content": f"Successful workflow pattern for: {user_request[:100]}",
                "agents_used": execution_result.get("agents_involved", []),
                "success_rate": execution_result.get("success_rate", 0),
            }
        return None

    def _extract_agent_performance(
        self,
        execution_result: Dict[str, Any],
        agent_registry: Dict[str, AgentProfile],
    ) -> List[Dict[str, Any]]:
        """
        Extract performance insights for involved agents.

        Args:
            execution_result: Results from execution
            agent_registry: Registry of agent profiles

        Returns:
            List of agent performance insight dicts. Issue #620.
        """
        items = []
        for agent_id in execution_result.get("agents_involved", []):
            if agent_id in agent_registry:
                agent = agent_registry[agent_id]
                items.append(
                    {
                        "type": "agent_performance",
                        "agent_id": agent_id,
                        "success_rate": agent.success_rate,
                        "avg_completion_time": agent.average_completion_time,
                        "capabilities": [cap.value for cap in agent.capabilities],
                    }
                )
        return items

    async def _store_knowledge_items(
        self, knowledge_items: List[Dict[str, Any]]
    ) -> None:
        """
        Store extracted knowledge items in the knowledge base.

        Args:
            knowledge_items: List of knowledge items to store. Issue #620.
        """
        if knowledge_items and self.knowledge_base:
            if hasattr(self.knowledge_base, "add_document"):
                await asyncio.gather(
                    *[
                        self.knowledge_base.add_document(
                            content=f"Workflow Knowledge: {item['type']}",
                            metadata=item,
                            doc_type="workflow_knowledge",
                        )
                        for item in knowledge_items
                    ],
                    return_exceptions=True,
                )

    async def extract_workflow_knowledge(
        self,
        workflow_id: str,
        user_request: str,
        execution_result: Dict[str, Any],
        agent_registry: Dict[str, AgentProfile],
    ) -> None:
        """
        Extract and store knowledge from workflow execution.

        Args:
            workflow_id: Workflow identifier
            user_request: Original user request
            execution_result: Results from execution
            agent_registry: Registry of agent profiles.
            Issue #620: Refactored to use helper methods.
        """
        try:
            knowledge_items: List[Dict[str, Any]] = []

            success_pattern = self._extract_success_pattern(
                user_request, execution_result
            )
            if success_pattern:
                knowledge_items.append(success_pattern)

            knowledge_items.extend(
                self._extract_agent_performance(execution_result, agent_registry)
            )

            await self._store_knowledge_items(knowledge_items)
            self._metrics["knowledge_extracted"] += len(knowledge_items)

        except Exception as e:
            logger.warning("Failed to extract workflow knowledge: %s", e)

    async def document_workflow_failure(
        self,
        workflow_id: str,
        error_message: str,
    ) -> None:
        """
        Document workflow failure for analysis.

        Args:
            workflow_id: Workflow identifier
            error_message: Error message describing the failure
        """
        if workflow_id not in self._documentation:
            return

        workflow_doc = self._documentation[workflow_id]
        workflow_doc.documentation_type = DocumentationType.ERROR_ANALYSIS
        workflow_doc.content.update(
            {
                "error_message": error_message,
                "failure_time": datetime.now().isoformat(),
                "failure_analysis": (
                    "Workflow execution failed - requires investigation"
                ),
            }
        )

    def search_documentation(
        self,
        query: str,
        doc_type: Optional[DocumentationType] = None,
        limit: int = 10,
    ) -> List[WorkflowDocumentation]:
        """
        Search workflow documentation.

        Args:
            query: Search query string
            doc_type: Optional filter by documentation type
            limit: Maximum results to return

        Returns:
            List of matching WorkflowDocumentation
        """
        results = []
        query_lower = query.lower()

        for doc in self._documentation.values():
            # Filter by type if specified
            if doc_type and doc.documentation_type != doc_type:
                continue

            # Simple text matching
            if (
                query_lower in doc.title.lower()
                or query_lower in doc.description.lower()
                or any(query_lower in tag.lower() for tag in doc.tags)
            ):
                results.append(doc)

            if len(results) >= limit:
                break

        return results

    def get_metrics(self) -> Dict[str, int]:
        """Get documentation metrics."""
        return self._metrics.copy()
