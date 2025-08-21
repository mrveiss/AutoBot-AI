# Message Display Toggles Testing Guide

## Overview
The message display toggles in the chat interface allow you to control which types of agent messages are visible.

## Fixed Issues
✅ **Settings Reactivity**: Toggles now respond immediately when clicked
✅ **Persistence**: Toggle states are saved and restored after page reload
✅ **Message Filtering**: Each message type is properly categorized and filtered
✅ **Historical Messages**: Loaded chat history is also filtered by toggles
✅ **Message Normalization**: Backend `messageType` field converted to frontend `type` field
✅ **Autoscroll**: Scroll behavior can be controlled independently

## Manual Testing Steps

### 1. Access the Toggles
1. Start the AutoBot application
2. Navigate to the chat interface (http://localhost:5173)
3. If the sidebar is collapsed, click the toggle button (◀/▶) to expand it
4. Look for the "Message Display" section with checkboxes

### 2. Test Each Toggle

#### Show Thoughts Toggle
- **Purpose**: Controls visibility of internal agent reasoning
- **Message Type**: `message.type === 'thought'`
- **Test**:
  1. Uncheck the "Show Thoughts" toggle
  2. Send a message to the agent
  3. Verify thought messages are hidden
  4. Check the toggle again
  5. Verify thought messages reappear

#### Show JSON Output Toggle
- **Purpose**: Controls visibility of structured JSON data
- **Message Type**: `message.type === 'json'`
- **Default**: Usually unchecked (JSON can be verbose)

#### Show Utility Messages Toggle
- **Purpose**: Controls visibility of system/utility messages
- **Message Type**: `message.type === 'utility'`
- **Default**: Usually unchecked

#### Show Planning Messages Toggle
- **Purpose**: Controls visibility of planning phase messages
- **Message Type**: `message.type === 'planning'`
- **Default**: Usually checked (planning is useful to see)

#### Show Debug Messages Toggle
- **Purpose**: Controls visibility of debug information
- **Message Type**: `message.type === 'debug'`
- **Default**: Usually unchecked (debug can be verbose)

#### Autoscroll Toggle
- **Purpose**: Controls automatic scrolling to bottom of chat
- **Default**: Usually checked
- **Test**:
  1. Uncheck "Autoscroll"
  2. Send several messages
  3. Verify chat doesn't auto-scroll
  4. Check "Autoscroll" again
  5. Send a message and verify it scrolls to bottom

### 3. Test Persistence
1. Change several toggle states
2. Reload the page (Ctrl+F5)
3. Expand sidebar if needed
4. Verify all toggle states were preserved

### 4. Test Historical Message Filtering
1. Load a chat session with existing history
2. Toggle different message types on/off
3. Verify historical messages are also filtered (not just new messages)
4. Switch between different chat sessions
5. Confirm toggles affect all loaded messages

### 5. Test New Message Filtering
1. Send a complex query that generates multiple message types
2. Toggle different message types on/off
3. Observe messages appearing/disappearing in real-time

## Debugging Console Output

Open browser DevTools (F12) and look for console messages:

**Message Loading and Normalization:**
```
Loaded chat messages from backend for chat abc123
Normalized 8 historical messages for filtering
Loaded and normalized chat messages for chat abc123.
```

**Message Filtering:**
```
🔍 Filtering messages: {
  totalMessages: 8,
  toggleStates: {
    show_thoughts: true,
    show_json: false,
    show_utility: false,
    show_planning: true,
    show_debug: false
  }
}

✅ Filtered messages: {
  originalCount: 8,
  filteredCount: 5,
  messageTypes: [
    {type: "user", sender: "user"},
    {type: "thought", sender: "bot"},
    {type: "planning", sender: "bot"},
    {type: "response", sender: "bot"},
    {type: "debug", sender: "debug"}  // Note: type field, not messageType
  ]
}
```

**Historical Message Normalization:**
You should see that historical messages loaded from the backend now have proper `type` fields instead of `messageType` fields.

## Message Type Categories

### Always Shown (Cannot be hidden)
- **User messages**: `message.sender === 'user'`
- **Main responses**: `message.type === 'response'`
- **Tool output**: `message.type === 'tool_output'`

### Toggleable Message Types
- **Thoughts**: Internal reasoning processes
- **JSON**: Structured data output
- **Utility**: System messages and utilities
- **Planning**: Task planning and goal setting
- **Debug**: Technical debugging information

## Troubleshooting

### Toggles Not Responding
1. Check browser console for JavaScript errors
2. Verify Vue DevTools shows reactive settings object
3. Look for the debug console output when clicking toggles

### Settings Not Persisting
1. Check if localStorage is enabled in browser
2. Verify no browser extensions are blocking localStorage
3. Check for console errors during settings save

### Messages Not Filtering
1. Verify message objects have correct `type` property
2. Check if filteredMessages computed property is being called
3. Look for debug output showing message types and counts

## Expected Behavior

When working correctly:
- ✅ Clicks on toggles immediately show/hide relevant messages
- ✅ Settings persist across browser sessions
- ✅ Debug console shows filtering activity
- ✅ No JavaScript errors in console
- ✅ Autoscroll works when enabled
- ✅ Message counts change when toggling different types

The toggle system provides fine-grained control over chat verbosity, allowing users to focus on the information most relevant to their needs.
