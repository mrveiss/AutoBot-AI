<template>
  <div class="settings-section" v-if="isActive">
    <h3>Notification Settings</h3>
    <p class="text-sm text-gray-600 mb-4">
      Control how system notifications are displayed. These settings help you stay informed without being disruptive.
    </p>

    <!-- Enable/Disable Notifications -->
    <div class="setting-item">
      <label class="with-description">
        Enable System Notifications
        <span class="description">Turn on/off all system status notifications</span>
      </label>
      <input 
        type="checkbox" 
        :checked="settings.enabled"
        @change="handleCheckboxChange('enabled', $event)" 
      />
    </div>

    <!-- Notification Level -->
    <div class="setting-item" v-if="settings.enabled">
      <label class="with-description">
        Default Notification Level
        <span class="description">How notifications should be displayed by default</span>
      </label>
      <select 
        :value="settings.level"
        @change="handleSelectChange('level', $event)"
      >
        <option value="toast">Toast (Top-right corner)</option>
        <option value="banner">Banner (Top of page)</option>
        <option value="modal">Modal (Center overlay)</option>
      </select>
    </div>

    <!-- Warning Minimum Level -->
    <div class="setting-item" v-if="settings.enabled">
      <label class="with-description">
        Warning Notifications
        <span class="description">Minimum display level for warning messages</span>
      </label>
      <select 
        :value="settings.warningMinLevel || 'banner'"
        @change="handleSelectChange('warningMinLevel', $event)"
      >
        <option value="toast">Toast</option>
        <option value="banner">Banner</option>
        <option value="modal">Modal</option>
      </select>
    </div>

    <!-- Error Minimum Level -->
    <div class="setting-item" v-if="settings.enabled">
      <label class="with-description">
        Error Notifications
        <span class="description">Minimum display level for error messages</span>
      </label>
      <select 
        :value="settings.errorMinLevel || 'modal'"
        @change="handleSelectChange('errorMinLevel', $event)"
      >
        <option value="toast">Toast</option>
        <option value="banner">Banner</option>
        <option value="modal">Modal</option>
      </select>
    </div>

    <!-- Position -->
    <div class="setting-item" v-if="settings.enabled">
      <label class="with-description">
        Toast Position
        <span class="description">Where toast notifications should appear</span>
      </label>
      <select 
        :value="settings.position || 'top-right'"
        @change="handleSelectChange('position', $event)"
      >
        <option value="top-right">Top Right</option>
        <option value="top-left">Top Left</option>
        <option value="bottom-right">Bottom Right</option>
        <option value="bottom-left">Bottom Left</option>
        <option value="top-center">Top Center</option>
        <option value="bottom-center">Bottom Center</option>
      </select>
    </div>

    <!-- Auto-hide Options -->
    <div class="notification-auto-hide mt-6 pt-4 border-t border-gray-200" v-if="settings.enabled">
      <h4>Auto-hide Settings</h4>
      
      <div class="setting-item">
        <label class="with-description">
          Auto-hide Success Messages
          <span class="description">Automatically close success notifications after a delay</span>
        </label>
        <input 
          type="checkbox" 
          :checked="settings.autoHide?.success || true"
          @change="handleAutoHideChange('success', $event)" 
        />
      </div>
      
      <div class="setting-item">
        <label class="with-description">
          Success Auto-hide Duration (seconds)
          <span class="description">How long to show success messages before auto-closing</span>
        </label>
        <input 
          type="number" 
          :value="settings.autoHideDelay?.success || 5"
          min="1" 
          max="60" 
          @input="handleNumberChange('autoHideDelay.success', $event)"
        />
      </div>
      
      <div class="setting-item">
        <label class="with-description">
          Auto-hide Info Messages
          <span class="description">Automatically close info notifications after a delay</span>
        </label>
        <input 
          type="checkbox" 
          :checked="settings.autoHide?.info || true"
          @change="handleAutoHideChange('info', $event)" 
        />
      </div>
      
      <div class="setting-item">
        <label class="with-description">
          Info Auto-hide Duration (seconds)
          <span class="description">How long to show info messages before auto-closing</span>
        </label>
        <input 
          type="number" 
          :value="settings.autoHideDelay?.info || 8"
          min="1" 
          max="60" 
          @input="handleNumberChange('autoHideDelay.info', $event)"
        />
      </div>
      
      <div class="setting-item">
        <label class="with-description">
          Auto-hide Warnings
          <span class="description">Automatically close warning notifications (not recommended)</span>
        </label>
        <input 
          type="checkbox" 
          :checked="settings.autoHide?.warning || false"
          @change="handleAutoHideChange('warning', $event)" 
        />
      </div>
      
      <div class="setting-item" v-if="settings.autoHide?.warning">
        <label class="with-description">
          Warning Auto-hide Duration (seconds)
          <span class="description">How long to show warning messages before auto-closing</span>
        </label>
        <input 
          type="number" 
          :value="settings.autoHideDelay?.warning || 15"
          min="5" 
          max="120" 
          @input="handleNumberChange('autoHideDelay.warning', $event)"
        />
      </div>
      
      <div class="setting-item">
        <label class="with-description">
          Keep Errors Visible
          <span class="description">Never auto-hide error notifications (recommended)</span>
        </label>
        <input 
          type="checkbox" 
          :checked="!(settings.autoHide?.error || false)"
          @change="handleErrorAutoHideToggle($event)" 
        />
      </div>
    </div>

    <!-- Test Notifications -->
    <div class="notification-test mt-6 pt-4 border-t border-gray-200" v-if="settings.enabled">
      <h4>Test Notifications</h4>
      <p class="text-xs text-gray-500 mb-3">
        Preview how different notification types will appear with your current settings.
      </p>
      <div class="flex gap-2 flex-wrap">
        <button 
          @click="testNotification('info')" 
          class="px-3 py-1 text-xs bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
        >
          Test Info
        </button>
        <button 
          @click="testNotification('success')" 
          class="px-3 py-1 text-xs bg-green-100 text-green-700 rounded hover:bg-green-200"
        >
          Test Success
        </button>
        <button 
          @click="testNotification('warning')" 
          class="px-3 py-1 text-xs bg-yellow-100 text-yellow-700 rounded hover:bg-yellow-200"
        >
          Test Warning
        </button>
        <button 
          @click="testNotification('error')" 
          class="px-3 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200"
        >
          Test Error
        </button>
      </div>
    </div>

    <!-- Reset to Defaults -->
    <div class="mt-6 pt-4 border-t border-gray-200">
      <button 
        @click="resetToDefaults"
        class="px-3 py-2 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
      >
        Reset to Defaults
      </button>
      <p class="text-xs text-gray-500 mt-2">
        This will restore all notification settings to their default values.
      </p>
    </div>

    <!-- Current Status -->
    <div class="notification-status mt-6 pt-4 border-t border-gray-200">
      <h4>Current System Status</h4>
      <div class="flex items-center mt-2">
        <div :class="[
          'w-3 h-3 rounded-full mr-3',
          systemStatus.status === 'success' ? 'bg-green-500' :
          systemStatus.status === 'warning' ? 'bg-yellow-500' :
          systemStatus.status === 'error' ? 'bg-red-500' :
          'bg-gray-500'
        ]"></div>
        <span class="text-sm">{{ systemStatus.text }}</span>
        <span v-if="systemStatus.pulse" class="ml-2 text-xs text-gray-500 animate-pulse">●</span>
      </div>
      <div class="text-xs text-gray-500 mt-1">
        Active notifications: {{ activeNotificationCount }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '@/stores/useAppStore'
import type { NotificationSettings } from '@/stores/useAppStore'

interface Props {
  isActive: boolean
}

defineProps<Props>()

const appStore = useAppStore()

// Computed properties
const settings = computed(() => appStore.notificationSettings)
const systemStatus = computed(() => appStore.systemStatusIndicator)
const activeNotificationCount = computed(() => 
  appStore.systemNotifications.filter((n: any) => n.visible).length
)

// Event handlers with proper typing
const handleCheckboxChange = (key: keyof NotificationSettings, event: Event) => {
  const target = event.target as HTMLInputElement
  if (target) {
    updateSetting(key, target.checked)
  }
}

const handleSelectChange = (key: keyof NotificationSettings, event: Event) => {
  const target = event.target as HTMLSelectElement
  if (target) {
    updateSetting(key, target.value)
  }
}

const handleNumberChange = (key: string, event: Event) => {
  const target = event.target as HTMLInputElement
  if (target) {
    const value = parseInt(target.value, 10)
    if (key.includes('.')) {
      const [parentKey, childKey] = key.split('.')
      const currentValue = (settings.value as any)[parentKey] || {}
      updateSetting(parentKey as keyof NotificationSettings, { ...currentValue, [childKey]: value })
    } else {
      updateSetting(key as keyof NotificationSettings, value)
    }
  }
}

const handleAutoHideChange = (type: string, event: Event) => {
  const target = event.target as HTMLInputElement
  if (target) {
    const currentAutoHide = settings.value.autoHide || {}
    updateSetting('autoHide', { ...currentAutoHide, [type]: target.checked })
  }
}

const handleErrorAutoHideToggle = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (target) {
    const currentAutoHide = settings.value.autoHide || {}
    updateSetting('autoHide', { ...currentAutoHide, error: !target.checked })
  }
}

// Methods
const updateSetting = (key: keyof NotificationSettings, value: any) => {
  appStore.updateNotificationSettings({ [key]: value })
}

const testNotification = (severity: 'info' | 'success' | 'warning' | 'error') => {
  const messages = {
    info: {
      title: 'Test Info Notification',
      message: 'This is a test information notification to preview how info messages appear.'
    },
    success: {
      title: 'Test Success Notification', 
      message: 'This is a test success notification to preview how success messages appear.'
    },
    warning: {
      title: 'Test Warning Notification',
      message: 'This is a test warning notification to preview how warning messages appear.'
    },
    error: {
      title: 'Test Error Notification',
      message: 'This is a test error notification to preview how error messages appear.'
    }
  }

  appStore.addSystemNotification({
    severity,
    ...messages[severity],
    statusDetails: {
      status: 'Test',
      lastCheck: Date.now(),
      timestamp: Date.now()
    }
  })
}

const resetToDefaults = () => {
  appStore.resetNotificationSettings()
}
</script>

<style scoped>
.notification-auto-hide h4,
.notification-test h4,
.notification-status h4 {
  font-size: 0.875rem;
  font-weight: 600;
  color: #374151;
  margin-bottom: 0.5rem;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 0;
  border-bottom: 1px solid #f3f4f6;
}

.setting-item:last-child {
  border-bottom: none;
}

.setting-item label {
  flex: 1;
  font-weight: 500;
  color: #374151;
}

.setting-item label.with-description {
  display: flex;
  flex-direction: column;
}

.setting-item .description {
  font-size: 0.75rem;
  font-weight: normal;
  color: #6b7280;
  margin-top: 0.25rem;
}

.setting-item input,
.setting-item select {
  margin-left: 1rem;
  flex-shrink: 0;
}

.setting-item input[type="checkbox"] {
  transform: scale(1.2);
}

.setting-item input[type="number"] {
  padding: 0.25rem 0.5rem;
  border: 1px solid #d1d5db;
  border-radius: 0.25rem;
  text-align: center;
}

.setting-item select {
  padding: 0.25rem 0.5rem;
  border: 1px solid #d1d5db;
  border-radius: 0.25rem;
  background-color: white;
}

.text-xs {
  font-size: 0.75rem;
}

.text-sm {
  font-size: 0.875rem;
}
</style>