<template>
  <div class="z-10 flex border-b border-autobot-border bg-autobot-bg-card shrink-0 overflow-x-auto">
    <button
      v-for="tab in visibleTabs"
      :key="tab.key"
      @click="$emit('tab-change', tab.key)"
      :class="[
        'px-6 py-3 text-sm font-medium transition-colors whitespace-nowrap',
        activeTab === tab.key
          ? 'border-b-2 border-electric-500 text-electric-600 bg-electric-50'
          : 'text-autobot-text-secondary hover:text-autobot-text-primary hover:bg-autobot-bg-secondary'
      ]"
    >
      <i :class="`${tab.icon} mr-2`"></i>
      {{ tab.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
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
 * `hasPermission` short-circuits on `isAdmin` and would offer the tab to a
 * superadmin, whose table entry is empty and whom the socket refuses (#17370).
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

defineEmits<Emits>()
</script>

<style scoped>
/* Tabs are styled via Tailwind classes in template */
</style>
