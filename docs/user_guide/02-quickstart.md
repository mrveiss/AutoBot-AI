# Quick Start Guide

## First Steps

Once AutoBot is installed and running, follow these steps to get started:

### 1. Access the Control Panel
Open your web browser and navigate to:
```
http://localhost:8001
```

### 2. Configure Your LLM
1. Click the settings icon or type `/settings open`
2. Navigate to **LLM Configuration**
3. Choose your preferred backend:
   - **Ollama** (recommended for local inference)
   - **OpenAI API** (cloud-based)
   - **LM Studio** (local with GUI)

#### For Ollama Setup:
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model
ollama pull phi3:mini
```

### 3. Set Up Knowledge Base
1. In settings, navigate to **Knowledge Base Configuration**
2. Configure storage location (local or network)
3. Test the connection

### 4. Give Your First Command
In the main interface, try these example commands:

```
Create a simple Python script that prints "Hello, AutoBot!"
```

```
Search my knowledge base for information about Python
```

```
/knowledge add Python is a high-level programming language
```

## Basic Commands

### Chat Commands
- Direct questions or instructions
- `/help` - Show available commands
- `/status` - Display current system status

### Knowledge Management
- `/knowledge add <content>` - Add information
- `/knowledge search <query>` - Search knowledge base
- `/knowledge list` - Show all entries

### System Commands
- `/settings open` - Open settings panel
- `/workers list` - Show connected worker nodes
- `/logs show` - Display recent logs

## Understanding the Interface

### Event Stream
The main area shows a real-time stream of:
- 💬 User messages
- 🤖 Agent responses
- 🔧 Tool executions
- 📊 System events

### Status Indicators
- 🟢 **Active** - Agent is processing
- 🟡 **Idle** - Waiting for input
- 🔴 **Error** - Issue requires attention

## Next Steps

1. **Upload Documents**: Use the Knowledge Manager to upload PDFs, text files, etc.
2. **Configure Workers**: Set up additional nodes for distributed processing
3. **Customize Settings**: Adjust LLM parameters, enable GPU acceleration
4. **Explore Tools**: Try file operations, web scraping, system commands

## Tips for Effective Use

1. **Be Specific**: Clear, detailed instructions yield better results
2. **Use Context**: Reference previous conversations and knowledge
3. **Break Down Complex Tasks**: Large goals work better as smaller steps
4. **Monitor Logs**: Check logs for troubleshooting and optimization

## Safety Notes

- AutoBot has access to your system - use appropriate permissions
- Review commands before execution in sensitive environments
- Keep your API keys secure
- Regular backups of your knowledge base are recommended
