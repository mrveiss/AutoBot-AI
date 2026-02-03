#!/bin/bash
# Redis Stack Optimized Startup Script
# Enables multi-threading for better CPU utilization on 12-core system

# Kill existing Redis Stack process
pkill -f redis-server

# Wait for process to terminate
sleep 2

# Start Redis Stack with multi-threading enabled
/opt/redis-stack/bin/redis-server \
  --bind 0.0.0.0 \
  --port 6379 \
  --io-threads 10 \
  --io-threads-do-reads yes \
  --maxmemory 8gb \
  --maxmemory-policy allkeys-lru \
  --appendonly yes \
  --appendfsync everysec \
  --lazyfree-lazy-eviction yes \
  --lazyfree-lazy-expire yes \
  --lazyfree-lazy-server-del yes \
  --save "900 1" \
  --save "300 10" \
  --save "60 10000" \
  --daemonize yes \
  --logfile /var/log/redis/redis-server.log \
  --loadmodule /opt/redis-stack/lib/redisearch.so \
  --loadmodule /opt/redis-stack/lib/rejson.so \
  --loadmodule /opt/redis-stack/lib/redistimeseries.so \
  --loadmodule /opt/redis-stack/lib/redisbloom.so

# Verify startup
sleep 2
redis-cli ping && echo "Redis Stack started successfully with 10 I/O threads"
redis-cli INFO SERVER | grep -E "io_threads|multiplexing"
