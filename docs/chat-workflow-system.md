# AutoBot Chat Workflow System Documentation

## Overview

The AutoBot Chat Workflow System implements a comprehensive message processing pipeline that handles user queries through knowledge base lookup, task classification, and user-controlled research workflows. The system is designed to never hallucinate information and always involve users in research decisions.

## Architecture

### Core Components

1. **KB/Librarian** - Single function that manages the knowledge base and local documentation
2. **Research Agent** - Subordinate agent called by librarian for web-based research (requires user involvement)
3. **Classification Agent** - Determines message type and complexity
4. **MCP Integration** - Provides access to manual pages and system documentation
5. **File Search Fallback** - Simple grep-like search when KB unavailable

### Message Flow

```
User Message → Classification → Knowledge Search → Research Decision → Response Generation
```

## Workflow Process

### Step 1: Message Classification

Messages are classified into types:
- `GENERAL_QUERY` - General questions and conversations
- `DESKTOP_TASK` - GUI application and interface tasks
- `TERMINAL_TASK` - Command line and shell operations
- `SYSTEM_TASK` - System administration and configuration
- `RESEARCH_NEEDED` - Complex queries requiring external research

### Step 2: Knowledge Search

The system searches for relevant information in this order:

1. **Knowledge Base** (if enabled)
   - Semantic search through indexed documents
   - Confidence scoring and result filtering
   - Timeout protection (5 seconds max)

2. **File Search Fallback** (if KB unavailable)
   - Simple text search through documentation files
   - Pattern-based file selection by message type
   - Limited to prevent performance issues

### Step 3: Knowledge Status Assessment

Results are categorized as:
- `FOUND` - Sufficient high-confidence information available
- `PARTIAL` - Some relevant information found, but incomplete
- `MISSING` - No relevant information in knowledge base
- `RESEARCH_REQUIRED` - External research needed for current information

### Step 4: Research Decision (User-Controlled)

When knowledge is missing or insufficient, the system follows this dialogue:

```
AutoBot: "I don't have specific knowledge about this topic in my knowledge base.

Do you want me to research this topic? (yes/no)

If you answer 'no', I'll end this workflow here. If you answer 'yes', I can help research this topic with your guidance."
```

#### User Response Handling

**User says "Yes":**
```
AutoBot: "Great! I'll help you research this topic. Please provide more details about what specifically you'd like me to look into, or guide me to specific sources you'd like me to check."
```

**User says "No":**
```
AutoBot: "Understood. I don't have information about this topic in my knowledge base, so I'll end this workflow here. Feel free to ask me about something else!"
```

### Step 5: Response Generation

Based on knowledge status, the system generates appropriate responses:

- **Knowledge Found**: Provides comprehensive response with source attribution
- **Partial Knowledge**: Indicates limitations and suggests additional information sources
- **No Knowledge**: Follows research dialogue or ends workflow per user decision

## Configuration

### Settings Files

Configuration is managed through:
- `config/config.yaml` - Base configuration
- `config/settings.json` - User settings override

### Key Settings

```yaml
knowledge_base:
  enabled: true                    # Enable/disable KB functionality
  semantic_chunking:
    enabled: true                  # Enable semantic document chunking
    percentile_threshold: 95.0     # Similarity threshold

web_research:
  enabled: true                    # Enable/disable research agent
  timeout_seconds: 30             # Research operation timeout
  max_results: 5                  # Maximum research results
  fallback_to_file_search: true   # Use file search when KB unavailable
```

## Error Handling

### Timeout Protection

- Classification: 10 seconds maximum
- Knowledge search: 5 seconds maximum  
- Research operations: 15 seconds maximum
- Response generation: 15 seconds maximum

### Fallback Mechanisms

1. **Classification failure** → Default to GENERAL_QUERY
2. **KB search failure** → Fall back to file search
3. **Research agent unavailable** → Inform user of limitation
4. **LLM response failure** → Provide generic fallback response

### Research Agent Status

**When Disabled in Settings:**
```
"Currently, the research agent is disabled in settings. I can only provide information from my local knowledge base and documentation files."
```

**When Unavailable/Error:**
```
"Currently, the research agent is not available. I can only provide information from my local knowledge base and documentation files."
```

## API Integration

### Chat Endpoint Usage

The workflow integrates with the main chat API at `/api/chats/{chat_id}/message`:

```python
from src.chat_workflow_manager import process_chat_message

# Process message through complete workflow
result = await process_chat_message(
    user_message="How do I configure SSH?",
    chat_id="unique-chat-id",
    conversation=None  # Optional existing conversation
)

# Access results
response = result.response              # Generated response text
knowledge_status = result.knowledge_status  # FOUND/PARTIAL/MISSING/RESEARCH_REQUIRED
message_type = result.message_type      # Classified message type
sources = result.sources               # Attribution sources
processing_time = result.processing_time # Performance metrics
```

### Response Object

```python
@dataclass
class ChatWorkflowResult:
    response: str                           # Generated response
    message_type: MessageType              # Message classification
    knowledge_status: KnowledgeStatus      # Knowledge availability
    kb_results: List[Dict[str, Any]]       # Knowledge base results
    research_results: Optional[Dict]       # Research results (if any)
    sources: List[Dict[str, Any]]          # Source attributions
    processing_time: float                 # Processing duration
    librarian_engaged: bool               # Whether librarian was used
    mcp_used: bool                        # Whether MCP was used
    error: Optional[str]                   # Error message (if any)
```

## MCP Integration

### Manual Page Lookups

For terminal and system tasks, the system can query MCP servers for:
- Linux manual pages (`man` command documentation)
- Help text for command-line tools
- System administration guides

### Usage Example

```python
from src.mcp_manual_integration import lookup_system_manual

# Look up command documentation
manual_info = await lookup_system_manual("ssh configuration")
```

## Performance Optimizations

### Timeout Management

All operations have aggressive timeouts to prevent system hanging:
- Quick classification prevents workflow delays
- KB search limited to prevent blocking
- Research operations bounded by user expectations

### Memory Management

- KB results limited to 5 maximum entries
- File content truncated to prevent memory issues
- Source attribution capped to essential information

### Concurrent Processing

- Classification and knowledge search can run in parallel
- Multiple file searches executed concurrently
- Error isolation prevents single failures from blocking workflow

## Usage Examples

### Example 1: Knowledge Available

```
User: "How do I restart a systemd service?"

AutoBot: "To restart a systemd service, you can use the following command:

sudo systemctl restart [service-name]

For example:
sudo systemctl restart nginx
sudo systemctl restart ssh

You can also check the status with:
sudo systemctl status [service-name]

This information comes from the system administration documentation in the knowledge base."
```

### Example 2: Knowledge Missing - Research Offered

```
User: "What are the latest features in Python 3.13?"

AutoBot: "I don't have specific knowledge about this topic in my knowledge base.

Do you want me to research this topic? (yes/no)

If you answer 'no', I'll end this workflow here. If you answer 'yes', I can help research this topic with your guidance."

User: "yes"

AutoBot: "Great! I'll help you research this topic. Please provide more details about what specifically you'd like me to look into, or guide me to specific sources you'd like me to check."
```

### Example 3: Research Declined

```
User: "What's the weather like in Tokyo?"

AutoBot: "I don't have specific knowledge about this topic in my knowledge base.

Do you want me to research this topic? (yes/no)

If you answer 'no', I'll end this workflow here. If you answer 'yes', I can help research this topic with your guidance."

User: "no"

AutoBot: "Understood. I don't have information about this topic in my knowledge base, so I'll end this workflow here. Feel free to ask me about something else!"
```

## Testing

### Test Scripts

Several test scripts are available:

1. **`test_chat_simple.py`** - Basic workflow functionality
2. **`test_research_dialogue.py`** - Yes/no research dialogue
3. **`test_research_disabled.py`** - Behavior when research disabled
4. **`demo_research_workflow.py`** - Complete workflow demonstration

### Running Tests

```bash
# Basic functionality test
python3 test_chat_simple.py

# Research dialogue test
python3 test_research_dialogue.py

# Demo all scenarios
python3 demo_research_workflow.py
```

## Troubleshooting

### Common Issues

1. **Chat hanging/timeout**: Check KB initialization status and timeout settings
2. **No research option**: Verify `web_research.enabled: true` in settings
3. **Classification failures**: Ensure Ollama is running and accessible
4. **KB search errors**: Check knowledge base initialization and index status

### Debug Logging

Enable debug logging to trace workflow execution:

```yaml
logging:
  log_level: debug
  debug_logging: true
```

### Performance Monitoring

Monitor processing times through the workflow result object:
- Classification time should be < 5 seconds
- Knowledge search should be < 5 seconds  
- Total workflow should be < 20 seconds

## Security Considerations

### Input Validation

- User messages are sanitized before processing
- File paths validated to prevent directory traversal
- Research queries filtered to prevent malicious injection

### Privacy Protection

- No automatic web research without user consent
- Local knowledge base prioritized over external sources
- User control over all research activities

### Rate Limiting

- Timeouts prevent resource exhaustion
- Concurrent operation limits prevent system overload
- Graceful degradation when services unavailable

## Future Enhancements

### Planned Features

1. **Enhanced Research Integration** - More sophisticated user-guided research workflows
2. **Context Retention** - Remember previous research decisions within conversation
3. **Source Verification** - Automatic fact-checking for research results
4. **Personalized Knowledge** - User-specific knowledge base sections

### Extension Points

- Custom message type handlers
- Additional MCP server integrations
- Pluggable research backends
- Custom knowledge source adapters

---

*This documentation covers AutoBot Chat Workflow System v1.0. For updates and additional information, see the project's CLAUDE.md file.*