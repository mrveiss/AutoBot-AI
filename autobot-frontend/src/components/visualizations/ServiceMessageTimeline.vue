<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ServiceMessageTimeline.vue - Cross-service message audit trail widget
  Issue #1379: Cross-service message audit trail
-->
<template>
  <div class="smt">
    <div class="smt-header">
      <h3>{{ t('serviceMessages.title') }}</h3>
      <div class="smt-controls">
        <select v-model="senderFilter" class="smt-select" aria-label="Filter by sender" @change="refresh">
          <option value="">{{ t('serviceMessages.allSenders') }}</option>
          <option v-for="s in senderOptions" :key="s" :value="s">{{ s }}</option>
        </select>
        <select v-model="typeFilter" class="smt-select" aria-label="Filter by message type" @change="refresh">
          <option value="">{{ t('serviceMessages.allTypes') }}</option>
          <option v-for="mt in typeOptions" :key="mt" :value="mt">{{ mt }}</option>
        </select>
        <button class="smt-btn" :class="{ active: isPolling }" :aria-label="isPolling ? t('serviceMessages.stopPolling') : t('serviceMessages.startPolling')" @click="togglePolling">
          <Icon :name="isPolling ? 'pause' : 'play'" />
        </button>
        <button class="smt-btn" :aria-label="t('common.refresh')" @click="refresh">
          <Icon name="sync-alt" />
        </button>
      </div>
    </div>

    <div v-if="loading && messages.length === 0" class="smt-empty">
      <Icon name="spinner" class="animate-spin" />
    </div>
    <div v-else-if="messages.length === 0" class="smt-empty">
      <Icon name="inbox" />
      <p>{{ t('serviceMessages.noMessages') }}</p>
    </div>

    <div v-else class="smt-body">
      <div
        v-for="msg in messages"
        :key="msg.msg_id"
        class="smt-entry"
        :class="{ selected: selected?.msg_id === msg.msg_id }"
        @click="selected = msg"
      >
        <div class="smt-dot" :class="`t-${msg.msg_type}`"></div>
        <div class="smt-info">
          <div class="smt-route">
            <span>{{ msg.sender }}</span>
            <Icon name="arrow-right" />
            <span>{{ msg.receiver }}</span>
            <span class="smt-badge" :class="`t-${msg.msg_type}`">{{ msg.msg_type }}</span>
          </div>
          <div class="smt-meta">
            {{ formatTime(msg.ts) }} &middot; {{ msg.content.slice(0, 60) }}
          </div>
        </div>
      </div>
    </div>

    <div v-if="selected" class="smt-detail">
      <div class="smt-detail-head">
        <strong>{{ t('serviceMessages.messageDetail') }}</strong>
        <button class="smt-btn" :aria-label="t('common.close')" @click="selected = null"><Icon name="times" /></button>
      </div>
      <table class="smt-table">
        <tr><td>ID</td><td><code>{{ selected.msg_id }}</code></td></tr>
        <tr><td>{{ t('serviceMessages.timestamp') }}</td><td>{{ formatFull(selected.ts) }}</td></tr>
        <tr><td>{{ t('serviceMessages.route') }}</td><td>{{ selected.sender }} → {{ selected.receiver }}</td></tr>
        <tr><td>{{ t('serviceMessages.type') }}</td><td><span class="smt-badge" :class="`t-${selected.msg_type}`">{{ selected.msg_type }}</span></td></tr>
        <tr>
          <td>{{ t('serviceMessages.correlationId') }}</td>
          <td><code class="smt-link" role="button" tabindex="0" :aria-label="`View correlation chain for ${selected.correlation_id.slice(0, 12)}`" @click="loadChain(selected!.correlation_id)" @keydown.enter="loadChain(selected!.correlation_id)" @keydown.space.prevent="loadChain(selected!.correlation_id)">{{ selected.correlation_id.slice(0, 12) }}… <Icon name="link" /></code></td>
        </tr>
      </table>
      <pre class="smt-pre">{{ formatPayload(selected.content) }}</pre>

      <div v-if="chainMessages.length > 1" class="smt-chain">
        <strong>{{ t('serviceMessages.correlationChain') }} ({{ chainMessages.length }})</strong>
        <div
          v-for="(cm, idx) in chainMessages"
          :key="cm.msg_id"
          class="smt-chain-row"
          :class="{ current: cm.msg_id === selected?.msg_id }"
        >
          <span class="smt-chain-idx">{{ idx + 1 }}</span>
          {{ cm.sender }} → {{ cm.receiver }}
          <span class="smt-badge" :class="`t-${cm.msg_type}`">{{ cm.msg_type }}</span>
          <span class="smt-muted">{{ formatTime(cm.ts) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  useServiceMessages,
  type ServiceMessageEntry
} from '@/composables/useServiceMessages'

const { t } = useI18n()
const {
  messages, chainMessages, loading, isPolling,
  fetchLatest, fetchChain, startPolling, stopPolling
} = useServiceMessages()

const senderFilter = ref('')
const typeFilter = ref('')
const selected = ref<ServiceMessageEntry | null>(null)

const senderOptions = [
  'main-backend', 'slm-backend', 'ai-stack',
  'browser-worker', 'npu-worker', 'llm-cpu'
]
const typeOptions = [
  'task', 'result', 'error', 'health',
  'deploy', 'workflow_step', 'notification'
]

function refresh() {
  fetchLatest({
    count: 100,
    sender: senderFilter.value || undefined,
    msg_type: typeFilter.value || undefined
  })
}

function togglePolling() {
  if (isPolling.value) {
    stopPolling()
  } else {
    startPolling(15000, {
      count: 100,
      sender: senderFilter.value || undefined,
      msg_type: typeFilter.value || undefined
    })
  }
}

function loadChain(id: string) { fetchChain(id) }

function formatTime(iso: string): string {
  try { return new Date(iso).toLocaleTimeString() } catch { return iso }
}

function formatFull(iso: string): string {
  try { return new Date(iso).toLocaleString() } catch { return iso }
}

function formatPayload(c: string): string {
  try { return JSON.stringify(JSON.parse(c), null, 2) } catch { return c }
}

onMounted(() => refresh())
</script>

<style scoped>
.smt { display:flex; flex-direction:column; height:100%; background:var(--bg-primary,#1a1a2e); border-radius: var(--radius-lg); overflow:hidden; }
.smt-header { display:flex; justify-content:space-between; align-items:center; padding:var(--spacing-3) var(--spacing-4); border-bottom:1px solid var(--border-color,#2a2a4a); }
.smt-header h3 { margin:var(--spacing-0); font-size: var(--text-sm); font-weight:600; color:var(--text-primary,#e0e0ff); }
.smt-controls { display:flex; gap:var(--spacing-1); align-items:center; }
.smt-select { background:var(--bg-secondary,#16213e); color:var(--text-secondary,#a0a0c0); border:1px solid var(--border-color,#2a2a4a); border-radius: var(--radius-default); padding:var(--spacing-1) var(--spacing-2); font-size: var(--text-xs); }
.smt-btn { background:none; border:1px solid var(--border-color,#2a2a4a); color:var(--text-secondary,#a0a0c0); border-radius: var(--radius-default); padding:var(--spacing-1) var(--spacing-2); cursor:pointer; font-size: var(--text-xs); transition:all .2s; }
.smt-btn:hover { background:var(--bg-hover,#2a2a4a); color:var(--text-primary,#e0e0ff); }
.smt-btn.active { background:var(--accent-color,#4a90d9); color:#fff; border-color:var(--accent-color,#4a90d9); }
.smt-empty { display:flex; flex-direction:column; align-items:center; justify-content:center; padding:var(--spacing-10); color:var(--text-secondary,#a0a0c0); gap:var(--spacing-2); }
.smt-body { flex:1; overflow-y:auto; padding:var(--spacing-1) var(--spacing-3); }
.smt-entry { display:flex; gap:var(--spacing-2-5); padding:var(--spacing-2) var(--spacing-1); cursor:pointer; border-radius: var(--radius-default); transition:background .15s; align-items:flex-start; }
.smt-entry:hover { background:rgba(255,255,255,.03); }
.smt-entry.selected { background:rgba(74,144,217,.1); }
.smt-dot { width:10px; height:10px; border-radius:50%; margin-top:var(--spacing-1); flex-shrink:0; }
.smt-dot.t-task { background:#4a90d9; } .smt-dot.t-result { background:#4caf50; } .smt-dot.t-error { background:#f44336; }
.smt-dot.t-health { background:#8bc34a; } .smt-dot.t-deploy { background:#ff9800; } .smt-dot.t-workflow_step { background:#9c27b0; }
.smt-dot.t-notification { background:#00bcd4; }
.smt-info { flex:1; min-width:0; }
.smt-route { display:flex; align-items:center; gap:var(--spacing-1); font-size: var(--text-sm); font-weight:500; color:var(--text-primary,#e0e0ff); }
.smt-route i { font-size: var(--text-xs); color:var(--text-secondary,#a0a0c0); }
.smt-meta { font-size: var(--text-xs); color:var(--text-muted,#707090); margin-top:var(--spacing-0-5); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.smt-badge { font-size: var(--text-xs); padding:var(--spacing-px) var(--spacing-1-5); border-radius: var(--radius-default); font-weight:500; margin-left:auto; }
.smt-badge.t-task { background:rgba(74,144,217,.2); color:#4a90d9; } .smt-badge.t-result { background:rgba(76,175,80,.2); color:#4caf50; }
.smt-badge.t-error { background:rgba(244,67,54,.2); color:#f44336; } .smt-badge.t-health { background:rgba(139,195,74,.2); color:#8bc34a; }
.smt-badge.t-deploy { background:rgba(255,152,0,.2); color:#ff9800; } .smt-badge.t-workflow_step { background:rgba(156,39,176,.2); color:#9c27b0; }
.smt-badge.t-notification { background:rgba(0,188,212,.2); color:#00bcd4; }
.smt-detail { border-top:1px solid var(--border-color,#2a2a4a); background:var(--bg-secondary,#16213e); max-height:50%; overflow-y:auto; padding:var(--spacing-3) var(--spacing-4); }
.smt-detail-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:var(--spacing-2); color:var(--text-primary,#e0e0ff); font-size: var(--text-sm); }
.smt-table { width:100%; font-size: var(--text-xs); border-collapse:collapse; }
.smt-table td { padding:3px 0; }
.smt-table td:first-child { color:var(--text-muted,#707090); font-weight:500; width:120px; }
.smt-table td:last-child { color:var(--text-primary,#e0e0ff); }
.smt-table code { font-family:'JetBrains Mono',monospace; font-size: var(--text-xs); background:var(--bg-primary,#1a1a2e); padding:var(--spacing-0-5) var(--spacing-1-5); border-radius: var(--radius-default); }
.smt-link { cursor:pointer; } .smt-link:hover { color:var(--accent-color,#4a90d9)!important; }
.smt-pre { background:var(--bg-primary,#1a1a2e); padding:var(--spacing-2) var(--spacing-3); border-radius: var(--radius-default); font-size: var(--text-xs); font-family:'JetBrains Mono',monospace; color:var(--text-secondary,#a0a0c0); overflow-x:auto; max-height:120px; margin:var(--spacing-2) var(--spacing-0) var(--spacing-0); }
.smt-chain { margin-top:var(--spacing-3); border-top:1px solid var(--border-color,#2a2a4a); padding-top:var(--spacing-2); }
.smt-chain strong { font-size: var(--text-sm); color:var(--text-primary,#e0e0ff); }
.smt-chain-row { display:flex; align-items:center; gap:var(--spacing-2); padding:3px 8px; font-size: var(--text-xs); border-radius: var(--radius-default); color:var(--text-primary,#e0e0ff); }
.smt-chain-row.current { background:rgba(74,144,217,.15); }
.smt-chain-idx { color:var(--text-muted,#707090); font-weight:600; min-width:18px; }
.smt-muted { color:var(--text-muted,#707090); font-size: var(--text-xs); margin-left:auto; }
</style>
