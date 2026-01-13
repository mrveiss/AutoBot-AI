<template>
  <aside class="settings-sidebar">
    <div class="sidebar-header">
      <h3><i class="fas fa-cog"></i> Settings</h3>
    </div>

    <!-- Unsaved Changes Indicator -->
    <div v-if="hasUnsavedChanges" class="unsaved-changes-indicator">
      <i class="fas fa-exclamation-circle"></i>
      <span>Unsaved changes</span>
    </div>

    <!-- Category Navigation -->
    <nav class="category-nav">
      <router-link
        v-for="tab in tabs"
        :key="tab.id"
        :to="`/settings/${tab.id}`"
        class="category-item"
        :class="{ active: isActiveTab(tab.id) }"
        :aria-label="tab.label"
      >
        <i :class="getTabIcon(tab.id)"></i>
        <span>{{ tab.label }}</span>
      </router-link>
    </nav>
  </aside>
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

// Map tab IDs to appropriate icons
const getTabIcon = (tabId: string): string => {
  const iconMap: Record<string, string> = {
    'user': 'fas fa-users',
    'chat': 'fas fa-comments',
    'backend': 'fas fa-server',
    'optimization': 'fas fa-bolt',
    'ui': 'fas fa-palette',
    'logging': 'fas fa-file-alt',
    'log-forwarding': 'fas fa-share-alt',
    'cache': 'fas fa-database',
    'prompts': 'fas fa-edit',
    'infrastructure': 'fas fa-network-wired',
    'developer': 'fas fa-code',
    'feature-flags': 'fas fa-flag'
  }
  return iconMap[tabId] || 'fas fa-cog'
}
</script>

<style scoped>
/* Issue #704: Sidebar navigation style matching SecretsManager */
.settings-sidebar {
  width: 240px;
  min-width: 240px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  height: 100%;
}

.sidebar-header {
  padding: 20px;
  border-bottom: 1px solid var(--border-default);
}

.sidebar-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.sidebar-header i {
  color: var(--color-primary);
}

.unsaved-changes-indicator {
  background: var(--color-warning-bg);
  color: var(--color-warning);
  padding: 10px 20px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  font-size: 13px;
  border-bottom: 1px solid var(--border-default);
}

.unsaved-changes-indicator i {
  font-size: 14px;
}

.category-nav {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
}

.category-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px;
  cursor: pointer;
  transition: all 0.15s;
  color: var(--text-secondary);
  text-decoration: none;
}

.category-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.category-item.active {
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-right: 3px solid var(--color-primary);
}

.category-item i {
  width: 20px;
  text-align: center;
  font-size: 14px;
}

.category-item span {
  font-size: 14px;
  font-weight: 500;
}

/* Scrollbar styling */
.category-nav::-webkit-scrollbar {
  width: 6px;
}

.category-nav::-webkit-scrollbar-track {
  background: transparent;
}

.category-nav::-webkit-scrollbar-thumb {
  background: var(--bg-tertiary);
  border-radius: 3px;
}

.category-nav::-webkit-scrollbar-thumb:hover {
  background: var(--text-muted);
}

/* Mobile responsive */
@media (max-width: 768px) {
  .settings-sidebar {
    width: 100%;
    min-width: 100%;
    max-height: 200px;
    border-right: none;
    border-bottom: 1px solid var(--border-default);
  }

  .category-nav {
    display: flex;
    flex-wrap: wrap;
    padding: 8px;
    gap: 4px;
  }

  .category-item {
    padding: 8px 12px;
    border-radius: 6px;
    flex: 0 0 auto;
  }

  .category-item.active {
    border-right: none;
    border-radius: 6px;
  }

  .category-item span {
    font-size: 12px;
  }
}
</style>
