"""
Redis Immediate Connection Test - No Timeouts
Replaces timeout-based Redis connection with immediate success/failure patterns
"""

import asyncio
import logging
import redis
from typing import Dict, Any, Optional, Tuple
from contextlib import asynccontextmanager
from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)

class RedisConnectionState:
    """Track Redis connection state without timeouts"""
    
    def __init__(self):
        self.is_connected = False
        self.client: Optional[redis.Redis] = None
        self.last_error: Optional[str] = None
        self.connection_params: Dict[str, Any] = {}
        
    def mark_connected(self, client: redis.Redis, params: Dict[str, Any]):
        """Mark as successfully connected"""
        self.is_connected = True
        self.client = client
        self.connection_params = params
        self.last_error = None
        
    def mark_disconnected(self, error: str):
        """Mark as disconnected with error"""
        self.is_connected = False
        self.client = None
        self.last_error = error

@asynccontextmanager
async def immediate_redis_test(host: str, port: int, db: int = 0):
    """
    Test Redis connection immediately - no timeout waits.
    Either succeeds instantly or fails instantly.
    """
    connection_state = RedisConnectionState()
    
    try:
        # Create connection with no timeout parameters
        # If Redis is reachable, connection is immediate
        # If unreachable, fails immediately
        client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
            socket_keepalive=True,
            socket_keepalive_options={},
            retry_on_timeout=False,
            health_check_interval=0,  # No background health checks
            socket_connect_timeout=None,  # No timeout - immediate fail/success
            socket_timeout=None,  # No timeout - immediate fail/success
        )
        
        # Try immediate PING - either works or doesn't
        # Use thread pool to prevent blocking event loop
        ping_result = await asyncio.to_thread(client.ping)
        
        if ping_result:
            logger.info(f"✅ Redis immediate connection SUCCESS: {host}:{port}")
            connection_state.mark_connected(client, {
                'host': host, 
                'port': port, 
                'db': db
            })
            yield connection_state
        else:
            raise redis.ConnectionError("PING returned False")
            
    except Exception as e:
        error_msg = f"Redis immediate connection FAILED: {host}:{port} - {str(e)}"
        logger.warning(f"⚠️ {error_msg}")
        connection_state.mark_disconnected(error_msg)
        yield connection_state
    finally:
        # Cleanup connection if it exists
        if connection_state.client:
            try:
                await asyncio.to_thread(connection_state.client.close)
            except Exception:
                pass  # Ignore cleanup errors

async def create_redis_with_fallback(
    primary_config: Dict[str, Any], 
    fallback_configs: Optional[list] = None
) -> Tuple[Optional[redis.Redis], str]:
    """
    Create Redis connection with immediate fallback testing.
    No timeouts - tries each config immediately.
    
    Returns:
        Tuple of (client, status_message)
    """
    
    # Try primary configuration first
    async with immediate_redis_test(
        primary_config['host'], 
        primary_config['port'], 
        primary_config.get('db', 0)
    ) as state:
        if state.is_connected:
            # Success! Return the working client
            return state.client, f"Connected to {primary_config['host']}:{primary_config['port']}"
    
    # Primary failed, try fallbacks if provided
    if fallback_configs:
        for i, config in enumerate(fallback_configs):
            logger.info(f"Trying fallback Redis config {i+1}: {config['host']}:{config['port']}")
            
            async with immediate_redis_test(
                config['host'], 
                config['port'], 
                config.get('db', 0)
            ) as state:
                if state.is_connected:
                    return state.client, f"Connected via fallback to {config['host']}:{config['port']}"
    
    # All connections failed
    return None, "All Redis connections failed immediately"

class RedisCircuitBreaker:
    """
    Circuit breaker pattern for Redis - no timeouts, just immediate state tracking
    """
    
    def __init__(self, failure_threshold: int = 3):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.is_circuit_open = False
        self.last_success_time = None
        self.last_failure_time = None
        
    def record_success(self):
        """Record successful operation"""
        self.failure_count = 0
        self.is_circuit_open = False
        self.last_success_time = asyncio.get_event_loop().time()
        
    def record_failure(self):
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = asyncio.get_event_loop().time()
        
        if self.failure_count >= self.failure_threshold:
            self.is_circuit_open = True
            logger.warning(f"🚫 Redis circuit breaker OPENED after {self.failure_count} failures")
            
    def should_attempt_connection(self) -> bool:
        """Check if we should attempt connection (no timeout logic)"""
        return not self.is_circuit_open
        
    async def attempt_redis_operation(self, client: redis.Redis, operation_name: str):
        """Attempt Redis operation with circuit breaker"""
        if not self.should_attempt_connection():
            raise redis.ConnectionError(f"Circuit breaker open for {operation_name}")
            
        try:
            # Execute operation immediately
            result = await asyncio.to_thread(client.ping)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise

# Global circuit breaker instance
redis_circuit_breaker = RedisCircuitBreaker()

async def get_redis_with_immediate_test(config: Dict[str, Any]) -> Tuple[Optional[redis.Redis], str]:
    """
    Get Redis client using immediate testing pattern.
    No arbitrary timeouts - either works immediately or fails immediately.
    """
    
    # Define fallback configurations
    fallback_configs = [
        {'host': '127.0.0.1', 'port': 6379, 'db': config.get('db', 0)},
        {'host': 'localhost', 'port': 6379, 'db': config.get('db', 0)},
        {'host': '172.16.168.23', 'port': 6379, 'db': config.get('db', 0)},  # Redis VM
    ]
    
    return await create_redis_with_fallback(config, fallback_configs)

async def test_redis_connection_immediate(redis_host: str, redis_port: int, redis_db: int = 0) -> Optional[redis.Redis]:
    """
    Test Redis connection immediately and return client if successful.
    Used by backend startup to quickly test Redis availability.
    
    Args:
        redis_host: Redis host address
        redis_port: Redis port number  
        redis_db: Redis database number
        
    Returns:
        Redis client if connection successful, None if failed
    """
    try:
        async with immediate_redis_test(redis_host, redis_port, redis_db) as state:
            if state.is_connected:
                logger.info(f"✅ Redis connection test successful: {redis_host}:{redis_port}")
                # Return a new client for the caller to use
                return redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    decode_responses=True,
                    socket_keepalive=True,
                    socket_keepalive_options={},
                    retry_on_timeout=False,
                    health_check_interval=0
                )
            else:
                logger.warning(f"⚠️ Redis connection test failed: {redis_host}:{redis_port}")
                return None
    except Exception as e:
        logger.error(f"❌ Redis connection test error: {redis_host}:{redis_port} - {str(e)}")
        return None