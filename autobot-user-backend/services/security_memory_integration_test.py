# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for SecurityMemoryIntegration.

Tests memory graph entity creation and ChromaDB indexing for security findings.
Issue #260.
"""

import unittest
from unittest.mock import AsyncMock, patch

import pytest

try:
    from backend.services.security_memory_integration import SecurityMemoryIntegration

    HAS_MEMORY_GRAPH = True
except ImportError:
    HAS_MEMORY_GRAPH = False

pytestmark = pytest.mark.skipif(
    not HAS_MEMORY_GRAPH,
    reason="autobot_memory_graph.core not available",
)


class TestSecurityMemoryIntegration(unittest.IsolatedAsyncioTestCase):
    """Test security memory integration functionality."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.mock_memory_graph = AsyncMock()
        self.integration = SecurityMemoryIntegration(
            memory_graph=self.mock_memory_graph
        )
        self.integration._initialized = True

    async def test_create_assessment_entity(self):
        """Test creating assessment entity with correct observations."""
        self.mock_memory_graph.create_entity = AsyncMock(
            return_value={"name": "Security Assessment: Test Assessment", "id": "123"}
        )

        result = await self.integration.create_assessment_entity(
            assessment_id="test-001",
            name="Test Assessment",
            target="192.168.1.0/24",
            scope=["192.168.1.0/24"],
            training_mode=True,
            metadata={"user": "admin"},
        )

        self.mock_memory_graph.create_entity.assert_called_once()
        call_args = self.mock_memory_graph.create_entity.call_args
        self.assertEqual(call_args[1]["entity_type"], "task")
        self.assertIn(
            "Security assessment: Test Assessment", call_args[1]["observations"]
        )
        self.assertIn("security", call_args[1]["tags"])
        self.assertEqual(result["name"], "Security Assessment: Test Assessment")

    async def test_create_host_entity(self):
        """Test creating host entity and assessment-host relation."""
        self.mock_memory_graph.create_entity = AsyncMock(
            return_value={"name": "Host: 192.168.1.10", "id": "host-123"}
        )
        self.mock_memory_graph.create_relation = AsyncMock(return_value=True)

        with patch.object(
            self.integration._findings_index, "index_finding", new_callable=AsyncMock
        ) as mock_index:
            result = await self.integration.create_host_entity(
                assessment_id="test-001",
                ip="192.168.1.10",
                hostname="webserver",
                status="up",
                os_guess="Linux 5.x",
            )

            self.mock_memory_graph.create_entity.assert_called_once()
            call_args = self.mock_memory_graph.create_entity.call_args
            self.assertEqual(call_args[1]["metadata"]["ip"], "192.168.1.10")
            self.assertEqual(call_args[1]["metadata"]["type"], "target_host")

            self.mock_memory_graph.create_relation.assert_called_once_with(
                from_entity="Security Assessment: test-001",
                to_entity="Host: 192.168.1.10",
                relation_type="contains",
                strength=1.0,
            )

            mock_index.assert_called_once()
            self.assertEqual(result["name"], "Host: 192.168.1.10")

    async def test_create_service_entity(self):
        """Test creating service entity and host-service relation."""
        self.mock_memory_graph.create_entity = AsyncMock(
            return_value={
                "name": "Service: 192.168.1.10:80/tcp (http)",
                "id": "service-123",
            }
        )
        self.mock_memory_graph.create_relation = AsyncMock(return_value=True)

        with patch.object(
            self.integration._findings_index, "index_finding", new_callable=AsyncMock
        ) as mock_index:
            result = await self.integration.create_service_entity(
                assessment_id="test-001",
                host_ip="192.168.1.10",
                port=80,
                protocol="tcp",
                service_name="http",
                version="Apache 2.4",
            )

            self.mock_memory_graph.create_entity.assert_called_once()
            call_args = self.mock_memory_graph.create_entity.call_args
            self.assertEqual(call_args[1]["metadata"]["port"], 80)
            self.assertEqual(call_args[1]["metadata"]["type"], "service")

            self.mock_memory_graph.create_relation.assert_called_once_with(
                from_entity="Host: 192.168.1.10",
                to_entity="Service: 192.168.1.10:80/tcp (http)",
                relation_type="runs",
                strength=1.0,
            )

            mock_index.assert_called_once()
            self.assertIn("Service: 192.168.1.10:80/tcp", result["name"])

    async def test_create_vulnerability_entity(self):
        """Test creating vulnerability entity and relations."""
        self.mock_memory_graph.create_entity = AsyncMock(
            return_value={
                "name": "Vuln: CVE-2024-1234 on 192.168.1.10",
                "id": "vuln-123",
            }
        )
        self.mock_memory_graph.create_relation = AsyncMock(return_value=True)

        with patch.object(
            self.integration._findings_index, "index_finding", new_callable=AsyncMock
        ) as mock_index:
            result = await self.integration.create_vulnerability_entity(
                assessment_id="test-001",
                host_ip="192.168.1.10",
                cve_id="CVE-2024-1234",
                title="SQL Injection",
                severity="critical",
                description="SQL injection in login form",
                affected_port=80,
                affected_service="http",
            )

            self.mock_memory_graph.create_entity.assert_called_once()
            call_args = self.mock_memory_graph.create_entity.call_args
            self.assertEqual(call_args[1]["metadata"]["severity"], "critical")
            self.assertEqual(call_args[1]["metadata"]["type"], "vulnerability")

            self.assertEqual(self.mock_memory_graph.create_relation.call_count, 2)
            mock_index.assert_called_once()
            self.assertIn("CVE-2024-1234", result["name"])

    async def test_search_security_findings(self):
        """Test filtering for security entities."""
        mock_results = [
            {"name": "Host: 192.168.1.10", "metadata": {"type": "target_host"}},
            {"name": "Service: 192.168.1.10:80/tcp", "metadata": {"type": "service"}},
            {"name": "Other Entity", "metadata": {"type": "other"}},
        ]
        self.mock_memory_graph.search_entities = AsyncMock(return_value=mock_results)

        results = await self.integration.search_security_findings(
            query="192.168.1.10", limit=10
        )

        self.assertEqual(len(results), 2)
        self.assertTrue(
            all(r["metadata"]["type"] in ["target_host", "service"] for r in results)
        )

    async def test_chromadb_indexing_on_entity_creation(self):
        """Test ChromaDB index is called when entities are created."""
        self.mock_memory_graph.create_entity = AsyncMock(
            return_value={"name": "Host: 10.0.0.1", "id": "123"}
        )
        self.mock_memory_graph.create_relation = AsyncMock(return_value=True)

        with patch.object(
            self.integration._findings_index, "index_finding", new_callable=AsyncMock
        ) as mock_index:
            await self.integration.create_host_entity(
                assessment_id="test-001", ip="10.0.0.1", status="up"
            )

            mock_index.assert_called_once()
            call_args = mock_index.call_args
            self.assertIn("host_test-001_10.0.0.1", call_args[0][0])
            self.assertIn("Host 10.0.0.1", call_args[0][1])
            self.assertEqual(call_args[0][2]["type"], "host")

    async def test_chromadb_failure_doesnt_break_flow(self):
        """Test ChromaDB errors are handled gracefully."""
        self.mock_memory_graph.create_entity = AsyncMock(
            return_value={"name": "Host: 10.0.0.1", "id": "123"}
        )
        self.mock_memory_graph.create_relation = AsyncMock(return_value=True)

        with patch.object(
            self.integration._findings_index,
            "index_finding",
            new_callable=AsyncMock,
            side_effect=Exception("ChromaDB connection failed"),
        ):
            result = await self.integration.create_host_entity(
                assessment_id="test-001", ip="10.0.0.1", status="up"
            )

            self.assertEqual(result["name"], "Host: 10.0.0.1")
            self.mock_memory_graph.create_entity.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
