#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Error Boundary System Examples

This module demonstrates how to use the error boundary system in various
AutoBot components.
These examples can be copied and adapted for other components.
"""

import asyncio
import logging
import os
import sys
from typing import Any, Dict, List

# Add project root to path for imports  # noqa: E402
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from autobot_shared.error_boundaries import ErrorContext  # noqa: E402
from autobot_shared.error_boundaries import (
    RecoveryStrategy,
    error_boundary,
    get_error_boundary_manager,
    with_async_error_boundary,
    with_error_boundary,
)

logger = logging.getLogger(__name__)


# Example 1: Using decorator for sync functions
@error_boundary(component="example_service", function="risky_calculation")
def risky_calculation(a: int, b: int) -> float:
    """Example function that might fail - demonstrates decorator usage"""
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")

    # Simulate other possible errors
    if a < 0:
        raise ValueError("Negative values not supported")

    return a / b


# Example 2: Using decorator for async functions
@error_boundary(
    component="async_service",
    function="fetch_data",
    recovery_strategy=RecoveryStrategy.FALLBACK,
    max_retries=3,
)
async def fetch_external_data(url: str) -> Dict[str, Any]:
    """Example async function with error boundary"""
    import random

    # Simulate network errors
    if random.random() < 0.3:
        raise ConnectionError(f"Failed to connect to {url}")

    # Simulate timeout
    if random.random() < 0.2:
        raise TimeoutError(f"Timeout connecting to {url}")

    # Return mock data
    return {"data": f"Results from {url}", "status": "success"}


# Example 3: Using context manager for sync operations
def database_operation(query: str) -> List[Dict[str, Any]]:
    """Example database operation with error boundary"""
    with with_error_boundary("database", "execute_query"):
        # Simulate database operations
        if "DROP" in query.upper():
            raise PermissionError("DROP operations not allowed")

        if "invalid" in query.lower():
            raise ValueError("Invalid SQL syntax")

        # Return mock results
        return [{"id": 1, "name": "test"}, {"id": 2, "name": "example"}]


# Example 4: Using async context manager
async def llm_request(prompt: str, model: str = "default") -> str:
    """Example LLM request with error boundary"""
    async with with_async_error_boundary("llm_service", "generate_response"):
        # Simulate LLM errors
        if len(prompt) > 1000:
            raise ValueError("Prompt too long")

        if "error" in prompt.lower():
            raise ConnectionError("LLM service unavailable")

        # Simulate processing delay
        await asyncio.sleep(0.1)

        return f"Generated response for: {prompt[:50]}..."


# Example 5: Manual error handling with error boundary manager
class ExampleService:
    """Example service class using error boundaries"""

    def __init__(self):
        """Initialize example service with error boundary manager."""
        self.error_manager = get_error_boundary_manager()

    async def complex_operation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Complex operation with manual error handling"""
        context = ErrorContext(
            component="example_service",
            function="complex_operation",
            args=(data,),
            user_id=data.get("user_id"),
            request_id=data.get("request_id"),
            additional_data={"operation_type": "complex"},
        )

        try:
            # Step 1: Validate input
            if not data:
                raise ValueError("No data provided")

            # Step 2: Process data
            processed_data = await self._process_data(data)

            # Step 3: Save results
            results = await self._save_results(processed_data)

            return results

        except Exception as e:
            # Let error boundary handle the error
            return await self.error_manager.handle_error(e, context)

    async def _process_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Internal processing step"""
        # Simulate processing errors
        if data.get("corrupt", False):
            raise ValueError("Corrupted data detected")

        return {"processed": True, "original": data}

    async def _save_results(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Internal save step"""
        # Simulate database errors
        if data.get("readonly", False):
            raise PermissionError("Database is readonly")

        return {"saved": True, "id": 12345, "data": data}


# Example 6: Custom recovery handler
class CustomRecoveryHandler:
    """Example custom recovery handler for specific error scenarios"""

    def __init__(self):
        """Initialize custom recovery handler with fallback values for error scenarios."""
        self.error_manager = get_error_boundary_manager()

        # Add custom fallback handler for this service
        from autobot_shared.error_boundaries import FallbackRecoveryHandler

        custom_fallbacks = {
            "example_service.risky_calculation": 0.0,
            "example_service.complex_operation": {"error": True, "fallback": True},
            "llm_service.generate_response": (
                "I apologize, but I'm having trouble "
                "generating a response right now."
            ),
        }

        fallback_handler = FallbackRecoveryHandler(custom_fallbacks)
        self.error_manager.add_recovery_handler(fallback_handler)


# Example 7: Integration with existing AutoBot components
def integrate_with_knowledge_base():
    """Example showing how to add error boundaries to existing KB operations"""

    @error_boundary(component="knowledge_base", function="search")
    def safe_kb_search(query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Wrapped KB search with error boundary"""
        try:
            # Import KB here to avoid circular imports
            from knowledge_base import KnowledgeBase

            kb = KnowledgeBase()
            results = kb.search_chunks(query, limit=limit)
            return results
        except Exception as e:
            logger.error("KB search failed: %s", e)
            # Error boundary will handle this
            raise

    return safe_kb_search


def integrate_with_llm_interface():
    """Example showing how to add error boundaries to LLM operations"""

    @error_boundary(
        component="llm_interface",
        function="chat_completion",
        recovery_strategy=RecoveryStrategy.FALLBACK,
    )
    async def safe_llm_chat(messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """Wrapped LLM chat with error boundary"""
        try:
            # Import LLM interface here to avoid circular imports
            from llm_interface import LLMInterface

            llm = LLMInterface()
            response = await llm.achat_completion(messages, **kwargs)
            return response
        except Exception as e:
            logger.error("LLM chat failed: %s", e)
            # Error boundary will handle this
            raise

    return safe_llm_chat


# Example testing and demonstration functions
async def run_examples():
    """Run all examples to demonstrate the error boundary system"""
    print("🧪 Running Error Boundary Examples")  # noqa: print
    print("=" * 50)  # noqa: print

    # Example 1: Decorator usage
    print("\n1. Testing decorator with successful operation:")  # noqa: print
    result = risky_calculation(10, 2)
    print(f"   Result: {result}")  # noqa: print

    print("\n2. Testing decorator with error (division by zero):")  # noqa: print
    try:
        result = risky_calculation(10, 0)
        print(f"   Result: {result}")  # noqa: print
    except Exception as e:
        print(f"   Caught: {e}")  # noqa: print

    # Example 2: Async decorator
    print("\n3. Testing async decorator:")  # noqa: print
    try:
        result = await fetch_external_data("https://api.example.com")
        print(f"   Result: {result}")  # noqa: print
    except Exception as e:
        print(f"   Caught: {e}")  # noqa: print

    # Example 3: Context manager
    print("\n4. Testing sync context manager:")  # noqa: print
    try:
        result = database_operation("SELECT * FROM users")
        print(f"   Result: {len(result)} records")  # noqa: print
    except Exception as e:
        print(f"   Caught: {e}")  # noqa: print

    # Example 4: Async context manager
    print("\n5. Testing async context manager:")  # noqa: print
    try:
        result = await llm_request("What is Python?")
        print(f"   Result: {result}")  # noqa: print
    except Exception as e:
        print(f"   Caught: {e}")  # noqa: print

    # Example 5: Service class
    print("\n6. Testing service class:")  # noqa: print
    service = ExampleService()
    try:
        data = {"user_id": "test123", "data": "sample"}
        result = await service.complex_operation(data)
        print(f"   Result: {result}")  # noqa: print
    except Exception as e:
        print(f"   Caught: {e}")  # noqa: print

    # Show error statistics
    print("\n📊 Error Statistics:")  # noqa: print
    from autobot_shared.error_boundaries import get_error_statistics

    stats = get_error_statistics()
    if stats.get("total_errors", 0) > 0:
        print(f"   Total Errors: {stats['total_errors']}")  # noqa: print
        print(f"   Categories: {stats.get('categories', {})}")  # noqa: print
        print(f"   Components: {stats.get('components', {})}")  # noqa: print
    else:
        print("   No errors recorded yet")  # noqa: print

    print("\n✅ Error boundary examples completed!")  # noqa: print


if __name__ == "__main__":
    # Initialize custom recovery handler
    CustomRecoveryHandler()

    # Run examples
    asyncio.run(run_examples())
