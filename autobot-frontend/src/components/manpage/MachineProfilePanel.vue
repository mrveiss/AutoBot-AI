<template>
  <BasePanel variant="bordered" size="md">
    <template #header>
      <h3><Icon name="desktop" /> {{ $t('manpage.machineProfile.title') }}</h3>
      <BaseButton
        size="sm"
        variant="outline-solid"
        @click="$emit('refresh')"
        :disabled="loading"
      >
        <Icon name="sync" />
        {{ $t('manpage.machineProfile.refresh') }}
      </BaseButton>
    </template>

    <div v-if="profile && !loading" class="machine-info">
      <div class="info-grid">
        <div class="info-item">
          <label>{{ $t('manpage.machineProfile.machineId') }}</label>
          <span class="mono">{{ profile.machine_id || $t('manpage.machineProfile.notDetected') }}</span>
        </div>
        <div class="info-item">
          <label>{{ $t('manpage.machineProfile.osType') }}</label>
          <span class="badge" :class="osBadgeClass">
            {{ profile.os_type || $t('manpage.machineProfile.unknown') }}
          </span>
        </div>
        <div class="info-item">
          <label>{{ $t('manpage.machineProfile.distribution') }}</label>
          <span>{{ profile.distro || $t('manpage.machineProfile.na') }}</span>
        </div>
        <div class="info-item">
          <label>{{ $t('manpage.machineProfile.packageManager') }}</label>
          <span class="mono">{{ profile.package_manager || $t('manpage.machineProfile.unknown') }}</span>
        </div>
        <div class="info-item">
          <label>{{ $t('manpage.machineProfile.availableTools') }}</label>
          <span class="highlight">{{ (profile.available_tools || []).length }}</span>
        </div>
        <div class="info-item">
          <label>{{ $t('manpage.machineProfile.architecture') }}</label>
          <span>{{ profile.architecture || $t('manpage.machineProfile.unknown') }}</span>
        </div>
      </div>
    </div>

    <div v-else-if="!loading" class="no-data">
      <Icon name="exclamation-triangle" />
      {{ $t('manpage.machineProfile.noData') }}
    </div>

    <div v-if="loading" class="loading">
      <Icon name="spinner" class="animate-spin" />
      {{ $t('manpage.machineProfile.loading') }}
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

import Icon from '@/components/ui/Icon.vue'
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
@reference "../../assets/tailwind.css";
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
  @apply text-sm font-medium text-autobot-text-muted mb-1;
}

.info-item span {
  @apply text-autobot-text-primary;
}

.mono {
  @apply font-mono text-sm;
}

.badge {
  @apply inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium;
}

.badge-linux {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.badge-windows {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.badge-macos {
  @apply bg-autobot-bg-secondary text-autobot-text-primary;
}

.badge-unknown {
  @apply bg-autobot-bg-secondary text-autobot-text-secondary;
}

.highlight {
  @apply font-semibold;
  color: var(--color-primary);
}

.no-data {
  @apply flex items-center gap-3 p-4 rounded-lg;
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.loading {
  @apply flex items-center gap-2 p-4;
  color: var(--color-info);
}
</style>
