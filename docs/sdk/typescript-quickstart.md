# TypeScript SDK Quickstart

This guide shows how to integrate with AutoBot using TypeScript or JavaScript. Until the official `@autobot/sdk` package is published, you can call the API directly with `fetch` or any HTTP client.

---

## Installation

### Official SDK (planned)

```bash
npm install @autobot/sdk
# or
yarn add @autobot/sdk
```

### Direct HTTP (available now)

No additional dependencies needed -- the native `fetch` API works in Node.js 18+ and all modern browsers. For older environments:

```bash
npm install node-fetch
```

---

## Configuration

```typescript
const BASE_URL = 'https://autobot.example.com:8443/api';
const API_KEY = 'your-api-key';

// Helper for authenticated requests
async function apiRequest<T>(
  method: string,
  path: string,
  body?: Record<string, unknown>,
): Promise<T> {
  const options: RequestInit = {
    method,
    headers: {
      'Authorization': `Bearer ${API_KEY}`,
      'Content-Type': 'application/json',
    },
  };

  if (body) {
    options.body = JSON.stringify(body);
  }

  const response = await fetch(`${BASE_URL}${path}`, options);

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      `API error ${response.status}: ${error.message || response.statusText}`
    );
  }

  return response.json() as Promise<T>;
}
```

---

## Authentication

### Login with credentials

```typescript
interface LoginResponse {
  token: string;
  user: {
    username: string;
    role: string;
    user_id: string;
    org_id?: string;
  };
  expires_in: number;
}

async function login(username: string, password: string): Promise<string> {
  const result = await apiRequest<LoginResponse>('POST', '/auth/login', {
    username,
    password,
  });
  return result.token;
}

// Usage
const token = await login('myuser', 'mypassword');
// Update API_KEY or create a new apiRequest instance with the token
```

---

## Chat

### Send a message

```typescript
interface ChatResponse {
  success: boolean;
  response: string;
  session_id: string;
  message_id: string;
  metadata: {
    model: string;
    tokens_used: number;
    knowledge_base_used: boolean;
  };
}

async function sendMessage(
  content: string,
  sessionId?: string,
): Promise<ChatResponse> {
  const payload: Record<string, unknown> = { content, role: 'user' };
  if (sessionId) {
    payload.session_id = sessionId;
  }
  return apiRequest<ChatResponse>('POST', '/chat', payload);
}

// Usage
const result = await sendMessage('How do I configure network scanning?');
console.log(result.response);
```

### Stream a response

```typescript
async function streamMessage(
  content: string,
  onToken: (token: string) => void,
  sessionId?: string,
): Promise<void> {
  const payload: Record<string, unknown> = { content, role: 'user' };
  if (sessionId) {
    payload.session_id = sessionId;
  }

  const response = await fetch(`${BASE_URL}/chat/stream`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${API_KEY}`,
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    throw new Error(`Stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        if (data.type === 'token') {
          onToken(data.content);
        } else if (data.type === 'done') {
          return;
        }
      }
    }
  }
}

// Usage
await streamMessage(
  'Explain NPU acceleration in detail',
  (token) => process.stdout.write(token),
);
```

### Manage sessions

```typescript
interface Session {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

interface SessionListResponse {
  success: boolean;
  sessions: Session[];
  total: number;
}

async function createSession(title: string = 'New conversation') {
  return apiRequest<{ success: boolean; session_id: string }>(
    'POST', '/chat/sessions', { title },
  );
}

async function listSessions(limit: number = 50): Promise<SessionListResponse> {
  return apiRequest<SessionListResponse>(
    'GET', `/chats?limit=${limit}`,
  );
}

async function getSession(sessionId: string) {
  return apiRequest<{ success: boolean; session: Session & { messages: unknown[] } }>(
    'GET', `/chat/sessions/${sessionId}`,
  );
}

async function deleteSession(sessionId: string) {
  return apiRequest<{ success: boolean }>('DELETE', `/chats/${sessionId}`);
}

// Usage
const session = await createSession('Security Research');
const result = await sendMessage('What are the OWASP top 10?', session.session_id);
```

---

## Knowledge Base

### Add content

```typescript
async function addFact(
  content: string,
  title: string = '',
  category: string = 'general',
  tags: string[] = [],
) {
  return apiRequest('POST', '/knowledge_base/facts', {
    content, title, category, tags,
  });
}

await addFact(
  'AutoBot supports Intel NPU acceleration for local AI inference.',
  'NPU Support',
  'hardware',
  ['npu', 'intel', 'acceleration'],
);
```

### Upload a document

```typescript
async function uploadDocument(
  file: File | Blob,
  filename: string,
  category: string = 'general',
) {
  const formData = new FormData();
  formData.append('file', file, filename);
  formData.append('category', category);

  const response = await fetch(`${BASE_URL}/knowledge_base/upload`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${API_KEY}` },
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.status}`);
  }

  return response.json();
}

// Node.js usage with fs
import { readFileSync } from 'fs';

const fileBuffer = readFileSync('docs/architecture.pdf');
const blob = new Blob([fileBuffer], { type: 'application/pdf' });
const result = await uploadDocument(blob, 'architecture.pdf', 'architecture');
console.log(`Created ${result.chunks_created} chunks`);
```

### Query the knowledge base

```typescript
interface SearchResult {
  content: string;
  score: number;
  source: string;
  category: string;
  metadata: Record<string, unknown>;
}

interface QueryResponse {
  success: boolean;
  results: SearchResult[];
  query_time_ms: number;
}

async function queryKnowledge(
  query: string,
  topK: number = 5,
  category?: string,
): Promise<QueryResponse> {
  const payload: Record<string, unknown> = { query, top_k: topK };
  if (category) payload.category = category;

  return apiRequest<QueryResponse>('POST', '/knowledge_base/query', payload);
}

const results = await queryKnowledge('How does NPU acceleration work?', 3);
for (const r of results.results) {
  console.log(`[${r.score.toFixed(2)}] ${r.content.slice(0, 100)}...`);
}
```

### Search with filters

```typescript
async function searchKnowledge(
  query: string,
  options: {
    searchType?: string;
    categories?: string[];
    tags?: string[];
    topK?: number;
  } = {},
) {
  return apiRequest('POST', '/knowledge_base/search', {
    query,
    search_type: options.searchType || 'hybrid',
    top_k: options.topK || 10,
    filters: {
      ...(options.categories && { categories: options.categories }),
      ...(options.tags && { tags: options.tags }),
    },
  });
}

const results = await searchKnowledge('network scanning tools', {
  categories: ['security', 'tools'],
  tags: ['network'],
});
```

### Collections

```typescript
async function createCollection(name: string, description: string = '') {
  return apiRequest('POST', '/knowledge_base/collections', {
    name, description,
  });
}

async function listCollections() {
  return apiRequest('GET', '/knowledge_base/collections');
}

const collection = await createCollection(
  'Security Playbooks',
  'Automation playbooks for security',
);
```

---

## Agents

### List available agents

```typescript
interface Agent {
  name: string;
  description: string;
  capabilities: string[];
}

async function listAgents(): Promise<{ agents: Agent[] }> {
  return apiRequest('GET', '/agent/agents/available');
}

const { agents } = await listAgents();
for (const agent of agents) {
  console.log(`${agent.name}: ${agent.description}`);
}
```

### Execute an agent goal

```typescript
async function executeGoal(goal: string, agent: string = 'research') {
  return apiRequest('POST', '/agent/goal', { goal, agent });
}

const task = await executeGoal(
  'Research the latest network vulnerability disclosures',
  'research',
);
console.log(`Task ${task.task_id}: ${task.status}`);
```

### Multi-agent coordination

```typescript
async function coordinateAgents(
  task: string,
  agents: string[],
  mode: string = 'sequential',
) {
  return apiRequest('POST', '/agent/multi-agent/coordinate', {
    task,
    agents,
    coordination_mode: mode,
  });
}

const result = await coordinateAgents(
  'Research and document network scanning best practices',
  ['research', 'rag', 'knowledge_extraction'],
);
```

---

## Workflows

### Trigger a workflow

```typescript
async function executeWorkflow(
  workflowType: string,
  parameters: Record<string, unknown> = {},
) {
  return apiRequest('POST', '/workflow/execute', {
    workflow_type: workflowType,
    parameters,
  });
}

const workflow = await executeWorkflow('research_and_document', {
  topic: 'Zero trust architecture',
  output_format: 'report',
});
```

### Poll workflow status

```typescript
async function waitForWorkflow(
  workflowId: string,
  pollIntervalMs: number = 5000,
  timeoutMs: number = 300000,
): Promise<Record<string, unknown>> {
  const start = Date.now();

  while (Date.now() - start < timeoutMs) {
    const status = await apiRequest<Record<string, unknown>>(
      'GET', `/workflow/workflow/${workflowId}/status`,
    );

    if (['completed', 'failed', 'cancelled'].includes(status.status as string)) {
      return status;
    }

    const progress = ((status.progress as number) || 0) * 100;
    console.log(
      `Progress: ${progress.toFixed(0)}% ` +
      `(step ${status.current_step}/${status.total_steps})`
    );

    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
  }

  throw new Error(`Workflow ${workflowId} did not complete within ${timeoutMs}ms`);
}

const finalStatus = await waitForWorkflow(workflow.workflow_id);
console.log(`Workflow finished: ${finalStatus.status}`);
```

---

## Models

### List available models

```typescript
async function listModels() {
  return apiRequest('GET', '/llm/models');
}

async function getCurrentModel() {
  return apiRequest('GET', '/llm/current');
}

const { models } = await listModels();
for (const model of models) {
  const status = model.available ? 'available' : 'unavailable';
  console.log(`${model.name} (${model.provider}) - ${status}`);
}
```

---

## Error Handling

```typescript
class AutoBotError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public errorCode?: string,
  ) {
    super(message);
    this.name = 'AutoBotError';
  }
}

async function safeApiRequest<T>(
  method: string,
  path: string,
  body?: Record<string, unknown>,
): Promise<T> {
  const options: RequestInit = {
    method,
    headers: {
      'Authorization': `Bearer ${API_KEY}`,
      'Content-Type': 'application/json',
    },
  };

  if (body) {
    options.body = JSON.stringify(body);
  }

  const response = await fetch(`${BASE_URL}${path}`, options);

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));

    switch (response.status) {
      case 401:
        throw new AutoBotError('Authentication failed. Check your API key.', 401);
      case 429: {
        const retryAfter = response.headers.get('Retry-After') || '60';
        throw new AutoBotError(
          `Rate limited. Retry after ${retryAfter} seconds.`,
          429,
          'rate_limit_exceeded',
        );
      }
      case 404:
        throw new AutoBotError(`Resource not found: ${path}`, 404);
      default:
        throw new AutoBotError(
          error.message || `API error: ${response.statusText}`,
          response.status,
          error.error,
        );
    }
  }

  return response.json() as Promise<T>;
}

// Usage with error handling
try {
  const result = await safeApiRequest('POST', '/chat', {
    content: 'Hello',
    role: 'user',
  });
  console.log(result);
} catch (error) {
  if (error instanceof AutoBotError) {
    console.error(`API Error [${error.statusCode}]: ${error.message}`);
    if (error.statusCode === 429) {
      // Implement retry logic
    }
  }
}
```

---

## React Integration Example

```typescript
import { useState, useCallback } from 'react';

function useChatMessage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(async (content: string, sessionId?: string) => {
    setLoading(true);
    setError(null);

    try {
      const payload: Record<string, unknown> = { content, role: 'user' };
      if (sessionId) payload.session_id = sessionId;

      const response = await fetch(`${BASE_URL}/chat`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${API_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { sendMessage, loading, error };
}

// Usage in a component
function ChatInput() {
  const { sendMessage, loading, error } = useChatMessage();

  const handleSend = async (message: string) => {
    const result = await sendMessage(message);
    if (result) {
      console.log(result.response);
    }
  };

  // ... render form
}
```

---

## Next Steps

- See the full [API Reference](../api/public-api-reference.md) for all endpoints
- Read the [API Versioning Strategy](../api/api-versioning.md) for stability guarantees
- Check the [Python Quickstart](python-quickstart.md) for Python usage
