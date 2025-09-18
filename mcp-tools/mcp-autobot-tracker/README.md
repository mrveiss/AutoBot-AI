# AutoBot MCP Tracker

An advanced MCP (Model Context Protocol) server that tracks Claude chat conversations, identifies unfinished tasks, correlates errors, and integrates with AutoBot's knowledge base for comprehensive project management.

## 🚀 Features

### 📝 Chat Conversation Tracking
- **Ingest Claude Conversations**: Feed your Claude chat conversations into the tracker
- **Task Extraction**: Automatically identifies TODO items, FIXME comments, and action items
- **Error Detection**: Extracts error messages and exceptions from conversations
- **Context Preservation**: Maintains conversation context across sessions

### 🔍 Background Log Monitoring
- **Real-time Log Analysis**: Monitors AutoBot log files continuously
- **Docker Log Integration**: Tracks all Docker service logs
- **Pattern Recognition**: Identifies recurring error patterns and issues
- **Automatic Categorization**: Organizes errors by component, severity, and type

### 🧠 Knowledge Integration
- **Pattern Analysis**: Analyzes error patterns and generates insights
- **Knowledge Generation**: Creates actionable knowledge entries for AutoBot
- **Error Correlation**: Links related errors and tasks automatically
- **System Insights**: Generates system health and performance insights

### ⚡ Smart Correlations
- **Task-Error Linking**: Uses TF-IDF similarity to correlate tasks with errors
- **Component Mapping**: Maps issues to specific AutoBot components
- **Severity Assessment**: Automatically assesses error severity levels
- **Trend Analysis**: Identifies trends in system behavior

### 🎯 MCP Integration
- **Claude Desktop Compatible**: Works seamlessly with Claude Desktop
- **Resource Access**: Provides easy access to reports and insights
- **Tool Integration**: Rich set of tools for querying and management
- **Real-time Updates**: Live monitoring and reporting

## 📦 Installation

### Prerequisites
- Node.js 18+ with npm
- Redis server (AutoBot's Redis instance at 172.16.168.23:6379)
- Claude Desktop application
- AutoBot system running

### Quick Install
```bash
# From AutoBot root directory
cd mcp-autobot-tracker
chmod +x install.sh
./install.sh
```

### Manual Installation
```bash
# Install dependencies
npm install

# Build the project
npm run build

# Create configuration
cp config.example.json config.json

# Configure Claude Desktop (see Configuration section)
```

## ⚙️ Configuration

### Claude Desktop Setup
The installer automatically configures Claude Desktop. Manual configuration:

**Location**: `~/.config/Claude/claude_desktop_config.json` (Linux) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)

```json
{
    "mcpServers": {
        "autobot-tracker": {
            "command": "node",
            "args": ["/path/to/mcp-autobot-tracker/dist/index.js"],
            "env": {
                "REDIS_HOST": "172.16.168.23",
                "REDIS_PORT": "6379"
            }
        }
    }
}
```

### Environment Variables
- `REDIS_HOST`: Redis server host (default: 172.16.168.23)
- `REDIS_PORT`: Redis server port (default: 6379)
- `NODE_ENV`: Environment mode (development/production)

## 🛠️ Usage

### Starting the Service
```bash
# Production mode (systemd service)
./start-mcp-tracker.sh

# Development mode
./dev-run.sh
```

### Management Commands
```bash
./start-mcp-tracker.sh    # Start the service
./stop-mcp-tracker.sh     # Stop the service  
./status-mcp-tracker.sh   # Check service status
./logs-mcp-tracker.sh     # View live logs
./test-mcp-tracker.sh     # Run system tests
```

### Using in Claude Desktop

Once configured, you can use these tools in Claude Desktop:

#### **Ingesting Chat Conversations**
```
Use the "ingest_chat" tool to feed a conversation:
- session_id: unique identifier for the chat
- messages: array of message objects with role, content, timestamp
```

#### **Getting Unfinished Tasks**
```
Use "get_unfinished_tasks" to see all incomplete tasks:
- Optionally filter by session_id
- Shows task description, status, and correlations
```

#### **Analyzing Recent Activity**
```
Use "get_recent_activity" to see what's happening:
- Specify time range (default: last 60 minutes)
- Shows errors, warnings, and new tasks
```

#### **System Health Monitoring**
```
Use "get_system_health" for current system status:
- Service health checks
- Resource usage
- System alerts
```

#### **Knowledge Insights**
```
Use "analyze_and_generate_knowledge" to generate insights:
- Analyzes patterns in errors and tasks
- Creates actionable knowledge entries
- Integrates with AutoBot's knowledge base
```

### Resource Access
The MCP server provides these resources:
- `autobot://unfinished-tasks` - All unfinished tasks
- `autobot://error-correlations` - Errors with correlations  
- `autobot://recent-activity` - Recent monitoring data
- `autobot://system-health` - Current system health
- `autobot://summary-report` - Comprehensive report

## 🗃️ Database Structure

### Redis Database Layout
- **DB 10**: MCP tracking data (tasks, errors, correlations)
- **DB 1**: AutoBot knowledge base integration
- **DB 0**: Main AutoBot data (read-only access)

### Data Types Stored
- **Tasks**: Extracted from conversations and logs
- **Errors**: Detected errors with severity and component mapping
- **Insights**: Generated knowledge from pattern analysis
- **Health Data**: System health checks and metrics
- **Correlations**: Links between tasks, errors, and insights

## 🔧 Architecture

### Components
1. **Chat Tracker**: Ingests and analyzes conversations
2. **Background Monitor**: Watches logs and Docker containers
3. **Knowledge Integration**: Generates insights and patterns
4. **MCP Server**: Provides tools and resources to Claude

### Data Flow
```
Claude Chats → Task/Error Extraction → Pattern Analysis → Knowledge Generation
     ↓                                        ↑
System Logs → Background Monitor → Redis Storage → MCP Resources
```

### Monitoring Targets
- AutoBot backend logs (`/data/logs/backend.log`)
- Frontend logs (`/data/logs/frontend.log`) 
- Redis logs (`/data/logs/redis.log`)
- Docker container logs (all AutoBot services)
- System health metrics

## 🧪 Testing

### Run Tests
```bash
./test-mcp-tracker.sh
```

### Manual Testing
```bash
# Test Redis connection
redis-cli -h 172.16.168.23 -p 6379 ping

# Test service
systemctl status autobot-mcp-tracker.service

# Test in Claude Desktop
# Use any of the MCP tools listed above
```

## 🐛 Troubleshooting

### Common Issues

**Service won't start**
```bash
# Check logs
journalctl -u autobot-mcp-tracker.service -f

# Check Redis connection
redis-cli -h 172.16.168.23 -p 6379 ping
```

**Claude Desktop not seeing MCP server**
- Restart Claude Desktop after configuration changes
- Check config file syntax with `jq . ~/.config/Claude/claude_desktop_config.json`
- Verify file paths in configuration

**No log data being captured**
- Ensure log files exist and are readable
- Check file permissions
- Verify Docker containers are running

**Knowledge insights not generating**
- Ensure sufficient data (3+ errors/tasks for patterns)
- Check Redis DB 1 permissions
- Verify background monitoring is active

### Debug Mode
```bash
export NODE_ENV=development
./dev-run.sh
```

## 📊 Monitoring & Metrics

### Key Metrics Tracked
- **Error Rates**: By component and severity
- **Task Completion**: Success rates and patterns  
- **System Health**: Service uptime and resource usage
- **Knowledge Generation**: Insight creation and confidence scores

### Reports Generated
- **Summary Reports**: Overall system status
- **Pattern Analysis**: Recurring issues and trends
- **Correlation Reports**: Links between errors and tasks
- **Health Reports**: System stability and performance

## 🔐 Security Considerations

- **Redis Access**: Uses read-only access where possible
- **Log Privacy**: Sanitizes sensitive information
- **Process Isolation**: Runs as unprivileged user
- **Resource Limits**: Prevents excessive resource usage

## 🤝 Contributing

This MCP server is designed to evolve with AutoBot. Key extension points:

- **New Log Sources**: Add monitoring for additional log files
- **Enhanced Patterns**: Improve task/error extraction patterns
- **Additional Insights**: Expand knowledge generation algorithms
- **Integration Points**: Add connections to other AutoBot systems

## 📝 License

Part of the AutoBot project. See main project license.

---

## 🎯 Quick Start Example

1. **Install**: Run `./install.sh` from AutoBot directory
2. **Start**: Execute `./start-mcp-tracker.sh`
3. **Test**: Run `./test-mcp-tracker.sh` 
4. **Use**: Open Claude Desktop and try:
   - "Get recent activity from AutoBot monitoring"
   - "Show me unfinished tasks"
   - "Analyze patterns and generate knowledge insights"

The MCP tracker will begin monitoring AutoBot immediately and will have useful insights within minutes of operation.