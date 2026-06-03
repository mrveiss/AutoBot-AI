# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Ansible inventory name sanitization (#9283).
"""

import pytest

from api.setup_wizard import _sanitize_ansible_name


class TestAnsibleNameSanitization:
    """Test _sanitize_ansible_name function."""

    def test_name_starting_with_number(self):
        """Names starting with numbers should get 'node_' prefix."""
        assert _sanitize_ansible_name("01-Backend") == "node_01_Backend"
        assert _sanitize_ansible_name("02-Frontend") == "node_02_Frontend"
        assert _sanitize_ansible_name("03-AI-Stack") == "node_03_AI_Stack"
        assert _sanitize_ansible_name("04-Databases") == "node_04_Databases"
        assert _sanitize_ansible_name("05-LLM-CPU") == "node_05_LLM_CPU"
        assert _sanitize_ansible_name("06-Node-27") == "node_06_Node_27"

    def test_name_with_hyphens(self):
        """Hyphens should be replaced with underscores."""
        assert _sanitize_ansible_name("backend-server") == "backend_server"
        assert _sanitize_ansible_name("ai-stack") == "ai_stack"
        assert _sanitize_ansible_name("npu-worker") == "npu_worker"

    def test_name_with_dots(self):
        """Dots should be replaced with underscores."""
        assert _sanitize_ansible_name("server.example.com") == "server_example_com"

    def test_valid_names_unchanged(self):
        """Valid names (letters, numbers, underscores) should not change."""
        assert _sanitize_ansible_name("backend") == "backend"
        assert _sanitize_ansible_name("frontend") == "frontend"
        assert _sanitize_ansible_name("ai_stack") == "ai_stack"
        assert _sanitize_ansible_name("npu_worker") == "npu_worker"
        assert _sanitize_ansible_name("slm_server") == "slm_server"

    def test_slm_manager(self):
        """SLM manager node should be sanitized correctly."""
        assert _sanitize_ansible_name("00-SLM-Manager") == "node_00_SLM_Manager"

    def test_special_characters(self):
        """Other special characters should be replaced with underscores."""
        assert _sanitize_ansible_name("node@host") == "node_host"
        assert _sanitize_ansible_name("node#123") == "node_123"
        assert _sanitize_ansible_name("node%test") == "node_test"

    def test_empty_string(self):
        """Empty string should remain empty."""
        assert _sanitize_ansible_name("") == ""

    def test_ip_addresses(self):
        """IP addresses should be sanitized (dots replaced, may get prefix)."""
        # IP starting with number gets prefix, dots become underscores
        assert _sanitize_ansible_name("192.168.1.100") == "node_192_168_1_100"
        assert _sanitize_ansible_name("10.0.0.1") == "node_10_0_0_1"
