#!/usr/bin/env python3
"""
Example usage of the retry mechanism in AutoBot
Demonstrates integration with various AutoBot components and common patterns
"""

import asyncio
import logging
import time
from typing import Any, Dict, List

# Import retry components
from retry_mechanism import (
    RetryConfig,
    RetryExhaustedError,
    RetryMechanism,
    RetryStrategy,
    retry_async,
    retry_file_operation,
    retry_sync,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AutoBotServiceWithRetry:
    """Example AutoBot service with integrated retry mechanisms"""

    def __init__(self):
        # Configure different retry strategies for different operations
        self.network_retry = RetryMechanism(
            RetryConfig(
                max_attempts=5,
                base_delay=1.0,
                max_delay=30.0,
                strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
                retryable_exceptions=(ConnectionError, TimeoutError, OSError),
            )
        )

        self.database_retry = RetryMechanism(
            RetryConfig(
                max_attempts=3,
                base_delay=0.5,
                max_delay=5.0,
                strategy=RetryStrategy.JITTERED_BACKOFF,
                retryable_exceptions=(
                    Exception,
                ),  # More specific in real implementation
            )
        )

        self.file_retry = RetryMechanism(
            RetryConfig(
                max_attempts=3,
                base_delay=0.1,
                max_delay=2.0,
                strategy=RetryStrategy.LINEAR_BACKOFF,
            )
        )

    @retry_async(
        max_attempts=3, base_delay=1.0, strategy=RetryStrategy.EXPONENTIAL_BACKOFF
    )
    async def fetch_llm_response(self, prompt: str) -> Dict[str, Any]:
        """
        Example LLM API call with retry mechanism
        Simulates network failures and recovers automatically
        """
        logger.info(f"Fetching LLM response for prompt: {prompt[:50]}...")

        # Simulate network call that might fail
        import random

        if random.random() < 0.3:  # 30% chance of failure
            raise ConnectionError("API temporarily unavailable")

        # Simulate processing time
        await asyncio.sleep(0.1)

        return {
            "response": f"LLM response to: {prompt}",
            "model": "example-llm",
            "timestamp": time.time(),
        }

    async def search_knowledge_base(
        self, query: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Knowledge base search with database retry
        Uses specialized database retry configuration
        """

        async def perform_search():
            logger.info(f"Searching knowledge base for: {query}")

            # Simulate database operation that might fail
            import random

            if random.random() < 0.2:  # 20% chance of failure
                raise ConnectionError("Vector database temporarily unavailable")

            # Simulate search results
            return [
                {"content": f"Result {i} for query: {query}", "score": 0.9 - i * 0.1}
                for i in range(min(limit, 3))
            ]

        try:
            return await self.database_retry.execute_async(
                perform_search, operation_name="knowledge_base_search"
            )
        except RetryExhaustedError as e:
            logger.error(f"Knowledge base search failed after retries: {e}")
            return []

    async def process_file_upload(self, file_path: str) -> Dict[str, Any]:
        """
        File processing with retry for transient file system issues
        """

        async def read_and_process_file():
            logger.info(f"Processing file: {file_path}")

            # Simulate file operation that might fail
            import random

            if random.random() < 0.15:  # 15% chance of failure
                raise OSError("Temporary file system error")

            # Simulate file processing
            await asyncio.sleep(0.05)

            return {
                "file_path": file_path,
                "size": 1024,
                "processed_at": time.time(),
                "status": "success",
            }

        return await retry_file_operation(read_and_process_file)

    async def execute_command_with_retry(self, command: str) -> Dict[str, Any]:
        """
        Command execution with retry for system operations
        Example of custom retry configuration
        """
        command_retry = RetryMechanism(
            RetryConfig(
                max_attempts=2,  # Don't retry commands too many times
                base_delay=0.5,
                strategy=RetryStrategy.FIXED_DELAY,
                retryable_exceptions=(OSError, TimeoutError),
                non_retryable_exceptions=(PermissionError, FileNotFoundError),
            )
        )

        async def execute_command():
            logger.info(f"Executing command: {command}")

            # Simulate command execution
            import random

            failure_type = random.random()

            if failure_type < 0.1:  # 10% chance of retryable failure
                raise OSError("Temporary system error")
            elif failure_type < 0.15:  # 5% chance of non-retryable failure
                raise PermissionError("Permission denied")

            # Simulate successful execution
            await asyncio.sleep(0.1)
            return {
                "command": command,
                "exit_code": 0,
                "output": f"Command '{command}' executed successfully",
                "duration": 0.1,
            }

        try:
            return await command_retry.execute_async(
                execute_command, operation_name="command_execution"
            )
        except PermissionError:
            logger.error(f"Permission denied for command: {command}")
            return {
                "command": command,
                "exit_code": 1,
                "error": "Permission denied",
                "retryable": False,
            }
        except RetryExhaustedError as e:
            logger.error(f"Command execution failed after retries: {e}")
            return {
                "command": command,
                "exit_code": 1,
                "error": str(e.last_exception),
                "retryable": True,
                "attempts": e.attempts,
            }

    def get_retry_statistics(self) -> Dict[str, Any]:
        """Get comprehensive retry statistics from all retry mechanisms"""
        return {
            "network_retry": self.network_retry.get_stats(),
            "database_retry": self.database_retry.get_stats(),
            "file_retry": self.file_retry.get_stats(),
        }

    def reset_all_statistics(self):
        """Reset all retry statistics"""
        self.network_retry.reset_stats()
        self.database_retry.reset_stats()
        self.file_retry.reset_stats()


# Example workflow orchestrator with retry patterns
class WorkflowOrchestratorWithRetry:
    """Example workflow orchestrator demonstrating retry patterns"""

    def __init__(self):
        self.service = AutoBotServiceWithRetry()

    async def _run_research_steps(self, query, workflow_results):
        """Execute the three research workflow steps sequentially.

        Helper for execute_research_workflow (#825).
        """
        logger.info("Step 1: Searching knowledge base...")
        kb_results = await self.service.search_knowledge_base(query)
        workflow_results["steps"].append(
            {
                "step": "knowledge_base_search",
                "status": "completed",
                "results_count": len(kb_results),
                "timestamp": time.time(),
            }
        )

        if kb_results:
            context = "\\n".join([result["content"] for result in kb_results[:3]])
            prompt = (
                f"Based on this context:\\n{context}\\n\\n"
                f"Answer this query: {query}"
            )
        else:
            prompt = f"Answer this query: {query}"

        logger.info("Step 2: Generating LLM response...")
        llm_response = await self.service.fetch_llm_response(prompt)
        workflow_results["steps"].append(
            {
                "step": "llm_generation",
                "status": "completed",
                "response_length": len(llm_response.get("response", "")),
                "timestamp": time.time(),
            }
        )

        logger.info("Step 3: Processing related files...")
        file_results = await self.service.process_file_upload(
            f"research_{query[:20]}.txt"
        )
        workflow_results["steps"].append(
            {
                "step": "file_processing",
                "status": "completed",
                "file_size": file_results.get("size", 0),
                "timestamp": time.time(),
            }
        )

        return kb_results, llm_response, file_results

    async def execute_research_workflow(self, query: str) -> Dict[str, Any]:
        """Execute a research workflow with retry-enabled steps."""
        logger.info(f"Starting research workflow for query: {query}")

        workflow_results = {
            "query": query,
            "steps": [],
            "status": "in_progress",
            "start_time": time.time(),
        }

        try:
            kb_results, llm_response, file_results = await self._run_research_steps(
                query, workflow_results
            )
            workflow_results.update(
                {
                    "status": "completed",
                    "kb_results": kb_results,
                    "llm_response": llm_response,
                    "file_results": file_results,
                    "end_time": time.time(),
                    "duration": (time.time() - workflow_results["start_time"]),
                }
            )

        except Exception as e:
            logger.error(f"Workflow failed: {e}")
            workflow_results.update(
                {
                    "status": "failed",
                    "error": str(e),
                    "end_time": time.time(),
                    "duration": (time.time() - workflow_results["start_time"]),
                }
            )

        return workflow_results

    async def batch_process_with_retry(self, items: List[str]) -> Dict[str, Any]:
        """
        Process multiple items with retry, demonstrating batch processing patterns
        """
        logger.info(f"Starting batch processing of {len(items)} items")

        results = {
            "total_items": len(items),
            "successful": 0,
            "failed": 0,
            "results": [],
            "start_time": time.time(),
        }

        # Process items with controlled concurrency and retries
        semaphore = asyncio.Semaphore(3)  # Limit concurrent operations

        async def process_item(item: str) -> Dict[str, Any]:
            async with semaphore:
                try:
                    result = await self.service.fetch_llm_response(
                        f"Process item: {item}"
                    )
                    return {"item": item, "status": "success", "result": result}
                except RetryExhaustedError as e:
                    logger.warning(f"Item {item} failed after retries: {e}")
                    return {"item": item, "status": "failed", "error": str(e)}

        # Execute all items concurrently
        tasks = [process_item(item) for item in items]
        item_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results
        for item_result in item_results:
            if isinstance(item_result, Exception):
                results["failed"] += 1
                results["results"].append(
                    {"item": "unknown", "status": "error", "error": str(item_result)}
                )
            elif item_result["status"] == "success":
                results["successful"] += 1
                results["results"].append(item_result)
            else:
                results["failed"] += 1
                results["results"].append(item_result)

        results.update(
            {
                "end_time": time.time(),
                "duration": time.time() - results["start_time"],
                "success_rate": (results["successful"] / results["total_items"]) * 100,
            }
        )

        return results


def _log_retry_statistics(stats):
    """Log retry statistics for all components.

    Helper for demonstrate_retry_patterns (#825).
    """
    for component, component_stats in stats.items():
        label = component.replace("_", " ").title()
        logger.info(f"\\n📊 {label} Statistics:")
        logger.info(f"   Total Attempts: {component_stats['total_attempts']}")
        logger.info(
            f"   Successful Retries: " f"{component_stats['successful_retries']}"
        )
        logger.info(f"   Failed Operations: " f"{component_stats['failed_operations']}")
        logger.info(f"   Success Rate: {component_stats['success_rate']:.1f}%")

        if component_stats["operations_by_type"]:
            logger.info("   Operations by Type:")
            for op_type, op_stats in component_stats["operations_by_type"].items():
                logger.info(
                    f"     {op_type}: "
                    f"{op_stats['succeeded']}/{op_stats['total']} "
                    f"succeeded"
                )


async def demonstrate_retry_patterns():
    """Demonstrate various retry patterns and usage examples."""
    logger.info("🔄 AutoBot Retry Mechanism Demonstration")
    logger.info("=" * 60)

    logger.info("\\n1. Basic Service Operations with Retry")
    service = AutoBotServiceWithRetry()

    try:
        llm_result = await service.fetch_llm_response(
            "What is artificial intelligence?"
        )
        logger.info(f"✅ LLM Response: {llm_result['response'][:100]}...")

        kb_results = await service.search_knowledge_base("machine learning algorithms")
        logger.info(f"✅ Knowledge Base: Found {len(kb_results)} results")

        file_result = await service.process_file_upload("example_document.pdf")
        logger.info(f"✅ File Processing: {file_result['status']}")

    except Exception as e:
        logger.error(f"❌ Service operation failed: {e}")

    logger.info("\\n2. Workflow Orchestration with Retry")
    orchestrator = WorkflowOrchestratorWithRetry()

    workflow_result = await orchestrator.execute_research_workflow(
        "quantum computing applications"
    )
    logger.info(f"✅ Workflow Status: {workflow_result['status']}")
    logger.info(f"📊 Steps Completed: {len(workflow_result['steps'])}")
    logger.info(f"⏱️  Duration: {workflow_result['duration']:.2f} seconds")

    logger.info("\\n3. Batch Processing with Retry")
    test_items = [f"analyze data trend {i}" for i in range(1, 6)]

    batch_result = await orchestrator.batch_process_with_retry(test_items)
    logger.info(
        f"✅ Batch Processing: "
        f"{batch_result['successful']}/{batch_result['total_items']} "
        f"succeeded"
    )
    logger.info(f"📈 Success Rate: {batch_result['success_rate']:.1f}%")
    logger.info(f"⏱️  Total Duration: {batch_result['duration']:.2f} seconds")

    logger.info("\\n4. Retry Statistics")
    _log_retry_statistics(service.get_retry_statistics())


# Example decorator usage patterns
@retry_async(max_attempts=3, base_delay=1.0, strategy=RetryStrategy.EXPONENTIAL_BACKOFF)
async def external_api_call(endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Example external API call with retry decorator"""
    logger.info(f"Calling external API: {endpoint}")

    # Simulate API call that might fail
    import random

    if random.random() < 0.4:  # 40% chance of failure
        raise ConnectionError(f"Failed to connect to {endpoint}")

    return {"status": "success", "data": data, "endpoint": endpoint}


@retry_sync(max_attempts=2, base_delay=0.5, strategy=RetryStrategy.FIXED_DELAY)
def config_file_operation(config_path: str) -> Dict[str, Any]:
    """Example config file operation with sync retry"""
    logger.info(f"Reading configuration from: {config_path}")

    # Simulate file operation that might fail
    import random

    if random.random() < 0.25:  # 25% chance of failure
        raise OSError(f"Temporary error accessing {config_path}")

    return {
        "config_path": config_path,
        "settings": {"debug": True, "max_workers": 4},
        "loaded_at": time.time(),
    }


async def demonstrate_decorators():
    """Demonstrate retry decorator patterns"""

    logger.info("\\n🎯 Retry Decorator Demonstrations")
    logger.info("=" * 60)

    # Test async decorator
    try:
        api_result = await external_api_call("/api/v1/process", {"input": "test data"})
        logger.info(f"✅ External API Call: {api_result['status']}")
    except RetryExhaustedError as e:
        logger.error(f"❌ External API failed after {e.attempts} attempts")

    # Test sync decorator
    try:
        config_result = config_file_operation("/etc/autobot/config.json")
        logger.info(
            f"✅ Config Loading: {len(config_result['settings'])} settings loaded"
        )
    except RetryExhaustedError as e:
        logger.error(f"❌ Config loading failed after {e.attempts} attempts")


if __name__ == "__main__":

    async def main():
        """Main demonstration function"""
        await demonstrate_retry_patterns()
        await demonstrate_decorators()

        logger.info("\\n🎉 Retry Mechanism Demonstration Complete!")
        logger.info("\\n💡 Key Takeaways:")
        logger.info(
            "   - Use specialized retry functions for different operation types"
        )
        logger.info(
            "   - Configure retry strategies based on operation characteristics"
        )
        logger.info("   - Monitor retry statistics to optimize configurations")
        logger.info(
            "   - Use decorators for simple cases, RetryMechanism for complex ones"
        )
        logger.error("   - Handle RetryExhaustedError gracefully in production code")

    # Run the demonstration
    asyncio.run(main())
