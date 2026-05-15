# Quick Start Guide

Get up and running with AutoBot in minutes. This guide assumes you have already completed the [Installation Guide](01-installation.md).

## First Launch

### Start AutoBot Services

```bash
# Navigate to your AutoBot directory
cd AutoBot-AI

# Launch all services (backend + frontend)
./run_agent.sh
```

**Expected output:**
```
🚀 Starting AutoBot services...
✓ Backend server starting on http://localhost:8001
✓ Frontend development server on http://localhost:5173
✓ Redis connection established
✓ LLM provider connected (Ollama: tinyllama:latest)
✓ Knowledge base initialized
✓ All systems operational

🌐 Access AutoBot at: http://localhost:5173
📚 API Documentation: http://localhost:8001/docs
```

### Access the Web Interface

Open your browser and navigate to **http://localhost:5173**

## Interface Overview

### Main Dashboard

The AutoBot interface consists of several key areas:

1. **Chat Area** (center): Real-time conversation and event stream
2. **Sidebar** (left): Navigation and system status
3. **Status Bar** (top): Connection indicators and system health
4. **Settings Panel** (accessible via gear icon): Configuration options

### Status Indicators

- 🟢 **Connected**: All services operational
- 🟡 **Processing**: Agent is working on a task
- 🔴 **Error**: Issue requires attention
- ⚡ **Offline**: Service unavailable

## Your First Interactions

### Basic Chat

Try these simple interactions to get familiar with AutoBot:

```
Hello! What can you help me with?
```

```
What's the current time and date?
```

```
List the files in the current directory
```

### System Commands

AutoBot can execute system commands with your approval:

```
Show me system information
```

```
Create a simple text file with "Hello AutoBot" content
```

```
Check disk space usage
```

**Note**: You'll be prompted to approve system commands before execution.

### Knowledge Base Operations

Add information to AutoBot's knowledge base:

```
Remember that Python is my preferred programming language
```

Search the knowledge base:

```
What do you know about Python?
```

Upload documents via drag-and-drop into the chat area or use:

```
Help me upload a document to your knowledge base
```

## Essential Features

### File Management

**Upload Files:**
- Drag and drop files directly into the chat area
- Or click the 📎 attachment icon
- Supported formats: PDF, DOCX, TXT, CSV, MD, JSON

**Browse Files:**
- Access the file browser from the sidebar
- View, download, and organize uploaded files
- Secure sandboxed environment

### Knowledge Templates

AutoBot includes professional templates for structured knowledge entry:

1. **Research Article Template**: For documenting research findings
2. **Meeting Notes Template**: For meeting summaries and action items
3. **Bug Report Template**: For software issue documentation
4. **Learning Notes Template**: For educational content and tutorials

**Access templates:**
- Navigate to Knowledge Manager in the sidebar
- Click "Template Gallery"
- Select and apply templates with one click

### Settings Configuration

Access settings via the gear icon (⚙️) or type:
```
/settings
```

**Key settings to configure:**

1. **LLM Provider**: Choose between Ollama, OpenAI, Anthropic
2. **Model Selection**: Pick your preferred AI model
3. **Temperature**: Adjust creativity vs consistency (0.1-1.0)
4. **System Behavior**: Configure autonomy level and permissions
5. **Hardware**: Enable GPU acceleration if available

## Common Tasks

### Development Tasks

**Create a Python script:**
```
Create a Python script that reads a CSV file and generates a summary report
```

**Code review:**
```
Review this Python code for best practices and potential improvements:
[paste your code here]
```

**Debug assistance:**
```
I'm getting this error in my Python script: [error message]
Can you help me fix it?
```

### Data Analysis Tasks

**Analyze uploaded data:**
```
Analyze the sales data I just uploaded and provide insights
```

**Generate reports:**
```
Create a summary report of the customer feedback data in my knowledge base
```

### Research and Information Tasks

**Web research:**
```
Research the latest trends in machine learning and add the findings to my knowledge base
```

**Document analysis:**
```
Summarize the key points from the research paper I uploaded
```

### System Administration

**Monitor system:**
```
Show me current system resource usage
```

**Manage processes:**
```
List running processes and their CPU usage
```

**File operations:**
```
Organize the files in my downloads folder by file type
```

## Slash Commands

AutoBot supports various slash commands for quick actions:

| Command | Purpose | Example |
|---------|---------|---------|
| `/help` | Show available commands | `/help` |
| `/status` | Display system status | `/status` |
| `/settings` | Open settings panel | `/settings` |
| `/clear` | Clear chat history | `/clear` |
| `/new` | Start new chat session | `/new` |
| `/save` | Save current session | `/save session_name` |
| `/load` | Load saved session | `/load session_name` |
| `/knowledge` | Knowledge base operations | `/knowledge search python` |
| `/files` | File operations | `/files list` |

## Best Practices

### Effective Prompting

1. **Be Specific**: Provide clear, detailed instructions
   ```
   ✓ Good: "Create a Python function that validates email addresses using regex"
   ✗ Vague: "Make a function"
   ```

2. **Provide Context**: Reference previous conversations and uploaded files
   ```
   ✓ "Based on the sales data I uploaded earlier, create a visualization"
   ✗ "Create a chart"
   ```

3. **Break Down Complex Tasks**: Large goals work better as smaller steps
   ```
   ✓ "First analyze the data, then create visualizations, finally generate a report"
   ✗ "Do a complete data analysis project"
   ```

### Knowledge Management

1. **Organize Information**: Use templates for structured data entry
2. **Regular Updates**: Keep your knowledge base current
3. **Tag Content**: Use descriptive titles and metadata
4. **Backup Data**: Export knowledge base regularly

### Security Considerations

1. **Review Commands**: Always review system commands before approval
2. **Sensitive Data**: Be cautious with personal or confidential information
3. **API Keys**: Store API keys securely in environment variables
4. **File Permissions**: Monitor file system access and permissions

## Monitoring and Maintenance

### System Health

Monitor AutoBot's health via:

- **Dashboard Status**: Check connection indicators
- **Health Endpoint**: Visit http://localhost:8001/api/health
- **Log Files**: Check `logs/autobot.log` for issues

### Performance Optimization

1. **Model Selection**: Use lighter models (tinyllama) for simple tasks
2. **GPU Acceleration**: Enable GPU if available for better performance
3. **Memory Management**: Monitor RAM usage with large knowledge bases
4. **Regular Cleanup**: Clean up old chat sessions and temporary files

### Backup and Recovery

**Export Knowledge Base:**
```
Export my complete knowledge base
```

**Backup Configuration:**
```bash
# Backup configuration
cp config/config.yaml config/config.backup.yaml

# Backup data directory
tar -czf autobot-backup-$(date +%Y%m%d).tar.gz data/
```

## Getting Help

### Built-in Help

- Type `/help` for available commands
- Visit http://localhost:8001/docs for API documentation
- Check system status with `/status`

### Troubleshooting

If you encounter issues:

1. **Check Status**: Use `/status` to identify problems
2. **Review Logs**: Check `logs/autobot.log` for error messages
3. **Restart Services**: `./run_agent.sh` to restart
4. **Configuration**: Verify `config/config.yaml` settings

### Community Support

- **GitHub Issues**: Report bugs and request features
- **Documentation**: Comprehensive guides in `docs/` directory
- **API Reference**: Complete API documentation available

## Next Steps

Now that you're familiar with the basics:

1. **Explore Advanced Features**: Knowledge templates, file management, system automation
2. **Customize Configuration**: Optimize settings for your workflow
3. **Build Knowledge Base**: Upload documents and organize information
4. **Integrate with Tools**: Connect to external services and APIs
5. **Automate Tasks**: Create workflows for repetitive operations

### Advanced Guides

- **[Configuration Guide](../configuration.md)**: Detailed configuration options
- **[API Documentation](../backend_api.md)**: Complete REST API reference
- **[Troubleshooting Guide](04-troubleshooting.md)**: Common issues and solutions

---

**You're ready to use AutoBot!** Start with simple tasks and gradually explore more advanced features. 🚀
