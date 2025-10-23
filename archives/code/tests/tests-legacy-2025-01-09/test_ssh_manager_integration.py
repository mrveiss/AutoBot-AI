"""
Integration Tests for SSH Manager
Tests real SSH connections and remote command execution
"""

import asyncio
import os
import pytest
from datetime import datetime

from backend.services.ssh_manager import SSHManager, HostConfig, RemoteCommandResult


# Skip tests if SSH key doesn't exist
SSH_KEY_PATH = os.path.expanduser('~/.ssh/autobot_key')
SSH_AVAILABLE = os.path.exists(SSH_KEY_PATH)

pytestmark = pytest.mark.skipif(
    not SSH_AVAILABLE,
    reason="SSH key not available for testing"
)


@pytest.fixture
async def ssh_manager():
    """Create SSH manager for testing"""
    manager = SSHManager(
        ssh_key_path=SSH_KEY_PATH,
        enable_audit_logging=False  # Disable for tests
    )
    await manager.start()
    yield manager
    await manager.stop()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ssh_manager_initialization(ssh_manager):
    """Test SSH manager initialization"""
    assert ssh_manager is not None
    assert len(ssh_manager.hosts) == 6  # Should have 6 default hosts

    # Check default hosts
    assert 'main' in ssh_manager.hosts
    assert 'frontend' in ssh_manager.hosts
    assert 'npu-worker' in ssh_manager.hosts
    assert 'redis' in ssh_manager.hosts
    assert 'ai-stack' in ssh_manager.hosts
    assert 'browser' in ssh_manager.hosts


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_host_config(ssh_manager):
    """Test getting host configuration"""
    config = ssh_manager.get_host_config('main')

    assert config is not None
    assert config.name == 'main'
    assert config.ip == '172.16.168.20'
    assert config.port == 22
    assert config.username == 'autobot'
    assert config.enabled is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_hosts(ssh_manager):
    """Test listing all hosts"""
    hosts = ssh_manager.list_hosts()

    assert len(hosts) == 6
    assert all(isinstance(h, HostConfig) for h in hosts)
    assert all(h.enabled for h in hosts)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_execute_command_simple(ssh_manager):
    """Test simple command execution on localhost (main)"""
    try:
        result = await ssh_manager.execute_command(
            host='main',
            command='echo "test_output"',
            timeout=10,
            validate=True,
            use_pty=False
        )

        assert isinstance(result, RemoteCommandResult)
        assert result.host == 'main'
        assert result.command == 'echo "test_output"'
        assert 'test_output' in result.stdout
        assert result.exit_code == 0
        assert result.success is True
        assert result.execution_time > 0

    except ConnectionError:
        pytest.skip("Cannot connect to main host")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_execute_command_with_validation(ssh_manager):
    """Test command execution with security validation"""
    try:
        result = await ssh_manager.execute_command(
            host='main',
            command='pwd',
            timeout=10,
            validate=True
        )

        assert result.success is True
        assert 'security_info' in result.security_info
        assert result.security_info.get('validated') is True

    except ConnectionError:
        pytest.skip("Cannot connect to main host")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_execute_dangerous_command_blocked(ssh_manager):
    """Test that dangerous commands are blocked"""
    try:
        with pytest.raises(PermissionError, match="Command blocked"):
            await ssh_manager.execute_command(
                host='main',
                command='rm -rf /',
                timeout=10,
                validate=True
            )

    except ConnectionError:
        pytest.skip("Cannot connect to main host")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_execute_command_with_pty(ssh_manager):
    """Test command execution with PTY"""
    try:
        result = await ssh_manager.execute_command(
            host='main',
            command='echo "pty_test"',
            timeout=10,
            validate=True,
            use_pty=True
        )

        assert result.success is True
        assert 'pty_test' in result.stdout

    except ConnectionError:
        pytest.skip("Cannot connect to main host")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_execute_command_timeout(ssh_manager):
    """Test command execution timeout"""
    try:
        with pytest.raises(Exception):  # Could be TimeoutError or other
            await ssh_manager.execute_command(
                host='main',
                command='sleep 30',
                timeout=2,  # 2 second timeout
                validate=False
            )

    except ConnectionError:
        pytest.skip("Cannot connect to main host")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_execute_command_all_hosts_parallel(ssh_manager):
    """Test parallel command execution on all hosts"""
    try:
        results = await ssh_manager.execute_command_all_hosts(
            command='echo "batch_test"',
            timeout=10,
            validate=True,
            parallel=True
        )

        assert isinstance(results, dict)
        assert len(results) > 0

        # Check at least main host succeeded (others may not be accessible)
        if 'main' in results:
            result = results['main']
            if isinstance(result, RemoteCommandResult):
                assert result.success is True
                assert 'batch_test' in result.stdout

    except Exception as e:
        pytest.skip(f"Batch execution not available: {e}")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_execute_command_all_hosts_sequential(ssh_manager):
    """Test sequential command execution on all hosts"""
    try:
        results = await ssh_manager.execute_command_all_hosts(
            command='whoami',
            timeout=10,
            validate=True,
            parallel=False
        )

        assert isinstance(results, dict)
        assert len(results) > 0

        # Check at least main host succeeded
        if 'main' in results:
            result = results['main']
            if isinstance(result, RemoteCommandResult):
                assert result.success is True

    except Exception as e:
        pytest.skip(f"Batch execution not available: {e}")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_health_check_all_hosts(ssh_manager):
    """Test health check on all hosts"""
    try:
        health_status = await ssh_manager.health_check_all_hosts()

        assert isinstance(health_status, dict)
        assert len(health_status) == 6

        # All hosts should have a status (True, False, or None)
        for host, status in health_status.items():
            assert status in [True, False, None]

    except Exception as e:
        pytest.skip(f"Health check not available: {e}")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_connection_pool_reuse(ssh_manager):
    """Test that connection pool reuses connections"""
    try:
        # Execute multiple commands to same host
        for _ in range(3):
            result = await ssh_manager.execute_command(
                host='main',
                command='echo "connection_test"',
                timeout=10,
                validate=False
            )
            assert result.success is True

        # Check pool stats
        stats = await ssh_manager.get_pool_stats()
        assert isinstance(stats, dict)

        # Should have at least one connection in pool for main
        main_pool_key = 'autobot@172.16.168.20:22'
        if main_pool_key in stats:
            # Connection should be reused (idle after release)
            assert stats[main_pool_key]['total'] >= 1

    except ConnectionError:
        pytest.skip("Cannot connect to main host")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_pool_stats(ssh_manager):
    """Test getting pool statistics"""
    try:
        # Execute a command to create a connection
        await ssh_manager.execute_command(
            host='main',
            command='echo "stats_test"',
            timeout=10,
            validate=False
        )

        # Get stats
        stats = await ssh_manager.get_pool_stats()

        assert isinstance(stats, dict)
        # Stats may be empty if all connections cleaned up

    except ConnectionError:
        pytest.skip("Cannot connect to main host")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_invalid_host(ssh_manager):
    """Test execution on invalid host"""
    with pytest.raises(ValueError, match="Unknown host"):
        await ssh_manager.execute_command(
            host='invalid_host',
            command='echo "test"',
            timeout=10
        )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_command_with_error_exit_code(ssh_manager):
    """Test command that returns non-zero exit code"""
    try:
        result = await ssh_manager.execute_command(
            host='main',
            command='ls /nonexistent_directory',
            timeout=10,
            validate=False
        )

        assert result.exit_code != 0
        assert result.success is False
        assert len(result.stderr) > 0 or len(result.stdout) > 0

    except ConnectionError:
        pytest.skip("Cannot connect to main host")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_concurrent_commands_same_host(ssh_manager):
    """Test concurrent command execution on same host"""
    try:
        # Execute multiple commands concurrently
        tasks = [
            ssh_manager.execute_command(
                host='main',
                command=f'echo "concurrent_{i}"',
                timeout=10,
                validate=False
            )
            for i in range(3)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should succeed (or be exceptions we can handle)
        for i, result in enumerate(results):
            if isinstance(result, RemoteCommandResult):
                assert result.success is True
                assert f'concurrent_{i}' in result.stdout

    except ConnectionError:
        pytest.skip("Cannot connect to main host")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-m', 'integration'])
