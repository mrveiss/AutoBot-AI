<template>
  <div
    ref="tablistRef"
    role="tablist"
    :aria-label="t('chat.tabs.ariaLabel')"
    class="z-10 flex border-b border-autobot-border bg-autobot-bg-card shrink-0 overflow-x-auto"
    @keydown="onKeydown"
  >
    <button
      v-for="tab in visibleTabs"
      :id="`tab-${tab.key}`"
      :key="tab.key"
      type="button"
      role="tab"
      :aria-selected="activeTab === tab.key"
      :aria-controls="activeTab === tab.key ? `tabpanel-${tab.key}` : undefined"
      :tabindex="activeTab === tab.key ? 0 : -1"
      @click="$emit('tab-change', tab.key)"
      :class="[
        'px-6 py-3 text-sm font-medium transition-colors whitespace-nowrap focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-autobot-primary',
        activeTab === tab.key
          ? 'border-b-2 border-autobot-primary text-autobot-primary bg-autobot-primary-bg'
          : 'text-autobot-text-secondary hover:text-autobot-text-primary hover:bg-autobot-bg-secondary'
      ]"
    >
      <i :class="`${tab.icon} mr-2`" aria-hidden="true"></i>
      {{ tab.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePermissions } from '@/composables/usePermissions'

interface TabItem {
  key: string
  label: string
  icon: string
}

interface Props {
  activeTab: string
  tabs?: TabItem[]
}

interface Emits {
  (e: 'tab-change', tabKey: string): void
}

const props = defineProps<Props>()
const { t } = useI18n()
const { holdsPermission } = usePermissions()

/**
 * The permission the desktop socket itself asks for (#17054). Read through
 * `holdsPermission` -- the role table, no administrative override -- because
 * `hasPermission` short-circuits on `isAdmin`, which is not what the socket
 * asks. Superadmin holds it through admin's derived table entry (#19125), so
 * the two agree (#17370).
 */
const DESKTOP_PERMISSION = 'mcp.desktop.control'

// #17370: all five labels were hardcoded English in a `withDefaults` default.
// A computed rather than a default factory so they follow a locale change --
// a default is evaluated once.
const defaultTabs = computed<TabItem[]>(() => [
  { key: 'chat', label: t('chat.tabs.chat'), icon: 'comments' },
  { key: 'files', label: t('chat.tabs.files'), icon: 'folder' },
  { key: 'terminal', label: t('chat.tabs.terminal'), icon: 'terminal' },
  { key: 'browser', label: t('chat.tabs.browser'), icon: 'globe' },
  { key: 'novnc', label: t('chat.tabs.novnc'), icon: 'desktop' }
])

const visibleTabs = computed<TabItem[]>(() => {
  const all = props.tabs ?? defaultTabs.value
  if (holdsPermission(DESKTOP_PERMISSION)) return all
  return all.filter((tab) => tab.key !== 'novnc')
})

const emit = defineEmits<Emits>()

const tablistRef = ref<HTMLElement | null>(null)

/** Index the key moves to, or null for a key the tablist ignores. */
function targetIndex(key: string, from: number, count: number): number | null {
  if (key === 'ArrowRight') return (from + 1) % count
  if (key === 'ArrowLeft') return (from - 1 + count) % count
  if (key === 'Home') return 0
  if (key === 'End') return count - 1
  return null
}

/**
 * WAI-ARIA tablist keys (automatic activation). Kept local rather than
 * `useTabs` because the visible set here is permission-filtered and the
 * active tab is owned by the parent route, not by the composable.
 */
async function onKeydown(event: KeyboardEvent): Promise<void> {
  const list = visibleTabs.value
  const current = list.findIndex((tab) => tab.key === props.activeTab)
  const next = targetIndex(event.key, Math.max(current, 0), list.length)
  if (next === null || list.length === 0) return
  event.preventDefault()
  emit('tab-change', list[next].key)
  await nextTick()
  tablistRef.value?.querySelectorAll<HTMLElement>('[role="tab"]')[next]?.focus()
}
</script>
