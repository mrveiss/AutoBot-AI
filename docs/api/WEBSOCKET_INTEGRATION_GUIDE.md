# AutoBot WebSocket Integration Guide

## Overview
This guide provides comprehensive WebSocket integration patterns for real-time communication with the AutoBot backend. WebSocket endpoints provide live updates for chat messages, system events, workflow progress, and error notifications.

## WebSocket Endpoints

### Primary Endpoints
- **Main WebSocket**: `wss://172.16.168.20:8443/ws`
- **Test WebSocket**: `wss://172.16.168.20:8443/ws-test`
- **Health Check**: `wss://172.16.168.20:8443/ws/health`

## Message Formats

### Server-to-Client Messages

#### Connection Management
```typescript
// Connection established
{
  "type": "connection_established",
  "payload": {
    "message": "WebSocket connected successfully"
  }
}

// Keep-alive ping
{
  "type": "ping"
}

// Health check response  
{
  "type": "health_response",
  "payload": {
    "status": "healthy",
    "timestamp": "2025-09-11T13:45:00.000Z"
  }
}
```

#### Chat Events
```typescript
// User message received
{
  "type": "user_message",
  "payload": {
    "message": "User message content",
    "chat_id": "uuid",
    "timestamp": "2025-09-11T13:45:00.000Z"
  }
}

// AI/Bot response
{
  "type": "llm_response",
  "payload": {
    "response": "AI response content",
    "chat_id": "uuid",
    "model": "llama3.2:1b-instruct-q4_K_M",
    "processing_time": 2.34
  }
}

// Goal received from user
{
  "type": "goal_received",
  "payload": {
    "goal": "User's stated goal or objective"
  }
}

// Plan generated for goal
{
  "type": "plan_ready",
  "payload": {
    "llm_response": "Detailed plan text from AI",
    "steps": ["step1", "step2", "step3"]
  }
}

// Goal completion
{
  "type": "goal_completed",
  "payload": {
    "results": {
      "status": "success",
      "output": "Final results",
      "metrics": {}
    }
  }
}
```

#### Command Execution Events
```typescript
// Command execution started
{
  "type": "command_execution_start",
  "payload": {
    "command": "ls -la /home/user",
    "execution_id": "exec-uuid"
  }
}

// Command execution completed
{
  "type": "command_execution_end",
  "payload": {
    "execution_id": "exec-uuid",
    "status": "success|failed",
    "output": "command output text",
    "error": "error message if failed",
    "exit_code": 0
  }
}
```

#### Workflow Events  
```typescript
// Workflow step started
{
  "type": "workflow_step_started",
  "payload": {
    "workflow_id": "workflow-uuid",
    "description": "Step description",
    "step_number": 1,
    "total_steps": 5
  }
}

// Workflow step completed
{
  "type": "workflow_step_completed",
  "payload": {
    "workflow_id": "workflow-uuid",
    "description": "Step description",
    "result": "Step completion result",
    "step_number": 1,
    "total_steps": 5
  }
}

// Workflow requires approval
{
  "type": "workflow_approval_required",
  "payload": {
    "workflow_id": "workflow-uuid",
    "description": "Action requiring approval",
    "action": "delete_file|install_package|modify_config",
    "details": {}
  }
}

// Workflow completed successfully
{
  "type": "workflow_completed",
  "payload": {
    "workflow_id": "workflow-uuid",
    "total_steps": 5,
    "execution_time": 45.2,
    "results": {}
  }
}

// Workflow failed
{
  "type": "workflow_failed",
  "payload": {
    "workflow_id": "workflow-uuid",
    "error": "Detailed error message",
    "failed_step": 3,
    "total_steps": 5
  }
}

// Workflow cancelled by user
{
  "type": "workflow_cancelled",
  "payload": {
    "workflow_id": "workflow-uuid",
    "cancelled_at_step": 2,
    "total_steps": 5
  }
}
```

#### System Events
```typescript
// System error
{
  "type": "error",
  "payload": {
    "message": "Error description",
    "error_code": "SYSTEM_ERROR",
    "severity": "low|medium|high|critical"
  }
}

// Progress updates
{
  "type": "progress",
  "payload": {
    "message": "Progress description",
    "percentage": 45,
    "stage": "processing|analyzing|executing"
  }
}

// LLM status change
{
  "type": "llm_status",
  "payload": {
    "status": "connected|disconnected|reconnecting",
    "model": "model-name",
    "message": "Status details"
  }
}

// Settings updated
{
  "type": "settings_updated",
  "payload": {
    "settings": {
      "updated_keys": ["theme", "timeout"],
      "timestamp": "2025-09-11T13:45:00.000Z"
    }
  }
}

// File uploaded
{
  "type": "file_uploaded",
  "payload": {
    "filename": "document.pdf",
    "size": 1024,
    "chat_id": "uuid",
    "file_id": "file-uuid"
  }
}

// Knowledge base updated
{
  "type": "knowledge_base_update",
  "payload": {
    "type": "document_added|document_removed|reindexed",
    "details": {
      "document_count": 3279,
      "chunks_added": 15
    }
  }
}
```

#### Tool/Code Execution
```typescript
// Tool code execution
{
  "type": "tool_code",
  "payload": {
    "code": "print('Hello World')",
    "language": "python",
    "tool": "python_interpreter"
  }
}

// Tool execution output
{
  "type": "tool_output",
  "payload": {
    "output": "Hello World\n",
    "tool": "python_interpreter",
    "success": true
  }
}

// AI thinking/reasoning
{
  "type": "thought",
  "payload": {
    "thought": {
      "content": "I need to analyze this request...",
      "reasoning": "step-by-step analysis",
      "confidence": 0.85
    }
  }
}
```

#### Monitoring Events
```typescript
// Diagnostics report
{
  "type": "diagnostics_report",
  "payload": {
    "system": {
      "cpu_usage": 45.2,
      "memory_usage": 78.1,
      "disk_usage": 23.4
    },
    "services": {
      "redis": "healthy",
      "ollama": "healthy",
      "knowledge_base": "healthy"  
    }
  }
}

// User permission request
{
  "type": "user_permission_request",
  "payload": {
    "action": "install_package",
    "package": "nodejs",
    "reason": "Required for build process"
  }
}
```

### Client-to-Server Messages

#### Basic Messages
```typescript
// User message to chat
{
  "type": "user_message",
  "payload": {
    "message": "Hello AutoBot",
    "chat_id": "optional-chat-uuid"
  }
}

// Pong response to ping
{
  "type": "pong"
}

// Health check request
{
  "type": "health_check"
}
```

#### Workflow Control
```typescript
// Approve workflow action
{
  "type": "workflow_approval",
  "payload": {
    "workflow_id": "workflow-uuid",
    "approved": true,
    "message": "Approved by user"
  }
}

// Cancel workflow
{
  "type": "workflow_cancel",
  "payload": {
    "workflow_id": "workflow-uuid",
    "reason": "User cancelled"
  }
}
```

## Implementation Patterns

### React Hook Implementation
```typescript
import { useEffect, useRef, useState, useCallback } from 'react';

interface WebSocketMessage {
  type: string;
  payload: any;
}

interface UseWebSocketOptions {
  onMessage?: (message: WebSocketMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
  reconnectAttempts?: number;
  reconnectDelay?: number;
}

export function useWebSocket(url: string, options: UseWebSocketOptions = {}) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);

  const {
    onMessage,
    onConnect,
    onDisconnect,
    onError,
    reconnectAttempts = 5,
    reconnectDelay = 1000
  } = options;

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    try {
      wsRef.current = new WebSocket(url);

      wsRef.current.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
        setConnectionError(null);
        reconnectAttemptsRef.current = 0;
        onConnect?.();
      };

      wsRef.current.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          setLastMessage(message);
          onMessage?.(message);

          // Handle ping-pong
          if (message.type === 'ping') {
            sendMessage({ type: 'pong' });
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      wsRef.current.onclose = (event) => {
        console.log('WebSocket disconnected:', event.code, event.reason);
        setIsConnected(false);
        onDisconnect?.();

        // Attempt reconnection
        if (reconnectAttemptsRef.current < reconnectAttempts) {
          const delay = reconnectDelay * Math.pow(2, reconnectAttemptsRef.current);
          console.log(`Attempting reconnect in ${delay}ms (attempt ${reconnectAttemptsRef.current + 1})`);

          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptsRef.current++;
            connect();
          }, delay);
        } else {
          setConnectionError('Max reconnection attempts reached');
        }
      };

      wsRef.current.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnectionError('WebSocket connection error');
        onError?.(error);
      };

    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      setConnectionError('Failed to create WebSocket connection');
    }
  }, [url, onMessage, onConnect, onDisconnect, onError, reconnectAttempts, reconnectDelay]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setIsConnected(false);
  }, []);

  const sendMessage = useCallback((message: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket is not connected. Cannot send message:', message);
    }
  }, []);

  useEffect(() => {
    connect();
    return disconnect;
  }, [connect, disconnect]);

  return {
    isConnected,
    lastMessage,
    connectionError,
    sendMessage,
    connect,
    disconnect
  };
}
```

### Vue.js Composable
```typescript
import { ref, onMounted, onUnmounted } from 'vue';

export function useWebSocket(url: string) {
  const isConnected = ref(false);
  const lastMessage = ref<any>(null);
  const connectionError = ref<string | null>(null);
  const messages = ref<any[]>([]);

  let ws: WebSocket | null = null;
  let reconnectTimeout: NodeJS.Timeout | null = null;
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 5;
  const reconnectDelay = 1000;

  const connect = () => {
    try {
      ws = new WebSocket(url);

      ws.onopen = () => {
        console.log('WebSocket connected');
        isConnected.value = true;
        connectionError.value = null;
        reconnectAttempts = 0;
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          lastMessage.value = message;
          messages.value.push(message);

          // Keep only last 1000 messages
          if (messages.value.length > 1000) {
            messages.value = messages.value.slice(-1000);
          }

          // Auto-respond to pings
          if (message.type === 'ping') {
            sendMessage({ type: 'pong' });
          }
        } catch (error) {
          console.error('Failed to parse message:', error);
        }
      };

      ws.onclose = (event) => {
        console.log('WebSocket closed:', event.code, event.reason);
        isConnected.value = false;

        // Attempt reconnection
        if (reconnectAttempts < maxReconnectAttempts) {
          const delay = reconnectDelay * Math.pow(2, reconnectAttempts);
          reconnectTimeout = setTimeout(() => {
            reconnectAttempts++;
            connect();
          }, delay);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        connectionError.value = 'Connection error';
      };

    } catch (error) {
      console.error('Failed to connect:', error);
      connectionError.value = 'Failed to connect';
    }
  };

  const disconnect = () => {
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
    }
    if (ws) {
      ws.close();
      ws = null;
    }
    isConnected.value = false;
  };

  const sendMessage = (message: any) => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket not connected');
    }
  };

  const clearMessages = () => {
    messages.value = [];
  };

  onMounted(() => {
    connect();
  });

  onUnmounted(() => {
    disconnect();
  });

  return {
    isConnected,
    lastMessage,
    messages,
    connectionError,
    sendMessage,
    connect,
    disconnect,
    clearMessages
  };
}
```

### Message Processing Patterns

#### Message Type Router
```typescript
class WebSocketMessageRouter {
  private handlers: Map<string, (payload: any) => void> = new Map();

  addHandler(messageType: string, handler: (payload: any) => void) {
    this.handlers.set(messageType, handler);
  }

  removeHandler(messageType: string) {
    this.handlers.delete(messageType);
  }

  processMessage(message: WebSocketMessage) {
    const handler = this.handlers.get(message.type);
    if (handler) {
      try {
        handler(message.payload);
      } catch (error) {
        console.error(`Error processing ${message.type}:`, error);
      }
    } else {
      console.warn(`No handler for message type: ${message.type}`);
    }
  }
}

// Usage example
const messageRouter = new WebSocketMessageRouter();

messageRouter.addHandler('llm_response', (payload) => {
  console.log('AI Response:', payload.response);
  // Update UI with AI response
});

messageRouter.addHandler('workflow_step_started', (payload) => {
  console.log('Workflow step started:', payload.description);
  // Update progress UI
});

messageRouter.addHandler('error', (payload) => {
  console.error('System error:', payload.message);
  // Show error notification
});

// In WebSocket onmessage handler
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  messageRouter.processMessage(message);
};
```

#### Event Aggregator Pattern
```typescript
interface ChatEvent {
  id: string;
  type: string;
  timestamp: Date;
  payload: any;
}

class ChatEventAggregator {
  private events: ChatEvent[] = [];
  private listeners: ((event: ChatEvent) => void)[] = [];

  addEvent(type: string, payload: any) {
    const event: ChatEvent = {
      id: crypto.randomUUID(),
      type,
      timestamp: new Date(),
      payload
    };

    this.events.push(event);

    // Keep only last 10000 events
    if (this.events.length > 10000) {
      this.events = this.events.slice(-10000);
    }

    // Notify listeners
    this.listeners.forEach(listener => {
      try {
        listener(event);
      } catch (error) {
        console.error('Error in event listener:', error);
      }
    });
  }

  subscribe(listener: (event: ChatEvent) => void) {
    this.listeners.push(listener);
    return () => {
      const index = this.listeners.indexOf(listener);
      if (index > -1) {
        this.listeners.splice(index, 1);
      }
    };
  }

  getEvents(type?: string): ChatEvent[] {
    return type
      ? this.events.filter(event => event.type === type)
      : this.events;
  }

  getEventsSince(timestamp: Date, type?: string): ChatEvent[] {
    return this.getEvents(type).filter(event => event.timestamp >= timestamp);
  }

  clearEvents() {
    this.events = [];
  }
}
```

### Error Handling and Recovery

#### Connection Health Monitor
```typescript
class WebSocketHealthMonitor {
  private ws: WebSocket;
  private pingInterval: NodeJS.Timeout | null = null;
  private pongReceived = false;
  private healthCheckInterval = 30000; // 30 seconds

  constructor(ws: WebSocket) {
    this.ws = ws;
    this.startHealthCheck();
  }

  private startHealthCheck() {
    this.pingInterval = setInterval(() => {
      if (this.ws.readyState === WebSocket.OPEN) {
        // Send ping and wait for pong
        this.pongReceived = false;
        this.ws.send(JSON.stringify({ type: 'ping' }));

        // Check for pong response
        setTimeout(() => {
          if (!this.pongReceived) {
            console.warn('WebSocket ping timeout - connection may be dead');
            this.ws.close();
          }
        }, 5000); // 5 second pong timeout
      }
    }, this.healthCheckInterval);
  }

  handlePong() {
    this.pongReceived = true;
  }

  destroy() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }
}
```

#### Queue-based Message Sending
```typescript
class WebSocketQueue {
  private ws: WebSocket | null = null;
  private messageQueue: any[] = [];
  private maxQueueSize = 1000;

  setWebSocket(ws: WebSocket) {
    this.ws = ws;
    this.processQueue();
  }

  send(message: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      // Queue message for later
      if (this.messageQueue.length >= this.maxQueueSize) {
        this.messageQueue.shift(); // Remove oldest message
      }
      this.messageQueue.push(message);
    }
  }

  private processQueue() {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }

    while (this.messageQueue.length > 0) {
      const message = this.messageQueue.shift();
      this.ws.send(JSON.stringify(message));
    }
  }

  clearQueue() {
    this.messageQueue = [];
  }

  getQueueSize(): number {
    return this.messageQueue.length;
  }
}
```

## Testing WebSocket Integration

### Unit Test Example (Jest)
```typescript
// Mock WebSocket for testing
class MockWebSocket extends EventTarget {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = MockWebSocket.CONNECTING;

  constructor(public url: string) {
    super();
    // Simulate async connection
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN;
      this.dispatchEvent(new Event('open'));
    }, 10);
  }

  send(data: string) {
    if (this.readyState !== MockWebSocket.OPEN) {
      throw new Error('WebSocket is not open');
    }
    // Echo back for testing
    setTimeout(() => {
      const message = new MessageEvent('message', { data });
      this.dispatchEvent(message);
    }, 5);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.dispatchEvent(new CloseEvent('close'));
  }
}

// Test WebSocket hook
describe('useWebSocket', () => {
  beforeAll(() => {
    global.WebSocket = MockWebSocket as any;
  });

  test('connects and receives messages', async () => {
    const onMessage = jest.fn();
    const { result } = renderHook(() =>
      useWebSocket('ws://test', { onMessage })
    );

    // Wait for connection
    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    // Send test message
    result.current.sendMessage({ type: 'test', data: 'hello' });

    // Wait for echo
    await waitFor(() => {
      expect(onMessage).toHaveBeenCalled();
    });
  });
});
```

### Integration Test Example
```typescript
// Test actual WebSocket connection
describe('AutoBot WebSocket Integration', () => {
  let ws: WebSocket;

  beforeEach(() => {
    ws = new WebSocket('wss://172.16.168.20:8443/ws-test');
  });

  afterEach(() => {
    if (ws) {
      ws.close();
    }
  });

  test('connects successfully', (done) => {
    ws.onopen = () => {
      expect(ws.readyState).toBe(WebSocket.OPEN);
      done();
    };

    ws.onerror = (error) => {
      done(error);
    };
  });

  test('echoes messages', (done) => {
    ws.onopen = () => {
      ws.send('test message');
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'echo') {
        expect(data.message).toBe('test message');
        done();
      }
    };
  });

  test('handles connection failures gracefully', (done) => {
    const invalidWs = new WebSocket('ws://invalid-host:9999');

    invalidWs.onerror = () => {
      expect(invalidWs.readyState).toBe(WebSocket.CLOSED);
      done();
    };
  });
});
```

## Performance Optimization

### Message Batching
```typescript
class MessageBatcher {
  private batch: any[] = [];
  private batchTimeout: NodeJS.Timeout | null = null;
  private batchSize = 10;
  private batchDelay = 100; // ms

  constructor(
    private sendFunction: (messages: any[]) => void
  ) {}

  add(message: any) {
    this.batch.push(message);

    if (this.batch.length >= this.batchSize) {
      this.flush();
    } else if (!this.batchTimeout) {
      this.batchTimeout = setTimeout(() => this.flush(), this.batchDelay);
    }
  }

  flush() {
    if (this.batch.length > 0) {
      this.sendFunction([...this.batch]);
      this.batch = [];
    }

    if (this.batchTimeout) {
      clearTimeout(this.batchTimeout);
      this.batchTimeout = null;
    }
  }
}
```

### Message Filtering
```typescript
class MessageFilter {
  private filters: ((message: any) => boolean)[] = [];

  addFilter(filter: (message: any) => boolean) {
    this.filters.push(filter);
  }

  shouldProcess(message: any): boolean {
    return this.filters.every(filter => filter(message));
  }

  // Pre-built filters
  static createTypeFilter(allowedTypes: string[]) {
    return (message: any) => allowedTypes.includes(message.type);
  }

  static createRateLimitFilter(maxPerSecond: number) {
    const timestamps: number[] = [];
    return (message: any) => {
      const now = Date.now();
      const oneSecondAgo = now - 1000;

      // Remove old timestamps
      while (timestamps.length > 0 && timestamps[0] < oneSecondAgo) {
        timestamps.shift();
      }

      if (timestamps.length >= maxPerSecond) {
        return false; // Rate limit exceeded
      }

      timestamps.push(now);
      return true;
    };
  }
}
```

## Summary

This WebSocket integration guide provides:

✅ **Complete Message Formats**: All server-to-client and client-to-server message types  
✅ **React/Vue Integration**: Production-ready hooks and composables  
✅ **Error Handling**: Connection recovery, message queuing, health monitoring  
✅ **Testing Strategies**: Unit tests and integration tests  
✅ **Performance Patterns**: Message batching, filtering, and optimization  
✅ **Advanced Patterns**: Message routing, event aggregation, queue management  

The WebSocket integration enables real-time communication for chat, workflows, system monitoring, and command execution with robust error handling and reconnection capabilities.
