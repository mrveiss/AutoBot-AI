"""
Async Redis Connection Manager for AutoBot
Provides fully async Redis operations with connection pooling, health monitoring,
circuit breaker pattern, and proper error handling.

This replaces the blocking Redis timeout workarounds with proper async implementation.
"""

import asyncio
import logging
import os
import time
import yaml
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from weakref import WeakSet

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool
from redis.asyncio.client import Pipeline  # Import Pipeline correctly for aioredis 2.0
from redis.exceptions import ConnectionError, TimeoutError, RedisError

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Redis connection states for circuit breaker pattern"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass
class DatabaseConfig:
    """Configuration for a Redis database"""
    db: int
    description: str
    max_connections: int = 10
    retry_attempts: int = 3
    timeout_seconds: float = 5.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 60  # seconds


@dataclass
class RedisStats:
    """Redis database statistics"""
    db_number: int
    connection_count: int
    total_requests: int = 0
    failed_requests: int = 0
    avg_response_time_ms: float = 0
    last_success_time: Optional[float] = None
    last_failure_time: Optional[float] = None
    circuit_breaker_state: str = "closed"
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_requests == 0:
            return 100.0
        return ((self.total_requests - self.failed_requests) / self.total_requests) * 100


@dataclass 
class ManagerStats:
    """Overall Redis manager statistics"""
    total_databases: int
    healthy_databases: int
    total_connections: int
    total_requests: int
    total_failures: int
    uptime_seconds: float
    database_stats: Dict[str, RedisStats] = field(default_factory=dict)
    
    @property
    def overall_success_rate(self) -> float:
        """Calculate overall success rate"""
        if self.total_requests == 0:
            return 100.0
        return ((self.total_requests - self.total_failures) / self.total_requests) * 100


class AsyncRedisDatabase:
    """Async Redis database connection with circuit breaker and monitoring"""

    def __init__(self, name: str, config: DatabaseConfig, host: str = None, port: int = None):
        self.name = name
        self.config = config
        # Default to environment variables if not provided
        self.host = host if host is not None else os.getenv("AUTOBOT_REDIS_HOST", "172.16.168.23")
        self.port = port if port is not None else int(os.getenv("AUTOBOT_REDIS_PORT", "6379"))
        
        # Connection state
        self._redis: Optional[aioredis.Redis] = None
        self._pool: Optional[ConnectionPool] = None
        self._initialized = False
        self._state = ConnectionState.HEALTHY
        
        # Circuit breaker
        self._failure_count = 0
        self._last_failure_time = 0
        self._circuit_open = False
        
        # Statistics
        self._stats = RedisStats(db_number=config.db, connection_count=0)
        self._request_times: List[float] = []
        self._max_response_times = 100  # Keep last 100 response times
        
        # Active connections tracking
        self._active_connections: WeakSet = WeakSet()
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> bool:
        """Initialize Redis connection with connection pooling"""
        async with self._lock:
            if self._initialized:
                return True
                
            try:
                # Create connection pool
                self._pool = ConnectionPool(
                    host=self.host,
                    port=self.port,
                    db=self.config.db,
                    max_connections=self.config.max_connections,
                    socket_connect_timeout=self.config.timeout_seconds,
                    socket_timeout=self.config.timeout_seconds,
                    retry_on_timeout=True,
                    retry_on_error=[ConnectionError, TimeoutError],
                    health_check_interval=30
                )
                
                # Create Redis client with connection pool
                self._redis = aioredis.Redis(connection_pool=self._pool)
                
                # Test connection
                await asyncio.wait_for(self._redis.ping(), timeout=self.config.timeout_seconds)
                
                self._initialized = True
                self._state = ConnectionState.HEALTHY
                self._failure_count = 0
                self._circuit_open = False
                self._stats.last_success_time = time.time()
                
                logger.info(f"Redis database '{self.name}' (DB {self.config.db}) initialized successfully")
                return True
                
            except Exception as e:
                self._state = ConnectionState.FAILED
                self._stats.last_failure_time = time.time()
                logger.error(f"Failed to initialize Redis database '{self.name}': {e}")
                return False
    
    async def close(self):
        """Close Redis connection and cleanup"""
        async with self._lock:
            if self._redis:
                try:
                    await self._redis.aclose()
                except Exception as e:
                    logger.warning(f"Error closing Redis connection '{self.name}': {e}")
                finally:
                    self._redis = None
                    
            if self._pool:
                try:
                    await self._pool.aclose()
                except Exception as e:
                    logger.warning(f"Error closing Redis pool '{self.name}': {e}")
                finally:
                    self._pool = None
                    
            self._initialized = False
            self._active_connections.clear()
            logger.info(f"Redis database '{self.name}' closed")
    
    def _is_circuit_open(self) -> bool:
        """Check if circuit breaker is open"""
        if not self._circuit_open:
            return False
            
        # Check if timeout period has passed
        if time.time() - self._last_failure_time > self.config.circuit_breaker_timeout:
            self._circuit_open = False
            self._failure_count = 0
            logger.info(f"Circuit breaker reset for Redis database '{self.name}'")
            return False
            
        return True
    
    def _record_success(self, response_time: float):
        """Record successful request"""
        self._stats.total_requests += 1
        self._stats.last_success_time = time.time()
        
        # Update response time statistics
        self._request_times.append(response_time)
        if len(self._request_times) > self._max_response_times:
            self._request_times.pop(0)
            
        if self._request_times:
            self._stats.avg_response_time_ms = sum(self._request_times) / len(self._request_times) * 1000
        
        # Reset failure count on success
        if self._failure_count > 0:
            self._failure_count = max(0, self._failure_count - 1)
            if self._circuit_open and self._failure_count == 0:
                self._circuit_open = False
                logger.info(f"Circuit breaker closed for Redis database '{self.name}'")
    
    def _record_failure(self):
        """Record failed request and update circuit breaker"""
        self._stats.total_requests += 1
        self._stats.failed_requests += 1
        self._stats.last_failure_time = time.time()
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        # Check if circuit breaker should open
        if self._failure_count >= self.config.circuit_breaker_threshold:
            self._circuit_open = True
            self._state = ConnectionState.FAILED
            logger.warning(f"Circuit breaker opened for Redis database '{self.name}' after {self._failure_count} failures")
    
    async def _execute_with_retry(self, operation, *args, **kwargs):
        """Execute Redis operation with retry logic and circuit breaker"""
        if self._is_circuit_open():
            raise ConnectionError(f"Circuit breaker is open for Redis database '{self.name}'")
        
        if not self._initialized:
            if not await self.initialize():
                raise ConnectionError(f"Redis database '{self.name}' not initialized")
        
        last_error = None
        
        for attempt in range(self.config.retry_attempts):
            try:
                start_time = time.time()
                result = await asyncio.wait_for(
                    operation(*args, **kwargs), 
                    timeout=self.config.timeout_seconds
                )
                response_time = time.time() - start_time
                self._record_success(response_time)
                return result
                
            except Exception as e:
                last_error = e
                self._record_failure()
                
                if attempt < self.config.retry_attempts - 1:
                    wait_time = 0.1 * (2 ** attempt)  # Exponential backoff
                    await asyncio.sleep(wait_time)
                    logger.warning(f"Redis operation failed (attempt {attempt + 1}/{self.config.retry_attempts}) for '{self.name}': {e}")
                    
                    # Try to reinitialize connection on failure
                    if isinstance(e, (ConnectionError, TimeoutError)):
                        self._initialized = False
                        await self.initialize()
        
        # All retries failed
        self._state = ConnectionState.FAILED
        raise last_error
    
    async def ping(self) -> bool:
        """Health check - ping Redis server"""
        try:
            await self._execute_with_retry(self._redis.ping)
            self._state = ConnectionState.HEALTHY
            return True
        except Exception:
            self._state = ConnectionState.FAILED
            return False
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis"""
        result = await self._execute_with_retry(self._redis.get, key)
        return result.decode('utf-8') if result else None
    
    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """Set value in Redis with optional expiration"""
        return await self._execute_with_retry(self._redis.set, key, value, ex=ex)
    
    async def delete(self, *keys: str) -> int:
        """Delete keys from Redis"""
        return await self._execute_with_retry(self._redis.delete, *keys)
    
    async def exists(self, *keys: str) -> int:
        """Check if keys exist in Redis"""
        return await self._execute_with_retry(self._redis.exists, *keys)
    
    async def hget(self, name: str, key: str) -> Optional[str]:
        """Get hash field value"""
        result = await self._execute_with_retry(self._redis.hget, name, key)
        return result.decode('utf-8') if result else None
    
    async def hset(self, name: str, key: str, value: str) -> int:
        """Set hash field value"""
        return await self._execute_with_retry(self._redis.hset, name, key, value)
    
    async def hgetall(self, name: str) -> Dict[str, str]:
        """Get all hash fields"""
        result = await self._execute_with_retry(self._redis.hgetall, name)
        return {k.decode('utf-8'): v.decode('utf-8') for k, v in result.items()}
    
    async def sadd(self, name: str, *values: str) -> int:
        """Add members to set"""
        return await self._execute_with_retry(self._redis.sadd, name, *values)
    
    async def smembers(self, name: str) -> set:
        """Get all set members"""
        result = await self._execute_with_retry(self._redis.smembers, name)
        return {member.decode('utf-8') for member in result}
    
    async def zadd(self, name: str, mapping: Dict[str, float]) -> int:
        """Add members to sorted set"""
        return await self._execute_with_retry(self._redis.zadd, name, mapping)
    
    async def zrange(self, name: str, start: int, end: int, withscores: bool = False) -> List:
        """Get range from sorted set"""
        result = await self._execute_with_retry(self._redis.zrange, name, start, end, withscores=withscores)
        if withscores:
            return [(member.decode('utf-8'), score) for member, score in result]
        return [member.decode('utf-8') for member in result]
    
    async def incr(self, name: str, amount: int = 1) -> int:
        """Increment counter"""
        return await self._execute_with_retry(self._redis.incr, name, amount)
    
    async def expire(self, name: str, time: int) -> bool:
        """Set key expiration"""
        return await self._execute_with_retry(self._redis.expire, name, time)
    
    async def ttl(self, name: str) -> int:
        """Get key time to live"""
        return await self._execute_with_retry(self._redis.ttl, name)
    
    async def flushdb(self):
        """Clear all keys in current database"""
        return await self._execute_with_retry(self._redis.flushdb)
    
    @asynccontextmanager
    async def pipeline(self) -> AsyncGenerator[Pipeline, None]:  # Fixed type annotation
        """Get Redis pipeline for batch operations"""
        if not self._initialized:
            if not await self.initialize():
                raise ConnectionError(f"Redis '{self.name}' not initialized")
        
        pipe = self._redis.pipeline()
        self._active_connections.add(pipe)
        try:
            yield pipe
        finally:
            self._active_connections.discard(pipe)
    
    def get_stats(self) -> RedisStats:
        """Get database statistics"""
        self._stats.connection_count = len(self._active_connections)
        self._stats.circuit_breaker_state = "open" if self._circuit_open else "closed"
        return self._stats
    
    @property
    def healthy(self) -> bool:
        """Check if database is healthy"""
        return self._state == ConnectionState.HEALTHY and not self._circuit_open
    
    @property
    def state(self) -> ConnectionState:
        """Get current connection state"""
        return self._state


class AsyncRedisManager:
    """
    Centralized async Redis connection manager
    Provides access to multiple Redis databases with connection pooling,
    health monitoring, and automatic failover.
    """

    def __init__(self, config_file: str = "config/redis-databases.yaml",
                 host: str = None, port: int = None):
        # Get host and port from environment variables if not provided
        self.host = host if host is not None else os.getenv("AUTOBOT_REDIS_HOST", "172.16.168.23")
        self.port = port if port is not None else int(os.getenv("AUTOBOT_REDIS_PORT", "6379"))
        self.config_file = config_file
        self._databases: Dict[str, AsyncRedisDatabase] = {}
        self._start_time = time.time()
        
        # Global statistics
        self._global_stats = ManagerStats(
            total_databases=0,
            healthy_databases=0,
            total_connections=0,
            total_requests=0,
            total_failures=0,
            uptime_seconds=0
        )
        
        # Load database configurations
        self._load_config()
    
    def _load_config(self):
        """Load Redis database configurations from YAML file"""
        try:
            config_path = Path(self.config_file)
            if not config_path.exists():
                # Create default configuration
                self._create_default_config(config_path)
            
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            
            if not config_data or 'redis_databases' not in config_data:
                raise ValueError("Invalid Redis configuration format")
            
            databases_config = config_data['redis_databases']
            
            for name, db_config in databases_config.items():
                if 'db' not in db_config:
                    logger.warning(f"Database '{name}' missing 'db' number, skipping")
                    continue
                
                config = DatabaseConfig(
                    db=db_config['db'],
                    description=db_config.get('description', f'Database {name}'),
                    max_connections=db_config.get('max_connections', 10),
                    retry_attempts=db_config.get('retry_attempts', 3),
                    timeout_seconds=db_config.get('timeout_seconds', 5.0),
                    circuit_breaker_threshold=db_config.get('circuit_breaker_threshold', 5),
                    circuit_breaker_timeout=db_config.get('circuit_breaker_timeout', 60)
                )
                
                self._databases[name] = AsyncRedisDatabase(name, config, self.host, self.port)
                logger.info(f"Configured Redis database '{name}' (DB {config.db}): {config.description}")
            
            logger.info(f"Loaded {len(self._databases)} Redis database configurations")
            
        except Exception as e:
            logger.error(f"Failed to load Redis configuration: {e}")
            # Fall back to default main database
            self._databases['main'] = AsyncRedisDatabase(
                'main', 
                DatabaseConfig(db=0, description='Default main database'), 
                self.host, 
                self.port
            )
    
    def _create_default_config(self, config_path: Path):
        """Create default Redis configuration file"""
        default_config = {
            'redis_databases': {
                'main': {'db': 0, 'description': 'Main application data'},
                'knowledge': {'db': 1, 'description': 'Knowledge base and documents'},
                'sessions': {'db': 2, 'description': 'User sessions and temporary data'},
                'vectors': {'db': 8, 'description': 'Vector embeddings and search indexes'},
                'cache': {'db': 3, 'description': 'Application cache'},
                'metrics': {'db': 4, 'description': 'System metrics and monitoring'},
                'workflows': {'db': 7, 'description': 'Workflow coordination and state'},
                'events': {'db': 5, 'description': 'Event streaming and pub/sub'},
                'queue': {'db': 6, 'description': 'Background job queue'},
                'testing': {'db': 9, 'description': 'Testing and development'},
                'archive': {'db': 10, 'description': 'Data archival and backup'}
            }
        }
        
        # Create directory if it doesn't exist
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Created default Redis configuration at {config_path}")
    
    async def initialize_all(self) -> Dict[str, bool]:
        """Initialize all Redis databases"""
        results = {}
        
        for name, database in self._databases.items():
            try:
                success = await database.initialize()
                results[name] = success
                if success:
                    logger.info(f"✅ Redis database '{name}' initialized")
                else:
                    logger.warning(f"❌ Redis database '{name}' failed to initialize")
            except Exception as e:
                logger.error(f"❌ Redis database '{name}' initialization error: {e}")
                results[name] = False
        
        successful = sum(1 for success in results.values() if success)
        logger.info(f"Redis initialization complete: {successful}/{len(results)} databases ready")
        
        return results
    
    async def close_all(self):
        """Close all Redis connections"""
        for name, database in self._databases.items():
            try:
                await database.close()
                logger.info(f"✅ Redis database '{name}' closed")
            except Exception as e:
                logger.error(f"❌ Error closing Redis database '{name}': {e}")
    
    # Database access methods
    async def main(self) -> AsyncRedisDatabase:
        """Get main database (DB 0)"""
        return await self._get_database('main')
    
    async def knowledge(self) -> AsyncRedisDatabase:
        """Get knowledge database (DB 1)"""
        return await self._get_database('knowledge')
    
    async def sessions(self) -> AsyncRedisDatabase:
        """Get sessions database (DB 2)"""
        return await self._get_database('sessions')
    
    async def vectors(self) -> AsyncRedisDatabase:
        """Get vectors database (DB 8)"""
        return await self._get_database('vectors')
    
    async def cache(self) -> AsyncRedisDatabase:
        """Get cache database (DB 3)"""
        return await self._get_database('cache')
    
    async def metrics(self) -> AsyncRedisDatabase:
        """Get metrics database (DB 4)"""
        return await self._get_database('metrics')
    
    async def workflows(self) -> AsyncRedisDatabase:
        """Get workflows database (DB 7)"""
        return await self._get_database('workflows')
    
    async def events(self) -> AsyncRedisDatabase:
        """Get events database (DB 5)"""
        return await self._get_database('events')
    
    async def queue(self) -> AsyncRedisDatabase:
        """Get queue database (DB 6)"""
        return await self._get_database('queue')
    
    async def testing(self) -> AsyncRedisDatabase:
        """Get testing database (DB 9)"""
        return await self._get_database('testing')
    
    async def audit(self) -> AsyncRedisDatabase:
        """Get audit database (DB 10)"""
        return await self._get_database('audit')
    
    async def _get_database(self, name: str) -> AsyncRedisDatabase:
        """Get database by name, initializing if needed"""
        if name not in self._databases:
            raise ValueError(f"Redis database '{name}' not configured")
        
        database = self._databases[name]
        if not database._initialized:
            success = await database.initialize()
            if not success:
                raise ConnectionError(f"Failed to initialize Redis database '{name}'")
        
        return database
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check of all databases"""
        health_report = {
            'overall_healthy': True,
            'databases': {},
            'summary': {
                'total': len(self._databases),
                'healthy': 0,
                'degraded': 0,
                'failed': 0
            }
        }
        
        for name, database in self._databases.items():
            try:
                is_healthy = await database.ping()
                stats = database.get_stats()
                
                health_report['databases'][name] = {
                    'healthy': is_healthy,
                    'state': database.state.value,
                    'db_number': database.config.db,
                    'total_requests': stats.total_requests,
                    'failed_requests': stats.failed_requests,
                    'success_rate': stats.success_rate,
                    'avg_response_time_ms': stats.avg_response_time_ms,
                    'circuit_breaker_state': stats.circuit_breaker_state
                }
                
                if is_healthy:
                    health_report['summary']['healthy'] += 1
                elif database.state == ConnectionState.DEGRADED:
                    health_report['summary']['degraded'] += 1
                else:
                    health_report['summary']['failed'] += 1
                    health_report['overall_healthy'] = False
                    
            except Exception as e:
                health_report['databases'][name] = {
                    'healthy': False,
                    'state': 'error',
                    'error': str(e)
                }
                health_report['summary']['failed'] += 1
                health_report['overall_healthy'] = False
        
        return health_report
    
    async def get_statistics(self) -> ManagerStats:
        """Get comprehensive manager statistics"""
        self._global_stats.uptime_seconds = time.time() - self._start_time
        self._global_stats.total_databases = len(self._databases)
        
        # Reset counters
        self._global_stats.healthy_databases = 0
        self._global_stats.total_connections = 0
        self._global_stats.total_requests = 0
        self._global_stats.total_failures = 0
        self._global_stats.database_stats = {}
        
        # Aggregate statistics from all databases
        for name, database in self._databases.items():
            stats = database.get_stats()
            self._global_stats.database_stats[name] = stats
            
            self._global_stats.total_connections += stats.connection_count
            self._global_stats.total_requests += stats.total_requests
            self._global_stats.total_failures += stats.failed_requests
            
            if database.healthy:
                self._global_stats.healthy_databases += 1
        
        return self._global_stats
    
    def list_databases(self) -> List[Dict[str, Any]]:
        """List all configured databases"""
        return [
            {
                'name': name,
                'db_number': database.config.db,
                'description': database.config.description,
                'initialized': database._initialized,
                'healthy': database.healthy,
                'state': database.state.value
            }
            for name, database in self._databases.items()
        ]


# Global manager instance
_redis_manager_instance: Optional[AsyncRedisManager] = None
_manager_lock = asyncio.Lock()


async def get_redis_manager(host: str = None, port: int = None) -> AsyncRedisManager:
    """
    Get or create global Redis manager instance

    This function ensures only one Redis manager instance exists across the application
    and handles proper initialization and connection management.

    Args:
        host: Redis host (defaults to AUTOBOT_REDIS_HOST env var or 172.16.168.23)
        port: Redis port (defaults to AUTOBOT_REDIS_PORT env var or 6379)
    """
    global _redis_manager_instance

    async with _manager_lock:
        if _redis_manager_instance is None:
            # Get host and port from environment variables if not provided
            if host is None:
                host = os.getenv("AUTOBOT_REDIS_HOST", "172.16.168.23")
            if port is None:
                port = int(os.getenv("AUTOBOT_REDIS_PORT", "6379"))

            logger.info(f"Initializing AsyncRedisManager with host={host}, port={port}")

            # Create new manager instance
            _redis_manager_instance = AsyncRedisManager(host=host, port=port)
            
            # Initialize all databases
            try:
                results = await _redis_manager_instance.initialize_all()
                successful = sum(1 for success in results.values() if success)
                
                if successful == 0:
                    logger.warning("No Redis databases initialized successfully")
                else:
                    logger.info(f"Redis manager ready with {successful}/{len(results)} databases")
                    
            except Exception as e:
                logger.error(f"Failed to initialize Redis manager: {e}")
                # Continue with manager creation even if some databases fail
        
        return _redis_manager_instance


async def close_redis_manager():
    """Close global Redis manager and cleanup connections"""
    global _redis_manager_instance
    
    async with _manager_lock:
        if _redis_manager_instance:
            await _redis_manager_instance.close_all()
            _redis_manager_instance = None
            logger.info("Global Redis manager closed")


# Convenience functions for common operations
async def get_main_redis() -> AsyncRedisDatabase:
    """Quick access to main Redis database"""
    manager = await get_redis_manager()
    return await manager.main()


async def get_cache_redis() -> AsyncRedisDatabase:
    """Quick access to cache Redis database"""
    manager = await get_redis_manager()
    return await manager.cache()


async def get_knowledge_redis() -> AsyncRedisDatabase:
    """Quick access to knowledge Redis database"""
    manager = await get_redis_manager()
    return await manager.knowledge()


# Example usage and testing
if __name__ == "__main__":
    async def test_redis_manager():
        """Test Redis manager functionality"""
        try:
            # Get manager instance
            manager = await get_redis_manager()
            
            # Health check
            health = await manager.health_check()
            print(f"Overall health: {'✅ Healthy' if health['overall_healthy'] else '❌ Degraded'}")
            
            # Test main database
            main_db = await manager.main()
            await main_db.set("test_key", "test_value", ex=60)
            value = await main_db.get("test_key")
            print(f"Test write/read: {value}")
            
            # Get statistics
            stats = await manager.get_statistics()
            print(f"Manager uptime: {stats.uptime_seconds:.2f}s")
            print(f"Healthy databases: {stats.healthy_databases}/{stats.total_databases}")
            
            # List databases
            databases = manager.list_databases()
            print(f"Available databases: {len(databases)}")
            
        except Exception as e:
            print(f"Test failed: {e}")
        finally:
            # Cleanup
            await close_redis_manager()
    
    # Run test
    asyncio.run(test_redis_manager())