#!/usr/bin/env python3
"""
File Upload API Testing
Tests the file upload API endpoints and validation
"""

import json
import os
import tempfile
from pathlib import Path

import requests


class FileUploadAPITester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.session = requests.Session()
        self.results = []

    def test_file_upload_api(self):
        """Run comprehensive file upload API tests"""
        print("🧪 Testing File Upload API")
        print("=" * 50)

        # Test 1: API endpoint accessibility
        self._test_upload_endpoint_availability()

        # Test 2: Valid file upload
        self._test_valid_file_upload()

        # Test 3: Invalid file types
        self._test_invalid_file_types()

        # Test 4: File size limits
        self._test_file_size_limits()

        # Test 5: Security validation
        self._test_security_validation()

        # Print results summary
        self._print_summary()

        return self.results

    def _test_upload_endpoint_availability(self):
        """Test if upload endpoint is accessible"""
        try:
            response = self.session.options(f"{self.base_url}/api/files/upload")

            if response.status_code in [200, 204]:
                self._add_result(
                    "Upload Endpoint Available",
                    "PASS",
                    "API endpoint accepts OPTIONS requests",
                )
            else:
                self._add_result(
                    "Upload Endpoint Available",
                    "FAIL",
                    f"OPTIONS returned {response.status_code}",
                )
        except requests.ConnectionError:
            self._add_result(
                "Upload Endpoint Available",
                "SKIP",
                "Backend not running - skipping API tests",
            )
        except Exception as e:
            self._add_result("Upload Endpoint Available", "ERROR", str(e))

    def _test_valid_file_upload(self):
        """Test uploading valid files"""
        if not self._is_backend_available():
            self._add_result("Valid File Upload", "SKIP", "Backend not available")
            return

        try:
            # Create a test file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                f.write("This is a test file for upload validation.\n")
                f.write("Content: File upload API test\n")
                test_file_path = f.name

            # Test upload with unique filename to avoid conflicts
            import uuid

            unique_filename = f"test_upload_{uuid.uuid4().hex[:8]}.txt"

            with open(test_file_path, "rb") as f:
                files = {"file": (unique_filename, f, "text/plain")}
                response = self.session.post(
                    f"{self.base_url}/api/files/upload", files=files
                )

            # Cleanup
            os.unlink(test_file_path)

            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    self._add_result(
                        "Valid File Upload",
                        "PASS",
                        f"File uploaded successfully: {result.get('filename')}",
                    )
                else:
                    self._add_result(
                        "Valid File Upload",
                        "FAIL",
                        f"Upload failed: {result.get('message')}",
                    )
            else:
                self._add_result(
                    "Valid File Upload",
                    "FAIL",
                    f"HTTP {response.status_code}: {response.text[:100]}",
                )

        except Exception as e:
            self._add_result("Valid File Upload", "ERROR", str(e))

    def _test_invalid_file_types(self):
        """Test that invalid file types are rejected"""
        if not self._is_backend_available():
            self._add_result(
                "Invalid File Type Rejection", "SKIP", "Backend not available"
            )
            return

        try:
            # Create a fake executable file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".exe", delete=False
            ) as f:
                f.write("FAKE EXECUTABLE CONTENT")
                test_file_path = f.name

            # Test upload (should be rejected)
            with open(test_file_path, "rb") as f:
                files = {"file": ("malware.exe", f, "application/octet-stream")}
                response = self.session.post(
                    f"{self.base_url}/api/files/upload", files=files
                )

            # Cleanup
            os.unlink(test_file_path)

            if response.status_code == 400:
                self._add_result(
                    "Invalid File Type Rejection",
                    "PASS",
                    "Executable file properly rejected",
                )
            elif response.status_code == 200:
                self._add_result(
                    "Invalid File Type Rejection",
                    "FAIL",
                    "Executable file was accepted - SECURITY RISK!",
                )
            else:
                self._add_result(
                    "Invalid File Type Rejection",
                    "PARTIAL",
                    f"Unexpected response: {response.status_code}",
                )

        except Exception as e:
            self._add_result("Invalid File Type Rejection", "ERROR", str(e))

    def _test_file_size_limits(self):
        """Test file size limit enforcement"""
        if not self._is_backend_available():
            self._add_result("File Size Limit", "SKIP", "Backend not available")
            return

        try:
            # Create a large file (10MB)
            large_content = "A" * (10 * 1024 * 1024)

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                f.write(large_content)
                test_file_path = f.name

            # Test upload (may be rejected due to size)
            import uuid

            unique_large_filename = f"large_file_{uuid.uuid4().hex[:8]}.txt"

            with open(test_file_path, "rb") as f:
                files = {"file": (unique_large_filename, f, "text/plain")}
                response = self.session.post(
                    f"{self.base_url}/api/files/upload", files=files
                )

            # Cleanup
            os.unlink(test_file_path)

            if response.status_code == 413:
                self._add_result(
                    "File Size Limit",
                    "PASS",
                    "Large file properly rejected (413 Payload Too Large)",
                )
            elif response.status_code == 400:
                result = response.json()
                if "too large" in result.get("message", "").lower():
                    self._add_result(
                        "File Size Limit",
                        "PASS",
                        "Large file rejected with proper error message",
                    )
                else:
                    self._add_result(
                        "File Size Limit",
                        "PARTIAL",
                        f"File rejected but unclear reason: {result.get('message')}",
                    )
            elif response.status_code == 200:
                self._add_result(
                    "File Size Limit",
                    "INFO",
                    "Large file accepted - no size limit or limit >10MB",
                )
            else:
                self._add_result(
                    "File Size Limit",
                    "PARTIAL",
                    f"Unexpected response: {response.status_code}",
                )

        except Exception as e:
            self._add_result("File Size Limit", "ERROR", str(e))

    def _test_security_validation(self):
        """Test security validation features"""
        if not self._is_backend_available():
            self._add_result("Security Validation", "SKIP", "Backend not available")
            return

        try:
            # Test path traversal attempt
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                f.write("Path traversal attempt")
                test_file_path = f.name

            # Try to upload with malicious filename
            with open(test_file_path, "rb") as f:
                files = {"file": ("../../../etc/passwd", f, "text/plain")}
                response = self.session.post(
                    f"{self.base_url}/api/files/upload", files=files
                )

            # Cleanup
            os.unlink(test_file_path)

            if response.status_code == 400:
                self._add_result(
                    "Security Validation",
                    "PASS",
                    "Path traversal attempt properly blocked",
                )
            elif response.status_code == 200:
                result = response.json()
                # Check if filename was sanitized
                if "passwd" not in result.get("filename", "").lower():
                    self._add_result(
                        "Security Validation", "PASS", "Filename was sanitized"
                    )
                else:
                    self._add_result(
                        "Security Validation",
                        "FAIL",
                        "Path traversal filename not sanitized - SECURITY RISK!",
                    )
            else:
                self._add_result(
                    "Security Validation",
                    "PARTIAL",
                    f"Unexpected response: {response.status_code}",
                )

        except Exception as e:
            self._add_result("Security Validation", "ERROR", str(e))

    def _is_backend_available(self):
        """Check if backend is running"""
        try:
            response = self.session.get(f"{self.base_url}/api/system/health", timeout=5)
            return response.status_code == 200
        except (requests.RequestException, ConnectionError):
            return False

    def _add_result(self, test_name, status, message):
        """Add test result"""
        result = {"test": test_name, "status": status, "message": message}
        self.results.append(result)

        # Print immediately
        status_emoji = {
            "PASS": "✅",
            "FAIL": "❌",
            "ERROR": "🔴",
            "SKIP": "⏭️",
            "PARTIAL": "⚠️",
            "INFO": "ℹ️",
        }.get(status, "?")

        print(f"{status_emoji} {test_name}: {message}")

    def _print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 50)
        print("📊 File Upload API Test Summary")
        print("=" * 50)

        status_counts = {}
        for result in self.results:
            status = result["status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        for status, count in status_counts.items():
            emoji = {
                "PASS": "✅",
                "FAIL": "❌",
                "ERROR": "🔴",
                "SKIP": "⏭️",
                "PARTIAL": "⚠️",
                "INFO": "ℹ️",
            }.get(status, "?")
            print(f"{emoji} {status}: {count} tests")

        print(f"\n📋 Total tests: {len(self.results)}")


if __name__ == "__main__":
    tester = FileUploadAPITester()
    results = tester.test_file_upload_api()

    # Save results to file
    results_file = (
        Path(__file__).parent.parent / "results" / "file_upload_api_results.json"
    )
    results_file.parent.mkdir(exist_ok=True)

    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n📄 Results saved to: {results_file}")
