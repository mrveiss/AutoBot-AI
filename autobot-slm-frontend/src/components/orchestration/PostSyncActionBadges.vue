<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * PostSyncActionBadges - Post-sync action badges per node (Issue #1243)
 *
 * Renders categorised badges (schema, build, install, restart) with
 * click-to-execute support. Used in the per-node orchestration view
 * to show what needs to happen after code sync.
 */

import type { PostSyncAction } from '@/composables/useRoles'

interface Props {
  actions: PostSyncAction[]
  executingAction: {
    roleName: string
    category: string
  } | null
}

defineProps<Props>()

const emit = defineEmits<{
  execute: [action: PostSyncAction]
}>()

const CATEGORY_STYLES: Record<
  string,
  { bg: string; text: string; icon: string; hoverBg: string }
> = {
  schema: {
    bg: 'bg-purple-100',
    text: 'text-purple-700',
    icon: 'M4 7v10c0 2 1 3 3 3h10c2 0 3-1 3-3V7M9 11h6M9 15h4',
    hoverBg: 'hover:bg-purple-200',
  },
  build: {
    bg: 'bg-amber-100',
    text: 'text-amber-700',
    icon: 'M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z',
    hoverBg: 'hover:bg-amber-200',
  },
  install: {
    bg: 'bg-blue-100',
    text: 'text-blue-700',
    icon: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4',
    hoverBg: 'hover:bg-blue-200',
  },
  restart: {
    bg: 'bg-orange-100',
    text: 'text-orange-700',
    icon: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15',
    hoverBg: 'hover:bg-orange-200',
  },
}

function getStyle(category: string) {
  return (
    CATEGORY_STYLES[category] ?? {
      bg: 'bg-gray-100',
      text: 'text-gray-600',
      icon: '',
      hoverBg: 'hover:bg-gray-200',
    }
  )
}

function isExecuting(
  action: PostSyncAction,
  active: Props['executingAction'],
): boolean {
  if (!active) return false
  return (
    active.roleName === action.role_name &&
    active.category === action.category
  )
}
</script>

<template>
  <div
    v-if="actions.length > 0"
    class="px-4 py-2 bg-gray-50 border-b border-gray-100 flex flex-wrap items-center gap-1.5"
  >
    <span class="text-xs font-medium text-gray-500 mr-1">
      Post-sync:
    </span>
    <button
      v-for="action in actions"
      :key="`${action.role_name}-${action.category}`"
      @click.stop="emit('execute', action)"
      :disabled="executingAction !== null"
      :title="action.command || action.label"
      :class="[
        'inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed',
        getStyle(action.category).bg,
        getStyle(action.category).text,
        getStyle(action.category).hoverBg,
      ]"
    >
      <!-- Spinner when executing -->
      <svg
        v-if="isExecuting(action, executingAction)"
        class="w-3 h-3 animate-spin"
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle
          class="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          stroke-width="4"
        />
        <path
          class="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
        />
      </svg>
      <!-- Category icon -->
      <svg
        v-else
        class="w-3 h-3"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          :d="getStyle(action.category).icon"
        />
      </svg>
      {{ action.label }}
    </button>
  </div>
</template>
