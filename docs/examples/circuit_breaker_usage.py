#!/usr/bin/env python3
"""
Example usage of the circuit breaker pattern in AutoBot
Demonstrates protection against cascading failures and service degradation

SECURITY NOTE: This example demonstrates secure database query practices:
- Uses parameterized queries to prevent SQL injection attacks
- Avoids string interpolation/concatenation for SQL queries
- Safely logs query structure without exposing sensitive parameter values

For production use, always:
1. Use parameterized queries with proper database drivers (e.g., asyncpg, SQLAlchemy)
2. Validate and sanitize all user inputs
3. Implement proper access controls and authentication
4. Use connection pooling and prepared statements
5. Never log sensitive parameter values in production
"""

import asyncio
import logging
import random
import time
from typing import Any, Dict, List

# Import circuit breaker components
from circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    circuit_breaker_async,
    circuit_breaker_manager,
    circuit_breaker_sync,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AutoBotServiceWithCircuitBreaker:
    """Example AutoBot service with integrated circuit breaker protection"""

    def __init__(self):
        # Configure circuit breakers for different services
        self.llm_config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=30.0,
            success_threshold=2,
            timeout=120.0,  # LLM calls can be slow
            slow_call_threshold=20.0,
            monitored_exceptions=(ConnectionError, TimeoutError, OSError),
        )

        self.database_config = CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=10.0,
            success_threshold=3,
            timeout=5.0,
            slow_call_threshold=1.0,  # Database should be fast
            slow_call_rate_threshold=0.3,  # 30% slow calls trigger circuit
            monitored_exceptions=(ConnectionError, TimeoutError, OSError),
        )

        self.external_api_config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=60.0,
            success_threshold=2,
            timeout=15.0,
            monitored_exceptions=(ConnectionError, TimeoutError),
        )

    @circuit_breaker_async(
        "llm_service", failure_threshold=3, recovery_timeout=30.0, timeout=120.0
    )
    async def call_llm_with_protection(self, prompt: str) -> Dict[str, Any]:
        """
        LLM call with circuit breaker protection
        Automatically handles service failures and prevents cascading issues
        """
        logger.info(f"Calling LLM with prompt: {prompt[:50]}...")

        # Simulate LLM API call that might fail
        failure_rate = 0.3  # 30% chance of failure
        slow_call_rate = 0.2  # 20% chance of slow response

        if random.random() < failure_rate:
            raise ConnectionError("LLM API temporarily unavailable")

        # Simulate slow response
        if random.random() < slow_call_rate:
            await asyncio.sleep(2.0)  # Slow response
        else:
            await asyncio.sleep(0.1)  # Normal response time

        return {
            "response": f"LLM response to: {prompt}",
            "model": "protected-llm",
            "processing_time": time.time(),
            "protected": True,
        }

    @circuit_breaker_async(
        "database_service", failure_threshold=5, recovery_timeout=10.0, timeout=5.0
    )
    async def query_database_with_protection(
        self, query: str, *params
    ) -> List[Dict[str, Any]]:
        """
        Database query with circuit breaker protection
        Fast timeout and recovery for database operations

        Args:
            query: SQL query with parameter placeholders (? for positional parameters)
            params: Query parameters to be safely bound to the query
        """
        # Log query safely without exposing parameter values in production
        if params:
            logger.info(f"Querying database: {query} with {len(params)} parameter(s)")
        else:
            logger.info(f"Querying database: {query}")

        # Simulate database operations with occasional failures
        failure_rate = 0.2  # 20% chance of failure
        slow_query_rate = 0.15  # 15% chance of slow query

        if random.random() < failure_rate:
            raise ConnectionError("Database connection lost")

        # Simulate slow query
        if random.random() < slow_query_rate:
            await asyncio.sleep(1.5)  # Slow query
        else:
            await asyncio.sleep(0.05)  # Fast query

        # Simulate parameterized query execution
        # In a real implementation, this would use proper database parameterized queries
        safe_query_description = query.replace("?", "<param>") if params else query

        return [
            {"id": i, "data": f"Result {i} for query: {safe_query_description}"}
            for i in range(3)
        ]

    @circuit_breaker_async(
        "external_api", failure_threshold=2, recovery_timeout=60.0, timeout=15.0
    )
    async def call_external_api_with_protection(
        self, endpoint: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        External API call with circuit breaker protection
        Lower threshold for external services that may be unreliable
        """
        logger.info(f"Calling external API: {endpoint}")

        # Simulate external API with higher failure rate
        failure_rate = 0.4  # 40% chance of failure

        if random.random() < failure_rate:
            raise ConnectionError(f"External API {endpoint} unavailable")

        await asyncio.sleep(0.2)  # API response time

        return {
            "status": "success",
            "endpoint": endpoint,
            "data": data,
            "timestamp": time.time(),
        }

    async def _try_llm_with_fallback(self, operation_id, result):
        """Attempt LLM call with circuit breaker fallback.

        Helper for perform_complex_operation_with_fallbacks (#825).
        """
        try:
            llm_result = await self.call_llm_with_protection(
                f"Process operation {operation_id}"
            )
            result["results"]["llm"] = llm_result
            logger.info("✅ LLM call successful")

        except CircuitBreakerOpenError as e:
            logger.warning(f"LLM circuit breaker is open: {e}")
            result["fallbacks_used"].append("llm_fallback")
            result["results"]["llm"] = {
                "response": f"Fallback response for operation {operation_id}",
                "source": "fallback",
                "circuit_breaker_open": True,
            }

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            result["errors"].append(f"LLM error: {str(e)}")

    async def _try_database_with_fallback(self, operation_id, result):
        """Attempt database query with circuit breaker fallback.

        Helper for perform_complex_operation_with_fallbacks (#825).
        """
        try:
            db_result = await self.query_database_with_protection(
                "SELECT * FROM operations WHERE id=?", operation_id
            )
            result["results"]["database"] = db_result
            logger.info("✅ Database query successful")

        except CircuitBreakerOpenError as e:
            logger.warning(f"Database circuit breaker is open: {e}")
            result["fallbacks_used"].append("database_cache")
            result["results"]["database"] = [
                {"id": operation_id, "data": "cached_result", "source": "cache"}
            ]

        except Exception as e:
            logger.error(f"Database query failed: {e}")
            result["errors"].append(f"Database error: {str(e)}")

    async def _try_external_api_with_fallback(self, operation_id, result):
        """Attempt external API call with circuit breaker fallback.

        Helper for perform_complex_operation_with_fallbacks (#825).
        """
        try:
            api_result = await self.call_external_api_with_protection(
                "/api/process", {"operation_id": operation_id}
            )
            result["results"]["external_api"] = api_result
            logger.info("✅ External API call successful")

        except CircuitBreakerOpenError as e:
            logger.warning(f"External API circuit breaker is open: {e}")
            result["fallbacks_used"].append("skip_external_api")
            result["results"]["external_api"] = {
                "status": "skipped",
                "reason": "circuit_breaker_open",
            }

        except Exception as e:
            logger.error(f"External API call failed: {e}")
            result["errors"].append(f"External API error: {str(e)}")

    async def perform_complex_operation_with_fallbacks(
        self, operation_id: str
    ) -> Dict[str, Any]:
        """Complex operation using multiple protected services with fallbacks."""
        logger.info(f"Starting complex operation: {operation_id}")

        result = {
            "operation_id": operation_id,
            "status": "in_progress",
            "results": {},
            "fallbacks_used": [],
            "errors": [],
        }

        await self._try_llm_with_fallback(operation_id, result)
        await self._try_database_with_fallback(operation_id, result)
        await self._try_external_api_with_fallback(operation_id, result)

        # Determine overall status
        successful_ops = len([r for r in result["results"].values() if r])
        total_operations = 3

        if successful_ops == total_operations:
            result["status"] = "completed"
        elif successful_ops > 0:
            result["status"] = "partially_completed"
        else:
            result["status"] = "failed"

        result["success_rate"] = successful_ops / total_operations

        return result

    def get_circuit_breaker_dashboard(self) -> Dict[str, Any]:
        """Get dashboard view of all circuit breaker states"""
        return {
            "timestamp": time.time(),
            "circuit_breakers": circuit_breaker_manager.get_all_states(),
            "summary": self._generate_circuit_breaker_summary(),
        }

    def _generate_circuit_breaker_summary(self) -> Dict[str, Any]:
        """Generate summary of circuit breaker health"""
        states = circuit_breaker_manager.get_all_states()

        summary = {
            "total_services": len(states),
            "healthy_services": 0,
            "degraded_services": 0,
            "failed_services": 0,
            "blocked_calls_total": 0,
            "success_rate_avg": 0.0,
        }

        if not states:
            return summary

        success_rates = []

        for service_name, state in states.items():
            summary["blocked_calls_total"] += state["stats"]["blocked_calls"]

            if state["state"] == "closed":
                summary["healthy_services"] += 1
            elif state["state"] == "half_open":
                summary["degraded_services"] += 1
            elif state["state"] == "open":
                summary["failed_services"] += 1

            # Calculate success rate
            total_calls = state["stats"]["total_calls"]
            if total_calls > 0:
                success_rate = (state["stats"]["successful_calls"] / total_calls) * 100
                success_rates.append(success_rate)

        if success_rates:
            summary["success_rate_avg"] = sum(success_rates) / len(success_rates)

        return summary


class CircuitBreakerOrchestrator:
    """Orchestrate operations with circuit breaker awareness"""

    def __init__(self):
        self.service = AutoBotServiceWithCircuitBreaker()

    async def _process_single_operation(self, operation_id, batch_result, semaphore):
        """Process a single operation with concurrency control.

        Helper for execute_batch_operations_with_protection (#825).
        """
        async with semaphore:
            try:
                result = await self.service.perform_complex_operation_with_fallbacks(
                    operation_id
                )

                if result["status"] in ("completed", "partially_completed"):
                    batch_result["completed"] += 1
                else:
                    batch_result["failed"] += 1

                return result

            except CircuitBreakerOpenError as e:
                logger.warning(
                    f"Operation {operation_id} skipped - " f"circuit breaker open: {e}"
                )
                batch_result["skipped"] += 1
                return {
                    "operation_id": operation_id,
                    "status": "skipped",
                    "reason": "circuit_breaker_open",
                    "circuit_breaker_service": e.service_name,
                }

            except Exception as e:
                logger.error(f"Operation {operation_id} failed: {e}")
                batch_result["failed"] += 1
                return {
                    "operation_id": operation_id,
                    "status": "error",
                    "error": str(e),
                }

    async def execute_batch_operations_with_protection(
        self, operation_ids: List[str]
    ) -> Dict[str, Any]:
        """Execute batch operations with circuit breaker protection."""
        logger.info(f"Starting batch processing of {len(operation_ids)} operations")

        batch_result = {
            "total_operations": len(operation_ids),
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "results": [],
            "start_time": time.time(),
        }

        semaphore = asyncio.Semaphore(3)
        tasks = [
            self._process_single_operation(op_id, batch_result, semaphore)
            for op_id in operation_ids
        ]
        operation_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in operation_results:
            if isinstance(result, Exception):
                batch_result["failed"] += 1
                batch_result["results"].append(
                    {"status": "exception", "error": str(result)}
                )
            else:
                batch_result["results"].append(result)

        batch_result.update(
            {
                "end_time": time.time(),
                "duration": time.time() - batch_result["start_time"],
                "success_rate": (
                    batch_result["completed"] / batch_result["total_operations"]
                )
                * 100,
            }
        )

        return batch_result

    async def monitor_circuit_breaker_health(self, duration: float = 60.0):
        """
        Monitor circuit breaker health over time
        Useful for observability and alerting
        """
        logger.info(f"Starting circuit breaker health monitoring for {duration}s")

        start_time = time.time()
        health_history = []

        while time.time() - start_time < duration:
            dashboard = self.service.get_circuit_breaker_dashboard()
            health_snapshot = {
                "timestamp": dashboard["timestamp"],
                "summary": dashboard["summary"],
                "service_states": {
                    name: state["state"]
                    for name, state in dashboard["circuit_breakers"].items()
                },
            }
            health_history.append(health_snapshot)

            # Log health status
            summary = dashboard["summary"]
            logger.info(
                f"Circuit Breaker Health - "
                f"Healthy: {summary['healthy_services']}, "
                f"Degraded: {summary['degraded_services']}, "
                f"Failed: {summary['failed_services']}, "
                f"Avg Success Rate: {summary['success_rate_avg']:.1f}%"
            )

            # Check for alerts
            if summary["failed_services"] > 0:
                logger.warning(
                    f"⚠️ {summary['failed_services']} services have failed circuit breakers"
                )

            if summary["success_rate_avg"] < 80:
                logger.warning(
                    f"⚠️ Low average success rate: {summary['success_rate_avg']:.1f}%"
                )

            await asyncio.sleep(5.0)  # Check every 5 seconds

        return {
            "monitoring_duration": duration,
            "health_history": health_history,
            "final_status": dashboard,
        }


async def _demo_basic_service_operations(service):
    """Demonstrate basic service operations with circuit breaker protection.

    Helper for demonstrate_circuit_breaker_patterns (#825).
    """
    logger.info("\\n1. Basic Service Operations with Circuit Breaker Protection")

    for i in range(5):
        try:
            await service.call_llm_with_protection(f"Test prompt {i+1}")
            logger.info(f"✅ LLM Call {i+1}: Success")
        except CircuitBreakerOpenError as e:
            logger.info(
                f"🚫 LLM Call {i+1}: Circuit breaker open - " f"{e.service_name}"
            )
        except Exception as e:
            logger.error(f"❌ LLM Call {i+1}: Failed - {type(e).__name__}")

    dashboard = service.get_circuit_breaker_dashboard()
    logger.info("\\n📊 Circuit Breaker States:")
    for name, state in dashboard["circuit_breakers"].items():
        logger.info(
            f"   {name}: {state['state']} " f"(failures: {state['failure_count']})"
        )


async def _demo_batch_processing(orchestrator):
    """Demonstrate batch processing with circuit breaker protection.

    Helper for demonstrate_circuit_breaker_patterns (#825).
    """
    logger.info("\\n3. Batch Processing with Circuit Breaker Protection")

    operation_ids = [f"batch_op_{i:03d}" for i in range(8)]
    batch_result = await orchestrator.execute_batch_operations_with_protection(
        operation_ids
    )

    logger.info("✅ Batch Processing Results:")
    logger.info(f"   Total: {batch_result['total_operations']}")
    logger.info(f"   Completed: {batch_result['completed']}")
    logger.info(f"   Failed: {batch_result['failed']}")
    logger.info(f"   Skipped: {batch_result['skipped']}")
    logger.info(f"   Success Rate: {batch_result['success_rate']:.1f}%")
    logger.info(f"   Duration: {batch_result['duration']:.2f}s")


async def _demo_circuit_recovery():
    """Demonstrate circuit breaker recovery after failures.

    Helper for demonstrate_circuit_breaker_patterns (#825).
    """
    logger.info("\\n4. Circuit Breaker Recovery Demonstration")

    failing_service = "demo_recovery_service"

    @circuit_breaker_async(failing_service, failure_threshold=2, recovery_timeout=3.0)
    async def demo_failing_service():
        if demo_failing_service.failure_count < 4:
            demo_failing_service.failure_count += 1
            raise ConnectionError(
                f"Simulated failure {demo_failing_service.failure_count}"
            )
        return "Service recovered!"

    demo_failing_service.failure_count = 0

    for i in range(3):
        try:
            await demo_failing_service()
        except (ConnectionError, CircuitBreakerOpenError) as e:
            logger.info(f"   Attempt {i+1}: {type(e).__name__}")

    logger.info("   Waiting for recovery timeout...")
    await asyncio.sleep(3.5)

    try:
        result = await demo_failing_service()
        logger.info(f"✅ Recovery successful: {result}")
    except Exception as e:
        logger.error(f"❌ Recovery failed: {e}")


async def demonstrate_circuit_breaker_patterns():
    """Demonstrate various circuit breaker patterns."""
    logger.info("🛡️ AutoBot Circuit Breaker Pattern Demonstration")
    logger.info("=" * 60)

    service = AutoBotServiceWithCircuitBreaker()
    await _demo_basic_service_operations(service)

    logger.info("\\n2. Complex Operations with Fallback Strategies")
    orchestrator = CircuitBreakerOrchestrator()

    complex_result = (
        await orchestrator.service.perform_complex_operation_with_fallbacks(
            "complex_op_001"
        )
    )
    logger.info(f"✅ Complex Operation Status: {complex_result['status']}")
    logger.info(f"🔄 Fallbacks Used: {complex_result['fallbacks_used']}")
    logger.info(f"📈 Success Rate: {complex_result['success_rate']:.1%}")

    await _demo_batch_processing(orchestrator)
    await _demo_circuit_recovery()


# Example decorator patterns
@circuit_breaker_async("critical_service", failure_threshold=1, recovery_timeout=10.0)
async def critical_service_call():
    """Example of critical service with very low failure threshold"""
    if random.random() < 0.5:  # 50% failure rate
        raise ConnectionError("Critical service unavailable")
    return "Critical operation completed"


@circuit_breaker_sync("batch_processor", failure_threshold=3, timeout=5.0)
def batch_processing_service(batch_size: int):
    """Example of batch processing service with sync circuit breaker"""
    if batch_size > 100:
        raise ValueError("Batch size too large")  # Not monitored by circuit breaker

    if random.random() < 0.3:  # 30% failure rate
        raise OSError("Processing system overloaded")

    return f"Processed batch of {batch_size} items"


async def demonstrate_decorator_patterns():
    """Demonstrate circuit breaker decorator patterns"""

    logger.info("\\n🎯 Circuit Breaker Decorator Demonstrations")
    logger.info("=" * 60)

    # Test critical service with low threshold
    logger.error("\\n1. Critical Service (Low Failure Threshold)")

    for i in range(3):
        try:
            result = await critical_service_call()
            logger.info(f"   Attempt {i+1}: ✅ {result}")
        except CircuitBreakerOpenError:
            logger.info(f"   Attempt {i+1}: 🚫 Circuit breaker open")
        except ConnectionError:
            logger.error(f"   Attempt {i+1}: ❌ Connection failed")

    # Test sync batch processor
    logger.info("\\n2. Batch Processing Service (Sync)")

    batch_sizes = [50, 75, 150, 25, 80]  # Mix of valid and invalid sizes

    for i, size in enumerate(batch_sizes):
        try:
            result = batch_processing_service(size)
            logger.info(f"   Batch {i+1} (size {size}): ✅ {result}")
        except CircuitBreakerOpenError:
            logger.info(f"   Batch {i+1} (size {size}): 🚫 Circuit breaker open")
        except ValueError as e:
            logger.warning(f"   Batch {i+1} (size {size}): ⚠️ Invalid input: {e}")
        except OSError:
            logger.error(f"   Batch {i+1} (size {size}): ❌ System overloaded")


if __name__ == "__main__":

    async def main():
        """Main demonstration function"""
        await demonstrate_circuit_breaker_patterns()
        await demonstrate_decorator_patterns()

        logger.info("\\n🎉 Circuit Breaker Pattern Demonstration Complete!")
        logger.info("\\n💡 Key Benefits:")
        logger.error("   - Prevents cascading failures across services")
        logger.error("   - Automatic failure detection and recovery")
        logger.info("   - Performance-based circuit opening")
        logger.info("   - Graceful service degradation with fallbacks")
        logger.info("   - Real-time monitoring and observability")
        logger.info("   - Configurable thresholds per service type")

    # Run the demonstration
    asyncio.run(main())
