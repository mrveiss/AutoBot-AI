# Thinking Tools Configuration Guide

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
**Last Updated**: 2025-01-24

## Overview

AutoBot has two powerful MCP (Model Context Protocol) thinking tools that enable structured, multi-step reasoning:

1. **Sequential Thinking** (`mcp__sequential-thinking__sequentialthinking`)
2. **Structured Thinking / Chain of Thought** (`mcp__structured-thinking__chain_of_thought`)

This guide explains how to ensure these tools are ALWAYS used for complex reasoning tasks.

---

## 🚨 Mandatory Usage Policy

**RULE**: These tools MUST be used for ANY task requiring more than 2 steps of reasoning.

### When to Use Thinking Tools:

✅ **Always Use For:**
- Complex problem analysis
- Multi-step reasoning
- Planning and decision-making
- Architectural decisions
- Debugging complex issues
- Analyzing tradeoffs
- Problem decomposition
- Solution verification
- Hypothesis testing
- Code refactoring decisions

❌ **Not Needed For:**
- Simple factual questions
- Single-step commands
- Direct information retrieval
- Basic calculations

---

## Tool Descriptions

### 1. Sequential Thinking

**MCP Tool**: `mcp__sequential-thinking__sequentialthinking`

**Purpose**: Dynamic, reflective problem-solving through structured thinking process.

**Key Features**:
- Adjustable total_thoughts estimate
- Can revise previous thoughts
- Support for branching logic
- Handles uncertainty and exploration
- No rigid linear progression required

**Use Cases**:
- Breaking down complex problems
- Planning with room for revision
- Analysis that might need course correction
- Problems where scope isn't initially clear
- Multi-step solutions
- Context-dependent reasoning

**Parameters**:
```json
{
  "thought": "Current thinking step",
  "nextThoughtNeeded": true/false,
  "thoughtNumber": 1,
  "totalThoughts": 5,
  "isRevision": false,
  "revisesThought": null,
  "branchFromThought": null,
  "branchId": null,
  "needsMoreThoughts": false
}
```

### 2. Structured Thinking / Chain of Thought

**MCP Tool**: `mcp__structured-thinking__chain_of_thought`

**Purpose**: Comprehensive framework with hypothesis generation and verification.

**Key Features**:
- Generate solution hypotheses
- Verify hypotheses through reasoning
- Repeat until satisfied
- Provides correct final answer
- Filters irrelevant information
- Maintains context over multiple steps

**Use Cases**:
- Problems requiring hypothesis testing
- Multi-step solutions with validation
- Tasks needing context preservation
- Complex reasoning chains
- Solution verification
- Iterative problem solving

**Parameters**:
```json
{
  "thought": "Current thinking step and analysis",
  "nextThoughtNeeded": true/false,
  "thoughtNumber": 1,
  "totalThoughts": 3,
  "isRevision": false,
  "revisesThought": null,
  "branchFromThought": null,
  "branchId": null,
  "needsMoreThoughts": false,
  "commandSelection": {
    "type": "command|skip|skip_reason",
    "command": "command_name",
    "reason": "skip reason"
  },
  "agentSelection": {
    "type": "agents|skip|skip_reason",
    "agents": ["agent1", "agent2"],
    "reason": "skip reason"
  }
}
```

---

## Configuration Steps

### Step 1: System Prompt Configuration

**File**: `prompts/chat/system_prompt.md`

The system prompt has been updated to include mandatory thinking tool usage instructions. Section added:

```markdown
### Reasoning and Thinking Tools (MANDATORY for Complex Problems)

🚨 MANDATORY USAGE POLICY:
- For ANY task requiring more than 2 steps of reasoning → Use thinking tools
- For architectural decisions → Use thinking tools
- For debugging complex issues → Use thinking tools
- For analyzing tradeoffs → Use thinking tools
```

**Location**: Lines 23-92 in system_prompt.md

### Step 2: Verify MCP Tools Are Registered

**Backend API Endpoints**:
```bash
# Sequential Thinking MCP
autobot-user-backend/api/sequential_thinking_mcp.py

# Structured Thinking MCP
autobot-user-backend/api/structured_thinking_mcp.py
```

**Check Tool Registration**:
```bash
# Test sequential thinking endpoint
curl http://172.16.168.20:8001/api/mcp/sequential-thinking/tools

# Test structured thinking endpoint
curl http://172.16.168.20:8001/api/mcp/structured-thinking/tools
```

### Step 3: Ensure Tools Are Available to LLM

**Method 1: System Prompt Inclusion** ✅ (Already Done)
- Tools are described in system prompt
- Instructions mandate their use
- LLM is aware they exist

**Method 2: Explicit Tool List** (Optional Enhancement)
- Configure LLM interface to always include thinking tools in available_tools list
- File: `src/llm_interface.py`
- Method: `_setup_system_prompt()` or `query()` method

**Example Enhancement**:
```python
# In llm_interface.py, around line 670
def query(self, ...):
    # Add thinking tools to available_tools if not present
    if available_tools is None:
        available_tools = []

    thinking_tools = [
        'mcp__sequential-thinking__sequentialthinking',
        'mcp__structured-thinking__chain_of_thought'
    ]

    for tool in thinking_tools:
        if tool not in available_tools:
            available_tools.append(tool)

    # Continue with rest of method...
```

### Step 4: Model Configuration

**Ensure Mistral is Default Model** (Required for Tool Calling):
```bash
# In .env file:
AUTOBOT_DEFAULT_LLM_MODEL=mistral:7b-instruct
```

**Why Mistral?**
- ✅ Excellent function/tool calling capabilities
- ✅ Strong instruction following
- ✅ Better reasoning than smaller models (llama3.2:1b)
- ✅ Reliable with complex tool invocations

**Verify**:
```bash
grep "AUTOBOT_DEFAULT_LLM_MODEL" .env
# Should output: AUTOBOT_DEFAULT_LLM_MODEL=mistral:7b-instruct
```

---

## Verification

### Test 1: Check System Prompt Loaded
```bash
# Backend should load updated prompt on startup
tail -f logs/backend.log | grep "prompt"
```

### Test 2: Ask Complex Question
```
User: "How should we optimize the Redis connection pooling for better performance?"

Expected: LLM uses thinking tool to:
1. Analyze current bottlenecks
2. Evaluate pooling strategies
3. Consider trade-offs
4. Propose solution with rationale
```

### Test 3: Check MCP Tool Invocation
```bash
# Monitor backend logs for MCP tool calls
tail -f logs/backend.log | grep "mcp__.*thinking"
```

---

## Usage Examples

### Example 1: Complex Problem Analysis

**User Query**: "How should we refactor the config system?"

**Expected LLM Behavior**:
```
[THINKING TOOL START]
Thought 1: Identify current config system issues
  - Multiple competing implementations (config.py, unified_config.py, config_helper.py)
  - Inconsistent access patterns
  - Duplicate functionality

Thought 2: Analyze requirements
  - Need centralized configuration
  - Type safety required
  - Validation framework needed
  - Environment variable support

Thought 3: Evaluate approaches
  - Approach A: Extend unified_config.py (best architecture)
  - Approach B: Create new system (unnecessary work)
  - Approach C: Use config_helper.py (lacks type safety)

Thought 4: Verify decision
  - unified_config.py has: Type hints, validation, Pydantic models
  - Best choice: Consolidate into unified_config.py

Next thought needed: false
[THINKING TOOL END]

Based on my analysis, I recommend consolidating into unified_config.py because...
```

### Example 2: Multi-Step Planning

**User Query**: "Plan the implementation of the new feature X"

**Expected LLM Behavior**:
```
[THINKING TOOL START - Sequential Thinking]
Thought 1: Break down feature requirements
Thought 2: Identify dependencies
Thought 3: Plan implementation phases
Thought 4: Consider potential blockers
Thought 5 (revision of 3): Adjusted phases based on dependencies
Thought 6: Final implementation plan

Total thoughts adjusted from 5 to 6 (added clarity step)
[THINKING TOOL END]

Here's the implementation plan...
```

---

## Troubleshooting

### Issue: LLM Not Using Thinking Tools

**Possible Causes**:
1. System prompt not loaded
2. Model lacks tool-calling capability
3. Prompt doesn't emphasize mandatory usage

**Solutions**:
1. **Restart backend** to reload prompt:
   ```bash
   bash run_autobot.sh --restart
   ```

2. **Verify model is Mistral**:
   ```bash
   grep "AUTOBOT_DEFAULT_LLM_MODEL" .env
   # Should be: mistral:7b-instruct
   ```

3. **Check system prompt loaded**:
   ```bash
   # Check backend logs
   grep "system_prompt" logs/backend.log
   ```

4. **Strengthen enforcement** in prompt (if needed):
   - Add more explicit examples
   - Increase emphasis on mandatory usage
   - Add negative examples (what NOT to do)

### Issue: Thinking Tool Errors

**Check MCP Server Status**:
```bash
# Test endpoints
curl http://172.16.168.20:8001/api/mcp/sequential-thinking/tools
curl http://172.16.168.20:8001/api/mcp/structured-thinking/tools
```

**Check Backend Logs**:
```bash
tail -100 logs/backend.log | grep -i "thinking\|mcp"
```

### Issue: Incomplete Thinking Process

**Symptoms**:
- LLM stops thinking prematurely
- Doesn't revise thoughts when needed
- Skips verification step

**Solution**:
- Add explicit instruction to system prompt:
  ```markdown
  **MANDATORY COMPLETION CRITERIA:**
  - Continue thinking until solution is verified
  - Revise thoughts when new information emerges
  - Don't stop until confidence level is high
  ```

---

## Monitoring and Metrics

### Track Thinking Tool Usage

**Add Logging** (optional enhancement):
```python
# In autobot-user-backend/api/sequential_thinking_mcp.py or structured_thinking_mcp.py

@router.post("/think")
async def process_thinking(...):
    logger.info(f"[THINKING TOOL] Started: {tool_name}")
    logger.info(f"[THINKING TOOL] Thought {thoughtNumber}/{totalThoughts}")

    # Process thinking...

    logger.info(f"[THINKING TOOL] Completed: {thoughtNumber} thoughts")
```

**Metrics to Track**:
- Number of thinking tool invocations per session
- Average thoughts per problem
- Revision frequency
- Problem complexity correlation

---

## Best Practices

### For System Administrators:

1. **Always use Mistral or better** - Smaller models lack tool-calling reliability
2. **Monitor thinking tool usage** - Low usage may indicate prompt issues
3. **Restart backend after prompt changes** - Prompts are loaded at startup
4. **Keep thinking tools registered** - Check MCP endpoints are active

### For Prompt Engineers:

1. **Be explicit about mandatory usage** - Don't assume LLM will use tools
2. **Provide clear examples** - Show both correct and incorrect behavior
3. **Emphasize multi-step reasoning** - Trigger word: "complex", "analyze", "plan"
4. **Include verification steps** - Mandate checking work before finalizing

### For Developers:

1. **Log thinking tool invocations** - Helps debug reasoning issues
2. **Preserve thinking context** - Don't truncate thinking tool output
3. **Test with complex problems** - Simple queries won't trigger tools
4. **Monitor for regressions** - Tool usage should remain high

---

## Future Enhancements

### Automatic Tool Injection

**Idea**: Automatically inject thinking tools into LLM available_tools list.

**Implementation**:
```python
# In src/llm_interface.py

MANDATORY_TOOLS = [
    'mcp__sequential-thinking__sequentialthinking',
    'mcp__structured-thinking__chain_of_thought'
]

def _ensure_thinking_tools(self, available_tools):
    """Ensure thinking tools are always available"""
    if available_tools is None:
        available_tools = []

    for tool in MANDATORY_TOOLS:
        if tool not in available_tools:
            available_tools.append(tool)

    return available_tools
```

### Thinking Quality Metrics

**Idea**: Track thinking quality metrics to improve prompts.

**Metrics**:
- Thought depth (avg thoughts per problem)
- Revision rate (how often thoughts are revised)
- Verification completeness (hypothesis testing frequency)
- Solution accuracy (track if thinking led to correct solutions)

### Adaptive Thinking Depth

**Idea**: Automatically adjust thinking depth based on problem complexity.

**Heuristics**:
- Word count in user query
- Presence of keywords: "complex", "optimize", "architect"
- Historical data: Similar problems required N thoughts
- User feedback: Was solution satisfactory?

---

## References

### Documentation Files:
- System Prompt: `prompts/chat/system_prompt.md`
- Sequential Thinking API: `autobot-user-backend/api/sequential_thinking_mcp.py`
- Structured Thinking API: `autobot-user-backend/api/structured_thinking_mcp.py`
- LLM Interface: `src/llm_interface.py`

### MCP Tools:
- Sequential Thinking: `mcp__sequential-thinking__sequentialthinking`
- Structured Thinking: `mcp__structured-thinking__chain_of_thought`

### Configuration:
- Environment: `.env` (AUTOBOT_DEFAULT_LLM_MODEL)
- Prompts: `prompts/chat/system_prompt.md`
- Backend: `backend/main.py` (router registration)

---

## Support

For issues or questions about thinking tools configuration:

1. Check this guide first
2. Review system prompt: `prompts/chat/system_prompt.md`
3. Check backend logs: `logs/backend.log`
4. Test MCP endpoints with curl
5. Verify model is Mistral 7B or better

---

**Remember**: Thinking tools are MANDATORY for complex reasoning. If the LLM attempts complex reasoning without using these tools, the system prompt needs strengthening or the model needs upgrading.
