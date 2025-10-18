"""
Comprehensive API Integration Tests for Infrastructure Management

Tests all 15 API endpoints with success/error paths, validation, and edge cases.
Target: 80%+ code coverage for production readiness.
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open
from datetime import datetime
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Mock missing external dependencies before importing anything that depends on them
sys.modules["celery"] = MagicMock()
sys.modules["backend.celery_app"] = MagicMock()
sys.modules["ansible_runner"] = MagicMock()
sys.modules["backend.services.ansible_executor"] = MagicMock()

from fastapi.testclient import TestClient
from backend.services.infrastructure_db import InfrastructureDB
from backend.models.infrastructure import InfraHost, InfraRole


# ==================== Test Fixtures ====================

@pytest.fixture
def test_db():
    """Fixture providing test database with temporary file"""
    test_db_path = '/tmp/test_infrastructure_api.db'
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = InfrastructureDB(db_path=test_db_path)
    yield db

    # Cleanup
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.fixture
def client(test_db):
    """Fixture providing FastAPI test client with mocked database and Celery"""
    # Mock Celery task
    mock_deploy_task = Mock()
    mock_deploy_task.delay = Mock(return_value=Mock(id='test-celery-task-12345'))

    with patch('backend.tasks.deployment_tasks.deploy_host', mock_deploy_task):
        with patch('backend.api.infrastructure.deploy_host', mock_deploy_task):
            with patch('backend.api.infrastructure.db', test_db):
                from backend.app_factory import create_app
                app = create_app()
                with TestClient(app) as test_client:
                    yield test_client


@pytest.fixture
def mock_ssh_provisioner():
    """Fixture providing mocked SSH provisioner"""
    with patch('backend.api.infrastructure.ssh_provisioner') as mock:
        mock.provision_key.return_value = (
            'test_private_key_content',  # Returns content, not path
            'ssh-rsa AAAAB3NzaC1yc2EA... autobot-provisioned-key@172.16.168.30'
        )
        yield mock


@pytest.fixture
def sample_host_data():
    """Fixture providing sample host data for testing"""
    return {
        "hostname": "test-frontend-01",
        "ip_address": "172.16.168.30",
        "role": "frontend",
        "ssh_port": 22,
        "ssh_user": "autobot"
    }


@pytest.fixture
def created_host(client, sample_host_data, test_db):
    """Fixture creating a test host and returning it"""
    # Create host directly via database
    frontend_role = test_db.get_role_by_name('frontend')
    host_data = {
        'hostname': sample_host_data['hostname'],
        'ip_address': sample_host_data['ip_address'],
        'role_id': frontend_role.id,
        'status': 'new',
        'ssh_port': sample_host_data['ssh_port'],
        'ssh_user': sample_host_data['ssh_user']
    }
    host = test_db.create_host(host_data)
    return host


# ==================== Host Management Endpoint Tests ====================

class TestHostManagement:
    """Test suite for host management endpoints"""

    def test_list_hosts_empty(self, client):
        """Test listing hosts when none exist"""
        response = client.get("/api/iac/hosts")
        assert response.status_code == 200
        data = response.json()
        assert 'hosts' in data
        assert isinstance(data['hosts'], list)
        assert len(data['hosts']) == 0

    def test_list_hosts_with_data(self, client, created_host):
        """Test listing hosts when hosts exist"""
        response = client.get("/api/iac/hosts")
        assert response.status_code == 200
        data = response.json()
        assert 'hosts' in data
        assert len(data['hosts']) == 1
        assert data['hosts'][0]['hostname'] == 'test-frontend-01'
        assert data['hosts'][0]['ip_address'] == '172.16.168.30'

    def test_list_hosts_with_role_filter(self, client, created_host, test_db):
        """Test filtering hosts by role"""
        # Create redis host
        redis_role = test_db.get_role_by_name('redis')
        redis_host_data = {
            'hostname': 'test-redis-01',
            'ip_address': '172.16.168.31',
            'role_id': redis_role.id,
            'status': 'new',
            'ssh_port': 22,
            'ssh_user': 'autobot'
        }
        test_db.create_host(redis_host_data)

        # Filter by frontend role
        response = client.get("/api/iac/hosts?role=frontend")
        assert response.status_code == 200
        data = response.json()
        assert len(data['hosts']) == 1
        assert data['hosts'][0]['hostname'] == 'test-frontend-01'

    def test_list_hosts_with_status_filter(self, client, created_host, test_db):
        """Test filtering hosts by status"""
        # Update host status
        test_db.update_host_status(created_host.id, 'deployed')

        response = client.get("/api/iac/hosts?status=deployed")
        assert response.status_code == 200
        data = response.json()
        assert len(data['hosts']) == 1
        assert data['hosts'][0]['status'] == 'deployed'

    def test_list_hosts_pagination(self, client, test_db):
        """Test pagination functionality"""
        # Create multiple hosts
        frontend_role = test_db.get_role_by_name('frontend')
        for i in range(5):
            host_data = {
                'hostname': f'test-host-{i:02d}',
                'ip_address': f'172.16.168.{30+i}',
                'role_id': frontend_role.id,
                'status': 'new',
                'ssh_port': 22,
                'ssh_user': 'autobot'
            }
            test_db.create_host(host_data)

        # Test pagination
        response = client.get("/api/iac/hosts?page=1&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data['hosts']) == 2
        assert 'pagination' in data
        assert data['pagination']['total'] == 5

    def test_create_host_with_password_auth(self, client):
        """Test creating host with password authentication"""
        # Use form data (multipart/form-data)
        form_data = {
            "hostname": "test-frontend-02",
            "ip_address": "172.16.168.32",
            "role": "frontend",
            "ssh_port": "22",
            "ssh_user": "autobot",
            "auth_method": "password",
            "password": "test_password_123"
        }

        response = client.post("/api/iac/hosts", data=form_data)
        assert response.status_code == 201
        data = response.json()
        assert data['hostname'] == "test-frontend-02"
        assert data['ip_address'] == "172.16.168.32"
        assert data['status'] == "new"
        assert 'id' in data

    def test_create_host_with_ssh_key(self, client):
        """Test creating host with SSH key authentication"""
        form_data = {
            "hostname": "test-redis-01",
            "ip_address": "172.16.168.33",
            "role": "redis",
            "ssh_port": "22",
            "ssh_user": "autobot",
            "auth_method": "key"
        }

        # Mock SSH key file
        key_content = b"-----BEGIN OPENSSH PRIVATE KEY-----\nTEST_KEY_DATA\n-----END OPENSSH PRIVATE KEY-----"
        files = {
            "key_file": ("test_key.pem", key_content, "application/octet-stream")
        }

        with patch('builtins.open', mock_open()):
            with patch('os.makedirs'):
                with patch('os.chmod'):
                    response = client.post("/api/iac/hosts", data=form_data, files=files)

        assert response.status_code == 201
        data = response.json()
        assert data['hostname'] == "test-redis-01"

    def test_create_host_nonexistent_role(self, client):
        """Test creating host with non-existent role"""
        form_data = {
            "hostname": "test-invalid-role",
            "ip_address": "172.16.168.34",
            "role": "nonexistent_role",
            "auth_method": "password",
            "password": "test123"
        }

        response = client.post("/api/iac/hosts", data=form_data)
        assert response.status_code == 404
        assert "not found" in response.json()['detail'].lower()

    def test_create_host_duplicate_ip(self, client, created_host):
        """Test creating host with duplicate IP address"""
        form_data = {
            "hostname": "test-duplicate",
            "ip_address": created_host.ip_address,  # Duplicate IP
            "role": "frontend",
            "auth_method": "password",
            "password": "test123"
        }

        response = client.post("/api/iac/hosts", data=form_data)
        assert response.status_code == 409
        assert "already exists" in response.json()['detail'].lower()

    def test_create_host_password_auth_missing_password(self, client):
        """Test creating host with password auth but no password"""
        form_data = {
            "hostname": "test-no-password",
            "ip_address": "172.16.168.35",
            "role": "frontend",
            "auth_method": "password"
            # Missing password field
        }

        response = client.post("/api/iac/hosts", data=form_data)
        assert response.status_code == 400
        assert "password" in response.json()['detail'].lower()

    def test_create_host_key_auth_missing_key(self, client):
        """Test creating host with key auth but no key file"""
        form_data = {
            "hostname": "test-no-key",
            "ip_address": "172.16.168.36",
            "role": "frontend",
            "auth_method": "key"
            # Missing key_file
        }

        response = client.post("/api/iac/hosts", data=form_data)
        assert response.status_code == 400
        assert "key" in response.json()['detail'].lower()

    def test_get_host_by_id(self, client, created_host):
        """Test retrieving specific host by ID"""
        response = client.get(f"/api/iac/hosts/{created_host.id}")
        assert response.status_code == 200
        data = response.json()
        assert data['id'] == created_host.id
        assert data['hostname'] == created_host.hostname
        assert data['ip_address'] == created_host.ip_address
        assert 'role_name' in data
        assert 'has_active_credential' in data
        assert 'deployment_count' in data

    def test_get_host_not_found(self, client):
        """Test 404 for non-existent host"""
        response = client.get("/api/iac/hosts/99999")
        assert response.status_code == 404
        assert "not found" in response.json()['detail'].lower()

    def test_update_host_status(self, client, created_host):
        """Test updating host status"""
        update_data = {
            "status": "deployed"
        }

        response = client.put(
            f"/api/iac/hosts/{created_host.id}",
            json=update_data
        )
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == "deployed"

    def test_update_host_not_found(self, client):
        """Test updating non-existent host"""
        update_data = {
            "hostname": "updated-name"
        }

        response = client.put("/api/iac/hosts/99999", json=update_data)
        assert response.status_code == 404

    def test_update_host_no_data(self, client, created_host):
        """Test updating host with no update data"""
        response = client.put(
            f"/api/iac/hosts/{created_host.id}",
            json={}
        )
        assert response.status_code == 400
        assert "no update data" in response.json()['detail'].lower()

    def test_delete_host(self, client, created_host, test_db):
        """Test host deletion with cascade"""
        host_id = created_host.id

        # Create some credentials and deployments to test cascade
        test_db.store_ssh_credential(
            host_id=host_id,
            credential_type='ssh_key',
            value='test_key_data'
        )
        test_db.create_deployment(
            host_id=host_id,
            role='frontend',
            status='queued'
        )

        # Delete host
        response = client.delete(f"/api/iac/hosts/{host_id}")
        assert response.status_code == 204

        # Verify deletion
        get_response = client.get(f"/api/iac/hosts/{host_id}")
        assert get_response.status_code == 404

        # Verify cascade (credentials and deployments should be deleted)
        deployments = test_db.get_deployments(host_id=host_id)
        assert len(deployments) == 0

    def test_delete_host_not_found(self, client):
        """Test deleting non-existent host"""
        response = client.delete("/api/iac/hosts/99999")
        assert response.status_code == 404

    def test_get_host_status_reachable(self, client, created_host):
        """Test getting host status when reachable"""
        with patch('backend.api.infrastructure.socket.socket') as mock_socket:
            mock_sock_instance = Mock()
            mock_sock_instance.connect_ex.return_value = 0  # Success
            mock_socket.return_value = mock_sock_instance

            response = client.get(f"/api/iac/hosts/{created_host.id}/status")

        assert response.status_code == 200
        data = response.json()
        assert data['host_id'] == created_host.id
        assert data['hostname'] == created_host.hostname
        assert 'is_reachable' in data
        assert 'response_time_ms' in data
        assert 'active_deployments' in data

    def test_get_host_status_not_found(self, client):
        """Test getting status for non-existent host"""
        response = client.get("/api/iac/hosts/99999/status")
        assert response.status_code == 404


# ==================== Deployment Management Endpoint Tests ====================

class TestDeploymentManagement:
    """Test suite for deployment management endpoints"""

    def test_create_deployment_single_host(self, client, created_host, test_db):
        """Test triggering deployment for single host"""
        # Store SSH key credential (required for deployment)
        test_db.store_ssh_credential(
            host_id=created_host.id,
            credential_type='ssh_key',
            value='test_ssh_key_data'
        )

        deployment_data = {
            "host_ids": [created_host.id],
            "force_redeploy": False
        }

        response = client.post("/api/iac/deployments", json=deployment_data)
        assert response.status_code == 202  # Accepted
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]['host_id'] == created_host.id
        assert data[0]['status'] == 'queued'

    def test_create_deployment_host_not_found(self, client):
        """Test deployment with non-existent host"""
        deployment_data = {
            "host_ids": [99999],
            "force_redeploy": False
        }

        response = client.post("/api/iac/deployments", json=deployment_data)
        assert response.status_code == 404
        assert "not found" in response.json()['detail'].lower()

    def test_create_deployment_no_ssh_key(self, client, created_host):
        """Test deployment without SSH key provisioned"""
        deployment_data = {
            "host_ids": [created_host.id],
            "force_redeploy": False
        }

        response = client.post("/api/iac/deployments", json=deployment_data)
        assert response.status_code == 400
        assert "ssh key" in response.json()['detail'].lower()

    def test_get_deployment_by_id(self, client, created_host, test_db):
        """Test retrieving deployment by ID"""
        # Create deployment
        deployment = test_db.create_deployment(
            host_id=created_host.id,
            role='frontend',
            status='success'
        )

        response = client.get(f"/api/iac/deployments/{deployment.id}")
        assert response.status_code == 200
        data = response.json()
        assert data['id'] == deployment.id
        assert data['host_id'] == created_host.id
        assert data['hostname'] == created_host.hostname
        assert data['ip_address'] == created_host.ip_address
        assert data['status'] == 'success'

    def test_get_deployment_not_found(self, client):
        """Test retrieving non-existent deployment"""
        response = client.get("/api/iac/deployments/99999")
        assert response.status_code == 404

    def test_list_deployments_all(self, client, created_host, test_db):
        """Test listing all deployments"""
        # Create multiple deployments
        for i in range(3):
            test_db.create_deployment(
                host_id=created_host.id,
                role='frontend',
                status='success' if i % 2 == 0 else 'failed'
            )

        response = client.get("/api/iac/deployments")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    def test_list_deployments_by_status(self, client, created_host, test_db):
        """Test filtering deployments by status"""
        # Create deployments with different statuses
        test_db.create_deployment(host_id=created_host.id, role='frontend', status='success')
        test_db.create_deployment(host_id=created_host.id, role='frontend', status='failed')
        test_db.create_deployment(host_id=created_host.id, role='frontend', status='running')

        # Filter by success
        response = client.get("/api/iac/deployments?status=success")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]['status'] == 'success'


# ==================== Credential Management Endpoint Tests ====================

class TestCredentialManagement:
    """Test suite for SSH credential management endpoints"""

    def test_provision_ssh_key_success(self, client, created_host, mock_ssh_provisioner):
        """Test successful SSH key provisioning"""
        provision_data = {
            "password": "test_password_123"
        }

        response = client.post(
            f"/api/iac/hosts/{created_host.id}/provision-key",
            json=provision_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['host_id'] == created_host.id
        assert 'message' in data
        assert 'public_key_fingerprint' in data

    def test_provision_ssh_key_host_not_found(self, client):
        """Test provisioning for non-existent host"""
        provision_data = {
            "password": "test_password_123"
        }

        response = client.post(
            "/api/iac/hosts/99999/provision-key",
            json=provision_data
        )
        assert response.status_code == 404

    def test_provision_ssh_key_invalid_password(self, client, created_host, mock_ssh_provisioner):
        """Test provisioning with wrong password"""
        # Mock SSH provisioner to raise authentication error
        mock_ssh_provisioner.provision_key.side_effect = Exception("Authentication failed")

        provision_data = {
            "password": "wrong_password"
        }

        response = client.post(
            f"/api/iac/hosts/{created_host.id}/provision-key",
            json=provision_data
        )
        assert response.status_code == 400
        assert "failed" in response.json()['detail'].lower()

    def test_provision_ssh_key_empty_password(self, client, created_host):
        """Test provisioning with empty password"""
        provision_data = {
            "password": ""
        }

        response = client.post(
            f"/api/iac/hosts/{created_host.id}/provision-key",
            json=provision_data
        )
        # Should fail validation
        assert response.status_code == 422  # Unprocessable Entity


# ==================== Supporting Endpoint Tests ====================

class TestSupportingEndpoints:
    """Test suite for supporting endpoints (roles, statistics, health)"""

    def test_list_roles(self, client):
        """Test listing all infrastructure roles"""
        response = client.get("/api/iac/roles")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 5  # Default roles

        # Verify role structure
        role_names = [r['name'] for r in data]
        assert 'frontend' in role_names
        assert 'redis' in role_names
        assert 'npu-worker' in role_names
        assert 'ai-stack' in role_names
        assert 'browser' in role_names

    def test_get_statistics(self, client, test_db):
        """Test retrieving infrastructure statistics"""
        # Create some test data
        frontend_role = test_db.get_role_by_name('frontend')

        # Create hosts
        for i in range(3):
            host_data = {
                'hostname': f'stats-host-{i}',
                'ip_address': f'172.16.168.{60+i}',
                'role_id': frontend_role.id,
                'status': 'deployed' if i % 2 == 0 else 'new',
                'ssh_port': 22,
                'ssh_user': 'autobot'
            }
            host = test_db.create_host(host_data)

            # Create deployments
            test_db.create_deployment(
                host_id=host.id,
                role='frontend',
                status='success' if i % 2 == 0 else 'failed'
            )

            # Create credentials
            test_db.store_ssh_credential(
                host_id=host.id,
                credential_type='ssh_key',
                value='test_key'
            )

        response = client.get("/api/iac/statistics")
        assert response.status_code == 200
        data = response.json()

        assert 'total_hosts' in data
        assert data['total_hosts'] == 3

        assert 'total_roles' in data
        assert data['total_roles'] == 5

        assert 'total_deployments' in data
        assert data['total_deployments'] == 3

    def test_health_check_healthy(self, client):
        """Test health check when service is healthy"""
        response = client.get("/api/iac/health")
        assert response.status_code == 200
        data = response.json()

        assert data['status'] == 'healthy'
        assert data['service'] == 'infrastructure_api'
        assert 'timestamp' in data
        assert 'database' in data
        assert data['database'] == 'connected'


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
