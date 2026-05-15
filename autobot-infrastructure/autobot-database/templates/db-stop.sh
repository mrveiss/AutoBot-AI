#!/bin/bash
# AutoBot DB Stack - Stop Script
# Manual intervention script for stopping all database services

set -e

echo "Stopping AutoBot DB Stack..."

# Stop ChromaDB
echo "Stopping ChromaDB..."
if systemctl is-active --quiet autobot-chromadb 2>/dev/null; then
    sudo systemctl stop autobot-chromadb
fi

# Stop PostgreSQL
echo "Stopping PostgreSQL..."
if systemctl is-active --quiet postgresql 2>/dev/null; then
    sudo systemctl stop postgresql
fi

# Stop Redis Stack
echo "Stopping Redis Stack..."
if systemctl is-active --quiet autobot-redis 2>/dev/null; then
    sudo systemctl stop autobot-redis
elif systemctl is-active --quiet redis-stack-server 2>/dev/null; then
    sudo systemctl stop redis-stack-server
fi

echo "AutoBot DB Stack stopped"
