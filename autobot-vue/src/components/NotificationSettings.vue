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
        @change="updateSetting('enabled', $event.target.checked)" 
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
        @change="updateSetting('level', $event.target.value)"
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
        @change="updateSetting('warningMinLevel', $event.target.value)"
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
        :value="settings.errorMinLevel || 'banner'"
        @change="updateSetting('errorMinLevel', $event.target.value)"
      >
        <option value="toast">Toast</option>
        <option value="banner">Banner</option>
        <option value="modal">Modal</option>
      </select>
    </div>

    <!-- Critical as Modal -->
    <div class="setting-item" v-if="settings.enabled">
      <label class="with-description">
        Force Critical Errors as Modals
        <span class="description">Always show critical system errors as blocking modals</span>
      </label>
      <input 
        type="checkbox" 
        :checked="settings.criticalAsModal"
        @change="updateSetting('criticalAsModal', $event.target.checked)" 
      />
    </div>

    <!-- Auto-hide Settings -->
    <div class="notification-auto-hide" v-if="settings.enabled">
      <h4>Auto-Hide Timers</h4>
      <p class="text-xs text-gray-500 mb-3">
        Set to 0 to prevent auto-hiding. Times are in milliseconds (1000 = 1 second).
      </p>
      
      <div class="setting-item">
        <label>Success Messages (Auto-hide after)</label>
        <input 
          type="number" 
          :value="settings.autoHideSuccess"
          @input="updateSetting('autoHideSuccess', parseInt($event.target.value) || 0)"
          min="0" 
          max="30000" 
          step="1000"
          class="w-24"
        />
        <span class="text-xs text-gray-500 ml-2">ms</span>
      </div>

      <div class="setting-item">
        <label>Info Messages (Auto-hide after)</label>
        <input 
          type="number" 
          :value="settings.autoHideInfo"
          @input="updateSetting('autoHideInfo', parseInt($event.target.value) || 0)"
          min="0" 
          max="30000" 
          step="1000"
          class="w-24"
        />
        <span class="text-xs text-gray-500 ml-2">ms</span>
      </div>

      <div class="setting-item">
        <label>Warning Messages (Auto-hide after)</label>
        <input 
          type="number" 
          :value="settings.autoHideWarning"
          @input="updateSetting('autoHideWarning', parseInt($event.target.value) || 0)"
          min="0" 
          max="30000" 
          step="1000"
          class="w-24"
        />
        <span class="text-xs text-gray-500 ml-2">ms (0 = never)</span>
      </div>
    </div>

    <!-- Additional Options -->
    <div class="setting-item" v-if="settings.enabled">
      <label class="with-description">
        Show Details Button
        <span class="description">Allow expanding notifications to show detailed information</span>
      </label>
      <input 
        type="checkbox" 
        :checked="settings.showDetails"
        @change="updateSetting('showDetails', $event.target.checked)" 
      />
    </div>

    <div class="setting-item" v-if="settings.enabled">
      <label class="with-description">
        Sound Notifications
        <span class="description">Play sound alerts for notifications (not implemented yet)</span>
      </label>
      <input 
        type="checkbox" 
        :checked="settings.soundEnabled"
        @change="updateSetting('soundEnabled', $event.target.checked)"
        disabled
      />
      <span class="text-xs text-gray-400 ml-2">(Coming soon)</span>
    </div>

    <!-- Test Notification -->
    <div class="notification-test mt-6 pt-4 border-t border-gray-200" v-if="settings.enabled">
      <h4>Test Notifications</h4>
      <p class="text-xs text-gray-500 mb-3">
        Test different notification types to see how they appear with your current settings.
      </p>
      <div class="flex flex-wrap gap-2">
        <button 
          @click="testNotification('info')"
          class="px-3 py-1 bg-blue-500 text-white rounded text-xs hover:bg-blue-600 transition-colors"
        >
          Test Info
        </button>
        <button 
          @click="testNotification('success')"
          class="px-3 py-1 bg-green-500 text-white rounded text-xs hover:bg-green-600 transition-colors"
        >
          Test Success
        </button>
        <button 
          @click="testNotification('warning')"
          class="px-3 py-1 bg-yellow-500 text-white rounded text-xs hover:bg-yellow-600 transition-colors"
        >
          Test Warning
        </button>
        <button 
          @click="testNotification('error')"
          class="px-3 py-1 bg-red-500 text-white rounded text-xs hover:bg-red-600 transition-colors"
        >
          Test Error
        </button>
      </div>
    </div>

    <!-- Reset to Defaults -->
    <div class="notification-reset mt-6 pt-4 border-t border-gray-200">
      <button 
        @click="resetToDefaults"
        class="px-4 py-2 bg-gray-500 text-white rounded text-sm hover:bg-gray-600 transition-colors"
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
  appStore.systemNotifications.filter(n => n.visible).length
)

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