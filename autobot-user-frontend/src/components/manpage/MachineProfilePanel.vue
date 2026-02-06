<template>
  <BasePanel variant="bordered" size="medium">
    <template #header>
      <h3><i class="fas fa-desktop"></i> Current Machine Profile</h3>
      <BaseButton
        size="sm"
        variant="outline"
        @click="$emit('refresh')"
        :disabled="loading"
      >
        <i class="fas fa-sync" :class="{ 'fa-spin': loading }"></i>
        Refresh
      </BaseButton>
    </template>

    <div v-if="profile && !loading" class="machine-info">
      <div class="info-grid">
        <div class="info-item">
          <label>Machine ID:</label>
          <span class="mono">{{ profile.machine_id || 'Not detected' }}</span>
        </div>
        <div class="info-item">
          <label>OS Type:</label>
          <span class="badge" :class="osBadgeClass">
            {{ profile.os_type || 'Unknown' }}
          </span>
        </div>
        <div class="info-item">
          <label>Distribution:</label>
          <span>{{ profile.distro || 'N/A' }}</span>
        </div>
        <div class="info-item">
          <label>Package Manager:</label>
          <span class="mono">{{ profile.package_manager || 'Unknown' }}</span>
        </div>
        <div class="info-item">
          <label>Available Tools:</label>
          <span class="highlight">{{ (profile.available_tools || []).length }}</span>
        </div>
        <div class="info-item">
          <label>Architecture:</label>
          <span>{{ profile.architecture || 'Unknown' }}</span>
        </div>
      </div>
    </div>

    <div v-else-if="!loading" class="no-data">
      <i class="fas fa-exclamation-triangle"></i>
      Machine profile not loaded. Click refresh to detect current machine.
    </div>

    <div v-if="loading" class="loading">
      <i class="fas fa-spinner fa-spin"></i>
      Detecting machine profile...
    </div>
  </BasePanel>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Machine Profile Panel Component
 *
 * Displays current machine profile information.
 * Extracted from ManPageManager.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { computed } from 'vue'
import BasePanel from '@/components/base/BasePanel.vue'
import BaseButton from '@/components/base/BaseButton.vue'

interface MachineProfile {
  machine_id?: string
  os_type?: string
  distro?: string
  package_manager?: string
  available_tools?: string[]
  architecture?: string
}

interface Props {
  profile: MachineProfile | null
  loading?: boolean
}

interface Emits {
  (e: 'refresh'): void
}

const props = withDefaults(defineProps<Props>(), {
  loading: false
})

defineEmits<Emits>()

const osBadgeClass = computed(() => {
  const osType = props.profile?.os_type?.toLowerCase()
  if (osType === 'linux') return 'badge-linux'
  if (osType === 'windows') return 'badge-windows'
  if (osType === 'macos' || osType === 'darwin') return 'badge-macos'
  return 'badge-unknown'
})
</script>

<style scoped>
.machine-info {
  @apply p-4;
}

.info-grid {
  @apply grid grid-cols-2 md:grid-cols-3 gap-4;
}

.info-item {
  @apply flex flex-col;
}

.info-item label {
  @apply text-sm font-medium text-gray-500 mb-1;
}

.info-item span {
  @apply text-gray-900;
}

.mono {
  @apply font-mono text-sm;
}

.badge {
  @apply inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium;
}

.badge-linux {
  @apply bg-orange-100 text-orange-800;
}

.badge-windows {
  @apply bg-blue-100 text-blue-800;
}

.badge-macos {
  @apply bg-gray-100 text-gray-800;
}

.badge-unknown {
  @apply bg-gray-100 text-gray-600;
}

.highlight {
  @apply font-semibold text-blue-600;
}

.no-data {
  @apply flex items-center gap-3 p-4 text-yellow-700 bg-yellow-50 rounded-lg;
}

.loading {
  @apply flex items-center gap-2 p-4 text-blue-600;
}
</style>
