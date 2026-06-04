<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * AgentActivity — per-agent diary viewer (#5071)
 *
 * Fetches GET /api/agent-diary/summary and displays each agent's
 * recent journal entries with timestamps and a "View all" link.
 */

import { ref, onMounted } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AgentActivity')

interface DiaryEntry {
  content?: string
  metadata?: {
    diary_timestamp?: string
    topic?: string
    session_id?: string
  }
}

interface AgentSummary {
  agent_name: string
  recent_entries: DiaryEntry[]
  entry_count: number
}

interface SummaryResponse {
  data: {
    agents: AgentSummary[]
    total_agents: number
  }
}

const api = useApiClient()

const agents = ref<AgentSummary[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)
const selectedAgent = ref<string | null>(null)
const allEntries = ref<DiaryEntry[]>([])
const isLoadingAll = ref(false)

async function fetchSummary() {
  isLoading.value = true
  error.value = null
  try {
    const resp = await api.get<SummaryResponse>('/api/agent-diary/summary?last_n=3')
    agents.value = (resp as SummaryResponse).data?.agents ?? []
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Failed to fetch agent diary summary:', msg)
    error.value = msg
  } finally {
    isLoading.value = false
  }
}

async function viewAll(agentName: string) {
  selectedAgent.value = agentName
  isLoadingAll.value = true
  allEntries.value = []
  try {
    const resp = await api.get<{ data: { entries: DiaryEntry[] } }>(
      `/api/agent-diary/${encodeURIComponent(agentName)}/entries?last_n=50`
    )
    allEntries.value = (resp as { data: { entries: DiaryEntry[] } }).data?.entries ?? []
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Failed to fetch entries for agent %s: %s', agentName, msg)
  } finally {
    isLoadingAll.value = false
  }
}

function closeModal() {
  selectedAgent.value = null
  allEntries.value = []
}

function formatTimestamp(ts?: string): string {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ts
  }
}

onMounted(fetchSummary)
</script>

<template>
  <div class="p-6 max-w-5xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-semibold text-autobot-text-primary">
        Agent Activity
      </h1>
      <button
        class="px-4 py-2 rounded bg-autobot-accent text-white text-sm hover:bg-autobot-accent/80 transition-colors"
        :disabled="isLoading"
        @click="fetchSummary"
      >
        {{ isLoading ? 'Refreshing…' : 'Refresh' }}
      </button>
    </div>

    <!-- Error state -->
    <div
      v-if="error"
      class="mb-4 p-4 rounded bg-red-50 border border-red-200 text-red-700 text-sm dark:bg-red-900/20 dark:border-red-800 dark:text-red-400"
    >
      {{ error }}
    </div>

    <!-- Loading skeleton -->
    <div v-if="isLoading && !agents.length" class="space-y-4">
      <div
        v-for="i in 4"
        :key="i"
        class="h-28 rounded-lg bg-autobot-surface animate-pulse"
      />
    </div>

    <!-- Agent cards -->
    <div v-else class="space-y-4">
      <div
        v-for="agent in agents"
        :key="agent.agent_name"
        class="rounded-lg border border-autobot-border bg-autobot-surface p-4"
      >
        <!-- Card header -->
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <span class="text-xs font-mono bg-autobot-accent/10 text-autobot-accent px-2 py-0.5 rounded">
              {{ agent.agent_name }}
            </span>
            <span class="text-xs text-autobot-text-muted">
              {{ agent.entry_count }} recent {{ agent.entry_count === 1 ? 'entry' : 'entries' }}
            </span>
          </div>
          <button
            class="text-xs text-autobot-accent hover:underline"
            @click="viewAll(agent.agent_name)"
          >
            View all
          </button>
        </div>

        <!-- Entries -->
        <div v-if="agent.recent_entries.length" class="space-y-2">
          <div
            v-for="(entry, idx) in agent.recent_entries"
            :key="idx"
            class="text-sm border-l-2 border-autobot-accent/30 pl-3"
          >
            <p class="text-autobot-text-primary break-words">{{ entry.content ?? '—' }}</p>
            <p class="text-xs text-autobot-text-muted mt-0.5">
              {{ formatTimestamp(entry.metadata?.diary_timestamp) }}
              <span v-if="entry.metadata?.topic" class="ml-2 italic">{{ entry.metadata.topic }}</span>
            </p>
          </div>
        </div>
        <p v-else class="text-sm text-autobot-text-muted italic">No entries yet.</p>
      </div>

      <p v-if="!isLoading && !agents.length" class="text-center text-autobot-text-muted py-12">
        No agent diary data found.
      </p>
    </div>

    <!-- "View all" modal overlay -->
    <transition name="fade">
      <div
        v-if="selectedAgent"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="closeModal"
      >
        <div class="bg-autobot-surface rounded-xl shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col mx-4">
          <!-- Modal header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-autobot-border">
            <h2 class="font-semibold text-autobot-text-primary">
              All entries — <span class="font-mono text-autobot-accent">{{ selectedAgent }}</span>
            </h2>
            <button
              class="text-autobot-text-muted hover:text-autobot-text-primary"
              @click="closeModal"
            >
              ✕
            </button>
          </div>

          <!-- Modal body -->
          <div class="overflow-y-auto flex-1 px-6 py-4 space-y-3">
            <div v-if="isLoadingAll" class="flex justify-center py-8">
              <span class="text-autobot-text-muted text-sm">Loading…</span>
            </div>
            <template v-else>
              <div
                v-for="(entry, idx) in allEntries"
                :key="idx"
                class="text-sm border-l-2 border-autobot-accent/30 pl-3"
              >
                <p class="text-autobot-text-primary break-words">{{ entry.content ?? '—' }}</p>
                <p class="text-xs text-autobot-text-muted mt-0.5">
                  {{ formatTimestamp(entry.metadata?.diary_timestamp) }}
                  <span v-if="entry.metadata?.topic" class="ml-2 italic">{{ entry.metadata.topic }}</span>
                  <span v-if="entry.metadata?.session_id" class="ml-2 text-autobot-text-muted/60">
                    session {{ entry.metadata.session_id.slice(0, 8) }}
                  </span>
                </p>
              </div>
              <p v-if="!allEntries.length" class="text-autobot-text-muted italic text-center py-8">
                No entries found.
              </p>
            </template>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
