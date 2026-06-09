// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import CodeCell from './CodeCell.vue'
import type { CodePayload } from '@/types/canvas'

const meta: Meta<typeof CodeCell> = {
  title: 'Canvas/CodeCell',
  component: CodeCell,
  parameters: {
    layout: 'padded',
  },
  argTypes: {
    richPayload: { control: 'object' },
  },
}

export default meta
type Story = StoryObj<typeof CodeCell>

export const Python: Story = {
  args: {
    richPayload: {
      payloadType: 'code',
      code: `def fibonacci(n):
  """Calculate the nth Fibonacci number."""
  if n <= 1:
    return n
  return fibonacci(n-1) + fibonacci(n-2)

# Example usage
for i in range(10):
  print(f"fib({i}) = {fibonacci(i)}")`,
      language: 'python',
      executable: false,
    } as CodePayload,
  },
}

export const JavaScript: Story = {
  args: {
    richPayload: {
      payloadType: 'code',
      code: `async function fetchData(url) {
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(\`HTTP error! status: \${response.status}\`);
    }
    return await response.json();
  } catch (error) {
    console.error('Fetch error:', error);
    return null;
  }
}

// Usage
fetchData('/api/data').then(data => {
  if (data) console.log('Data:', data);
});`,
      language: 'javascript',
      executable: false,
    } as CodePayload,
  },
}

export const SQL: Story = {
  args: {
    richPayload: {
      payloadType: 'code',
      code: `SELECT
  u.user_id,
  u.name,
  COUNT(o.order_id) as order_count,
  SUM(o.total) as total_spent
FROM users u
LEFT JOIN orders o ON u.user_id = o.user_id
WHERE u.created_at > '2026-01-01'
GROUP BY u.user_id, u.name
HAVING COUNT(o.order_id) > 0
ORDER BY total_spent DESC
LIMIT 100;`,
      language: 'sql',
      executable: false,
    } as CodePayload,
  },
}

export const Plaintext: Story = {
  args: {
    richPayload: {
      payloadType: 'code',
      code: `This is a code block without language specification.
It will be rendered with auto-detected syntax highlighting.

Some common patterns:
- function foo() { }
- const x = 42
- print("hello")`,
      language: undefined,
      executable: false,
    } as CodePayload,
  },
}

export const Empty: Story = {
  args: {
    richPayload: null,
  },
}

export const JSON: Story = {
  args: {
    richPayload: {
      payloadType: 'code',
      code: `{
  "name": "AutoBot",
  "version": "2026.05",
  "features": [
    {
      "name": "Canvas",
      "status": "active"
    },
    {
      "name": "Charts",
      "status": "beta"
    }
  ],
  "config": {
    "debug": false,
    "timeout": 30000
  }
}`,
      language: 'json',
      executable: false,
    } as CodePayload,
  },
}
