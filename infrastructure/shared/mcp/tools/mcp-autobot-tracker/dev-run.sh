#!/bin/bash
echo "🚀 Running AutoBot MCP Tracker in development mode..."
export NODE_ENV=development
export REDIS_HOST=172.16.168.23
export REDIS_PORT=6379
npm run dev
