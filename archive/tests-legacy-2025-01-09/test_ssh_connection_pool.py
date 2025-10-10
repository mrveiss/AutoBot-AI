"""
Unit Tests for SSH Connection Pool
Tests connection pooling, health checks, and timeout management
"""

import asyncio
import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from backend.services.ssh_connection_pool import (
    SSHConnectionPool,
    SSHConnection,
    ConnectionState
)


@pytest.fixture
def connection_pool():
    """Create SSH connection pool for testing"""
    pool = SSHConnectionPool(
        max_connections_per_host=3,
        connect_timeout=5,
        idle_timeout=10,
        health_check_interval=5,
        retry_max_attempts=2,
        retry_base_delay=0.1
    )
    return pool


@pytest.fixture
async def started_pool(connection_pool):
    """Create and start connection pool"""
    await connection_pool.start()
    yield connection_pool
    await connection_pool.stop()


@pytest.mark.asyncio
async def test_pool_initialization(connection_pool):
    """Test connection pool initialization"""
    assert connection_pool.max_connections_per_host == 3
    assert connection_pool.connect_timeout == 5
    assert connection_pool.idle_timeout == 10
    assert connection_pool.health_check_interval == 5
    assert connection_pool.pools == {}
    assert connection_pool._running is False


@pytest.mark.asyncio
async def test_pool_start_stop(connection_pool):
    """Test starting and stopping the pool"""
    assert connection_pool._running is False

    await connection_pool.start()
    assert connection_pool._running is True
    assert connection_pool._health_check_task is not None

    await connection_pool.stop()
    assert connection_pool._running is False


@pytest.mark.asyncio
@patch('paramiko.SSHClient')
@patch('paramiko.RSAKey.from_private_key_file')
async def test_create_connection_success(mock_key, mock_ssh_client, connection_pool):
    """Test successful SSH connection creation"""
    # Mock SSH key
    mock_key.return_value = Mock()

    # Mock SSH client
    mock_client = Mock()
    mock_ssh_client.return_value = mock_client

    # Create temporary key file for testing
    key_path = '/tmp/test_autobot_key'
    with open(key_path, 'w') as f:
        f.write('test_key_content')

    try:
        client = await connection_pool._create_connection(
            host='172.16.168.21',
            port=22,
            username='autobot',
            key_path=key_path,
            passphrase=None
        )

        assert client == mock_client
        mock_client.connect.assert_called_once()

    finally:
        if os.path.exists(key_path):
            os.remove(key_path)


@pytest.mark.asyncio
@patch('paramiko.SSHClient')
async def test_create_connection_retry(mock_ssh_client, connection_pool):
    """Test connection retry with exponential backoff"""
    mock_client = Mock()
    mock_ssh_client.return_value = mock_client

    # First attempt fails, second succeeds
    mock_client.connect.side_effect = [ConnectionError("Failed"), None]

    # Create temporary key file
    key_path = '/tmp/test_autobot_key'
    with open(key_path, 'w') as f:
        f.write('test_key_content')

    try:
        with patch('paramiko.RSAKey.from_private_key_file') as mock_key:
            mock_key.return_value = Mock()

            client = await connection_pool._create_connection(
                host='172.16.168.21',
                port=22,
                username='autobot',
                key_path=key_path,
                passphrase=None
            )

            assert client == mock_client
            assert mock_client.connect.call_count == 2

    finally:
        if os.path.exists(key_path):
            os.remove(key_path)


@pytest.mark.asyncio
async def test_pool_key_generation(connection_pool):
    """Test pool key generation"""
    key1 = connection_pool._get_pool_key('172.16.168.21', 22, 'autobot')
    key2 = connection_pool._get_pool_key('172.16.168.22', 22, 'autobot')
    key3 = connection_pool._get_pool_key('172.16.168.21', 22, 'autobot')

    assert key1 == key3
    assert key1 != key2
    assert key1 == 'autobot@172.16.168.21:22'


@pytest.mark.asyncio
@patch('backend.services.ssh_connection_pool.SSHConnectionPool._create_connection')
async def test_get_connection_creates_new(mock_create, connection_pool):
    """Test getting connection creates new one when pool is empty"""
    mock_client = Mock()
    mock_create.return_value = mock_client

    # Create temporary key file
    key_path = '/tmp/test_autobot_key'
    with open(key_path, 'w') as f:
        f.write('test_key_content')

    try:
        client = await connection_pool.get_connection(
            host='172.16.168.21',
            port=22,
            username='autobot',
            key_path=key_path
        )

        assert client == mock_client
        mock_create.assert_called_once()

        # Check pool has connection
        pool_key = 'autobot@172.16.168.21:22'
        assert pool_key in connection_pool.pools
        assert len(connection_pool.pools[pool_key]) == 1

    finally:
        await connection_pool.cleanup_all()
        if os.path.exists(key_path):
            os.remove(key_path)


@pytest.mark.asyncio
@patch('backend.services.ssh_connection_pool.SSHConnectionPool._create_connection')
@patch('backend.services.ssh_connection_pool.SSHConnectionPool._check_connection_health')
async def test_get_connection_reuses_idle(mock_health, mock_create, connection_pool):
    """Test getting connection reuses idle healthy connection"""
    mock_client = Mock()
    mock_create.return_value = mock_client
    mock_health.return_value = True

    key_path = '/tmp/test_autobot_key'
    with open(key_path, 'w') as f:
        f.write('test_key_content')

    try:
        # Get first connection
        client1 = await connection_pool.get_connection(
            host='172.16.168.21',
            port=22,
            username='autobot',
            key_path=key_path
        )

        # Release it back to pool
        await connection_pool.release_connection(
            client1,
            host='172.16.168.21',
            port=22,
            username='autobot'
        )

        # Get second connection - should reuse
        client2 = await connection_pool.get_connection(
            host='172.16.168.21',
            port=22,
            username='autobot',
            key_path=key_path
        )

        assert client2 == client1
        assert mock_create.call_count == 1  # Only created once

    finally:
        await connection_pool.cleanup_all()
        if os.path.exists(key_path):
            os.remove(key_path)


@pytest.mark.asyncio
@patch('backend.services.ssh_connection_pool.SSHConnectionPool._create_connection')
async def test_connection_pool_limit(mock_create, connection_pool):
    """Test connection pool respects max connections limit"""
    mock_create.side_effect = [Mock() for _ in range(10)]

    key_path = '/tmp/test_autobot_key'
    with open(key_path, 'w') as f:
        f.write('test_key_content')

    try:
        # Get max connections (3 in test config)
        clients = []
        for _ in range(3):
            client = await connection_pool.get_connection(
                host='172.16.168.21',
                port=22,
                username='autobot',
                key_path=key_path
            )
            clients.append(client)

        # Try to get one more - should fail
        with pytest.raises(ConnectionError, match="Connection pool exhausted"):
            await connection_pool.get_connection(
                host='172.16.168.21',
                port=22,
                username='autobot',
                key_path=key_path
            )

    finally:
        await connection_pool.cleanup_all()
        if os.path.exists(key_path):
            os.remove(key_path)


@pytest.mark.asyncio
async def test_connection_health_check():
    """Test connection health check"""
    mock_client = Mock()
    mock_transport = Mock()
    mock_transport.is_active.return_value = True

    mock_client.get_transport.return_value = mock_transport
    mock_client.exec_command.return_value = (
        Mock(),  # stdin
        Mock(read=Mock(return_value=b'health_check')),  # stdout
        Mock()   # stderr
    )

    conn = SSHConnection(
        client=mock_client,
        host='172.16.168.21',
        port=22,
        username='autobot',
        state=ConnectionState.IDLE,
        created_at=datetime.now(),
        last_used=datetime.now(),
        last_health_check=datetime.now(),
        use_count=1
    )

    pool = SSHConnectionPool()
    result = await pool._check_connection_health(conn)

    assert result is True
    assert conn.state == ConnectionState.IDLE


@pytest.mark.asyncio
async def test_idle_timeout():
    """Test idle timeout detection"""
    conn = SSHConnection(
        client=Mock(),
        host='172.16.168.21',
        port=22,
        username='autobot',
        state=ConnectionState.IDLE,
        created_at=datetime.now(),
        last_used=datetime.now() - timedelta(seconds=400),
        last_health_check=datetime.now(),
        use_count=1
    )

    # Should be idle timeout with 300s limit
    assert conn.is_idle_timeout(idle_timeout=300) is True

    # Should not be idle timeout with 500s limit
    assert conn.is_idle_timeout(idle_timeout=500) is False


@pytest.mark.asyncio
async def test_needs_health_check():
    """Test health check interval detection"""
    conn = SSHConnection(
        client=Mock(),
        host='172.16.168.21',
        port=22,
        username='autobot',
        state=ConnectionState.IDLE,
        created_at=datetime.now(),
        last_used=datetime.now(),
        last_health_check=datetime.now() - timedelta(seconds=70),
        use_count=1
    )

    # Should need health check with 60s interval
    assert conn.needs_health_check(check_interval=60) is True

    # Should not need health check with 80s interval
    assert conn.needs_health_check(check_interval=80) is False


@pytest.mark.asyncio
async def test_pool_stats(connection_pool):
    """Test pool statistics"""
    # Add some mock connections
    pool_key = 'autobot@172.16.168.21:22'
    connection_pool.pools[pool_key] = [
        SSHConnection(
            client=Mock(),
            host='172.16.168.21',
            port=22,
            username='autobot',
            state=ConnectionState.IDLE,
            created_at=datetime.now(),
            last_used=datetime.now(),
            last_health_check=datetime.now(),
            use_count=1
        ),
        SSHConnection(
            client=Mock(),
            host='172.16.168.21',
            port=22,
            username='autobot',
            state=ConnectionState.ACTIVE,
            created_at=datetime.now(),
            last_used=datetime.now(),
            last_health_check=datetime.now(),
            use_count=2
        )
    ]

    stats = await connection_pool.get_pool_stats()

    assert pool_key in stats
    assert stats[pool_key]['total'] == 2
    assert stats[pool_key]['idle'] == 1
    assert stats[pool_key]['active'] == 1
    assert stats[pool_key]['unhealthy'] == 0


@pytest.mark.asyncio
async def test_cleanup_all(connection_pool):
    """Test cleanup all connections"""
    # Add mock connections
    mock_client1 = Mock()
    mock_client2 = Mock()

    pool_key = 'autobot@172.16.168.21:22'
    connection_pool.pools[pool_key] = [
        SSHConnection(
            client=mock_client1,
            host='172.16.168.21',
            port=22,
            username='autobot',
            state=ConnectionState.IDLE,
            created_at=datetime.now(),
            last_used=datetime.now(),
            last_health_check=datetime.now(),
            use_count=1
        ),
        SSHConnection(
            client=mock_client2,
            host='172.16.168.21',
            port=22,
            username='autobot',
            state=ConnectionState.ACTIVE,
            created_at=datetime.now(),
            last_used=datetime.now(),
            last_health_check=datetime.now(),
            use_count=1
        )
    ]

    await connection_pool.cleanup_all()

    # All connections should be closed
    mock_client1.close.assert_called_once()
    mock_client2.close.assert_called_once()

    # Pools should be cleared
    assert connection_pool.pools == {}
