# Frontend Testing Guide

Guidelines for writing and running frontend tests in AutoBot.

---

## Testing Stack

- **Vitest** — test runner and assertion library
- **@vue/test-utils** — Vue component mounting utilities
- **Pinia** — state management (requires explicit setup in tests)
- **vue-i18n** — internationalisation (provide via `global.plugins` when needed)

---

## Testing Vue Components with Pinia Stores

Any Vue component test that uses Pinia stores (accessed via `useChatStore()`, `useAppStore()`, etc.)
**requires explicit Pinia initialisation** in the test's `beforeEach` hook.

### Error without Pinia setup

```
"getActivePinia()" was called but there was no active Pinia.
Are you trying to use a store before calling "app.use(pinia)"?
```

This error occurs because Pinia stores call `getActivePinia()` at the point of first use. Without
calling `setActivePinia(createPinia())` before mounting the component, there is no active instance
and the store throws.

### Solution

Call `setActivePinia(createPinia())` in `beforeEach` so each test gets a fresh, isolated store:

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import MyComponent from '../MyComponent.vue'

describe('MyComponent', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should work with stores', () => {
    const wrapper = mount(MyComponent)
    // Store methods and state are now accessible
    expect(wrapper.exists()).toBe(true)
  })
})
```

Calling `createPinia()` in `beforeEach` (not once in `beforeAll`) ensures store state is reset
between tests, preventing one test's mutations from leaking into another.

### Real example

`autobot-frontend/src/components/__tests__/CommandPalette.test.ts` (lines 32-36):

```typescript
describe('CommandPalette.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
  })
  // ...
})
```

---

## Providing vue-i18n in Component Tests

Components that use `$t()` or `useI18n()` require an i18n instance passed as a global plugin.
Create it once at the top of the test file and reuse it across all tests:

```typescript
import { createI18n } from 'vue-i18n'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      // Only the keys the component actually uses
    }
  }
})

describe('MyComponent', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders translated text', () => {
    const wrapper = mount(MyComponent, {
      global: { plugins: [i18n] }
    })
    expect(wrapper.text()).toContain('Expected text')
  })
})
```

---

## Mocking async functions

`patch(asyncFn, { return_value: X })` creates a `MagicMock`, not an `AsyncMock`.
For async functions, always use `vi.fn().mockResolvedValue(X)` in Vitest:

```typescript
import { vi } from 'vitest'

const mockFetch = vi.fn().mockResolvedValue({ data: 'example' })
```

Note: `vi.mock` factories with `mockReset: true` in `vitest.config.ts` will wipe mock implementations
between tests. Re-apply `mockResolvedValue` / `mockReturnValue` inside `beforeEach` when this
option is enabled.

---

## Running Tests

```bash
cd autobot-frontend
npm run test          # run all tests once
npm run test:watch    # re-run on file change
npm run type-check    # TypeScript type checking (run before committing)
npm run lint          # ESLint (run before committing)
```
