# AutoBot Frontend Testing Guide

![Coverage](https://img.shields.io/badge/coverage-0%25-red)
[![Tests](https://github.com/your-org/autobot/workflows/Frontend%20Testing%20Suite/badge.svg)](https://github.com/your-org/autobot/actions)

## Overview

This document provides comprehensive guidelines for testing the AutoBot Vue.js frontend application. The testing framework is designed to ensure reliability, performance, and maintainability of the user interface components.

## Table of Contents

- [Testing Stack](#testing-stack)
- [Test Types](#test-types)
- [Getting Started](#getting-started)
- [Writing Tests](#writing-tests)
- [Test Organization](#test-organization)
- [Best Practices](#best-practices)
- [CI/CD Integration](#cicd-integration)
- [Troubleshooting](#troubleshooting)

## Testing Stack

### Core Testing Tools

- **[Vitest](https://vitest.dev/)** - Fast unit testing framework with native ESM support
- **[Vue Test Utils](https://test-utils.vuejs.org/)** - Official Vue.js testing utilities
- **[Testing Library](https://testing-library.com/)** - User-centric testing utilities
- **[Playwright](https://playwright.dev/)** - End-to-end testing framework
- **[MSW](https://mswjs.io/)** - Mock Service Worker for API mocking

### Additional Tools

- **[Happy DOM](https://github.com/capricorn86/happy-dom)** - Lightweight DOM implementation
- **[Mock Socket](https://github.com/thoov/mock-socket)** - WebSocket mocking
- **[Codecov](https://codecov.io/)** - Coverage reporting
- **[Lighthouse CI](https://github.com/GoogleChrome/lighthouse-ci)** - Performance testing

## Test Types

### 1. Unit Tests
- **Location**: `src/**/*.test.ts`
- **Purpose**: Test individual components, functions, and modules in isolation
- **Tools**: Vitest, Vue Test Utils, Testing Library
- **Run**: `npm run test:unit`

### 2. Integration Tests
- **Location**: `src/**/*.integration.test.ts`
- **Purpose**: Test component interactions and API service integrations
- **Tools**: Vitest, MSW
- **Run**: `npm run test:integration`

### 3. End-to-End Tests
- **Location**: `src/test/e2e/*.e2e.test.ts`
- **Purpose**: Test complete user workflows
- **Tools**: Playwright
- **Run**: `npm run test:playwright`

### 4. Visual Tests
- **Purpose**: Detect visual regressions
- **Tools**: Playwright
- **Run**: `npm run test:playwright -- --grep="visual"`

### 5. Performance Tests
- **Purpose**: Monitor bundle size and runtime performance
- **Tools**: Lighthouse CI, Webpack Bundle Analyzer
- **Run**: Automatic on CI

## Getting Started

### Initial Setup

```bash
# Install dependencies
npm install

# Run all tests
npm run test:all

# Run tests in watch mode
npm run test:unit:watch

# Run tests with coverage
npm run test:coverage

# Open test UI
npm run test:unit:ui
```

### Environment Setup

1. **Test Environment Variables**:
   ```bash
   # .env.test
   VITE_API_BASE_URL=http://localhost:8001
   VITE_WS_URL=ws://localhost:8001/ws
   ```

2. **Mock Data**: All tests use consistent mock data from `src/test/utils/test-utils.ts`

3. **Test Database**: Uses in-memory storage for isolated testing

## Writing Tests

### Component Testing

```typescript
import { describe, it, expect } from 'vitest'
import { renderComponent } from '../../test/utils/test-utils'
import MyComponent from '../MyComponent.vue'

describe('MyComponent', () => {
  it('renders correctly', () => {
    const { screen } = renderComponent(MyComponent, {
      props: { title: 'Test Title' }
    })
    
    expect(screen.getByText('Test Title')).toBeInTheDocument()
  })

  it('handles user interactions', async () => {
    const { screen, user } = renderComponent(MyComponent)
    
    const button = screen.getByRole('button', { name: 'Click me' })
    await user.click(button)
    
    expect(screen.getByText('Button clicked!')).toBeInTheDocument()
  })
})
```

### API Service Testing

```typescript
import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from '../mocks/api-handlers'
import ApiService from '../api'

const server = setupServer(...handlers)

describe('API Service', () => {
  beforeAll(() => server.listen())
  afterAll(() => server.close())

  it('sends chat message', async () => {
    const apiService = new ApiService()
    const result = await apiService.sendMessage('Hello')
    
    expect(result.success).toBe(true)
    expect(result.data.message.content).toBe('Hello')
  })
})
```

### E2E Testing

```typescript
import { test, expect } from '@playwright/test'

test.describe('Chat Workflow', () => {
  test('complete chat session', async ({ page }) => {
    await page.goto('/')
    
    // Start new chat
    await page.click('[data-testid="new-chat-button"]')
    
    // Send message
    await page.fill('[data-testid="message-input"]', 'Hello')
    await page.click('[data-testid="send-button"]')
    
    // Verify message appears
    await expect(page.locator('[data-testid="user-message"]')).toContainText('Hello')
  })
})
```

### WebSocket Testing

```typescript
import { webSocketTestUtil } from '../../test/mocks/websocket-mock'

describe('WebSocket Integration', () => {
  beforeEach(() => {
    webSocketTestUtil.setup()
  })

  afterEach(() => {
    webSocketTestUtil.teardown()
  })

  it('receives WebSocket messages', async () => {
    renderComponent(ChatInterface)
    
    webSocketTestUtil.connect('ws://localhost:8001/ws')
    webSocketTestUtil.simulateChatMessage('Hello from server')
    
    await waitFor(() => {
      expect(screen.getByText('Hello from server')).toBeInTheDocument()
    })
  })
})
```

## Test Organization

### Directory Structure

```
autobot-vue/
├── src/
│   ├── components/
│   │   ├── __tests__/           # Component unit tests
│   │   │   ├── ChatInterface.test.ts
│   │   │   ├── TerminalWindow.test.ts
│   │   │   └── SettingsPanel.test.ts
│   │   └── MyComponent.vue
│   ├── services/
│   │   ├── __tests__/           # Service unit tests
│   │   │   └── api.integration.test.ts
│   │   └── api.js
│   ├── test/
│   │   ├── e2e/                 # End-to-end tests
│   │   │   ├── chat-workflow.e2e.test.ts
│   │   │   └── terminal-workflow.e2e.test.ts
│   │   ├── mocks/               # Mock utilities
│   │   │   ├── api-handlers.ts
│   │   │   ├── websocket-mock.ts
│   │   │   └── api-client-mock.ts
│   │   ├── utils/               # Test utilities
│   │   │   └── test-utils.ts
│   │   ├── setup.ts             # Test setup
│   │   └── integration-setup.ts
│   └── ...
├── coverage/                    # Coverage reports
├── test-results/               # Test artifacts
└── playwright-report/          # E2E test reports
```

### Naming Conventions

- **Unit tests**: `ComponentName.test.ts`
- **Integration tests**: `service.integration.test.ts`
- **E2E tests**: `feature-workflow.e2e.test.ts`
- **Mock files**: `service-mock.ts`
- **Test utilities**: `test-utils.ts`

### Test Data Management

All test data should use the factory functions in `test-utils.ts`:

```typescript
// ✅ Good - Using factories
const mockMessage = createMockChatMessage({ content: 'Test' })
const mockSession = createMockChatSession({ messages: [mockMessage] })

// ❌ Bad - Hardcoded data
const mockMessage = {
  id: 'test-123',
  content: 'Test',
  sender: 'user',
  timestamp: 1234567890
}
```

## Best Practices

### General Testing Principles

1. **Test Behavior, Not Implementation**
   ```typescript
   // ✅ Good - Testing behavior
   expect(screen.getByText('Message sent')).toBeInTheDocument()
   
   // ❌ Bad - Testing implementation
   expect(component.vm.messageCount).toBe(1)
   ```

2. **Use Descriptive Test Names**
   ```typescript
   // ✅ Good
   it('displays error message when API request fails')
   
   // ❌ Bad
   it('test error')
   ```

3. **Follow AAA Pattern**
   ```typescript
   it('should update message count when new message is sent', async () => {
     // Arrange
     renderComponent(ChatInterface)
     const input = screen.getByLabelText('Message input')
     
     // Act
     await user.type(input, 'Hello')
     await user.click(screen.getByRole('button', { name: 'Send' }))
     
     // Assert
     expect(screen.getByText('Hello')).toBeInTheDocument()
   })
   ```

### Component Testing Best Practices

1. **Test User Interactions**
   ```typescript
   it('submits form when Enter is pressed', async () => {
     renderComponent(MessageInput)
     const input = screen.getByRole('textbox')
     
     await user.type(input, 'Test message')
     await user.keyboard('{Enter}')
     
     expect(mockSubmitHandler).toHaveBeenCalledWith('Test message')
   })
   ```

2. **Test Accessibility**
   ```typescript
   it('has proper ARIA labels', () => {
     renderComponent(ChatInterface)
     
     expect(screen.getByLabelText('Send message')).toBeInTheDocument()
     expect(screen.getByRole('button', { name: 'New chat' })).toBeInTheDocument()
   })
   ```

3. **Mock External Dependencies**
   ```typescript
   vi.mock('@/services/api', () => ({
     default: createMockApiService()
   }))
   ```

### E2E Testing Best Practices

1. **Use Data Test IDs**
   ```html
   <!-- In component -->
   <button data-testid="send-button">Send</button>
   ```
   
   ```typescript
   // In test
   await page.click('[data-testid="send-button"]')
   ```

2. **Test Critical User Paths**
   - User registration/login
   - Core feature workflows
   - Error handling scenarios

3. **Use Page Object Pattern**
   ```typescript
   class ChatPage {
     constructor(private page: Page) {}
     
     async sendMessage(message: string) {
       await this.page.fill('[data-testid="message-input"]', message)
       await this.page.click('[data-testid="send-button"]')
     }
   }
   ```

### Performance Testing

1. **Monitor Bundle Size**
   ```typescript
   test('bundle size stays within limits', async () => {
     const stats = await getBundleStats()
     expect(stats.totalSize).toBeLessThan(1024 * 1024) // 1MB
   })
   ```

2. **Test Rendering Performance**
   ```typescript
   test('renders large message list efficiently', async () => {
     const manyMessages = Array.from({ length: 1000 }, createMockMessage)
     const startTime = performance.now()
     
     renderComponent(ChatInterface, { props: { messages: manyMessages } })
     
     const endTime = performance.now()
     expect(endTime - startTime).toBeLessThan(100) // 100ms
   })
   ```

## Coverage Requirements

### Minimum Coverage Thresholds

```typescript
// vitest.config.ts
coverage: {
  thresholds: {
    global: {
      branches: 70,
      functions: 70,
      lines: 70,
      statements: 70,
    },
  },
}
```

### Coverage Exclusions

- Configuration files
- Type definitions
- Test utilities
- Development-only code

### Measuring Coverage

```bash
# Generate coverage report
npm run test:coverage

# View HTML report
open coverage/index.html

# View coverage in terminal
npm run test:coverage -- --reporter=text
```

## CI/CD Integration

### GitHub Actions Workflow

The testing suite runs automatically on:
- Push to main/develop branches
- Pull requests
- Scheduled runs (daily)

### Test Stages

1. **Static Analysis** - Linting, type checking
2. **Unit Tests** - Component and service tests
3. **Integration Tests** - API and service integration
4. **E2E Tests** - Cross-browser testing
5. **Performance Tests** - Bundle analysis, Lighthouse
6. **Security Scans** - Dependency vulnerabilities

### Test Artifacts

- Coverage reports → Codecov
- Test results → GitHub Actions
- Screenshots → Artifacts
- Performance reports → Lighthouse CI

## Troubleshooting

### Common Issues

#### 1. Tests Timing Out
```typescript
// Issue: Backend connectivity timeouts
// Solution: Use mocks and increase timeouts

test('handles API timeout', async () => {
  mockApi.client.get.mockImplementation(() => 
    new Promise(resolve => setTimeout(resolve, 35000))
  )
  
  await expect(apiService.getData()).rejects.toThrow(/timeout/)
}, 40000) // Increase test timeout
```

#### 2. WebSocket Connection Issues
```typescript
// Issue: WebSocket connection failures
// Solution: Use WebSocket mocks

beforeEach(() => {
  webSocketTestUtil.setup()
})

afterEach(() => {
  webSocketTestUtil.teardown()
})
```

#### 3. Flaky E2E Tests
```typescript
// Issue: Race conditions in E2E tests
// Solution: Use proper waits

// ❌ Bad
await page.click('[data-testid="button"]')
expect(page.locator('[data-testid="result"]')).toBeVisible()

// ✅ Good
await page.click('[data-testid="button"]')
await expect(page.locator('[data-testid="result"]')).toBeVisible()
```

#### 4. Memory Leaks in Tests
```typescript
// Issue: Tests not cleaning up properly
// Solution: Proper cleanup in beforeEach/afterEach

afterEach(() => {
  vi.clearAllMocks()
  cleanup() // From Testing Library
  webSocketTestUtil.teardown()
})
```

### Debug Mode

```bash
# Run tests in debug mode
npm run test:unit -- --reporter=verbose

# Run single test file
npm run test:unit -- ChatInterface.test.ts

# Run tests matching pattern
npm run test:unit -- --grep="chat message"

# Run E2E tests in headed mode
npm run test:playwright:headed
```

### Test Environment Issues

1. **JSDOM vs Happy DOM**: Use Happy DOM for better performance
2. **ESM Issues**: Ensure proper module resolution in `vitest.config.ts`
3. **Vue 3 Composition API**: Use proper testing utilities for `<script setup>`

## Contributing

### Adding New Tests

1. **Choose the Right Test Type**:
   - Unit: Testing isolated functionality
   - Integration: Testing component interactions
   - E2E: Testing user workflows

2. **Follow the Existing Patterns**:
   - Use established mock utilities
   - Follow naming conventions
   - Include proper cleanup

3. **Update Coverage Requirements**:
   - Ensure new code meets coverage thresholds
   - Add exclusions for non-testable code

### Code Review Checklist

- [ ] Tests cover the happy path
- [ ] Tests cover error scenarios
- [ ] Tests are not flaky
- [ ] Tests use proper mocking
- [ ] Tests have descriptive names
- [ ] Tests follow established patterns
- [ ] Coverage thresholds are met

## Resources

### Documentation
- [Vitest Documentation](https://vitest.dev/)
- [Vue Test Utils Guide](https://test-utils.vuejs.org/)
- [Testing Library Best Practices](https://testing-library.com/docs/guiding-principles)
- [Playwright Documentation](https://playwright.dev/)

### Examples
- Component tests: `src/components/__tests__/ChatInterface.test.ts`
- Integration tests: `src/services/__tests__/api.integration.test.ts`
- E2E tests: `src/test/e2e/chat-workflow.e2e.test.ts`

### Tools
- [Vue DevTools](https://devtools.vuejs.org/) - Debugging Vue components
- [Playwright Inspector](https://playwright.dev/docs/debug) - E2E test debugging
- [Coverage Reports](./coverage/index.html) - Local coverage analysis

---

For questions or issues with testing, please refer to the project's [issue tracker](https://github.com/your-org/autobot/issues) or contact the development team.