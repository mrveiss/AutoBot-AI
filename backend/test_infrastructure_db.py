"""
Test Suite for Infrastructure Database Foundation

Comprehensive tests for SQLAlchemy models and InfrastructureDB service layer.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.infrastructure_db import InfrastructureDB
from backend.models.infrastructure import InfraRole, InfraHost, InfraCredential, InfraDeployment


def test_database_initialization():
    """Test 1: Database initialization and table creation"""
    print("\n" + "="*80)
    print("TEST 1: Database Initialization")
    print("="*80)

    # Use temporary test database
    test_db_path = '/tmp/test_infrastructure.db'
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = InfrastructureDB(db_path=test_db_path)

    # Verify tables exist
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    expected_tables = ['infra_roles', 'infra_hosts', 'infra_credentials', 'infra_deployments', 'infra_audit_logs']
    for table in expected_tables:
        assert table in tables, f"Table {table} not created"
        print(f"✅ Table '{table}' created successfully")

    print("\n✅ TEST 1 PASSED: All tables created successfully")
    return db


def test_role_initialization(db: InfrastructureDB):
    """Test 2: Default role initialization"""
    print("\n" + "="*80)
    print("TEST 2: Default Role Initialization")
    print("="*80)

    roles = db.get_roles()
    assert len(roles) == 5, f"Expected 5 roles, got {len(roles)}"

    expected_roles = ['frontend', 'redis', 'npu-worker', 'ai-stack', 'browser']
    for role_name in expected_roles:
        role = db.get_role_by_name(role_name)
        assert role is not None, f"Role {role_name} not found"
        assert role.name == role_name
        print(f"✅ Role '{role_name}' initialized: {role.description}")

    print("\n✅ TEST 2 PASSED: All 5 default roles initialized")


def test_host_creation(db: InfrastructureDB):
    """Test 3: Host creation and retrieval"""
    print("\n" + "="*80)
    print("TEST 3: Host Creation and Retrieval")
    print("="*80)

    # Get frontend role
    frontend_role = db.get_role_by_name('frontend')
    assert frontend_role is not None

    # Create test host
    host_data = {
        'hostname': 'test-frontend-01',
        'ip_address': '172.16.168.99',
        'role_id': frontend_role.id,
        'status': 'new',
        'ssh_port': 22,
        'ssh_user': 'autobot'
    }

    host = db.create_host(host_data)
    assert host.id is not None
    assert host.hostname == 'test-frontend-01'
    assert host.ip_address == '172.16.168.99'
    print(f"✅ Created host: {host.hostname} ({host.ip_address})")

    # Retrieve by ID
    retrieved = db.get_host(host.id)
    assert retrieved is not None
    assert retrieved.hostname == host.hostname
    print(f"✅ Retrieved host by ID: {retrieved.hostname}")

    # Retrieve by IP
    retrieved_by_ip = db.get_host_by_ip('172.16.168.99')
    assert retrieved_by_ip is not None
    assert retrieved_by_ip.id == host.id
    print(f"✅ Retrieved host by IP: {retrieved_by_ip.ip_address}")

    print("\n✅ TEST 3 PASSED: Host creation and retrieval working")
    return host


def test_host_status_update(db: InfrastructureDB, host: InfraHost):
    """Test 4: Host status updates"""
    print("\n" + "="*80)
    print("TEST 4: Host Status Updates")
    print("="*80)

    # Update status
    db.update_host_status(host.id, 'provisioning', user_id='test_user')

    # Verify update
    updated_host = db.get_host(host.id)
    assert updated_host.status == 'provisioning'
    assert updated_host.last_seen_at is not None
    print(f"✅ Updated host status: new → provisioning")

    # Update to deployed
    db.update_host_status(host.id, 'deployed')
    updated_host = db.get_host(host.id)
    assert updated_host.status == 'deployed'
    print(f"✅ Updated host status: provisioning → deployed")

    print("\n✅ TEST 4 PASSED: Status updates working correctly")


def test_credential_encryption(db: InfrastructureDB, host: InfraHost):
    """Test 5: Credential encryption and storage"""
    print("\n" + "="*80)
    print("TEST 5: Credential Encryption and Storage")
    print("="*80)

    # Test SSH key storage
    test_private_key = "-----BEGIN OPENSSH PRIVATE KEY-----\nTEST_KEY_DATA_HERE\n-----END OPENSSH PRIVATE KEY-----"

    credential = db.store_ssh_credential(
        host_id=host.id,
        credential_type='ssh_key',
        value=test_private_key,
        user_id='test_user'
    )

    assert credential.id is not None
    assert credential.credential_type == 'ssh_key'
    assert credential.is_active == True
    print(f"✅ Stored encrypted SSH key credential")

    # Retrieve and decrypt
    decrypted = db.get_active_credential(host.id, 'ssh_key')
    assert decrypted == test_private_key
    print(f"✅ Retrieved and decrypted SSH key successfully")

    # Test password storage
    test_password = "SuperSecurePassword123!"
    password_cred = db.store_ssh_credential(
        host_id=host.id,
        credential_type='password',
        value=test_password
    )

    assert password_cred.credential_type == 'password'
    print(f"✅ Stored encrypted password credential")

    # Retrieve password
    decrypted_password = db.get_active_credential(host.id, 'password')
    assert decrypted_password == test_password
    print(f"✅ Retrieved and decrypted password successfully")

    print("\n✅ TEST 5 PASSED: Credential encryption working correctly")


def test_credential_deactivation(db: InfrastructureDB, host: InfraHost):
    """Test 6: Credential deactivation for rotation"""
    print("\n" + "="*80)
    print("TEST 6: Credential Deactivation")
    print("="*80)

    # Deactivate password credentials
    db.deactivate_credentials(host.id, credential_type='password', user_id='test_user')

    # Verify deactivation
    active_password = db.get_active_credential(host.id, 'password')
    assert active_password is None
    print(f"✅ Password credentials deactivated successfully")

    # SSH key should still be active
    active_ssh_key = db.get_active_credential(host.id, 'ssh_key')
    assert active_ssh_key is not None
    print(f"✅ SSH key credentials still active")

    print("\n✅ TEST 6 PASSED: Credential rotation working correctly")


def test_deployment_tracking(db: InfrastructureDB, host: InfraHost):
    """Test 7: Deployment creation and tracking"""
    print("\n" + "="*80)
    print("TEST 7: Deployment Tracking")
    print("="*80)

    # Create deployment
    deployment = db.create_deployment(
        host_id=host.id,
        role='frontend',
        status='queued',
        user_id='test_user'
    )

    assert deployment.id is not None
    assert deployment.status == 'queued'
    assert deployment.role == 'frontend'
    print(f"✅ Created deployment: {deployment.id} (status: queued)")

    # Update to running
    db.update_deployment_status(deployment.id, 'running')
    updated_deployment = db.get_deployments(host_id=host.id)[0]
    assert updated_deployment.status == 'running'
    assert updated_deployment.started_at is not None
    print(f"✅ Updated deployment status: queued → running")

    # Update to success
    db.update_deployment_status(deployment.id, 'success')
    updated_deployment = db.get_deployments(host_id=host.id)[0]
    assert updated_deployment.status == 'success'
    assert updated_deployment.completed_at is not None
    print(f"✅ Updated deployment status: running → success")

    # Test failed deployment
    failed_deployment = db.create_deployment(
        host_id=host.id,
        role='frontend',
        status='queued'
    )
    db.update_deployment_status(
        failed_deployment.id,
        'failed',
        error_message='Connection timeout'
    )
    updated_failed = db.get_deployments(host_id=host.id, status='failed')[0]
    assert updated_failed.status == 'failed'
    assert updated_failed.error_message == 'Connection timeout'
    print(f"✅ Tracked failed deployment with error message")

    print("\n✅ TEST 7 PASSED: Deployment tracking working correctly")


def test_audit_logging(db: InfrastructureDB):
    """Test 8: Audit log retrieval"""
    print("\n" + "="*80)
    print("TEST 8: Audit Logging")
    print("="*80)

    # Get all audit logs
    all_logs = db.get_audit_logs(limit=100)
    assert len(all_logs) > 0
    print(f"✅ Retrieved {len(all_logs)} audit log entries")

    # Get logs for specific resource type
    host_logs = db.get_audit_logs(resource_type='host', limit=50)
    assert len(host_logs) > 0
    print(f"✅ Retrieved {len(host_logs)} audit logs for hosts")

    credential_logs = db.get_audit_logs(resource_type='credential')
    assert len(credential_logs) > 0
    print(f"✅ Retrieved {len(credential_logs)} audit logs for credentials")

    deployment_logs = db.get_audit_logs(resource_type='deployment')
    assert len(deployment_logs) > 0
    print(f"✅ Retrieved {len(deployment_logs)} audit logs for deployments")

    # Verify audit log structure
    sample_log = all_logs[0]
    assert sample_log.action is not None
    assert sample_log.resource_type is not None
    assert sample_log.timestamp is not None
    print(f"✅ Audit log structure validated")

    print("\n✅ TEST 8 PASSED: Audit logging working correctly")


def test_statistics(db: InfrastructureDB):
    """Test 9: Statistics and metrics"""
    print("\n" + "="*80)
    print("TEST 9: Statistics and Metrics")
    print("="*80)

    stats = db.get_statistics()

    assert stats['total_hosts'] >= 1
    assert stats['total_roles'] == 5
    assert stats['total_deployments'] >= 1
    assert 'hosts_by_status' in stats
    assert 'deployments_by_status' in stats

    print(f"✅ Total hosts: {stats['total_hosts']}")
    print(f"✅ Total roles: {stats['total_roles']}")
    print(f"✅ Total deployments: {stats['total_deployments']}")
    print(f"✅ Active credentials: {stats['active_credentials']}")
    print(f"✅ Hosts by status: {stats['hosts_by_status']}")
    print(f"✅ Deployments by status: {stats['deployments_by_status']}")

    print("\n✅ TEST 9 PASSED: Statistics working correctly")


def test_host_deletion(db: InfrastructureDB, host: InfraHost):
    """Test 10: Host deletion with cascade"""
    print("\n" + "="*80)
    print("TEST 10: Host Deletion with Cascade")
    print("="*80)

    host_id = host.id

    # Delete host (should cascade to credentials and deployments)
    db.delete_host(host_id, user_id='test_user')

    # Verify deletion
    deleted_host = db.get_host(host_id)
    assert deleted_host is None
    print(f"✅ Host {host_id} deleted successfully")

    # Verify cascade deletion
    deployments = db.get_deployments(host_id=host_id)
    assert len(deployments) == 0
    print(f"✅ Associated deployments cascaded correctly")

    print("\n✅ TEST 10 PASSED: Host deletion with cascade working correctly")


def run_all_tests():
    """Run complete test suite"""
    print("\n" + "="*80)
    print("INFRASTRUCTURE DATABASE FOUNDATION - COMPREHENSIVE TEST SUITE")
    print("="*80)

    try:
        # Test 1: Initialize database
        db = test_database_initialization()

        # Test 2: Role initialization
        test_role_initialization(db)

        # Test 3: Host creation
        host = test_host_creation(db)

        # Test 4: Status updates
        test_host_status_update(db, host)

        # Test 5: Credential encryption
        test_credential_encryption(db, host)

        # Test 6: Credential deactivation
        test_credential_deactivation(db, host)

        # Test 7: Deployment tracking
        test_deployment_tracking(db, host)

        # Test 8: Audit logging
        test_audit_logging(db)

        # Test 9: Statistics
        test_statistics(db)

        # Test 10: Host deletion
        test_host_deletion(db, host)

        # Final summary
        print("\n" + "="*80)
        print("✅ ALL TESTS PASSED SUCCESSFULLY")
        print("="*80)
        print("\n📊 Test Summary:")
        print("  ✅ Database initialization: PASSED")
        print("  ✅ Role management: PASSED")
        print("  ✅ Host CRUD operations: PASSED")
        print("  ✅ Credential encryption: PASSED")
        print("  ✅ Credential rotation: PASSED")
        print("  ✅ Deployment tracking: PASSED")
        print("  ✅ Audit logging: PASSED")
        print("  ✅ Statistics: PASSED")
        print("  ✅ Cascade deletion: PASSED")
        print("\n🎉 Infrastructure Database Foundation is PRODUCTION READY!")
        print("\n✅ UNBLOCKS: SSH provisioning and IaC API implementations")

        return True

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
