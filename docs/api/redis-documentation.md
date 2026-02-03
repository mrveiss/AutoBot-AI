# Redis Configuration and Management in AutoBot

## Overview
AutoBot uses Redis Stack as a centralized database for:
- Session management and chat history
- Knowledge base caching and search indices
- Real-time WebSocket connection state
- API response caching and rate limiting
- Background task queues and job processing

## Docker Configuration

### Container Setup
```yaml
# docker-compose.yml
redis:
  image: redis/redis-stack:latest
  container_name: autobot-redis
  ports:
    - "6379:6379"    # Redis server
    - "8002:8001"    # RedisInsight web interface
  volumes:
    - redis_data:/data
    - ./config/redis.conf:/usr/local/etc/redis/redis.conf
  command: redis-server /usr/local/etc/redis/redis.conf
  networks:
    - autobot-network
  restart: unless-stopped
```

### Network Access
- **Container-to-container**: `redis:6379`
- **Host-to-container**: `localhost:6379` or `127.0.0.1:6379`
- **Container-to-host**: `host.docker.internal:6379`
- **Web Interface**: http://localhost:8002/

## Database Schema

AutoBot uses multiple Redis databases for organization:

| Database | Purpose | Key Patterns |
|----------|---------|--------------|
| DB 0 | Session Management | `session:*`, `user:*` |
| DB 1 | Chat History | `chat:*`, `message:*` |
| DB 2 | Knowledge Base | `kb:*`, `document:*` |
| DB 3 | API Cache | `api:*`, `cache:*` |
| DB 4 | WebSocket State | `ws:*`, `connection:*` |
| DB 5 | Background Jobs | `job:*`, `queue:*` |

## Connection Configuration

### Backend Python Configuration
```python
# src/utils/redis_database_manager.py
REDIS_CONFIG = {
    'host': 'localhost',  # Host system uses localhost
    'port': 6379,
    'decode_responses': True,
    'socket_timeout': 2,
    'socket_connect_timeout': 2,
    'retry_on_timeout': True,
    'health_check_interval': 30
}

# Multiple database connections
class RedisManager:
    def __init__(self):
        self.sessions_db = redis.Redis(db=0, **REDIS_CONFIG)
        self.chat_db = redis.Redis(db=1, **REDIS_CONFIG) 
        self.knowledge_db = redis.Redis(db=2, **REDIS_CONFIG)
        self.cache_db = redis.Redis(db=3, **REDIS_CONFIG)
        self.websocket_db = redis.Redis(db=4, **REDIS_CONFIG)
        self.jobs_db = redis.Redis(db=5, **REDIS_CONFIG)
```

### Frontend Configuration
```javascript
// Frontend connects through backend API, not directly to Redis
const API_BASE_URL = process.env.VITE_API_BASE_URL || 'http://host.docker.internal:8001';
```

## Data Structures

### Session Management (DB 0)
```redis
# User sessions
SET session:user_123 '{"user_id": "123", "created": "2024-01-01T00:00:00Z"}'
EXPIRE session:user_123 86400

# Session metadata
HSET user:123 "name" "John Doe" "email" "john@example.com" "last_active" "2024-01-01T00:00:00Z"
```

### Chat History (DB 1)
```redis
# Chat sessions
SET chat:session_456 '{"id": "456", "user_id": "123", "created": "2024-01-01T00:00:00Z"}'

# Messages in session
LPUSH chat:session_456:messages '{"role": "user", "content": "Hello", "timestamp": "..."}'
LPUSH chat:session_456:messages '{"role": "assistant", "content": "Hi there!", "timestamp": "..."}'
```

### Knowledge Base (DB 2)
```redis
# Document metadata
HSET kb:doc_789 "title" "API Documentation" "type" "markdown" "size" "1024" "indexed" "true"

# Document content chunks for search
SET kb:doc_789:chunk_1 '{"content": "...", "embedding": [...], "metadata": {...}}'
SET kb:doc_789:chunk_2 '{"content": "...", "embedding": [...], "metadata": {...}}'

# Search indices
SADD kb:index:api "doc_789" "doc_790"
SADD kb:index:documentation "doc_789" "doc_791"
```

### API Caching (DB 3)
```redis
# Response caching
SET api:cache:/api/system/health '{"status": "healthy", "timestamp": "..."}' EX 60

# Rate limiting
INCR api:ratelimit:user_123:/api/chat/send EX 3600
```

### WebSocket State (DB 4)
```redis
# Active connections
HSET ws:connections "conn_abc123" '{"user_id": "123", "session_id": "456", "connected": "..."}'

# Connection routing
SET ws:user_123:connection "conn_abc123" EX 7200
```

## Monitoring and Health Checks

### Health Check Commands
```bash
# Basic connectivity
redis-cli ping

# Database information
redis-cli info server
redis-cli info memory
redis-cli info stats

# Database sizes
redis-cli -n 0 dbsize  # Sessions
redis-cli -n 1 dbsize  # Chat history
redis-cli -n 2 dbsize  # Knowledge base

# Memory usage per database
redis-cli memory usage session:*
redis-cli memory usage chat:*
```

### Performance Monitoring
```bash
# Monitor real-time commands
redis-cli monitor

# Get slow queries
redis-cli slowlog get 10

# Memory statistics
redis-cli memory stats
```

## Backup and Persistence

### Data Persistence
```redis
# Redis configuration in redis.conf
save 900 1      # Save if at least 1 key changed in 900 seconds
save 300 10     # Save if at least 10 keys changed in 300 seconds  
save 60 10000   # Save if at least 10000 keys changed in 60 seconds

# AOF (Append Only File) for durability
appendonly yes
appendfsync everysec
```

### Backup Commands
```bash
# Manual backup
redis-cli bgsave

# Export specific database
redis-cli --rdb backup.rdb

# Import backup
redis-cli --rdb backup.rdb
```

## Troubleshooting

### Common Issues

1. **Connection Timeouts**
   - Check if Redis container is running: `docker ps | grep redis`
   - Test connectivity: `redis-cli ping`
   - Verify network configuration in docker-compose.yml

2. **Memory Issues**  
   - Check memory usage: `redis-cli info memory`
   - Clear cache databases: `redis-cli -n 3 flushdb`
   - Increase Docker container memory limits

3. **Performance Issues**
   - Monitor slow queries: `redis-cli slowlog get`
   - Check database sizes: `redis-cli info keyspace`
   - Optimize data structures and expiration times

4. **Data Corruption**
   - Check logs: `docker logs autobot-redis`
   - Verify data integrity: `redis-cli debug assert`
   - Restore from backup if needed

### DNS Resolution Issues
```bash
# Test Redis resolution from different contexts
ping redis                    # From containers
ping localhost               # From host
ping autobot-redis          # Full container name

# Test Redis connectivity
redis-cli -h redis ping               # From containers
redis-cli -h localhost ping           # From host  
redis-cli -h autobot-redis ping       # Full name
```

## MCP Integration

The AutoBot MCP server provides Redis debugging tools:

```javascript
// Available MCP tools for Redis
autobot_redis_info: {
  action: "info|databases|memory|clients|config",
  database: 0  // Specific database to query
}

// Example usage in Claude
"Show Redis database information for all databases"
"Check Redis memory usage and client connections"  
"Get Redis configuration and server stats"
```

## Security Considerations

1. **Access Control**
   - Use Redis AUTH if exposing port 6379 externally
   - Restrict Redis container network access
   - Use TLS for production deployments

2. **Data Privacy**
   - Encrypt sensitive data before storing in Redis
   - Use appropriate key expiration times
   - Regularly audit stored data patterns

3. **Network Security**
   - Keep Redis on internal Docker network only
   - Use firewall rules to restrict external access
   - Monitor connection patterns for anomalies