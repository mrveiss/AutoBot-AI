# 🔗 Claude Desktop Integration - Quick Setup Guide

## Step 1: Install MCP AutoBot Tracker

```bash
cd /home/kali/Desktop/AutoBot/mcp-autobot-tracker
./production-install.sh
```

## Step 2: Configure Claude Desktop

Add this configuration to your Claude Desktop config file:

**Location**: `~/.config/claude_desktop/config.json`

```json
{
  "mcpServers": {
    "autobot-tracker": {
      "command": "node",
      "args": ["dist/index.js"],
      "cwd": "/home/kali/Desktop/AutoBot/mcp-autobot-tracker",
      "env": {
        "NODE_ENV": "production"
      }
    }
  }
}
```

## Step 3: Restart Claude Desktop

Close and restart Claude Desktop to load the MCP server.

## Step 4: Test Integration

In Claude Desktop, you can now use these tools:

- **`ingest_chat`** - Track conversation data
- **`get_unfinished_tasks`** - View pending tasks  
- **`get_error_correlations`** - Analyze system issues
- **`get_insights`** - Generate actionable insights
- **`system_health_check`** - Monitor VM health
- **`validate_fixes`** - Track issue resolution
- **`get_task_analytics`** - Detailed task analysis
- **`correlate_conversations`** - Find patterns
- **`generate_system_report`** - Comprehensive status

## Example Usage

```
Use the get_unfinished_tasks tool to show me the highest priority items needing attention.

Then use get_insights to identify patterns in the issues we're tracking.

Finally, use system_health_check to verify all VMs are healthy.
```

## ✅ System Status

The MCP tracker is now monitoring:
- **96 tasks** across **4 conversation sessions**
- **69 errors** with correlation analysis
- **6 VMs** with real-time health monitoring
- **Background processes** for continuous analysis

🎉 **Your AutoBot system now has comprehensive conversation tracking and proactive task management!**
