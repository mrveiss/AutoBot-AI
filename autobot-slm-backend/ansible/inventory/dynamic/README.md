# AutoBot Dynamic Inventory

## Overview

This directory contains the dynamic inventory generator that reads host information from the AutoBot Redis service registry.

## Usage

### List all hosts

```bash
python generate_inventory.py --list
```

### Get variables for specific host

```bash
python generate_inventory.py --host autobot-frontend
```

### Use with Ansible

```bash
# Use dynamic inventory
ansible-playbook -i inventory/dynamic/generate_inventory.py playbook.yml

# Combine with static inventory
ansible-playbook -i inventory/production.yml -i inventory/dynamic/generate_inventory.py playbook.yml
```

## Configuration

Set environment variables to customize Redis connection:

```bash
export REDIS_HOST=172.16.168.23
export REDIS_PORT=6379
export REDIS_DB=0
```

## Redis Data Structure

The script expects host data in Redis with the following structure:

```
autobot:host:<hostname> (hash):
    ip: <ip_address>
    role: <vm_role>
    services: <comma_separated_services>
    status: <active|maintenance|decommissioned>
    last_seen: <timestamp>
```

### Example Redis Data

```bash
redis-cli HSET autobot:host:autobot-frontend ip 172.16.168.21 role frontend services "nginx,vue-frontend" status active
redis-cli HSET autobot:host:autobot-database ip 172.16.168.23 role database services "redis-stack" status active
```

## Fallback Behavior

If Redis is unavailable, the script falls back to a static inventory structure matching the production inventory.

## Dependencies

```bash
pip install redis
```

## Integration with Service Registry

The dynamic inventory integrates with the AutoBot service registry system. Host registrations are automatically created when services start up and register themselves.
