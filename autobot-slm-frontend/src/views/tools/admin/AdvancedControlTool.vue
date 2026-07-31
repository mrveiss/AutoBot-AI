// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * AdvancedControlTool - Agent desktop streaming + human takeover admin panel.
 *
 * Control-plane tool for #11506 desktop-session takeover. Wires the live
 * autobot-backend `/api/advanced-control/*` routes (reached from the SLM
 * frontend via nginx `/autobot-api/` -> getBackendUrl()). See #12102.
 *
 * The endpoints and their payload shapes live in `useAutobotApi` — the SLM
 * app's single client for the autobot backend — rather than being re-declared
 * here on top of a private `fetch` (#12653). That fork carried only
 * `authStore.token`, so it 401'd in the one case every other admin tool
 * survives: an autobot-issued token in `autobot_access_token` with no SLM
 * token. It also had no request timeout and no 401 cleanup.
 */

import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  useAutobotApi,
  ADVANCED_CONTROL_TRIGGERS,
  ADVANCED_CONTROL_PRIORITIES,
  type AdvancedControlCapabilities,
  type AdvancedControlStreamingSession,
  type AdvancedControlPendingRequest,
  type AdvancedControlActiveSession,
  type AdvancedControlTakeoverStatus,
  type AdvancedControlSessionAction,
} from '@/composables/useAutobotApi'
import { createLogger } from '@/utils/debugUtils'

const { t } = useI18n()
const logger = createLogger('AdvancedControlTool')

const {
  getAdvancedControlCapabilities,
  listAdvancedControlSessions,
  createAdvancedControlSession,
  terminateAdvancedControlSession,
  getAdvancedControlTakeoverStatus,
  getPendingTakeovers,
  getActiveTakeovers,
  requestTakeover,
  approveTakeover,
  takeoverSessionAction,
} = useAutobotApi()

const TRIGGERS = ADVANCED_CONTROL_TRIGGERS
const PRIORITIES = ADVANCED_CONTROL_PRIORITIES

const loading = ref(false)
const error = ref<string | null>(null)

const capabilities = ref<AdvancedControlCapabilities | null>(null)
const sessions = ref<AdvancedControlStreamingSession[]>([])
const takeoverStatus = ref<AdvancedControlTakeoverStatus | null>(null)
const pending = ref<AdvancedControlPendingRequest[]>([])
const active = ref<AdvancedControlActiveSession[]>([])

const createForm = reactive<{ user_id: string; resolution: string; depth: number | null }>({
  user_id: '', resolution: '', depth: null,
})
const requestForm = reactive<{ trigger: string; priority: string; reason: string; requesting_agent: string }>({
  trigger: 'MANUAL_REQUEST', priority: 'HIGH', reason: '', requesting_agent: '',
})
const operatorInputs = reactive<Record<string, string>>({})

const busy = reactive<{
  create: boolean; request: boolean
  terminate: string | null; approve: string | null; session: string | null
}>({ create: false, request: false, terminate: null, approve: null, session: null })

async function loadAll(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [caps, sess, status, pend, act] = await Promise.all([
      getAdvancedControlCapabilities(),
      listAdvancedControlSessions(),
      getAdvancedControlTakeoverStatus(),
      getPendingTakeovers(),
      getActiveTakeovers(),
    ])
    capabilities.value = caps
    sessions.value = sess
    takeoverStatus.value = status
    pending.value = pend
    active.value = act
  } catch (e) {
    error.value = describeError(e)
    logger.warn('Advanced-control load failed:', e)
  } finally {
    loading.value = false
  }
}

/**
 * Render an axios/network failure the way the previous raw-fetch transport did
 * (`HTTP <status>`), so the banner text and its test assertion are unchanged.
 */
function describeError(e: unknown): string {
  const status = (e as { response?: { status?: number } })?.response?.status
  if (typeof status === 'number') return `HTTP ${status}`
  if (e instanceof Error && e.message) return e.message
  return t('tools.admin.advancedControlTool.genericError')
}

/** Run an action, surface errors to the banner, and reload the given loaders. */
async function run(fn: () => Promise<unknown>): Promise<boolean> {
  error.value = null
  try {
    await fn()
    return true
  } catch (e) {
    error.value = describeError(e)
    logger.warn('Advanced-control action failed:', e)
    return false
  }
}

async function onCreateSession(): Promise<void> {
  if (!createForm.user_id) return
  busy.create = true
  const ok = await run(() => createAdvancedControlSession({
    user_id: createForm.user_id,
    resolution: createForm.resolution || '1024x768',
    depth: createForm.depth ?? 24,
  }))
  busy.create = false
  if (ok) { createForm.user_id = ''; await loadAll() }
}

async function onTerminate(sessionId: string): Promise<void> {
  busy.terminate = sessionId
  const ok = await run(() => terminateAdvancedControlSession(sessionId))
  busy.terminate = null
  if (ok) await loadAll()
}

async function onRequestTakeover(): Promise<void> {
  if (!requestForm.reason) return
  busy.request = true
  const ok = await run(() => requestTakeover({
    trigger: requestForm.trigger,
    reason: requestForm.reason,
    priority: requestForm.priority,
    requesting_agent: requestForm.requesting_agent || null,
  }))
  busy.request = false
  if (ok) { requestForm.reason = ''; requestForm.requesting_agent = ''; await loadAll() }
}

async function onApprove(requestId: string): Promise<void> {
  const operator = operatorInputs[requestId]
  if (!operator) return
  busy.approve = requestId
  const ok = await run(() => approveTakeover(requestId, operator))
  busy.approve = null
  if (ok) await loadAll()
}

async function onSessionAction(sessionId: string, action: AdvancedControlSessionAction): Promise<void> {
  busy.session = sessionId
  const body = action === 'complete'
    ? { resolution: t('tools.admin.advancedControlTool.completedResolution') }
    : undefined
  const ok = await run(() => takeoverSessionAction(sessionId, action, body))
  busy.session = null
  if (ok) await loadAll()
}

function yesNo(v: boolean | undefined): string {
  return v ? t('tools.admin.advancedControlTool.yes') : t('tools.admin.advancedControlTool.no')
}
function formatTime(iso: string | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}
function badgeClass(status: string | undefined): string {
  if (status === 'active' || status === 'approved') return 'bg-green-100 text-green-700'
  if (status === 'paused') return 'bg-yellow-100 text-yellow-700'
  if (status === 'terminated' || status === 'rejected') return 'bg-red-100 text-red-700'
  return 'bg-gray-100 text-gray-700'
}
function priorityClass(p: string | undefined): string {
  if (p === 'CRITICAL' || p === 'HIGH') return 'bg-red-100 text-red-700'
  if (p === 'MEDIUM') return 'bg-yellow-100 text-yellow-700'
  return 'bg-gray-100 text-gray-700'
}

onMounted(loadAll)
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-bold text-gray-900">{{ $t('tools.admin.advancedControlTool.title') }}</h2>
        <p class="text-sm text-gray-500">{{ $t('tools.admin.advancedControlTool.subtitle') }}</p>
      </div>
      <button
        data-test="refresh"
        @click="loadAll"
        :disabled="loading"
        class="px-4 py-2 text-sm font-medium rounded-lg bg-primary-100 text-primary-700 hover:bg-primary-200 disabled:opacity-50 transition-colors"
      >
        {{ loading ? $t('tools.admin.advancedControlTool.refreshing') : $t('tools.admin.advancedControlTool.refresh') }}
      </button>
    </div>

    <!-- Error banner -->
    <div v-if="error" data-test="error" class="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
      {{ error }}
    </div>

    <!-- Stat cards -->
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <div class="bg-white rounded-lg shadow-xs border border-gray-200 p-4">
        <div class="text-xs text-gray-500 uppercase tracking-wide">{{ $t('tools.admin.advancedControlTool.statStreaming') }}</div>
        <div class="text-2xl font-bold text-gray-900">{{ sessions.length }}</div>
      </div>
      <div class="bg-white rounded-lg shadow-xs border border-gray-200 p-4">
        <div class="text-xs text-gray-500 uppercase tracking-wide">{{ $t('tools.admin.advancedControlTool.statPending') }}</div>
        <div class="text-2xl font-bold text-gray-900">{{ pending.length }}</div>
      </div>
      <div class="bg-white rounded-lg shadow-xs border border-gray-200 p-4">
        <div class="text-xs text-gray-500 uppercase tracking-wide">{{ $t('tools.admin.advancedControlTool.statActive') }}</div>
        <div class="text-2xl font-bold text-gray-900">{{ active.length }}</div>
      </div>
    </div>

    <!-- ============================ STREAMING ============================ -->
    <section class="space-y-4">
      <h3 class="text-lg font-semibold text-gray-900">{{ $t('tools.admin.advancedControlTool.streamingTitle') }}</h3>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <!-- Capabilities -->
        <div class="bg-white rounded-lg shadow-xs border border-gray-200 p-4">
          <h4 class="text-sm font-medium text-gray-900 mb-3">{{ $t('tools.admin.advancedControlTool.capabilitiesTitle') }}</h4>
          <dl v-if="capabilities" class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt class="text-gray-500">{{ $t('tools.admin.advancedControlTool.capVnc') }}</dt>
            <dd class="text-gray-900">{{ yesNo(capabilities.vnc_available) }}</dd>
            <dt class="text-gray-500">{{ $t('tools.admin.advancedControlTool.capNoVnc') }}</dt>
            <dd class="text-gray-900">{{ yesNo(capabilities.novnc_available) }}</dd>
            <dt class="text-gray-500">{{ $t('tools.admin.advancedControlTool.capMaxSessions') }}</dt>
            <dd class="text-gray-900">{{ capabilities.max_sessions ?? '—' }}</dd>
            <dt class="text-gray-500">{{ $t('tools.admin.advancedControlTool.capResolutions') }}</dt>
            <dd class="text-gray-900">{{ (capabilities.supported_resolutions || []).join(', ') || '—' }}</dd>
            <dt class="text-gray-500">{{ $t('tools.admin.advancedControlTool.capDepths') }}</dt>
            <dd class="text-gray-900">{{ (capabilities.supported_depths || []).join(', ') || '—' }}</dd>
          </dl>
          <p v-else class="text-sm text-gray-400">{{ $t('tools.admin.advancedControlTool.noCapabilities') }}</p>
        </div>

        <!-- Create session -->
        <div class="bg-white rounded-lg shadow-xs border border-gray-200 p-4">
          <h4 class="text-sm font-medium text-gray-900 mb-3">{{ $t('tools.admin.advancedControlTool.createSessionTitle') }}</h4>
          <form class="space-y-3" @submit.prevent="onCreateSession">
            <div>
              <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('tools.admin.advancedControlTool.userId') }}</label>
              <input v-model.trim="createForm.user_id" required
                class="w-full text-sm px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('tools.admin.advancedControlTool.resolution') }}</label>
                <input v-model.trim="createForm.resolution" placeholder="1024x768"
                  class="w-full text-sm px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
              </div>
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('tools.admin.advancedControlTool.depth') }}</label>
                <input v-model.number="createForm.depth" type="number" placeholder="24"
                  class="w-full text-sm px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
              </div>
            </div>
            <button data-test="create" type="submit" :disabled="busy.create || !createForm.user_id"
              class="px-4 py-1.5 text-sm font-medium rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 transition-colors">
              {{ busy.create ? $t('tools.admin.advancedControlTool.creating') : $t('tools.admin.advancedControlTool.create') }}
            </button>
          </form>
        </div>
      </div>

      <!-- Sessions table -->
      <div class="bg-white rounded-lg shadow-xs border border-gray-200 overflow-hidden">
        <div class="px-4 py-3 border-b border-gray-200 text-sm font-medium text-gray-900">
          {{ $t('tools.admin.advancedControlTool.sessionsTitle') }}
        </div>
        <p v-if="sessions.length === 0" class="p-4 text-sm text-gray-400">
          {{ $t('tools.admin.advancedControlTool.noSessions') }}
        </p>
        <table v-else class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th class="text-left px-4 py-2">{{ $t('tools.admin.advancedControlTool.colSessionId') }}</th>
              <th class="text-left px-4 py-2">{{ $t('tools.admin.advancedControlTool.colUser') }}</th>
              <th class="text-left px-4 py-2">{{ $t('tools.admin.advancedControlTool.colDisplay') }}</th>
              <th class="text-left px-4 py-2">{{ $t('tools.admin.advancedControlTool.colVncPort') }}</th>
              <th class="text-left px-4 py-2">{{ $t('tools.admin.advancedControlTool.colStatus') }}</th>
              <th class="text-left px-4 py-2">{{ $t('tools.admin.advancedControlTool.colCreated') }}</th>
              <th class="text-right px-4 py-2">{{ $t('tools.admin.advancedControlTool.colActions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in sessions" :key="s.session_id" class="border-t border-gray-100">
              <td class="px-4 py-2 font-mono text-gray-900">{{ s.session_id }}</td>
              <td class="px-4 py-2 text-gray-700">{{ s.user_id || '—' }}</td>
              <td class="px-4 py-2 font-mono text-gray-700">{{ s.display || '—' }}</td>
              <td class="px-4 py-2 text-gray-700">{{ s.vnc_port ?? '—' }}</td>
              <td class="px-4 py-2">
                <span class="px-2 py-0.5 rounded-full text-xs" :class="badgeClass(s.status)">{{ s.status || '—' }}</span>
              </td>
              <td class="px-4 py-2 text-gray-500">{{ formatTime(s.created_at) }}</td>
              <td class="px-4 py-2 text-right">
                <button :data-test="`terminate-${s.session_id}`" :disabled="busy.terminate === s.session_id"
                  @click="onTerminate(s.session_id)"
                  class="px-3 py-1 text-xs font-medium rounded-lg bg-red-100 text-red-700 hover:bg-red-200 disabled:opacity-50 transition-colors">
                  {{ $t('tools.admin.advancedControlTool.terminate') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- ============================ TAKEOVER ============================ -->
    <section class="space-y-4">
      <h3 class="text-lg font-semibold text-gray-900">{{ $t('tools.admin.advancedControlTool.takeoverTitle') }}</h3>

      <!-- Request takeover -->
      <div class="bg-white rounded-lg shadow-xs border border-gray-200 p-4">
        <h4 class="text-sm font-medium text-gray-900 mb-3">{{ $t('tools.admin.advancedControlTool.requestTitle') }}</h4>
        <form class="grid grid-cols-1 sm:grid-cols-2 gap-3" @submit.prevent="onRequestTakeover">
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('tools.admin.advancedControlTool.trigger') }}</label>
            <select v-model="requestForm.trigger"
              class="w-full text-sm px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500">
              <option v-for="trg in TRIGGERS" :key="trg" :value="trg">{{ trg }}</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('tools.admin.advancedControlTool.priority') }}</label>
            <select v-model="requestForm.priority"
              class="w-full text-sm px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500">
              <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('tools.admin.advancedControlTool.reason') }}</label>
            <input v-model.trim="requestForm.reason" required
              class="w-full text-sm px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1">{{ $t('tools.admin.advancedControlTool.requestingAgent') }}</label>
            <input v-model.trim="requestForm.requesting_agent" :placeholder="$t('tools.admin.advancedControlTool.requestingAgentPlaceholder')"
              class="w-full text-sm px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
          </div>
          <div class="sm:col-span-2">
            <button data-test="request" type="submit" :disabled="busy.request || !requestForm.reason"
              class="px-4 py-1.5 text-sm font-medium rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 transition-colors">
              {{ busy.request ? $t('tools.admin.advancedControlTool.requesting') : $t('tools.admin.advancedControlTool.requestBtn') }}
            </button>
          </div>
        </form>
      </div>

      <!-- Pending requests -->
      <div class="bg-white rounded-lg shadow-xs border border-gray-200 overflow-hidden">
        <div class="px-4 py-3 border-b border-gray-200 text-sm font-medium text-gray-900">
          {{ $t('tools.admin.advancedControlTool.pendingTitle') }}
        </div>
        <p v-if="pending.length === 0" class="p-4 text-sm text-gray-400">
          {{ $t('tools.admin.advancedControlTool.noPending') }}
        </p>
        <table v-else class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th class="text-left px-4 py-2">{{ $t('tools.admin.advancedControlTool.colRequestId') }}</th>
              <th class="text-left px-4 py-2">{{ $t('tools.admin.advancedControlTool.colTrigger') }}</th>
              <th class="text-left px-4 py-2">{{ $t('tools.admin.advancedControlTool.colReason') }}</th>
              <th class="text-left px-4 py-2">{{ $t('tools.admin.advancedControlTool.colPriority') }}</th>
              <th class="text-left px-4 py-2">{{ $t('tools.admin.advancedControlTool.colCreated') }}</th>
              <th class="text-right px-4 py-2">{{ $t('tools.admin.advancedControlTool.colActions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in pending" :key="r.request_id" class="border-t border-gray-100">
              <td class="px-4 py-2 font-mono text-gray-900">{{ r.request_id }}</td>
              <td class="px-4 py-2 text-gray-700">{{ r.trigger || '—' }}</td>
              <td class="px-4 py-2 text-gray-700">{{ r.reason || '—' }}</td>
              <td class="px-4 py-2">
                <span class="px-2 py-0.5 rounded-full text-xs" :class="priorityClass(r.priority)">{{ r.priority || '—' }}</span>
              </td>
              <td class="px-4 py-2 text-gray-500">{{ formatTime(r.created_at) }}</td>
              <td class="px-4 py-2">
                <div class="flex items-center justify-end gap-2">
                  <input v-model.trim="operatorInputs[r.request_id]"
                    :placeholder="$t('tools.admin.advancedControlTool.operatorPlaceholder')"
                    class="w-32 text-xs px-2 py-1 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500" />
                  <button :data-test="`approve-${r.request_id}`"
                    :disabled="busy.approve === r.request_id || !operatorInputs[r.request_id]"
                    @click="onApprove(r.request_id)"
                    class="px-3 py-1 text-xs font-medium rounded-lg bg-green-100 text-green-700 hover:bg-green-200 disabled:opacity-50 transition-colors">
                    {{ $t('tools.admin.advancedControlTool.approve') }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Active takeover sessions -->
      <div class="bg-white rounded-lg shadow-xs border border-gray-200 overflow-hidden">
        <div class="px-4 py-3 border-b border-gray-200 text-sm font-medium text-gray-900">
          {{ $t('tools.admin.advancedControlTool.activeTitle') }}
        </div>
        <p v-if="active.length === 0" class="p-4 text-sm text-gray-400">
          {{ $t('tools.admin.advancedControlTool.noActive') }}
        </p>
        <table v-else class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th class="text-left px-4 py-2">{{ $t('tools.admin.advancedControlTool.colSessionId') }}</th>
              <th class="text-left px-4 py-2">{{ $t('tools.admin.advancedControlTool.colOperator') }}</th>
              <th class="text-left px-4 py-2">{{ $t('tools.admin.advancedControlTool.colStatus') }}</th>
              <th class="text-right px-4 py-2">{{ $t('tools.admin.advancedControlTool.colActions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in active" :key="a.session_id" class="border-t border-gray-100">
              <td class="px-4 py-2 font-mono text-gray-900">{{ a.session_id }}</td>
              <td class="px-4 py-2 text-gray-700">{{ a.human_operator || '—' }}</td>
              <td class="px-4 py-2">
                <span class="px-2 py-0.5 rounded-full text-xs" :class="badgeClass(a.status)">{{ a.status || '—' }}</span>
              </td>
              <td class="px-4 py-2">
                <div class="flex items-center justify-end gap-2">
                  <button :data-test="`pause-${a.session_id}`"
                    :disabled="busy.session === a.session_id || a.status === 'paused'"
                    @click="onSessionAction(a.session_id, 'pause')"
                    class="px-3 py-1 text-xs font-medium rounded-lg bg-yellow-100 text-yellow-700 hover:bg-yellow-200 disabled:opacity-50 transition-colors">
                    {{ $t('tools.admin.advancedControlTool.pause') }}
                  </button>
                  <button :data-test="`resume-${a.session_id}`"
                    :disabled="busy.session === a.session_id || a.status !== 'paused'"
                    @click="onSessionAction(a.session_id, 'resume')"
                    class="px-3 py-1 text-xs font-medium rounded-lg bg-green-100 text-green-700 hover:bg-green-200 disabled:opacity-50 transition-colors">
                    {{ $t('tools.admin.advancedControlTool.resume') }}
                  </button>
                  <button :data-test="`complete-${a.session_id}`"
                    :disabled="busy.session === a.session_id"
                    @click="onSessionAction(a.session_id, 'complete')"
                    class="px-3 py-1 text-xs font-medium rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200 disabled:opacity-50 transition-colors">
                    {{ $t('tools.admin.advancedControlTool.complete') }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Raw takeover system status -->
      <div class="bg-white rounded-lg shadow-xs border border-gray-200 p-4">
        <h4 class="text-sm font-medium text-gray-900 mb-3">{{ $t('tools.admin.advancedControlTool.systemStatusTitle') }}</h4>
        <dl v-if="takeoverStatus && Object.keys(takeoverStatus).length > 0" class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <template v-for="(value, key) in takeoverStatus" :key="key">
            <dt class="text-gray-500 font-mono">{{ key }}</dt>
            <dd class="text-gray-900 truncate">{{ value }}</dd>
          </template>
        </dl>
        <p v-else class="text-sm text-gray-400">{{ $t('tools.admin.advancedControlTool.noStatus') }}</p>
      </div>
    </section>
  </div>
</template>
