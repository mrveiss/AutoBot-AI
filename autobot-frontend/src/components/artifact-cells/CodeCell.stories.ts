// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import CodeCell from './CodeCell.vue'

const meta = {
  title: 'Components/Artifact Cells/CodeCell',
  component: CodeCell,
  tags: ['autodocs'],
  argTypes: {
    richPayload: {
      control: 'object',
      description: 'Code content object with code/content/text field'
    },
    language: {
      control: 'text',
      description: 'Programming language for syntax highlighting'
    },
    showLineNumbers: {
      control: 'boolean',
      description: 'Show line numbers (for future enhancement)'
    },
    copyable: {
      control: 'boolean',
      description: 'Allow copying code to clipboard'
    }
  }
} satisfies Meta<typeof CodeCell>

export default meta
type Story = StoryObj<typeof meta>

const pythonCode = `def fibonacci(n):
    """Calculate fibonacci number at position n."""
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

# Calculate first 10 fibonacci numbers
for i in range(10):
    print(f"F({i}) = {fibonacci(i)}")
`

const javascriptCode = `async function fetchUserData(userId) {
  try {
    const response = await fetch(\`/api/users/\${userId}\`);
    if (!response.ok) {
      throw new Error(\`HTTP error! status: \${response.status}\`);
    }
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Failed to fetch user:', error);
    return null;
  }
}

// Usage
const user = await fetchUserData(123);
console.log(user);
`

const sqlCode = `SELECT
    u.user_id,
    u.username,
    COUNT(p.post_id) as post_count,
    MAX(p.created_at) as last_post
FROM users u
LEFT JOIN posts p ON u.user_id = p.user_id
WHERE u.active = true
GROUP BY u.user_id, u.username
HAVING COUNT(p.post_id) > 0
ORDER BY post_count DESC
LIMIT 10;
`

const bashCode = `#!/bin/bash
# Deploy script

set -e  # Exit on error

echo "Starting deployment..."

# Build application
npm run build
echo "✓ Build completed"

# Run tests
npm run test
echo "✓ Tests passed"

# Deploy to production
git push origin main
echo "✓ Deployment complete"
`

const htmlCode = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hello World</title>
    <link rel="stylesheet" href="styles.css">
</head>
<body>
    <header>
        <nav>
            <ul>
                <li><a href="/">Home</a></li>
                <li><a href="/about">About</a></li>
            </ul>
        </nav>
    </header>
    <main>
        <h1>Welcome</h1>
        <p>This is a sample HTML document.</p>
    </main>
</body>
</html>
`

export const Python: Story = {
  args: {
    richPayload: { code: pythonCode },
    language: 'python'
  }
}

export const JavaScript: Story = {
  args: {
    richPayload: { code: javascriptCode },
    language: 'javascript'
  }
}

export const SQL: Story = {
  args: {
    richPayload: { code: sqlCode },
    language: 'sql'
  }
}

export const Bash: Story = {
  args: {
    richPayload: { code: bashCode },
    language: 'bash'
  }
}

export const HTML: Story = {
  args: {
    richPayload: { code: htmlCode },
    language: 'html'
  }
}

export const Empty: Story = {
  args: {
    richPayload: null,
    language: 'python'
  }
}

export const NoLanguageSpecified: Story = {
  args: {
    richPayload: { code: pythonCode },
    language: undefined
  }
}

export const NotCopyable: Story = {
  args: {
    richPayload: { code: javascriptCode },
    language: 'javascript',
    copyable: false
  }
}

export const LongCode: Story = {
  args: {
    richPayload: {
      code: Array(50)
        .fill(null)
        .map((_, i) => `// Line ${i + 1}`)
        .join('\n')
    },
    language: 'javascript'
  }
}

export const PlainText: Story = {
  args: {
    richPayload: {
      text: 'This is plain text\nNo syntax highlighting\nJust simple content'
    },
    language: 'text'
  }
}

export const JSONContent: Story = {
  args: {
    richPayload: {
      code: JSON.stringify(
        {
          name: 'example',
          version: '1.0.0',
          dependencies: {
            vue: '^3.5.0',
            typescript: '^5.0.0'
          }
        },
        null,
        2
      )
    },
    language: 'json'
  }
}

export const WithLineNumbers: Story = {
  args: {
    richPayload: { code: pythonCode },
    language: 'python',
    showLineNumbers: true
  }
}
