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
        <select v-model="senderFilter" class="smt-select" @change="refresh">
          <option value="">{{ t('serviceMessages.allSenders') }}</option>
          <option v-for="s in senderOptions" :key="s" :value="s">{{ s }}</option>
        </select>
        <select v-model="typeFilter" class="smt-select" @change="refresh">
          <option value="">{{ t('serviceMessages.allTypes') }}</option>
          <option v-for="mt in typeOptions" :key="mt" :value="mt">{{ mt }}</option>
        </select>
        <button class="smt-btn" :class="{ active: isPolling }" @click="togglePolling">
          <i :class="isPolling ? 'fas fa-pause' : 'fas fa-play'"></i>
        </button>
        <button class="smt-btn" @click="refresh">
          <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
        </button>
      </div>
    </div>

    <div v-if="loading && messages.length === 0" class="smt-empty">
      <i class="fas fa-spinner fa-spin"></i>
    </div>
    <div v-else-if="messages.length === 0" class="smt-empty">
      <i class="fas fa-inbox"></i>
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
            <i class="fas fa-arrow-right"></i>
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
        <button class="smt-btn" @click="selected = null"><i class="fas fa-times"></i></button>
      </div>
      <table class="smt-table">
        <tr><td>ID</td><td><code>{{ selected.msg_id }}</code></td></tr>
        <tr><td>{{ t('serviceMessages.timestamp') }}</td><td>{{ formatFull(selected.ts) }}</td></tr>
        <tr><td>{{ t('serviceMessages.route') }}</td><td>{{ selected.sender }} → {{ selected.receiver }}</td></tr>
        <tr><td>{{ t('serviceMessages.type') }}</td><td><span class="smt-badge" :class="`t-${selected.msg_type}`">{{ selected.msg_type }}</span></td></tr>
        <tr>
          <td>{{ t('serviceMessages.correlationId') }}</td>
          <td><code class="smt-link" @click="loadChain(selected!.correlation_id)">{{ selected.correlation_id.slice(0, 12) }}… <i class="fas fa-link"></i></code></td>
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
.smt { display:flex; flex-direction:column; height:100%; background:var(--bg-primary,#1a1a2e); border-radius:8px; overflow:hidden; }
.smt-header { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; border-bottom:1px solid var(--border-color,#2a2a4a); }
.smt-header h3 { margin:0; font-size:14px; font-weight:600; color:var(--text-primary,#e0e0ff); }
.smt-controls { display:flex; gap:4px; align-items:center; }
.smt-select { background:var(--bg-secondary,#16213e); color:var(--text-secondary,#a0a0c0); border:1px solid var(--border-color,#2a2a4a); border-radius:4px; padding:4px 8px; font-size:12px; }
.smt-btn { background:none; border:1px solid var(--border-color,#2a2a4a); color:var(--text-secondary,#a0a0c0); border-radius:4px; padding:4px 8px; cursor:pointer; font-size:12px; transition:all .2s; }
.smt-btn:hover { background:var(--bg-hover,#2a2a4a); color:var(--text-primary,#e0e0ff); }
.smt-btn.active { background:var(--accent-color,#4a90d9); color:#fff; border-color:var(--accent-color,#4a90d9); }
.smt-empty { display:flex; flex-direction:column; align-items:center; justify-content:center; padding:40px; color:var(--text-secondary,#a0a0c0); gap:8px; }
.smt-body { flex:1; overflow-y:auto; padding:4px 12px; }
.smt-entry { display:flex; gap:10px; padding:8px 4px; cursor:pointer; border-radius:4px; transition:background .15s; align-items:flex-start; }
.smt-entry:hover { background:rgba(255,255,255,.03); }
.smt-entry.selected { background:rgba(74,144,217,.1); }
.smt-dot { width:10px; height:10px; border-radius:50%; margin-top:4px; flex-shrink:0; }
.smt-dot.t-task { background:#4a90d9; } .smt-dot.t-result { background:#4caf50; } .smt-dot.t-error { background:#f44336; }
.smt-dot.t-health { background:#8bc34a; } .smt-dot.t-deploy { background:#ff9800; } .smt-dot.t-workflow_step { background:#9c27b0; }
.smt-dot.t-notification { background:#00bcd4; }
.smt-info { flex:1; min-width:0; }
.smt-route { display:flex; align-items:center; gap:4px; font-size:13px; font-weight:500; color:var(--text-primary,#e0e0ff); }
.smt-route i { font-size:10px; color:var(--text-secondary,#a0a0c0); }
.smt-meta { font-size:11px; color:var(--text-muted,#707090); margin-top:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.smt-badge { font-size:11px; padding:1px 6px; border-radius:3px; font-weight:500; margin-left:auto; }
.smt-badge.t-task { background:rgba(74,144,217,.2); color:#4a90d9; } .smt-badge.t-result { background:rgba(76,175,80,.2); color:#4caf50; }
.smt-badge.t-error { background:rgba(244,67,54,.2); color:#f44336; } .smt-badge.t-health { background:rgba(139,195,74,.2); color:#8bc34a; }
.smt-badge.t-deploy { background:rgba(255,152,0,.2); color:#ff9800; } .smt-badge.t-workflow_step { background:rgba(156,39,176,.2); color:#9c27b0; }
.smt-badge.t-notification { background:rgba(0,188,212,.2); color:#00bcd4; }
.smt-detail { border-top:1px solid var(--border-color,#2a2a4a); background:var(--bg-secondary,#16213e); max-height:50%; overflow-y:auto; padding:12px 16px; }
.smt-detail-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; color:var(--text-primary,#e0e0ff); font-size:13px; }
.smt-table { width:100%; font-size:12px; border-collapse:collapse; }
.smt-table td { padding:3px 0; }
.smt-table td:first-child { color:var(--text-muted,#707090); font-weight:500; width:120px; }
.smt-table td:last-child { color:var(--text-primary,#e0e0ff); }
.smt-table code { font-family:'JetBrains Mono',monospace; font-size:11px; background:var(--bg-primary,#1a1a2e); padding:2px 6px; border-radius:3px; }
.smt-link { cursor:pointer; } .smt-link:hover { color:var(--accent-color,#4a90d9)!important; }
.smt-pre { background:var(--bg-primary,#1a1a2e); padding:8px 12px; border-radius:4px; font-size:11px; font-family:'JetBrains Mono',monospace; color:var(--text-secondary,#a0a0c0); overflow-x:auto; max-height:120px; margin:8px 0 0; }
.smt-chain { margin-top:12px; border-top:1px solid var(--border-color,#2a2a4a); padding-top:8px; }
.smt-chain strong { font-size:13px; color:var(--text-primary,#e0e0ff); }
.smt-chain-row { display:flex; align-items:center; gap:8px; padding:3px 8px; font-size:12px; border-radius:4px; color:var(--text-primary,#e0e0ff); }
.smt-chain-row.current { background:rgba(74,144,217,.15); }
.smt-chain-idx { color:var(--text-muted,#707090); font-weight:600; min-width:18px; }
.smt-muted { color:var(--text-muted,#707090); font-size:11px; margin-left:auto; }
</style>
