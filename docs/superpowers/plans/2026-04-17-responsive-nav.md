# Responsive "More ▾" Nav Overflow Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the desktop navigation's unconstrained flex row with an overflow-aware layout that collapses extra items into a "More ▾" dropdown when the header shrinks below fit width.

**Architecture:** A `useNavOverflow` composable uses `ResizeObserver` on the nav container to recompute `visibleCount` on every resize. App.vue renders visible items normally and passes overflow items to a new `NavOverflowMenu.vue` dropdown component. Admin-only filtering happens before the split so hidden items never count toward visible slots.

**Tech Stack:** Vue 3 Composition API, TypeScript, Tailwind v4 CSS utilities, native `ResizeObserver`, Vue `Teleport`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `autobot-frontend/src/composables/useNavOverflow.ts` | ResizeObserver logic, visible/overflow split |
| Create | `autobot-frontend/src/components/layout/NavOverflowMenu.vue` | "More ▾" trigger button + teleported dropdown |
| Modify | `autobot-frontend/src/App.vue` | Wire composable, swap v-for, add NavOverflowMenu |
| Modify | `autobot-frontend/src/i18n/locales/en.json` | Add `nav.more` and `nav.moreItems` keys |

---

## Task 1: `useNavOverflow` composable

**Files:**
- Create: `autobot-frontend/src/composables/useNavOverflow.ts`
- Create: `autobot-frontend/src/composables/__tests__/useNavOverflow.test.ts`

- [ ] **Step 1: Write the failing test**

Create `autobot-frontend/src/composables/__tests__/useNavOverflow.test.ts`:

```typescript
import { describe, it, expect, vi, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useNavOverflow } from '../useNavOverflow'

let observeCallback: (() => void) | null = null
const mockObserver = { observe: vi.fn(), disconnect: vi.fn() }
vi.stubGlobal('ResizeObserver', vi.fn((cb: () => void) => {
  observeCallback = cb
  return mockObserver
}))

function makeContainer(width: number, itemWidths: number[]): HTMLElement {
  const container = document.createElement('div')
  Object.defineProperty(container, 'clientWidth', { get: () => width, configurable: true })
  itemWidths.forEach(w => {
    const el = document.createElement('a')
    el.setAttribute('data-nav-item', '')
    el.getBoundingClientRect = () => ({ width: w } as DOMRect)
    container.appendChild(el)
  })
  document.body.appendChild(container)
  return container
}

describe('useNavOverflow', () => {
  afterEach(() => { document.body.innerHTML = ''; vi.clearAllMocks() })

  it('shows all items when they fit', async () => {
    const container = makeContainer(800, [80, 80, 80, 80])
    const { visibleCount } = useNavOverflow(ref(container), ref(4))
    await nextTick()
    expect(visibleCount.value).toBe(4)
  })

  it('clamps when container is narrow', async () => {
    const container = makeContainer(250, [80, 80, 80, 80])
    const { visibleCount } = useNavOverflow(ref(container), ref(4))
    await nextTick()
    expect(visibleCount.value).toBe(1)
  })

  it('recalculates when ResizeObserver fires', async () => {
    const container = makeContainer(250, [80, 80, 80, 80])
    const { visibleCount } = useNavOverflow(ref(container), ref(4))
    await nextTick()
    expect(visibleCount.value).toBe(1)
    Object.defineProperty(container, 'clientWidth', { get: () => 800, configurable: true })
    observeCallback?.()
    await nextTick()
    expect(visibleCount.value).toBe(4)
  })

  it('always shows at least 1 item', async () => {
    const container = makeContainer(50, [200, 200, 200])
    const { visibleCount } = useNavOverflow(ref(container), ref(3))
    await nextTick()
    expect(visibleCount.value).toBe(1)
  })
})
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/autobot-frontend
npx vitest run src/composables/__tests__/useNavOverflow.test.ts --reporter=verbose 2>&1 | tail -20
```

Expected: FAIL — `useNavOverflow` not found.

- [ ] **Step 3: Implement the composable**

Create `autobot-frontend/src/composables/useNavOverflow.ts`:

```typescript
import { ref, onMounted, onUnmounted, nextTick, type Ref } from 'vue'

const MORE_BUTTON_WIDTH = 90  // px reserved for "More ▾" button
const GAP = 16                // matches space-x-4

export function useNavOverflow(
  containerRef: Ref<HTMLElement | null>,
  itemCount: Ref<number>
) {
  const visibleCount = ref(itemCount.value)
  let naturalWidths: number[] = []
  let ro: ResizeObserver | null = null

  function measureNaturalWidths() {
    const container = containerRef.value
    if (!container) return
    naturalWidths = Array.from(
      container.querySelectorAll<HTMLElement>('[data-nav-item]')
    ).map(el => el.getBoundingClientRect().width)
  }

  function recalculate() {
    const container = containerRef.value
    if (!container) return
    if (naturalWidths.length === 0) measureNaturalWidths()
    if (naturalWidths.length === 0) return

    const totalNatural = naturalWidths.reduce((s, w) => s + w + GAP, 0)
    const available = container.clientWidth

    if (totalNatural <= available) {
      visibleCount.value = naturalWidths.length
      return
    }

    const budget = available - MORE_BUTTON_WIDTH
    let consumed = 0
    let count = 0
    for (const w of naturalWidths) {
      consumed += w + GAP
      if (consumed > budget) break
      count++
    }
    visibleCount.value = Math.max(1, count)
  }

  onMounted(async () => {
    await nextTick()
    measureNaturalWidths()
    recalculate()
    ro = new ResizeObserver(recalculate)
    if (containerRef.value) ro.observe(containerRef.value)
  })

  onUnmounted(() => ro?.disconnect())

  return { visibleCount }
}
```

- [ ] **Step 4: Run tests**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/autobot-frontend
npx vitest run src/composables/__tests__/useNavOverflow.test.ts --reporter=verbose 2>&1 | tail -20
```

Expected: 4 tests PASS.

- [ ] **Step 5: Type-check**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/autobot-frontend
npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep useNavOverflow | head -10
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/autobot-frontend
git add src/composables/useNavOverflow.ts src/composables/__tests__/useNavOverflow.test.ts
git commit -m "feat(nav): add useNavOverflow composable with ResizeObserver-based overflow detection"
```

---

## Task 2: `NavOverflowMenu` component + i18n keys

**Files:**
- Create: `autobot-frontend/src/components/layout/NavOverflowMenu.vue`
- Modify: `autobot-frontend/src/i18n/locales/en.json`

- [ ] **Step 1: Add i18n keys to en.json**

In `autobot-frontend/src/i18n/locales/en.json`, find the `nav` object's last two entries:

```json
    "loadingTimeout": "Page load timeout",
    "loadingTimeoutMessage": "The page is taking longer than expected to load."
```

Replace with:

```json
    "loadingTimeout": "Page load timeout",
    "loadingTimeoutMessage": "The page is taking longer than expected to load.",
    "more": "More",
    "moreItems": "More navigation items"
```

- [ ] **Step 2: Create NavOverflowMenu.vue**

Create `autobot-frontend/src/components/layout/NavOverflowMenu.vue`:

```vue
<template>
  <div ref="triggerRef" class="relative">
    <button
      :aria-expanded="open"
      aria-haspopup="true"
      :aria-label="$t('nav.moreItems')"
      :class="[
        'px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 flex items-center space-x-1',
        hasActiveItem
          ? 'bg-autobot-primary text-white'
          : 'text-autobot-text-primary hover:bg-autobot-bg-tertiary'
      ]"
      @click="toggle"
      @keydown.escape="close"
    >
      <span>{{ $t('nav.more') }}</span>
      <svg
        class="w-3 h-3 transition-transform duration-150"
        :class="open ? 'rotate-180' : ''"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 20 20"
        aria-hidden="true"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8l5 5 5-5" />
      </svg>
    </button>

    <Teleport to="body">
      <div
        v-if="open"
        ref="dropdownRef"
        :style="dropdownStyle"
        class="fixed z-50 bg-autobot-bg-secondary border border-autobot-border rounded-md shadow-lg py-1 min-w-40"
        role="menu"
        :aria-label="$t('nav.moreItems')"
      >
        <router-link
          v-for="item in items"
          :key="item.to"
          :to="item.to"
          role="menuitem"
          class="flex items-center space-x-2 px-3 py-2 text-sm transition-colors duration-150 hover:bg-autobot-bg-tertiary"
          :class="$route.path.startsWith(item.to) ? 'text-autobot-primary' : 'text-autobot-text-primary'"
          @click="close"
        >
          <svg
            class="w-4 h-4 shrink-0"
            :fill="item.iconStroke ? 'none' : 'currentColor'"
            :stroke="item.iconStroke ? 'currentColor' : undefined"
            viewBox="0 0 20 20"
            aria-hidden="true"
          >
            <template v-if="item.iconPaths">
              <path
                v-for="(p, pi) in item.iconPaths"
                :key="pi"
                :d="p"
                :fill-rule="item.iconRule"
                :clip-rule="item.iconRule"
              />
            </template>
            <path
              v-else
              :d="item.icon"
              :fill-rule="item.iconRule"
              :clip-rule="item.iconRule"
              :stroke-linecap="item.iconStroke ? 'round' : undefined"
              :stroke-linejoin="item.iconStroke ? 'round' : undefined"
              :stroke-width="item.iconStroke ? '2' : undefined"
            />
          </svg>
          <span>{{ $t(item.labelKey) }}</span>
        </router-link>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'

type SvgFillRule = 'evenodd' | 'nonzero' | 'inherit'

interface NavItem {
  to: string
  labelKey: string
  icon?: string
  iconPaths?: string[]
  iconRule?: SvgFillRule
  iconStroke?: boolean
}

const props = defineProps<{ items: NavItem[] }>()

const route = useRoute()
const open = ref(false)
const triggerRef = ref<HTMLElement | null>(null)
const dropdownRef = ref<HTMLElement | null>(null)
const dropdownStyle = ref<Record<string, string>>({})

const hasActiveItem = computed(() =>
  props.items.some(item => route.path.startsWith(item.to))
)

function positionDropdown() {
  if (!triggerRef.value) return
  const rect = triggerRef.value.getBoundingClientRect()
  dropdownStyle.value = {
    top: `${rect.bottom + 4}px`,
    left: `${rect.left}px`,
  }
}

function toggle() {
  if (!open.value) positionDropdown()
  open.value = !open.value
}

function close() {
  open.value = false
}

function onClickOutside(event: MouseEvent) {
  const target = event.target as Node
  if (!triggerRef.value?.contains(target) && !dropdownRef.value?.contains(target)) {
    close()
  }
}

onMounted(() => document.addEventListener('click', onClickOutside, true))
onUnmounted(() => document.removeEventListener('click', onClickOutside, true))
</script>
```

- [ ] **Step 3: Type-check**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/autobot-frontend
npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep NavOverflowMenu | head -10
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/autobot-frontend
git add src/components/layout/NavOverflowMenu.vue src/i18n/locales/en.json
git commit -m "feat(nav): add NavOverflowMenu component with teleported dropdown and active-route highlight"
```

---

## Task 3: Wire overflow into App.vue desktop nav

**Files:**
- Modify: `autobot-frontend/src/App.vue`

- [ ] **Step 1: Read current desktop nav markup**

Read `autobot-frontend/src/App.vue` lines 40–90 to confirm exact current markup before editing.

- [ ] **Step 2: Replace desktop nav inner container**

In App.vue, replace the entire `<div class="hidden lg:flex items-center space-x-8">` block (lines ~42–87) with the following. Key changes: `ref="navContainerRef"`, `data-nav-item` on each link, `shrink-0` on all links, `overflow-hidden` on container, `v-for` uses `visibleNavItems`, `NavOverflowMenu` added after the loop:

```html
<div class="hidden lg:flex items-center space-x-8">
  <div ref="navContainerRef" class="flex items-center space-x-4 overflow-hidden">
    <template v-for="item in visibleNavItems" :key="item.to">
      <router-link
        v-if="!item.adminOnly || userStore.isAdmin"
        :to="item.to"
        data-nav-item
        :class="{
          'bg-autobot-primary text-white': $route.path.startsWith(item.to),
          'text-autobot-text-primary hover:bg-autobot-bg-tertiary': !$route.path.startsWith(item.to)
        }"
        class="px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 shrink-0"
      >
        <div class="flex items-center space-x-1">
          <svg class="w-4 h-4" :fill="item.iconStroke ? 'none' : 'currentColor'" :stroke="item.iconStroke ? 'currentColor' : undefined" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
            <template v-if="item.iconPaths">
              <path v-for="(p, pi) in item.iconPaths" :key="pi" :d="p" :fill-rule="item.iconRule" :clip-rule="item.iconRule"></path>
            </template>
            <path v-else :d="item.icon" :fill-rule="item.iconRule" :clip-rule="item.iconRule" :stroke-linecap="item.iconStroke ? 'round' : undefined" :stroke-linejoin="item.iconStroke ? 'round' : undefined" :stroke-width="item.iconStroke ? '2' : undefined"></path>
          </svg>
          <span>{{ $t(item.labelKey) }}</span>
        </div>
      </router-link>
    </template>

    <NavOverflowMenu
      v-if="overflowNavItems.length > 0"
      :items="overflowNavItems"
    />

    <!-- SLM Admin: external link (Issue #729) -->
    <a
      :href="slmAdminUrl"
      target="_blank"
      rel="noopener noreferrer"
      class="px-3 py-2 rounded text-sm font-medium transition-colors duration-150 text-autobot-text-primary hover:bg-autobot-bg-tertiary shrink-0"
      :title="$t('nav.slmAdminTitle')"
      :aria-label="$t('nav.slmAdminTitle')"
    >
      <div class="flex items-center space-x-1">
        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
          <path fill-rule="evenodd" d="M2 5a2 2 0 012-2h12a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm3.293 1.293a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 01-1.414-1.414L7.586 10 5.293 7.707a1 1 0 010-1.414zM11 12a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd"></path>
        </svg>
        <span>{{ $t('nav.slmAdmin') }}</span>
        <svg class="w-3 h-3 opacity-50" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
          <path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z"></path>
          <path d="M5 5a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-3a1 1 0 10-2 0v3H5V7h3a1 1 0 000-2H5z"></path>
        </svg>
      </div>
    </a>
  </div>
</div>
```

- [ ] **Step 3: Add imports to App.vue script section**

Add these two imports near the top of the script section (alongside other component/composable imports):

```typescript
import { useNavOverflow } from '@/composables/useNavOverflow'
import NavOverflowMenu from '@/components/layout/NavOverflowMenu.vue'
```

- [ ] **Step 4: Add reactive state and computed inside setup()**

After the `navItems` array definition (line ~815), add:

```typescript
const navContainerRef = ref<HTMLElement | null>(null)

const filteredNavItems = computed(() =>
  navItems.filter(item => !item.adminOnly || userStore.isAdmin)
)

const { visibleCount } = useNavOverflow(
  navContainerRef,
  computed(() => filteredNavItems.value.length)
)

const visibleNavItems = computed(() => filteredNavItems.value.slice(0, visibleCount.value))
const overflowNavItems = computed(() => filteredNavItems.value.slice(visibleCount.value))
```

- [ ] **Step 5: Add new symbols to the return object**

In the `return { ... }` statement, add `navContainerRef`, `visibleNavItems`, and `overflowNavItems` to the exported symbols list.

- [ ] **Step 6: Type-check**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/autobot-frontend
npx vue-tsc --noEmit -p tsconfig.app.json 2>&1 | grep -E "error TS" | head -20
```

Expected: no errors.

- [ ] **Step 7: Build**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/autobot-frontend
npm run build 2>&1 | tail -20
```

Expected: build succeeds.

- [ ] **Step 8: Commit**

```bash
cd /home/martins/AutoBot-Ai/AutoBot-AI/autobot-frontend
git add src/App.vue
git commit -m "feat(nav): wire useNavOverflow into desktop nav — overflow items collapse to More dropdown"
```

---

## Self-Review

1. **Spec coverage**: ResizeObserver fires on resize → visibleCount updates → visibleNavItems/overflowNavItems recompute. ✓
2. **Active route in overflow**: NavOverflowMenu `hasActiveItem` computed highlights trigger when overflow route is active. ✓
3. **Keyboard**: Escape closes, click-outside closes, aria-expanded/aria-haspopup set. ✓
4. **Admin items**: Pre-filtered before split — non-admin users never see admin items in overflow. ✓
5. **Mobile nav unchanged**: Mobile nav still uses `navItems` directly — untouched. ✓
6. **No TBD/TODO placeholders**: All code is complete in every task. ✓
7. **Type consistency**: `NavItem` interface in NavOverflowMenu.vue matches `navItems` array shape in App.vue. ✓
