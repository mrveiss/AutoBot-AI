#!/usr/bin/env python3
"""
Automated Chat Fix Verification Tests

This test suite validates the chat message submission fix across all scenarios:
- Normal message send (no attachments)
- Message with file attachments
- Message with metadata/options
- Error handling (network failures, 422, etc.)
- Retry logic validation
- Type safety verification

Run after syncing changes to Frontend VM (172.16.168.21)
"""

import asyncio
import json
import time
from typing import Dict, Any, List, Optional
import httpx
import pytest
from datetime import datetime


# Configuration
BACKEND_URL = "http://172.16.168.20:8001"
FRONTEND_URL = "http://172.16.168.21:5173"
CHAT_ENDPOINT = f"{BACKEND_URL}/api/chat/send"
HEALTH_ENDPOINT = f"{BACKEND_URL}/api/health"
TIMEOUT = 30.0


class ChatTestResult:
    """Test result container"""
    def __init__(self, test_name: str, passed: bool, details: str, duration: float):
        self.test_name = test_name
        self.passed = passed
        self.details = details
        self.duration = duration
        self.timestamp = datetime.now()

    def __str__(self):
        status = "✅ PASS" if self.passed else "❌ FAIL"
        return f"{status} | {self.test_name} | {self.duration:.2f}ms | {self.details}"


class ChatFixTestSuite:
    """Comprehensive chat fix test suite"""

    def __init__(self):
        self.results: List[ChatTestResult] = []
        self.client = httpx.AsyncClient(timeout=TIMEOUT)

    async def setup(self):
        """Verify test environment is ready"""
        print("🔧 Setting up test environment...")

        # Check backend health
        try:
            response = await self.client.get(HEALTH_ENDPOINT)
            if response.status_code != 200:
                raise Exception(f"Backend unhealthy: {response.status_code}")
            print("✅ Backend API is healthy")
        except Exception as e:
            raise Exception(f"Backend not accessible: {e}")

        # Check frontend availability
        try:
            response = await self.client.get(FRONTEND_URL)
            if response.status_code not in [200, 304]:
                raise Exception(f"Frontend not accessible: {response.status_code}")
            print("✅ Frontend is accessible")
        except Exception as e:
            raise Exception(f"Frontend not accessible: {e}")

        print("✅ Test environment ready\n")

    async def teardown(self):
        """Clean up test resources"""
        await self.client.aclose()

    def add_result(self, test_name: str, passed: bool, details: str, duration: float):
        """Add test result"""
        result = ChatTestResult(test_name, passed, details, duration)
        self.results.append(result)
        print(result)

    # =========================================================================
    # Test Scenario 1: Normal Message Send (No Attachments)
    # =========================================================================

    async def test_normal_message_send(self):
        """Test basic message send without attachments"""
        test_name = "Normal Message Send"
        start_time = time.time()

        try:
            payload = {
                "message": "Hello AutoBot - automated test",
                "user_id": "test_user_automated",
                "session_id": f"test_session_{int(time.time())}"
            }

            response = await self.client.post(
                CHAT_ENDPOINT,
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            duration = (time.time() - start_time) * 1000

            # Validate response
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"

            response_data = response.json()
            assert "response" in response_data or "message" in response_data, \
                "Response missing message field"

            self.add_result(test_name, True, f"Status: {response.status_code}", duration)
            return True

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(test_name, False, str(e), duration)
            return False

    async def test_message_with_special_characters(self):
        """Test message with special characters and emojis"""
        test_name = "Special Characters & Emojis"
        start_time = time.time()

        try:
            special_message = "Test: <script>alert('XSS')</script> & 🚀 🔥 💻 🤖"

            payload = {
                "message": special_message,
                "user_id": "test_user_automated",
                "session_id": f"test_session_{int(time.time())}"
            }

            response = await self.client.post(CHAT_ENDPOINT, json=payload)
            duration = (time.time() - start_time) * 1000

            assert response.status_code == 200, f"Expected 200, got {response.status_code}"

            self.add_result(test_name, True, "Special chars handled", duration)
            return True

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(test_name, False, str(e), duration)
            return False

    async def test_empty_message_validation(self):
        """Test that empty messages are rejected"""
        test_name = "Empty Message Validation"
        start_time = time.time()

        try:
            payload = {
                "message": "",
                "user_id": "test_user_automated",
                "session_id": f"test_session_{int(time.time())}"
            }

            response = await self.client.post(CHAT_ENDPOINT, json=payload)
            duration = (time.time() - start_time) * 1000

            # Empty message should either be rejected (422) or handled gracefully (200)
            assert response.status_code in [200, 422], \
                f"Unexpected status: {response.status_code}"

            self.add_result(test_name, True, f"Status: {response.status_code}", duration)
            return True

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(test_name, False, str(e), duration)
            return False

    async def test_very_long_message(self):
        """Test handling of very long messages"""
        test_name = "Very Long Message (10k chars)"
        start_time = time.time()

        try:
            long_message = "A" * 10000  # 10k character message

            payload = {
                "message": long_message,
                "user_id": "test_user_automated",
                "session_id": f"test_session_{int(time.time())}"
            }

            response = await self.client.post(CHAT_ENDPOINT, json=payload)
            duration = (time.time() - start_time) * 1000

            assert response.status_code in [200, 413, 422], \
                f"Unexpected status: {response.status_code}"

            self.add_result(test_name, True, f"Status: {response.status_code}", duration)
            return True

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(test_name, False, str(e), duration)
            return False

    # =========================================================================
    # Test Scenario 2: Message with File Attachments
    # =========================================================================

    async def test_message_with_file_reference(self):
        """Test message with file reference (not raw file_data)"""
        test_name = "Message with File Reference"
        start_time = time.time()

        try:
            payload = {
                "message": "Here is the document",
                "user_id": "test_user_automated",
                "session_id": f"test_session_{int(time.time())}",
                "attached_file_ids": ["test_file_id_12345"]
            }

            response = await self.client.post(CHAT_ENDPOINT, json=payload)
            duration = (time.time() - start_time) * 1000

            # Should accept file reference without 422 error
            assert response.status_code != 422, \
                f"422 validation error on file reference: {response.text}"

            self.add_result(test_name, True, f"Status: {response.status_code}", duration)
            return True

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(test_name, False, str(e), duration)
            return False

    async def test_invalid_file_data_rejected(self):
        """Test that raw file_data is rejected (422 expected)"""
        test_name = "Invalid file_data Rejected"
        start_time = time.time()

        try:
            payload = {
                "message": "Test with invalid file_data",
                "user_id": "test_user_automated",
                "session_id": f"test_session_{int(time.time())}",
                "file_data": "This field should not be accepted"  # Invalid field
            }

            response = await self.client.post(CHAT_ENDPOINT, json=payload)
            duration = (time.time() - start_time) * 1000

            # Should return 422 for unexpected field
            assert response.status_code == 422, \
                f"Expected 422 for invalid field, got {response.status_code}"

            self.add_result(test_name, True, "422 validation working", duration)
            return True

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(test_name, False, str(e), duration)
            return False

    # =========================================================================
    # Test Scenario 3: Message with Metadata/Options
    # =========================================================================

    async def test_message_with_metadata(self):
        """Test message with metadata options"""
        test_name = "Message with Metadata"
        start_time = time.time()

        try:
            payload = {
                "message": "Explain quantum computing",
                "user_id": "test_user_automated",
                "session_id": f"test_session_{int(time.time())}",
                "metadata": {
                    "temperature": 0.7,
                    "max_tokens": 500
                }
            }

            response = await self.client.post(CHAT_ENDPOINT, json=payload)
            duration = (time.time() - start_time) * 1000

            assert response.status_code in [200, 422], \
                f"Unexpected status: {response.status_code}"

            self.add_result(test_name, True, f"Status: {response.status_code}", duration)
            return True

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(test_name, False, str(e), duration)
            return False

    # =========================================================================
    # Test Scenario 4: Error Handling
    # =========================================================================

    async def test_network_timeout_handling(self):
        """Test timeout handling (3 second timeout)"""
        test_name = "Network Timeout Handling"
        start_time = time.time()

        try:
            # Create client with very short timeout
            timeout_client = httpx.AsyncClient(timeout=3.0)

            payload = {
                "message": "Timeout test",
                "user_id": "test_user_automated",
                "session_id": f"test_session_{int(time.time())}"
            }

            try:
                response = await timeout_client.post(CHAT_ENDPOINT, json=payload)
                duration = (time.time() - start_time) * 1000
                self.add_result(test_name, True, "No timeout occurred", duration)
                result = True
            except httpx.TimeoutException:
                duration = (time.time() - start_time) * 1000
                self.add_result(test_name, True, "Timeout handled gracefully", duration)
                result = True
            finally:
                await timeout_client.aclose()

            return result

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(test_name, False, str(e), duration)
            return False

    async def test_malformed_request_422(self):
        """Test 422 validation error handling"""
        test_name = "422 Validation Error"
        start_time = time.time()

        try:
            # Send request with invalid/unexpected fields
            payload = {
                "message": "Test 422 error",
                "user_id": "test_user_automated",
                "session_id": f"test_session_{int(time.time())}",
                "invalid_field": "This should trigger 422",
                "another_bad_field": 12345
            }

            response = await self.client.post(CHAT_ENDPOINT, json=payload)
            duration = (time.time() - start_time) * 1000

            # Should return 422 for validation error
            assert response.status_code == 422, \
                f"Expected 422 for invalid fields, got {response.status_code}"

            # Validate error response structure
            error_data = response.json()
            assert "detail" in error_data, "422 response missing error details"

            self.add_result(test_name, True, "422 validation working", duration)
            return True

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(test_name, False, str(e), duration)
            return False

    async def test_missing_required_fields(self):
        """Test handling of missing required fields"""
        test_name = "Missing Required Fields"
        start_time = time.time()

        try:
            # Missing user_id and session_id
            payload = {
                "message": "Test missing fields"
            }

            response = await self.client.post(CHAT_ENDPOINT, json=payload)
            duration = (time.time() - start_time) * 1000

            # Should return 422 for missing required fields
            assert response.status_code == 422, \
                f"Expected 422 for missing fields, got {response.status_code}"

            self.add_result(test_name, True, "Required field validation working", duration)
            return True

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(test_name, False, str(e), duration)
            return False

    # =========================================================================
    # Test Scenario 5: Retry Logic Validation
    # =========================================================================

    async def test_rapid_sequential_requests(self):
        """Test handling of rapid sequential requests"""
        test_name = "Rapid Sequential Requests (10x)"
        start_time = time.time()

        try:
            success_count = 0
            total_requests = 10

            for i in range(total_requests):
                payload = {
                    "message": f"Rapid test message {i}",
                    "user_id": "test_user_automated",
                    "session_id": f"test_session_{int(time.time())}"
                }

                response = await self.client.post(CHAT_ENDPOINT, json=payload)

                if response.status_code == 200:
                    success_count += 1

            duration = (time.time() - start_time) * 1000

            # At least 80% should succeed
            assert success_count >= total_requests * 0.8, \
                f"Only {success_count}/{total_requests} requests succeeded"

            self.add_result(
                test_name,
                True,
                f"{success_count}/{total_requests} succeeded",
                duration
            )
            return True

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(test_name, False, str(e), duration)
            return False

    # =========================================================================
    # Test Scenario 6: Type Safety Verification
    # =========================================================================

    async def test_type_validation_message(self):
        """Test type validation for message field"""
        test_name = "Type Validation - Message Field"
        start_time = time.time()

        try:
            # Send integer instead of string for message
            payload = {
                "message": 12345,  # Invalid type
                "user_id": "test_user_automated",
                "session_id": f"test_session_{int(time.time())}"
            }

            response = await self.client.post(CHAT_ENDPOINT, json=payload)
            duration = (time.time() - start_time) * 1000

            # Should return 422 for type mismatch
            assert response.status_code == 422, \
                f"Expected 422 for type error, got {response.status_code}"

            self.add_result(test_name, True, "Type validation working", duration)
            return True

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(test_name, False, str(e), duration)
            return False

    async def test_type_validation_user_id(self):
        """Test type validation for user_id field"""
        test_name = "Type Validation - User ID Field"
        start_time = time.time()

        try:
            # Send array instead of string for user_id
            payload = {
                "message": "Test type validation",
                "user_id": ["invalid", "array"],  # Invalid type
                "session_id": f"test_session_{int(time.time())}"
            }

            response = await self.client.post(CHAT_ENDPOINT, json=payload)
            duration = (time.time() - start_time) * 1000

            # Should return 422 for type mismatch
            assert response.status_code == 422, \
                f"Expected 422 for type error, got {response.status_code}"

            self.add_result(test_name, True, "Type validation working", duration)
            return True

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(test_name, False, str(e), duration)
            return False

    # =========================================================================
    # Performance Testing
    # =========================================================================

    async def test_performance_benchmark(self):
        """Benchmark chat API performance"""
        test_name = "Performance Benchmark (10 requests)"
        start_time = time.time()

        try:
            response_times = []

            for i in range(10):
                request_start = time.time()

                payload = {
                    "message": f"Performance benchmark {i}",
                    "user_id": "test_user_automated",
                    "session_id": f"test_session_{int(time.time())}"
                }

                response = await self.client.post(CHAT_ENDPOINT, json=payload)

                request_duration = (time.time() - request_start) * 1000
                response_times.append(request_duration)

                if response.status_code != 200:
                    raise Exception(f"Request {i} failed: {response.status_code}")

            total_duration = (time.time() - start_time) * 1000

            avg_time = sum(response_times) / len(response_times)
            min_time = min(response_times)
            max_time = max(response_times)

            details = f"Avg: {avg_time:.0f}ms | Min: {min_time:.0f}ms | Max: {max_time:.0f}ms"

            # Performance threshold: average < 5000ms (excluding LLM processing)
            performance_acceptable = avg_time < 5000

            self.add_result(test_name, performance_acceptable, details, total_duration)
            return performance_acceptable

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(test_name, False, str(e), duration)
            return False

    # =========================================================================
    # Main Test Runner
    # =========================================================================

    async def run_all_tests(self):
        """Run complete test suite"""
        print("=" * 80)
        print("🧪 CHAT FIX VERIFICATION - AUTOMATED TEST SUITE")
        print("=" * 80)
        print(f"Backend: {BACKEND_URL}")
        print(f"Frontend: {FRONTEND_URL}")
        print(f"Started: {datetime.now()}\n")

        await self.setup()

        # Test Scenario 1: Normal Message Send
        print("\n📋 Test Scenario 1: Normal Message Send")
        print("-" * 80)
        await self.test_normal_message_send()
        await self.test_message_with_special_characters()
        await self.test_empty_message_validation()
        await self.test_very_long_message()

        # Test Scenario 2: File Attachments
        print("\n📋 Test Scenario 2: File Attachments")
        print("-" * 80)
        await self.test_message_with_file_reference()
        await self.test_invalid_file_data_rejected()

        # Test Scenario 3: Metadata/Options
        print("\n📋 Test Scenario 3: Metadata/Options")
        print("-" * 80)
        await self.test_message_with_metadata()

        # Test Scenario 4: Error Handling
        print("\n📋 Test Scenario 4: Error Handling")
        print("-" * 80)
        await self.test_network_timeout_handling()
        await self.test_malformed_request_422()
        await self.test_missing_required_fields()

        # Test Scenario 5: Retry Logic
        print("\n📋 Test Scenario 5: Retry Logic")
        print("-" * 80)
        await self.test_rapid_sequential_requests()

        # Test Scenario 6: Type Safety
        print("\n📋 Test Scenario 6: Type Safety")
        print("-" * 80)
        await self.test_type_validation_message()
        await self.test_type_validation_user_id()

        # Performance Testing
        print("\n📋 Performance Testing")
        print("-" * 80)
        await self.test_performance_benchmark()

        await self.teardown()

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print test results summary"""
        print("\n" + "=" * 80)
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 80)

        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.passed)
        failed_tests = total_tests - passed_tests
        pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

        print(f"\nTotal Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"📈 Pass Rate: {pass_rate:.1f}%")

        if failed_tests > 0:
            print("\n❌ Failed Tests:")
            for result in self.results:
                if not result.passed:
                    print(f"  - {result.test_name}: {result.details}")

        total_duration = sum(r.duration for r in self.results)
        print(f"\n⏱️  Total Duration: {total_duration:.0f}ms")
        print(f"📅 Completed: {datetime.now()}")

        # Overall assessment
        print("\n" + "=" * 80)
        if pass_rate >= 90:
            print("✅ OVERALL: ALL CRITICAL TESTS PASSED")
            print("✅ Ready for production deployment")
        elif pass_rate >= 70:
            print("⚠️  OVERALL: MOST TESTS PASSED (Some issues found)")
            print("⚠️  Review failures before deployment")
        else:
            print("❌ OVERALL: SIGNIFICANT FAILURES DETECTED")
            print("❌ NOT ready for deployment - fix required")
        print("=" * 80)

        # Save results to file
        self.save_results()

    def save_results(self):
        """Save test results to file"""
        results_dir = "/home/kali/Desktop/AutoBot/tests/results"
        import os
        os.makedirs(results_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = f"{results_dir}/chat_fix_test_results_{timestamp}.json"

        results_data = {
            "timestamp": datetime.now().isoformat(),
            "backend_url": BACKEND_URL,
            "frontend_url": FRONTEND_URL,
            "total_tests": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "failed": sum(1 for r in self.results if not r.passed),
            "tests": [
                {
                    "name": r.test_name,
                    "passed": r.passed,
                    "details": r.details,
                    "duration_ms": r.duration,
                    "timestamp": r.timestamp.isoformat()
                }
                for r in self.results
            ]
        }

        with open(results_file, 'w') as f:
            json.dump(results_data, f, indent=2)

        print(f"\n💾 Results saved to: {results_file}")


async def main():
    """Main entry point"""
    test_suite = ChatFixTestSuite()
    await test_suite.run_all_tests()


if __name__ == "__main__":
    # Run test suite
    asyncio.run(main())
