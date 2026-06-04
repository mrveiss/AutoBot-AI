# Remove Orphaned Node Script

## Problem

Nodes that appear in the SLM database but are not enrolled/reachable cause warnings during every provision run:

```
WARNING: Node 172.16.168.26 (172.16.168.26) is unreachable -- skipping (not enrolled?)
```

This happens when:
- A node was added to the database but never enrolled
- A node was decommissioned but not properly removed from the database
- SSH access to the node was lost

## Solution

Use the `remove_orphaned_node.py` script to cleanly remove the node from the database.

## Usage

### List all unreachable nodes

```bash
python remove_orphaned_node.py --list-unreachable
```

This will test SSH connectivity to all nodes and list which ones are unreachable.

### Remove a specific node by IP

```bash
python remove_orphaned_node.py --ip 172.16.168.26
```

### Remove a specific node by ID

```bash
python remove_orphaned_node.py --node-id <node-id>
```

### Force removal without confirmation

```bash
python remove_orphaned_node.py --ip 172.16.168.26 --force
```

## Configuration

The script uses environment variables or command-line arguments:

- `SLM_API_URL` or `--api-url`: SLM API base URL (default: `http://localhost:8002`)
- `SLM_API_TOKEN` or `--api-token`: Authentication token for SLM API

## Example

```bash
# Set up environment
export SLM_API_URL=http://172.16.168.19:8002
export SLM_API_TOKEN=your-token-here

# Remove the orphaned node
python remove_orphaned_node.py --ip 172.16.168.26
```

Output:
```
Looking for node with IP 172.16.168.26...

Node found:
  ID:       abc123
  Hostname: monitoring-vm
  IP:       172.16.168.26
  Status:   unreachable

Remove this node? [y/N]: y

Removing node abc123...
✓ Node monitoring-vm (172.16.168.26) removed successfully

The node will no longer appear in provision warnings.
```

## What This Does

The script calls the SLM API's `DELETE /nodes/{node_id}` endpoint, which:
1. Removes the node record from the database
2. Cascades deletion to related records (roles, credentials, events)
3. Broadcasts a `node_deleted` lifecycle event via WebSocket

The node will no longer appear in wizard-generated inventories or provision warnings.

## Related Issues

- GitHub Issue #9285: fix(ansible): unreachable node 172.16.168.26 warned on every provision run
- Paperclip Issue: MVA-2435

## Alternative: Manual Database Cleanup

If the SLM API is not accessible, you can remove the node directly via SQL:

```sql
-- Find the node
SELECT node_id, hostname, ip_address, status FROM nodes WHERE ip_address = '172.16.168.26';

-- Delete related records first (due to foreign keys)
DELETE FROM node_roles WHERE node_id = '<node-id>';
DELETE FROM node_credentials WHERE node_id = '<node-id>';
DELETE FROM node_events WHERE node_id = '<node-id>';
DELETE FROM node_configs WHERE node_id = '<node-id>';
DELETE FROM deployments WHERE node_id = '<node-id>';

-- Finally delete the node
DELETE FROM nodes WHERE node_id = '<node-id>';
```

**Note:** Direct SQL deletion bypasses API validation and WebSocket notifications. Use the Python script when possible.
