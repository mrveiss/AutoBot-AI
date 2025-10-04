# Enhanced System Prompts - Test Cases

**Test Date**: 2025-10-03
**Feature**: Context-Aware System Prompts with Conversation Management
**Files Modified**:
- `prompts/chat/system_prompt.md` (enhanced base prompt)
- `prompts/chat/installation_help.md` (new)
- `prompts/chat/architecture_explanation.md` (new)
- `prompts/chat/troubleshooting.md` (new)
- `prompts/chat/api_documentation.md` (new)
- `src/chat_workflow_manager.py` (intent detection & selection logic)

## Test Objectives

1. Verify conversation continuation rules work correctly
2. Confirm intent detection accurately identifies user needs
3. Validate context-aware prompts are selected appropriately
4. Ensure no premature conversation endings
5. Test conversation flow across different intents

## Test Categories

### Category 1: Conversation Continuation Tests

**Test 1.1: Short Response Continuation**
```
User: "help me navigate the install process"
Expected: AutoBot asks clarifying question
User: "of autobot"
Expected: AutoBot continues with installation guidance (NO premature ending)
```

**Test 1.2: Single Word Clarification**
```
User: "tell me about the VMs"
Expected: AutoBot provides VM information
User: "yes"
Expected: AutoBot continues or offers more details (NO ending)
```

**Test 1.3: Question During Conversation**
```
User: "how do I install AutoBot?"
Expected: Installation guidance provided
User: "how many VMs?"
Expected: VM count with details (continues conversation)
```

**Test 1.4: Confusion Expression**
```
User: "I'm confused about the setup"
Expected: AutoBot offers step-by-step help, asks clarifying questions
User: "still not clear"
Expected: AutoBot provides alternative explanation (NO ending)
```

**Test 1.5: Minimum Exchange Rule**
```
Exchange 1:
User: "hello"
Expected: Greeting and offer to help

Exchange 2:
User: "thanks"
Expected: AutoBot asks if there's anything else (does NOT end yet)

Exchange 3:
User: "goodbye"
Expected: Now AutoBot can end conversation appropriately
```

### Category 2: Intent Detection Tests

**Test 2.1: Installation Intent**
```
User: "how do I install AutoBot?"
Expected Intent: installation
Expected Prompt: chat.installation_help
Expected Response: Mentions setup.sh, run_autobot.sh, 25-minute setup
```

**Test 2.2: Architecture Intent**
```
User: "how many VMs does AutoBot use?"
Expected Intent: architecture
Expected Prompt: chat.architecture_explanation
Expected Response: Lists 5 VMs with IPs, explains distributed architecture
```

**Test 2.3: Troubleshooting Intent**
```
User: "I'm getting an error when starting the backend"
Expected Intent: troubleshooting
Expected Prompt: chat.troubleshooting
Expected Response: Asks for error messages, guides to logs, systematic debugging
```

**Test 2.4: API Intent**
```
User: "what API endpoints are available for chat?"
Expected Intent: api
Expected Prompt: chat.api_documentation
Expected Response: Lists chat API endpoints with examples
```

**Test 2.5: General Intent (No Specific Match)**
```
User: "tell me a joke"
Expected Intent: general
Expected Prompt: chat.system_prompt (base only)
Expected Response: General helpful response
```

### Category 3: Context Switching Tests

**Test 3.1: Installation → Architecture**
```
User: "how do I setup AutoBot?"
Expected Intent: installation

User: "why do you need 5 VMs?"
Expected Intent: architecture (context switch detected)
```

**Test 3.2: Architecture → Troubleshooting**
```
User: "what is the distributed architecture?"
Expected Intent: architecture

User: "my Redis VM isn't connecting"
Expected Intent: troubleshooting (context switch)
```

**Test 3.3: Maintaining Context (No Switch)**
```
User: "help me install AutoBot"
Expected Intent: installation

User: "what's the first step?"
Expected Intent: installation (maintains context)

User: "and then?"
Expected Intent: installation (still maintaining context)
```

### Category 4: Exit Intent Tests

**Test 4.1: Explicit Goodbye**
```
User: "goodbye"
Expected: Conversation ends with polite farewell
```

**Test 4.2: Explicit Exit Words**
```
User: "exit"
Expected: Conversation ends

User: "quit"
Expected: Conversation ends

User: "that's all"
Expected: Conversation ends
```

**Test 4.3: Goodbye in Question (Should NOT Exit)**
```
User: "how do I say goodbye to AutoBot?"
Expected: Explains exit commands, does NOT end conversation
```

**Test 4.4: Thanks Without Goodbye**
```
User: "thanks for the help"
Expected: AutoBot asks if there's anything else (does NOT end)
```

**Test 4.5: Completion + Explicit Ending**
```
User: "thanks, that's all I needed"
Expected: AutoBot ends conversation appropriately
```

### Category 5: Response Quality Tests

**Test 5.1: Installation Response Quality**
```
User: "how do I install AutoBot?"
Expected Response MUST Include:
- Mention of setup.sh
- Mention of run_autobot.sh
- 25-minute setup time
- 5-VM architecture overview
- Actual IP addresses (172.16.168.20-25)
- Reference to PHASE_5_DEVELOPER_SETUP.md
```

**Test 5.2: Architecture Response Quality**
```
User: "explain the VM architecture"
Expected Response MUST Include:
- List of 5 VMs with IPs
- Purpose of each VM
- Design rationale (separation of concerns, scalability)
- Reference to PHASE_5_DISTRIBUTED_ARCHITECTURE.md
```

**Test 5.3: Troubleshooting Response Quality**
```
User: "backend is throwing errors"
Expected Response MUST Include:
- Ask for specific error messages
- Guide to log files (logs/backend.log)
- Systematic debugging steps
- Reference to COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md
- NO temporary fixes suggested
```

**Test 5.4: API Response Quality**
```
User: "show me chat API endpoints"
Expected Response MUST Include:
- Specific endpoints with URLs
- Request/response examples
- curl examples with actual IPs
- Reference to COMPREHENSIVE_API_DOCUMENTATION.md
```

### Category 6: Edge Cases

**Test 6.1: Empty or Very Short Messages**
```
User: "hi"
Expected: Greeting and offer to help (continues conversation)

User: "ok"
Expected: Asks what they'd like help with (continues)

User: " " (whitespace only)
Expected: Handles gracefully, asks for input
```

**Test 6.2: Multiple Intents in One Message**
```
User: "how do I install AutoBot and what APIs are available?"
Expected: Detects dominant intent or addresses both
```

**Test 6.3: Typos in Intent Keywords**
```
User: "how do I instal AutoBot?" (typo: instal)
Expected: Still detects installation intent (fuzzy matching beneficial)
```

**Test 6.4: Mixed Intent Conversation**
```
User: "help me setup AutoBot"
Intent: installation

User: "what happens if it fails?"
Intent: troubleshooting (related to installation context)

User: "how do the VMs communicate?"
Intent: architecture

Expected: Handles all context switches gracefully
```

## Test Execution Checklist

### Pre-Test Setup
- [ ] Backend running: `bash run_autobot.sh --dev`
- [ ] Frontend accessible at 172.16.168.21:5173
- [ ] Redis accessible at 172.16.168.23:6379
- [ ] Ollama running on AI Stack VM (172.16.168.24:11434)
- [ ] All prompt files exist in prompts/chat/
- [ ] Browser DevTools open to monitor WebSocket and API calls

### During Testing
- [ ] Monitor backend logs: `tail -f logs/backend.log`
- [ ] Check intent detection logs for each message
- [ ] Verify correct prompt is loaded (check logs)
- [ ] Observe conversation flow and response quality
- [ ] Note any unexpected behavior

### Post-Test Validation
- [ ] Review conversation transcripts in `data/conversation_transcripts/`
- [ ] Check Redis conversation history (DB 1)
- [ ] Verify no error logs during tests
- [ ] Document any issues found
- [ ] Update Memory MCP with test results

## Test Results Template

For each test case, record:

```markdown
**Test ID**: [e.g., 1.1]
**Test Name**: [e.g., Short Response Continuation]
**Date**: [Test execution date]
**Tester**: [Name/ID]

**Input**:
[User messages]

**Expected**:
[Expected behavior]

**Actual**:
[Actual behavior observed]

**Status**: ✅ PASS / ❌ FAIL / ⚠️ PARTIAL
**Notes**: [Any observations or issues]
**Logs**: [Relevant log excerpts if needed]
```

## Success Criteria

All tests must pass (✅) for feature to be considered complete:

1. **Conversation Continuation**: 100% of tests pass (no premature endings)
2. **Intent Detection**: 90%+ accuracy in intent detection
3. **Context Switching**: Smooth transitions, no confusion
4. **Exit Intent**: Only exits on explicit user intent
5. **Response Quality**: All MUST include items present in responses
6. **Edge Cases**: Handles gracefully without errors

## Known Limitations

Document any known limitations discovered during testing:
- [ ] Intent detection accuracy with very short messages
- [ ] Context switching latency
- [ ] Prompt combination length (token limits)
- [ ] Performance impact of longer prompts

## Follow-up Actions

If tests fail or issues found:
1. Document issue in detail
2. Create GitHub issue or task
3. Update Memory MCP with findings
4. Revise prompts or logic as needed
5. Re-test after fixes

## Automated Testing (Future)

Convert these manual tests to automated tests:
- Create `tests/automated/test_conversation_continuation.py`
- Create `tests/automated/test_intent_detection.py`
- Create `tests/automated/test_context_switching.py`
- Use pytest for automated test execution
- CI/CD integration for regression testing
