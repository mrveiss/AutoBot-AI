<template>
  <div class="z-10 flex border-b border-gray-200 bg-white flex-shrink-0 overflow-x-auto">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      @click="$emit('tab-change', tab.key)"
      :class="[
        'px-6 py-3 text-sm font-medium transition-colors whitespace-nowrap',
        activeTab === tab.key
          ? 'border-b-2 border-indigo-500 text-indigo-600 bg-indigo-50'
          : 'text-gray-600 hover:text-gray-800 hover:bg-gray-50'
      ]"
    >
      <i :class="`${tab.icon} mr-2`"></i>
      {{ tab.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
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

const props = withDefaults(defineProps<Props>(), {
  tabs: () => [
    { key: 'chat', label: 'Chat', icon: 'fas fa-comments' },
    { key: 'files', label: 'Files', icon: 'fas fa-folder' },
    { key: 'terminal', label: 'Terminal', icon: 'fas fa-terminal' },
    { key: 'browser', label: 'Browser', icon: 'fas fa-globe' },
    { key: 'novnc', label: 'noVNC', icon: 'fas fa-desktop' }
  ]
})

defineEmits<Emits>()
</script>

<style scoped>
/* Tabs are styled via Tailwind classes in template */
</style>
