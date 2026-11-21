<template>
  <!-- List-only: ChatTabContent owns the tabpanel, so the kit renders none (#18243). -->
  <BaseTabs
    class="chat-tabs"
    list-only
    :items="items"
    :label="t('chat.tabs.ariaLabel')"
    :model-value="activeTab"
    @update:model-value="emit('tab-change', $event)"
  >
    <template #icon="{ item }">
      <Icon :name="iconFor(item.value)" />
    </template>
  </BaseTabs>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseTabs } from '@autobot/ui'
import type { TabItem as KitTabItem } from '@autobot/ui'
import Icon, { type IconName } from '@/components/ui/Icon.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useUiMode } from '@/composables/useUiMode'

interface TabItem {
  key: string
  label: string
  icon: IconName
  /** Advanced-only: hidden in Minimal mode (#18240). */
  adv?: boolean
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
  { key: 'terminal', label: t('chat.tabs.terminal'), icon: 'terminal', adv: true },
  { key: 'browser', label: t('chat.tabs.browser'), icon: 'globe', adv: true },
  { key: 'novnc', label: t('chat.tabs.novnc'), icon: 'desktop', adv: true }
])

const visibleTabs = computed<TabItem[]>(() => {
  const all = props.tabs ?? defaultTabs.value
  if (holdsPermission(DESKTOP_PERMISSION)) return all
  return all.filter((tab) => tab.key !== 'novnc')
})

const emit = defineEmits<Emits>()

/**
 * The trigger ids and the controlled panel keep the pairing ChatTabContent renders:
 * `tab-<key>` labels `tabpanel-<key>`, and only the active tab carries aria-controls.
 * An advanced tab is hidden in Minimal mode unless it is the active one (R4): a user on
 * Terminal who switches to Minimal must still see which tab they are on.
 */
const { uiMode } = useUiMode()
const minimal = computed(() => uiMode.value === 'minimal')

// Switching to Minimal while an advanced tab is open moves to Chat, the one tab Minimal always has.
watch(minimal, (isMinimal) => {
  const open = visibleTabs.value.find((tab) => tab.key === props.activeTab)
  if (isMinimal && open?.adv) emit('tab-change', 'chat')
})

const items = computed<KitTabItem[]>(() =>
  visibleTabs.value
    // Advanced tabs are display:none in Minimal, so they leave the roving-focus set too; the
    // active one stays (a bookmarked /chat/terminal still shows where you are).
    .filter((tab) => !(minimal.value && tab.adv && tab.key !== props.activeTab))
    .map((tab) => {
      const active = tab.key === props.activeTab
      return {
        value: tab.key,
        label: tab.label,
        id: `tab-${tab.key}`,
        controls: active ? `tabpanel-${tab.key}` : undefined,
        class: tab.adv && !active ? 'adv' : undefined,
      }
    }),
)

const iconByKey = computed(() => new Map(visibleTabs.value.map((tab) => [tab.key, tab.icon])))
const iconFor = (key: string): IconName => iconByKey.value.get(key) ?? 'comments'
</script>
