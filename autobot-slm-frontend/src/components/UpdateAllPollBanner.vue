<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  Update All polling banner (#12593, #20201). One state at a time, in order:
  session expired, gave up, lost contact, reconnecting.
-->
<script setup lang="ts">
import { computed } from 'vue'
import { BaseAlert } from '@autobot/ui'

const props = defineProps<{
  reconnecting: boolean
  lostContact: boolean
  gaveUp: boolean
  authFailed: boolean
  attempt: number
}>()

defineEmits<{ login: []; recheck: []; update: [] }>()

const visible = computed(() => props.authFailed || props.gaveUp || props.lostContact || props.reconnecting)
const spinning = computed(() => props.reconnecting && !props.lostContact && !props.gaveUp && !props.authFailed)
</script>

<template>
  <BaseAlert v-if="visible" variant="warning" class="mb-6" :icon="!spinning">
    <template #title>
      <svg v-if="spinning" class="w-4 h-4 animate-spin inline-block mr-1.5 align-text-bottom" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
      <template v-if="authFailed">{{ $t('codeSyncView.pipelineSessionExpiredTitle') }}</template>
      <template v-else-if="gaveUp">{{ $t('codeSyncView.pipelineGaveUpTitle') }}</template>
      <template v-else>{{ $t('codeSyncView.sLMManagerRestarting') }}</template>
    </template>
    <span v-if="authFailed">{{ $t('codeSyncView.pipelineSessionExpired') }}</span>
    <span v-else-if="gaveUp">{{ $t('codeSyncView.pipelineGaveUp', { attempt }) }}</span>
    <span v-else-if="spinning">{{ $t('codeSyncView.pipelineReconnectingAttempt', { attempt }) }}</span>
    <span v-else>{{ $t('codeSyncView.codeSyncedSuccessfullyBackend') }}</span>
    <template v-if="authFailed || gaveUp || lostContact" #actions>
      <button v-if="authFailed" @click="$emit('login')" class="btn btn-secondary text-sm shrink-0">
        {{ $t('codeSyncView.pipelineLogInAgain') }}
      </button>
      <button v-else-if="gaveUp" @click="$emit('recheck')" class="btn btn-secondary text-sm shrink-0">
        {{ $t('codeSyncView.pipelineRecheckStatus') }}
      </button>
      <button v-else @click="$emit('update')" class="btn btn-secondary text-sm shrink-0">
        {{ $t('codeSyncView.updateAll') }}
      </button>
    </template>
  </BaseAlert>
</template>
