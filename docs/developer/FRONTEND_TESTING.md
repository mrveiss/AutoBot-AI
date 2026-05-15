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

---

## Advanced Patterns

### Router / Routing Setup

Components that use `useRouter()`, `$route`, or consume route params require router setup. Use a test helper
to mount the component with a fake router context:

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { setActivePinia, createPinia } from 'pinia'
import MyComponent from '../MyComponent.vue'

describe('MyComponent with Router', () => {
  let router: any

  beforeEach(() => {
    setActivePinia(createPinia())

    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/chat/:chatId',
          name: 'ChatView',
          component: { template: '<div />' }
        }
      ]
    })
  })

  it('accesses route params via useRouter()', async () => {
    const wrapper = mount(MyComponent, {
      global: {
        plugins: [router]
      }
    })

    await router.push('/chat/chat-123')
    await wrapper.vm.$nextTick()

    // Component can now call useRouter() and access route params
    expect(wrapper.vm.currentChatId).toBe('chat-123')
  })

  it('responds to route changes', async () => {
    const wrapper = mount(MyComponent, {
      global: { plugins: [router] }
    })

    await router.push('/chat/session-1')
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.session-1').exists()).toBe(true)

    await router.push('/chat/session-2')
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.session-2').exists()).toBe(true)
  })
})
```

Real example from `SettingsPanel.test.ts`: use `renderComponent(SettingsPanel, { router: true })`
to automatically set up router with test defaults.

---

### Module Mocking with vi.mock()

When a component depends on external modules (API clients, services), mock them at the top of
the test file using `vi.mock()`. This intercepts all `import` statements before tests run.

Always re-configure mock return values in `beforeEach` because Vitest's global `vi.clearAllMocks()`
wipes mock state between tests.

```typescript
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import axios from 'axios'

// Mock the entire module at module scope
vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    create: vi.fn().mockReturnThis(),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
  },
}))

// Mock domain-specific services
vi.mock('@/services/api', () => ({
  default: {
    getSettings: vi.fn(),
    saveSettings: vi.fn(),
  },
}))

describe('SettingsPanel', () => {
  beforeEach(() => {
    // Re-configure mock implementations after vi.clearAllMocks() wipes them
    vi.mocked(axios.get).mockImplementation((url: string) => {
      if (url === '/api/settings/') {
        return Promise.resolve({ data: { theme: 'dark' } })
      }
      return Promise.resolve({ data: {} })
    })

    vi.mocked(axios.post).mockResolvedValue({ data: { success: true } })
    vi.mocked(axios.put).mockResolvedValue({ data: { success: true } })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('calls API on mount and loads settings', async () => {
    renderComponent(SettingsPanel)

    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/api/settings/')
    })
  })

  it('saves settings with PUT request', async () => {
    const { user } = renderComponent(SettingsPanel)

    await user.click(screen.getByText('Save'))

    await waitFor(() => {
      expect(axios.put).toHaveBeenCalled()
    })
  })
})
```

Key points:

- `vi.mock()` is module-scoped; place it at the top level, not inside `beforeEach`
- Use `vi.mocked()` to access the mock and re-configure its return values
- `vi.clearAllMocks()` in `afterEach` resets call counts and clears mocks for the next test

Real example: `ChatInterface.test.ts` mocks `BatchApiService`, `ApiClient`, `ChatRepository`, and multiple composables.

---

### Composables Testing

Custom hooks (composables) are tested in isolation using a helper that mounts them in a component context.
Composables must be called during component setup, not in event handlers or watches.

```typescript
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { useToast } from '../useToast'

/**
 * Helper: Mount a minimal component and call the composable in setup().
 * Returns the composable's return value.
 */
function withSetup<T>(setup: () => T): T {
  let result!: T
  const Wrapper = defineComponent({
    setup() {
      result = setup()
      return {}
    },
    template: '<div />',
  })
  mount(Wrapper, { global: { stubs: { Teleport: true } } })
  return result
}

describe('useToast Composable', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('adds and removes toasts', async () => {
    const { showToast, removeToast, toasts } = withSetup(() => useToast())

    const id = showToast('Hello', 'success', 4000)
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0].id).toBe(id)

    removeToast(id)
    expect(toasts.value).toHaveLength(0)
  })

  it('auto-dismisses success toasts after 4 seconds', async () => {
    const { showToast, toasts } = withSetup(() => useToast())

    showToast('Auto-dismiss me', 'success') // default 4000ms
    expect(toasts.value).toHaveLength(1)

    vi.advanceTimersByTime(4000)
    await nextTick()

    expect(toasts.value).toHaveLength(0)
  })

  it('keeps error toasts until manually dismissed', async () => {
    const { showToast, toasts } = withSetup(() => useToast())

    showToast('Persistent error', 'error') // duration 0 = persistent
    vi.advanceTimersByTime(30000) // advance time way forward
    await nextTick()

    // Toast is still there
    expect(toasts.value).toHaveLength(1)
  })

  it('enforces max 5 toasts and evicts oldest', async () => {
    const { showToast, toasts } = withSetup(() => useToast())

    for (let i = 1; i <= 6; i++) {
      showToast(`Toast ${i}`, 'info', 0) // duration 0 = never auto-dismiss
    }

    // Stack is capped at 5; first toast is evicted
    expect(toasts.value).toHaveLength(5)
    expect(toasts.value.some(t => t.message === 'Toast 1')).toBe(false)
    expect(toasts.value[0].message).toBe('Toast 2')
  })
})
```

Key patterns:

- Use `withSetup()` to call composables in a component context
- Composables often manage state or side effects; test them in isolation first
- Use `vi.useFakeTimers()` to control time-based behavior (auto-dismiss, debounce)
- Composables can be tested without mounting full components

Real example: `useModal.test.ts` has 100+ tests covering initialization, state, callbacks, and edge cases.

---

### Events and Slots

Test component emissions (`@emit`) and slot rendering by mounting child components with template overrides.

#### Testing Emitted Events

```typescript
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CommandButton from '../CommandButton.vue'

describe('CommandButton Emissions', () => {
  it('emits "execute" with command data on click', async () => {
    const wrapper = mount(CommandButton, {
      props: {
        command: {
          id: 'task-create',
          label: 'Create Task',
          action: () => {}
        }
      }
    })

    await wrapper.find('button').trigger('click')

    // Check that emit was called with correct payload
    expect(wrapper.emitted('execute')).toBeTruthy()
    expect(wrapper.emitted('execute')?.[0]).toEqual([
      { id: 'task-create', label: 'Create Task' }
    ])
  })

  it('emits "close" when close button clicked', async () => {
    const wrapper = mount(CommandButton, {
      props: { command: { id: 'cmd-1', label: 'Test' } }
    })

    await wrapper.find('.close-btn').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('emits multiple events in sequence', async () => {
    const wrapper = mount(CommandButton)

    await wrapper.find('.open-btn').trigger('click')
    expect(wrapper.emitted('open')).toBeTruthy()

    await wrapper.find('.action-btn').trigger('click')
    expect(wrapper.emitted('action')).toBeTruthy()

    await wrapper.find('.close-btn').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()

    // Verify order: open -> action -> close
    const emits = [
      ...wrapper.emitted('open'),
      ...wrapper.emitted('action'),
      ...wrapper.emitted('close'),
    ]
    expect(emits).toHaveLength(3)
  })
})
```

#### Testing Slot Content

```typescript
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Modal from '../Modal.vue'

describe('Modal Slots', () => {
  it('renders default slot content', () => {
    const wrapper = mount(Modal, {
      slots: {
        default: 'Modal body content'
      }
    })

    expect(wrapper.text()).toContain('Modal body content')
  })

  it('renders named slots', () => {
    const wrapper = mount(Modal, {
      slots: {
        header: '<h1>Modal Header</h1>',
        body: '<p>Modal body</p>',
        footer: '<button>Close</button>'
      }
    })

    expect(wrapper.find('h1').text()).toBe('Modal Header')
    expect(wrapper.find('p').text()).toBe('Modal body')
    expect(wrapper.find('button').text()).toBe('Close')
  })

  it('renders scoped slot with data', () => {
    const wrapper = mount(Modal, {
      slots: {
        item: '<span>{{ slotProps.id }}</span>'
      }
    })

    // Scoped slots receive data from parent via v-slot="slotProps"
    // Access via wrapper.vm.$slots['item']
    expect(wrapper.find('span').exists()).toBe(true)
  })

  it('renders multiple items via slot', () => {
    const wrapper = mount(Modal, {
      slots: {
        body: `
          <div class="item">Item 1</div>
          <div class="item">Item 2</div>
          <div class="item">Item 3</div>
        `
      }
    })

    expect(wrapper.findAll('.item')).toHaveLength(3)
  })
})
```

Real example: `CommandPalette.test.ts` does not have slot tests because CommandPalette uses internal rendering,
but components like `List.vue` or `Card.vue` that have slot-based layouts would use this pattern.

---

### Stubbing Child Components

Isolate parent component logic by stubbing child components. This prevents child initialization
side effects and lets you focus on parent behavior.

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ParentComponent from '../ParentComponent.vue'
import ChildComponent from '../ChildComponent.vue'

describe('ParentComponent with Stubbed Child', () => {
  it('renders without initializing child', () => {
    const wrapper = mount(ParentComponent, {
      global: {
        stubs: {
          // Replace ChildComponent with a stub (minimal implementation)
          ChildComponent: true
        }
      }
    })

    // Parent renders; child is a generic <child-component /> stub
    expect(wrapper.find('child-component-stub').exists()).toBe(true)
  })

  it('passes props to stubbed child', () => {
    const wrapper = mount(ParentComponent, {
      global: {
        stubs: {
          ChildComponent: {
            template: '<div class="mock-child">{{ title }}</div>',
            props: ['title']
          }
        }
      }
    })

    const child = wrapper.findComponent({ name: 'ChildComponent' })
    expect(child.props('title')).toBe('Expected Title')
  })

  it('handles child emit events via stub', async () => {
    const wrapper = mount(ParentComponent, {
      global: {
        stubs: {
          ChildComponent: {
            template: '<button @click="$emit(\'selected\', 123)">Click me</button>',
            emits: ['selected']
          }
        }
      }
    })

    const button = wrapper.find('button')
    await button.trigger('click')

    // Parent receives emit from child
    expect(wrapper.emitted('child-action')).toBeTruthy()
  })

  it('stubs multiple children to test parent orchestration', () => {
    const wrapper = mount(ParentComponent, {
      global: {
        stubs: {
          HeaderComponent: { template: '<header>Stub Header</header>' },
          BodyComponent: { template: '<main>Stub Body</main>' },
          FooterComponent: { template: '<footer>Stub Footer</footer>' }
        }
      }
    })

    expect(wrapper.find('header').text()).toBe('Stub Header')
    expect(wrapper.find('main').text()).toBe('Stub Body')
    expect(wrapper.find('footer').text()).toBe('Stub Footer')
  })

  it('stubs child but preserves specific behaviors', () => {
    const mockOnLoad = vi.fn()

    const wrapper = mount(ParentComponent, {
      global: {
        stubs: {
          ChildComponent: {
            template: `
              <div>
                <button @click="$emit('load')">Load</button>
              </div>
            `,
            emits: ['load'],
            setup(props: any, { emit }: any) {
              const handleLoad = () => {
                mockOnLoad()
                emit('load')
              }
              return { handleLoad }
            }
          }
        }
      }
    })

    const button = wrapper.find('button')
    button.trigger('click')

    expect(mockOnLoad).toHaveBeenCalled()
  })
})
```

Key points:

- `stubs: { ChildComponent: true }` replaces component with a no-op (prevents side effects)
- `stubs: { ChildComponent: { template: '...' } }` creates a custom stub with your own template
- Stubs prevent child initialization, allowing isolated testing of parent logic
- Use stubs when child components have expensive setup (API calls, heavy computation)

Real example: `ChatInterface.test.ts` doesn't heavily stub because it tests integration,
but components with many child dependencies would stub heavily.

---