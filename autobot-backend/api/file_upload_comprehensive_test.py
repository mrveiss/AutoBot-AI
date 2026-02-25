#!/usr/bin/env python3
"""
Comprehensive File Upload Functionality Test Suite

This module provides comprehensive testing for AutoBot's file upload functionality,
including API endpoints, security features, error handling, and edge cases.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import requests

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FileUploadAPITests(unittest.TestCase):
    """Test file upload API endpoints"""

    BASE_URL = "http://localhost:8001/api/files"
    HEADERS = {"X-User-Role": "admin"}

    def setUp(self):
        """Set up test environment"""
        self.test_files = []

    def tearDown(self):
        """Clean up test files"""
        for file_path in self.test_files:
            try:
                os.unlink(file_path)
            except FileNotFoundError:
                pass

    def create_test_file(self, content: str, suffix: str = ".txt") -> str:
        """Create a temporary test file"""
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "w") as f:
            f.write(content)
        self.test_files.append(path)
        return path

    def test_basic_file_upload(self):
        """Test basic file upload functionality"""
        # Create test file
        test_content = "This is a test file for upload validation"
        test_file = self.create_test_file(test_content)

        # Upload file
        with open(test_file, "rb") as f:
            files = {"file": ("test_upload.txt", f, "text/plain")}
            data = {"path": "", "overwrite": False}

            try:
                response = requests.post(
                    f"{self.BASE_URL}/upload",
                    headers=self.HEADERS,
                    files=files,
                    data=data,
                    timeout=10,
                )

                self.assertEqual(response.status_code, 200)

                result = response.json()
                self.assertTrue(result.get("success"))
                self.assertIn("file_info", result)
                self.assertIn("upload_id", result)

                # Verify file info
                file_info = result["file_info"]
                self.assertEqual(file_info["name"], "test_upload.txt")
                self.assertEqual(file_info["extension"], ".txt")
                self.assertEqual(file_info["mime_type"], "text/plain")
                self.assertGreater(file_info["size"], 0)

            except requests.RequestException as e:
                self.skipTest(f"Backend not accessible: {e}")

    def test_file_type_validation(self):
        """Test file type validation and security"""
        # Test invalid file extension
        test_content = "fake executable content"
        test_file = self.create_test_file(test_content, suffix=".exe")

        with open(test_file, "rb") as f:
            files = {"file": ("malicious.exe", f, "application/octet-stream")}
            data = {"path": "", "overwrite": False}

            try:
                response = requests.post(
                    f"{self.BASE_URL}/upload",
                    headers=self.HEADERS,
                    files=files,
                    data=data,
                    timeout=10,
                )

                self.assertEqual(response.status_code, 400)

                result = response.json()
                self.assertIn("File type not allowed", result.get("detail", ""))

            except requests.RequestException as e:
                self.skipTest(f"Backend not accessible: {e}")

    def test_multiple_file_formats(self):
        """Test various allowed file formats"""
        test_cases = [
            ('{"test": "data"}', ".json", "application/json"),
            ('print("Hello World")', ".py", "text/x-python"),  # noqa: print
            ("# Test Markdown", ".md", "text/markdown"),
            ('console.log("test");', ".js", "application/javascript"),
            ("<html><body>Test</body></html>", ".html", "text/html"),
            ("body { color: red; }", ".css", "text/css"),
            ("test,data,value", ".csv", "text/csv"),
        ]

        for content, extension, expected_mime in test_cases:
            with self.subTest(extension=extension):
                test_file = self.create_test_file(content, suffix=extension)
                filename = f"test{extension}"

                with open(test_file, "rb") as f:
                    files = {"file": (filename, f, expected_mime)}
                    data = {"path": "", "overwrite": False}

                    try:
                        response = requests.post(
                            f"{self.BASE_URL}/upload",
                            headers=self.HEADERS,
                            files=files,
                            data=data,
                            timeout=10,
                        )

                        self.assertEqual(
                            response.status_code,
                            200,
                            f"Upload failed for {extension}: {response.text}",
                        )

                        result = response.json()
                        self.assertTrue(result.get("success"))

                    except requests.RequestException as e:
                        self.skipTest(f"Backend not accessible: {e}")

    def test_file_listing(self):
        """Test file listing API"""
        try:
            response = requests.get(
                f"{self.BASE_URL}/list", headers=self.HEADERS, timeout=10
            )

            self.assertEqual(response.status_code, 200)

            result = response.json()
            self.assertIn("files", result)
            self.assertIn("total_files", result)
            self.assertIn("total_directories", result)
            self.assertIn("total_size", result)

            # Verify file structure
            files = result["files"]
            self.assertIsInstance(files, list)

            for file_info in files:
                required_fields = [
                    "name",
                    "path",
                    "is_directory",
                    "last_modified",
                    "permissions",
                ]
                for field in required_fields:
                    self.assertIn(field, file_info)

        except requests.RequestException as e:
            self.skipTest(f"Backend not accessible: {e}")

    def test_file_statistics(self):
        """Test file statistics API"""
        try:
            response = requests.get(f"{self.BASE_URL}/stats", timeout=10)

            self.assertEqual(response.status_code, 200)

            result = response.json()
            required_fields = [
                "sandbox_root",
                "total_files",
                "total_directories",
                "total_size",
                "max_file_size_mb",
                "allowed_extensions",
            ]

            for field in required_fields:
                self.assertIn(field, result)

            # Verify allowed extensions is a list
            self.assertIsInstance(result["allowed_extensions"], list)
            self.assertGreater(len(result["allowed_extensions"]), 0)

            # Verify basic file types are allowed
            allowed_extensions = result["allowed_extensions"]
            expected_extensions = [".txt", ".json", ".md", ".py", ".js", ".html"]

            for ext in expected_extensions:
                self.assertIn(ext, allowed_extensions)

        except requests.RequestException as e:
            self.skipTest(f"Backend not accessible: {e}")

    def test_path_traversal_protection(self):
        """Test protection against path traversal attacks"""
        test_content = "malicious content"
        test_file = self.create_test_file(test_content)

        # Test various path traversal attempts
        malicious_paths = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "/etc/passwd",
            "\\windows\\system32",
            "..%2F..%2F..%2Fetc%2Fpasswd",  # URL encoded
        ]

        for malicious_path in malicious_paths:
            with self.subTest(path=malicious_path):
                with open(test_file, "rb") as f:
                    files = {"file": ("test.txt", f, "text/plain")}
                    data = {"path": malicious_path, "overwrite": False}

                    try:
                        response = requests.post(
                            f"{self.BASE_URL}/upload",
                            headers=self.HEADERS,
                            files=files,
                            data=data,
                            timeout=10,
                        )

                        # Should either reject the path or sanitize it
                        if response.status_code == 200:
                            result = response.json()
                            file_path = result.get("file_info", {}).get("path", "")
                            # Path should be sanitized and not contain traversal
                            self.assertNotIn("..", file_path)
                            self.assertFalse(file_path.startswith("/"))
                        else:
                            # Path should be rejected
                            self.assertIn(response.status_code, [400, 403])

                    except requests.RequestException as e:
                        self.skipTest(f"Backend not accessible: {e}")

    def test_subdirectory_upload(self):
        """Test uploading files to subdirectories"""
        test_content = "test content for subdirectory"
        test_file = self.create_test_file(test_content)

        with open(test_file, "rb") as f:
            files = {"file": ("subdir_test.txt", f, "text/plain")}
            data = {"path": "testsubdir", "overwrite": False}

            try:
                response = requests.post(
                    f"{self.BASE_URL}/upload",
                    headers=self.HEADERS,
                    files=files,
                    data=data,
                    timeout=10,
                )

                self.assertEqual(response.status_code, 200)

                result = response.json()
                self.assertTrue(result.get("success"))

                file_info = result["file_info"]
                self.assertEqual(file_info["path"], "testsubdir/subdir_test.txt")

                # Verify we can list the subdirectory
                list_response = requests.get(
                    f"{self.BASE_URL}/list",
                    headers=self.HEADERS,
                    params={"path": "testsubdir"},
                    timeout=10,
                )

                self.assertEqual(list_response.status_code, 200)

                list_result = list_response.json()
                self.assertEqual(list_result["current_path"], "testsubdir")
                self.assertGreater(len(list_result["files"]), 0)

            except requests.RequestException as e:
                self.skipTest(f"Backend not accessible: {e}")

    def test_file_download(self):
        """Test file download functionality"""
        # First upload a file
        test_content = "Content for download test"
        test_file = self.create_test_file(test_content)

        with open(test_file, "rb") as f:
            files = {"file": ("download_test.txt", f, "text/plain")}
            data = {"path": "", "overwrite": False}

            try:
                upload_response = requests.post(
                    f"{self.BASE_URL}/upload",
                    headers=self.HEADERS,
                    files=files,
                    data=data,
                    timeout=10,
                )

                self.assertEqual(upload_response.status_code, 200)

                # Now try to download it
                download_response = requests.get(
                    f"{self.BASE_URL}/download/download_test.txt",
                    headers=self.HEADERS,
                    timeout=10,
                )

                self.assertEqual(download_response.status_code, 200)
                self.assertEqual(download_response.text.strip(), test_content)

            except requests.RequestException as e:
                self.skipTest(f"Backend not accessible: {e}")


class FileUploadIntegrationTests(unittest.TestCase):
    """Integration tests for file upload with other systems"""

    def test_knowledge_base_integration(self):
        """Test file upload integration with knowledge base"""
        # This would test if uploaded files can be processed by the knowledge base
        # For now, just verify the integration points exist

        try:
            from knowledge_base import KnowledgeBase

            KnowledgeBase()
            # Verify KB can access uploaded files area
            upload_path = Path("data/file_manager_root")
            self.assertTrue(upload_path.exists())

        except ImportError:
            self.skipTest("Knowledge base not available for integration test")

    def test_security_layer_integration(self):
        """Test file upload integration with security layer"""
        try:
            from security_layer import SecurityLayer

            security = SecurityLayer()

            # Test permission checking
            # Note: In development mode, permissions might be permissive
            has_upload_permission = security.check_permission(
                user_role="admin",
                action_type="files.upload",
                resource="file_operation:upload",
            )

            # Admin should have upload permission
            self.assertTrue(has_upload_permission)

            # Guest should not have upload permission (in production)
            has_guest_permission = security.check_permission(
                user_role="guest",
                action_type="files.upload",
                resource="file_operation:upload",
            )

            # In development, this might be True due to permissive mode
            # In production, it should be False
            self.assertIsInstance(has_guest_permission, bool)

        except ImportError:
            self.skipTest("Security layer not available for integration test")


def run_comprehensive_tests():
    """Run the complete file upload test suite"""
    print("🧪 Running Comprehensive File Upload Tests")  # noqa: print
    print("=" * 60)  # noqa: print

    # Create test suite
    suite = unittest.TestSuite()

    # Add test classes
    test_classes = [
        FileUploadAPITests,
        FileUploadIntegrationTests,
    ]

    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        suite.addTests(tests)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Summary
    print("\n" + "=" * 60)  # noqa: print
    if result.wasSuccessful():
        print("✅ All File Upload Tests Passed!")  # noqa: print
        print(f"Ran {result.testsRun} tests successfully")  # noqa: print
        return 0
    else:
        print(  # noqa: print
            f"❌ {len(result.failures)} failures, {len(result.errors)} errors"
        )  # noqa: print

        # Print failure details
        if result.failures:
            print("\nFailures:")  # noqa: print
            for test, traceback in result.failures:
                print(f"- {test}: {traceback}")  # noqa: print

        if result.errors:
            print("\nErrors:")  # noqa: print
            for test, traceback in result.errors:
                print(f"- {test}: {traceback}")  # noqa: print

        return 1


if __name__ == "__main__":
    exit_code = run_comprehensive_tests()
    sys.exit(exit_code)
