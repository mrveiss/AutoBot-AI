<template>
  <div class="settings-tab-navigation">
    <!-- Unsaved Changes Indicator -->
    <div v-if="hasUnsavedChanges" class="unsaved-changes-indicator">
      <i class="fas fa-exclamation-circle"></i>
      <span>You have unsaved changes. Click "Save Settings" to apply them.</span>
    </div>

    <div class="settings-tabs">
      <router-link
        v-for="tab in tabs"
        :key="tab.id"
        :to="`/settings/${tab.id}`"
        class="settings-tab-link"
        :class="{ active: isActiveTab(tab.id) }"
        :aria-label="tab.label"
      >
        {{ tab.label }}
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'

interface Tab {
  id: string
  label: string
}

interface Props {
  hasUnsavedChanges: boolean
  tabs: Tab[]
}

defineProps<Props>()

const route = useRoute()

const isActiveTab = (tabId: string): boolean => {
  // Check if current route matches the tab
  const currentPath = route.path
  return currentPath === `/settings/${tabId}` ||
         route.name === `settings-${tabId}`
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.settings-tab-navigation {
  margin-bottom: var(--spacing-5);
}

.unsaved-changes-indicator {
  background: linear-gradient(45deg, var(--color-warning), var(--color-warning-hover));
  color: var(--text-on-primary);
  padding: var(--spacing-3) var(--spacing-4);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-5);
  display: flex;
  align-items: center;
  font-weight: var(--font-medium);
  box-shadow: var(--shadow-md);
}

.unsaved-changes-indicator i {
  margin-right: var(--spacing-3);
  font-size: var(--text-base);
}

.settings-tabs {
  display: flex;
  border-bottom: 1px solid var(--border-default);
  overflow-x: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.settings-tabs::-webkit-scrollbar {
  display: none;
}

.settings-tab-link {
  background: none;
  border: none;
  padding: var(--spacing-3) var(--spacing-5);
  cursor: pointer;
  border-bottom: 3px solid transparent;
  transition: all var(--duration-200) var(--ease-in-out);
  white-space: nowrap;
  color: var(--text-secondary);
  font-weight: var(--font-medium);
  min-width: 100px;
  text-decoration: none;
  text-align: center;
}

.settings-tab-link:hover {
  background-color: var(--bg-secondary);
  color: var(--text-primary);
}

.settings-tab-link.active {
  border-bottom-color: var(--color-primary);
  color: var(--color-primary);
  background-color: var(--bg-tertiary);
}

.settings-tab-link:focus {
  outline: none;
  box-shadow: inset 0 0 0 2px var(--color-primary);
}

/* Mobile responsive */
@media (max-width: 768px) {
  .settings-tab-link {
    padding: var(--spacing-2-5) var(--spacing-4);
    min-width: 80px;
    font-size: var(--text-sm);
  }
}
</style>
