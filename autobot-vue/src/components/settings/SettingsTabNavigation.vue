<template>
  <div class="settings-tab-navigation">
    <!-- Unsaved Changes Indicator -->
    <div v-if="hasUnsavedChanges" class="unsaved-changes-indicator">
      <i class="fas fa-exclamation-circle"></i>
      <span>You have unsaved changes. Click "Save Settings" to apply them.</span>
    </div>

    <div class="settings-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :class="{ active: activeTab === tab.id }"
        @click="$emit('tab-changed', tab.id)"
        :aria-label="tab.label"
      >
        {{ tab.label }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Tab {
  id: string
  label: string
}

interface Props {
  activeTab: string
  hasUnsavedChanges: boolean
  tabs: Tab[]
}

interface Emits {
  (e: 'tab-changed', tabId: string): void
}

defineProps<Props>()
defineEmits<Emits>()
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

.settings-tabs button {
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
}

.settings-tabs button:hover {
  background-color: #f5f5f5;
  color: #333;
}

.settings-tabs button.active {
  border-bottom-color: #007acc;
  color: #007acc;
  background-color: #f9f9f9;
}

.settings-tabs button:focus {
  outline: none;
  box-shadow: inset 0 0 0 2px #007acc;
}

/* Dark theme support */
@media (prefers-color-scheme: dark) {
  .settings-tabs {
    border-bottom-color: #444;
  }

  .settings-tabs button {
    color: #ccc;
  }

  .settings-tabs button:hover {
    background-color: #333;
    color: #fff;
  }

  .settings-tabs button.active {
    background-color: #2d2d2d;
    color: #4fc3f7;
    border-bottom-color: #4fc3f7;
  }
}

/* Mobile responsive */
@media (max-width: 768px) {
  .settings-tabs button {
    padding: 10px 16px;
    min-width: 80px;
    font-size: 14px;
  }
}
</style>