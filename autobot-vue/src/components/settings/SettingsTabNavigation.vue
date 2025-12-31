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
.settings-tab-navigation {
  margin-bottom: 20px;
}

.unsaved-changes-indicator {
  background: linear-gradient(45deg, #ff6b35, #ff8e3c);
  color: white;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  font-weight: 500;
  box-shadow: 0 2px 8px rgba(255, 107, 53, 0.3);
}

.unsaved-changes-indicator i {
  margin-right: 12px;
  font-size: 16px;
}

.settings-tabs {
  display: flex;
  border-bottom: 1px solid #e0e0e0;
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
  padding: 12px 20px;
  cursor: pointer;
  border-bottom: 3px solid transparent;
  transition: all 0.2s ease;
  white-space: nowrap;
  color: #666;
  font-weight: 500;
  min-width: 100px;
  text-decoration: none;
  text-align: center;
}

.settings-tab-link:hover {
  background-color: #f5f5f5;
  color: #333;
}

.settings-tab-link.active {
  border-bottom-color: #007acc;
  color: #007acc;
  background-color: #f9f9f9;
}

.settings-tab-link:focus {
  outline: none;
  box-shadow: inset 0 0 0 2px #007acc;
}

/* Dark theme support */
@media (prefers-color-scheme: dark) {
  .settings-tabs {
    border-bottom-color: #444;
  }

  .settings-tab-link {
    color: #ccc;
  }

  .settings-tab-link:hover {
    background-color: #333;
    color: #fff;
  }

  .settings-tab-link.active {
    background-color: #2d2d2d;
    color: #4fc3f7;
    border-bottom-color: #4fc3f7;
  }
}

/* Mobile responsive */
@media (max-width: 768px) {
  .settings-tab-link {
    padding: 10px 16px;
    min-width: 80px;
    font-size: 14px;
  }
}
</style>
