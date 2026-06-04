---
tags: [type/reference, status/current, component/frontend]
date: 2026-06-04
---

# Frontend Testing Guide

Testing approach and conventions for the AutoBot Vue.js frontend.

---

## Stack

| Tool | Purpose |
|---|---|
| [Vitest](https://vitest.dev/) | Unit testing (fast, native ESM) |
| [Vue Test Utils](https://test-utils.vuejs.org/) | Vue component testing |
| [Testing Library](https://testing-library.com/) | User-centric assertions |
| [Playwright](https://playwright.dev/) | End-to-end testing |
| [MSW](https://mswjs.io/) | API mocking (Mock Service Worker) |

---

## Getting Started

```bash
# Unit + integration tests
npm run test

# Watch mode
npm run test:watch

# With coverage
npm run test:coverage

# E2E
npx playwright test
```

---

## Test Types

### Unit — Composables and Utils

Test pure logic in isolation. Mock all external dependencies.

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useErrorHandler } from '@/composables/useErrorHandler'

describe('useErrorHandler', () => {
    beforeEach(() => {
        vi.clearAllMocks()
    })

    it('captures and formats API errors', () => {
        const { handleError, lastError } = useErrorHandler()
        handleError(new Error('404 Not Found'))
        expect(lastError.value?.message).toContain('Not Found')
    })
})
```

> **Note:** `mockReset: true` in vitest config clears `vi.mock()` factories between tests — re-apply mocks in `beforeEach` if needed.

### Component Tests

Test components through user interactions, not implementation details.

```typescript
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import MyComponent from '@/components/MyComponent.vue'

describe('MyComponent', () => {
    it('shows error state on failed fetch', async () => {
        const wrapper = mount(MyComponent, {
            global: { plugins: [createPinia()] },
        })

        await wrapper.find('[data-testid="retry-btn"]').trigger('click')
        await wrapper.vm.$nextTick()

        expect(wrapper.find('[data-testid="error-msg"]').exists()).toBe(true)
    })
})
```

### E2E Tests (Playwright)

Test full user workflows against a running dev server.

```typescript
// tests/e2e/chat.spec.ts
import { test, expect } from '@playwright/test'

test('sends a message and receives a response', async ({ page }) => {
    await page.goto('/chat')
    await page.fill('[data-testid="chat-input"]', 'Hello')
    await page.click('[data-testid="send-btn"]')
    await expect(page.locator('[data-testid="message-list"]')).toContainText('Hello')
})
```

---

## Organisation

```
autobot-frontend/
├── src/
│   ├── composables/
│   │   ├── useMyComposable.ts
│   │   └── __tests__/
│   │       └── useMyComposable.spec.ts   ← unit tests co-located
│   └── components/
│       ├── MyComponent.vue
│       └── __tests__/
│           └── MyComponent.spec.ts
└── tests/
    ├── e2e/          ← Playwright end-to-end tests
    └── visual/       ← Visual regression snapshots
```

---

## Mocking

### API Calls

Use MSW to intercept at the network layer:

```typescript
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

const server = setupServer(
    http.get('/api/chat/sessions', () =>
        HttpResponse.json([{ id: '1', title: 'Test Session' }])
    )
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
```

### Stores

```typescript
import { setActivePinia, createPinia } from 'pinia'

beforeEach(() => {
    setActivePinia(createPinia())
})
```

---

## ApiClient Return Shape

`useApi().get()` returns parsed JSON (`Promise<T>`), **not** a `Response` object. Never do `response.data.X` or `response.json()` in tests — that's the wrong shape.

---

## Best Practices

- Test behaviour, not implementation — prefer `getByRole`, `getByTestId`, `getByText`
- One assertion per test (or tightly related assertions)
- Avoid snapshots for dynamic content; use specific assertions
- Never test Pinia store internals directly — test through the component
- Keep test setup in `beforeEach`, not module scope, to avoid state leaks
