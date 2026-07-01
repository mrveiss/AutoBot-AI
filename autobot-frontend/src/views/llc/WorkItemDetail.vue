<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="work-item-detail-overlay" @click.self="$emit('close')">
    <div class="detail-drawer">
      <!-- Drawer Header -->
      <div class="drawer-header">
        <div class="header-left">
          <span class="item-identifier">{{ item.identifier }}</span>
          <span class="type-badge" :class="`type-${item.type}`">{{ item.type }}</span>
          <span class="status-badge" :class="`status-${item.status}`">{{ item.status.replace('_', ' ') }}</span>
        </div>
        <button class="close-btn" @click="$emit('close')" aria-label="Close">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" class="close-icon">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Goal ancestry breadcrumb -->
      <div v-if="goalAncestry.length > 0" class="goal-breadcrumb">
        <template v-for="(g, i) in goalAncestry" :key="g.id">
          <span class="breadcrumb-item">{{ g.title }}</span>
          <span v-if="i < goalAncestry.length - 1" class="breadcrumb-sep">/</span>
        </template>
      </div>

      <!-- Title -->
      <div class="title-row">
        <h2 class="item-title" v-if="!editingTitle" @dblclick="startEditTitle">{{ localItem.title }}</h2>
        <input
          v-else
          v-model="localItem.title"
          class="title-input"
          @blur="saveTitle"
          @keyup.enter="saveTitle"
          @keyup.escape="cancelTitle"
          ref="titleInput"
        />
      </div>

      <!-- Meta row -->
      <div class="meta-row">
        <div class="meta-field">
          <span class="meta-label">Priority</span>
          <span class="priority-badge" :class="`priority-${localItem.priority}`">{{ localItem.priority }}</span>
        </div>
        <div class="meta-field">
          <span class="meta-label">Assignee</span>
          <div class="assignee-row">
            <span v-if="localItem.assignee_name" class="assignee-chip">{{ localItem.assignee_name }}</span>
            <span v-else class="meta-empty">{{ $t('nav.llcUnassigned') }}</span>
            <button class="assignee-edit" :title="$t('nav.llcAssign')" @click="openAssign">✎</button>
          </div>
          <!-- #10532: assign to a human member or an agent. -->
          <div v-if="showAssign" class="assignee-picker">
            <select
              class="assignee-select"
              :disabled="isAssigning"
              @change="onAssignSelect(($event.target as HTMLSelectElement).value)"
            >
              <option value="">{{ $t('nav.llcAssign') }}…</option>
              <optgroup :label="$t('nav.llcHumans')">
                <option v-for="h in people.humans.value" :key="h.user_id" :value="`user:${h.user_id}`">
                  {{ h.name }}
                </option>
              </optgroup>
              <optgroup :label="$t('nav.llcAgents')">
                <option v-for="a in people.agents.value" :key="a.id" :value="`agent:${a.id}`">{{ a.name }}</option>
              </optgroup>
            </select>
            <button class="assignee-cancel" @click="showAssign = false">{{ $t('common.cancel') }}</button>
          </div>
        </div>
        <div class="meta-field">
          <span class="meta-label">Points</span>
          <span>{{ localItem.story_points ?? '—' }}</span>
        </div>
        <div class="meta-field" v-if="localItem.labels?.length">
          <span class="meta-label">Labels</span>
          <div class="label-chips">
            <span v-for="l in localItem.labels" :key="l" class="label-chip">{{ l }}</span>
          </div>
        </div>
      </div>

      <!-- Transition / Action buttons -->
      <div class="action-bar">
        <button
          v-for="action in availableActions"
          :key="action.key"
          class="action-btn"
          :class="`action-${action.key}`"
          :disabled="isActioning"
          @click="performAction(action)"
        >
          {{ action.label }}
        </button>
      </div>

      <!-- Tabs -->
      <div class="tab-bar">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          class="tab-btn"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- Tab content -->
      <div class="tab-content">
        <!-- Details tab -->
        <template v-if="activeTab === 'details'">
          <div class="detail-section">
            <label class="section-label">Description</label>
            <div v-if="!editingDesc" class="description-text" @dblclick="startEditDesc">
              <span v-if="localItem.description">{{ localItem.description }}</span>
              <span v-else class="meta-empty">No description. Double-click to add.</span>
            </div>
            <textarea
              v-else
              v-model="localItem.description"
              class="desc-textarea"
              rows="5"
              @blur="saveDesc"
              ref="descInput"
            />
          </div>

          <div class="detail-section">
            <label class="section-label">Acceptance Criteria</label>
            <div class="ac-list">
              <label
                v-for="(ac, i) in localItem.acceptance_criteria"
                :key="i"
                class="ac-item"
              >
                <input type="checkbox" v-model="checkedAC[i]" @change="saveAC" />
                <span :class="{ 'ac-done': checkedAC[i] }">{{ ac }}</span>
              </label>
              <div v-if="!localItem.acceptance_criteria?.length" class="meta-empty">
                No acceptance criteria defined.
              </div>
            </div>
          </div>
        </template>

        <!-- Comments tab -->
        <template v-if="activeTab === 'comments'">
          <div class="comments-list">
            <div v-for="c in comments" :key="c.id" class="comment-item">
              <div class="comment-author">
                <span class="author-avatar">{{ initials(c.author_name) }}</span>
                <div class="author-meta">
                  <span class="author-name">{{ c.author_name }}</span>
                  <span class="comment-time">{{ formatTime(c.created_at) }}</span>
                  <span v-if="c.author_type === 'agent'" class="agent-chip">agent</span>
                </div>
              </div>
              <div class="comment-body" v-html="renderMarkdown(c.body)" />
            </div>
            <div v-if="comments.length === 0 && !isLoadingComments" class="meta-empty">
              No comments yet.
            </div>
          </div>
          <div class="comment-input-row">
            <textarea
              v-model="newComment"
              class="comment-textarea"
              rows="3"
              placeholder="Write a comment..."
            />
            <button class="btn-primary" :disabled="!newComment.trim() || isPosting" @click="postComment">
              {{ isPosting ? 'Posting...' : 'Post' }}
            </button>
          </div>
        </template>

        <!-- Artifacts tab -->
        <template v-if="activeTab === 'artifacts'">
          <div class="artifacts-list">
            <div v-for="a in artifacts" :key="a.id" class="artifact-item">
              <span class="artifact-type-icon">{{ artifactIcon(a.type) }}</span>
              <div class="artifact-info">
                <span class="artifact-name">{{ a.name }}</span>
                <span class="artifact-type-label">{{ a.type }}</span>
              </div>
              <a :href="a.url" target="_blank" class="artifact-link" rel="noopener">View</a>
            </div>
            <div v-if="artifacts.length === 0 && !isLoadingArtifacts" class="meta-empty">
              No artifacts attached.
            </div>
          </div>
        </template>

        <!-- Activity tab -->
        <template v-if="activeTab === 'activity'">
          <div class="activity-list">
            <div v-for="evt in activity" :key="evt.id" class="activity-item">
              <span class="activity-time">{{ formatTime(evt.created_at) }}</span>
              <span class="activity-actor">{{ evt.actor_name }}</span>
              <span class="activity-text">{{ evt.description }}</span>
            </div>
            <div v-if="activity.length === 0 && !isLoadingActivity" class="meta-empty">
              No activity recorded.
            </div>
          </div>
        </template>

        <!-- Handoff Brief tab -->
        <template v-if="activeTab === 'handoff'">
          <div v-if="handoffBrief" class="handoff-brief" v-html="renderMarkdown(handoffBrief)" />
          <div v-else-if="!isLoadingHandoff" class="meta-empty">No handoff brief available.</div>
          <div v-if="isLoadingHandoff" class="meta-empty">Loading brief...</div>
        </template>
      </div>
    </div>

    <HandoffModal
      v-if="handoffDirection"
      :work-item-id="props.item.id"
      :company-id="props.companyId"
      :direction="handoffDirection"
      :agent-assignee-id="localItem.assignee_agent_id"
      @close="handoffDirection = null"
      @done="onHandoffDone"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import HandoffModal from '@/components/llc/HandoffModal.vue'
import { useCompanyPeople } from '@/composables/llc/useCompanyPeople'

const logger = createLogger('WorkItemDetail')
const api = useApiClient()

import type { WorkItem } from './workItemTypes'

interface Comment {
  id: string
  body: string
  author_name: string
  author_type: 'human' | 'agent'
  created_at: string
}

interface Artifact {
  id: string
  name: string
  type: string
  url: string
}

interface ActivityEvent {
  id: string
  actor_name: string
  description: string
  created_at: string
}

interface GoalAncestor {
  id: string
  title: string
}

const props = defineProps<{
  item: WorkItem
  companyId: string
}>()

const emit = defineEmits<{
  close: []
  updated: [WorkItem]
}>()

const TABS = [
  { key: 'details', label: 'Details' },
  { key: 'comments', label: 'Comments' },
  { key: 'artifacts', label: 'Artifacts' },
  { key: 'activity', label: 'Activity' },
  { key: 'handoff', label: 'Handoff Brief' },
]

const activeTab = ref('details')
const localItem = ref<WorkItem>({ ...props.item })
const checkedAC = ref<boolean[]>([])

const editingTitle = ref(false)
const editingDesc = ref(false)
const titleInput = ref<HTMLInputElement | null>(null)
const descInput = ref<HTMLTextAreaElement | null>(null)
const origTitle = ref('')
const origDesc = ref('')

const comments = ref<Comment[]>([])
const artifacts = ref<Artifact[]>([])
const activity = ref<ActivityEvent[]>([])
const goalAncestry = ref<GoalAncestor[]>([])
const handoffBrief = ref<string | null>(null)
const newComment = ref('')
const isPosting = ref(false)
const isActioning = ref(false)
const isLoadingComments = ref(false)
const isLoadingArtifacts = ref(false)
const isLoadingActivity = ref(false)
const isLoadingHandoff = ref(false)

// #10531 handoff dialog + #10532 assignee picker.
const handoffDirection = ref<'to_agent' | 'to_human' | null>(null)
const people = useCompanyPeople(props.companyId)
const showAssign = ref(false)
const isAssigning = ref(false)

function openAssign() {
  showAssign.value = true
  if (people.agents.value.length === 0 && people.humans.value.length === 0) void people.load()
}

async function onAssignSelect(value: string) {
  if (!value) return
  const [kind, id] = value.split(':')
  isAssigning.value = true
  try {
    const patch =
      kind === 'agent'
        ? { assignee_agent_id: id, assignee_user_id: null }
        : { assignee_user_id: id, assignee_agent_id: null }
    await patchItem(patch as Partial<WorkItem>)
    showAssign.value = false
  } finally {
    isAssigning.value = false
  }
}

const STATUS_TRANSITIONS: Record<string, { key: string; label: string }[]> = {
  backlog: [{ key: 'ready', label: 'Mark Ready' }],
  ready: [{ key: 'in_progress', label: 'Start' }, { key: 'backlog', label: 'Back to Backlog' }],
  in_progress: [{ key: 'in_review', label: 'Submit for Review' }, { key: 'blocked', label: 'Mark Blocked' }],
  in_review: [{ key: 'done', label: 'Approve / Done' }, { key: 'in_progress', label: 'Request Changes' }],
  blocked: [{ key: 'in_progress', label: 'Unblock' }],
  done: [],
  cancelled: [],
}

const availableActions = computed(() => {
  const transitions = (STATUS_TRANSITIONS[localItem.value.status] ?? []).map(t => ({ ...t, type: 'transition' }))
  const extras: { key: string; label: string; type: string }[] = []
  if (!['done', 'cancelled'].includes(localItem.value.status)) {
    extras.push({ key: 'claim', label: 'Claim', type: 'action' })
    extras.push({ key: 'handoff_human', label: 'Handoff to Human', type: 'action' })
    extras.push({ key: 'handoff_agent', label: 'Handoff to Agent', type: 'action' })
  }
  return [...transitions, ...extras]
})

function initials(name: string) {
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function renderMarkdown(text: string) {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
}

function artifactIcon(type: string) {
  const icons: Record<string, string> = {
    document: '📄', code: '💻', image: '🖼️', video: '🎥', data: '📊', link: '🔗',
  }
  return icons[type] ?? '📎'
}

function startEditTitle() {
  origTitle.value = localItem.value.title
  editingTitle.value = true
  nextTick(() => titleInput.value?.focus())
}

function cancelTitle() {
  localItem.value.title = origTitle.value
  editingTitle.value = false
}

async function saveTitle() {
  editingTitle.value = false
  if (localItem.value.title === origTitle.value) return
  await patchItem({ title: localItem.value.title })
}

function startEditDesc() {
  origDesc.value = localItem.value.description
  editingDesc.value = true
  nextTick(() => descInput.value?.focus())
}

async function saveDesc() {
  editingDesc.value = false
  if (localItem.value.description === origDesc.value) return
  await patchItem({ description: localItem.value.description })
}

async function saveAC() {
  // no-op: checkboxes are local display state; AC completion tracked via transition
}

async function patchItem(patch: Partial<WorkItem>) {
  try {
    const updated = await api.patch<WorkItem>(`/api/llc/work-items/${props.item.id}`, patch)
    Object.assign(localItem.value, updated)
    emit('updated', localItem.value)
  } catch (err) {
    logger.error('Failed to patch item', err)
  }
}

async function performAction(action: { key: string; type: string; label: string }) {
  isActioning.value = true
  try {
    if (action.type === 'transition') {
      const updated = await api.post<WorkItem>(`/api/llc/work-items/${props.item.id}/transition`, {
        status: action.key,
      })
      Object.assign(localItem.value, updated)
      emit('updated', localItem.value)
    } else if (action.key === 'claim') {
      await api.post<unknown>(`/api/llc/work-items/${props.item.id}/claim`, {})
    } else if (action.key === 'handoff_human' || action.key === 'handoff_agent') {
      // #10531: open the handoff dialog (real /handoff/to-* endpoints with a
      // target picker + notes) rather than blindly POSTing to /release.
      handoffDirection.value = action.key === 'handoff_human' ? 'to_human' : 'to_agent'
      isActioning.value = false
      return
    }
  } catch (err) {
    logger.error(`Action ${action.key} failed`, err)
  } finally {
    isActioning.value = false
  }
}

function onHandoffDone() {
  handoffDirection.value = null
  // Re-fetch the item so status/assignee/reviewer reflect the handoff.
  emit('updated', localItem.value)
  emit('close')
}

async function postComment() {
  if (!newComment.value.trim()) return
  isPosting.value = true
  try {
    const comment = await api.post<Comment>(`/api/llc/work-items/${props.item.id}/comments`, {
      body: newComment.value,
    })
    comments.value.push(comment)
    newComment.value = ''
  } catch (err) {
    logger.error('Post comment failed', err)
  } finally {
    isPosting.value = false
  }
}

async function fetchComments() {
  isLoadingComments.value = true
  try {
    const result = await api.get<{ comments: Comment[] }>(`/api/llc/work-items/${props.item.id}/comments`)
    comments.value = result.comments ?? []
  } catch (err) {
    logger.error('Failed to load comments', err)
  } finally {
    isLoadingComments.value = false
  }
}

async function fetchArtifacts() {
  isLoadingArtifacts.value = true
  try {
    // GH#9851: backend names these "products" (work products), returned as
    // {products:[...]}. The api client returns parsed JSON directly.
    const result = await api.get<{ products: Artifact[] }>(`/api/llc/work-items/${props.item.id}/products`)
    artifacts.value = result.products ?? []
  } catch (err) {
    logger.error('Failed to load artifacts', err)
  } finally {
    isLoadingArtifacts.value = false
  }
}

async function fetchActivity() {
  isLoadingActivity.value = true
  try {
    // GH#9851: /activity returns an ActivityLogResponse ({items:[...]}).
    const result = await api.get<{ items: ActivityEvent[] }>(`/api/llc/work-items/${props.item.id}/activity`)
    activity.value = result.items ?? []
  } catch (err) {
    logger.error('Failed to load activity', err)
  } finally {
    isLoadingActivity.value = false
  }
}

async function fetchHandoffBrief() {
  isLoadingHandoff.value = true
  try {
    const result = await api.get<{ brief: string }>(`/api/llc/work-items/${props.item.id}/handoff-brief`)
    handoffBrief.value = result.brief ?? null
  } catch {
    handoffBrief.value = null
  } finally {
    isLoadingHandoff.value = false
  }
}

watch(activeTab, (tab) => {
  if (tab === 'comments' && comments.value.length === 0) fetchComments()
  if (tab === 'artifacts' && artifacts.value.length === 0) fetchArtifacts()
  if (tab === 'activity' && activity.value.length === 0) fetchActivity()
  if (tab === 'handoff' && handoffBrief.value === null) fetchHandoffBrief()
})

onMounted(() => {
  localItem.value = { ...props.item }
  checkedAC.value = (props.item.acceptance_criteria ?? []).map(() => false)
})
</script>

<style scoped>
.work-item-detail-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  justify-content: flex-end;
  z-index: 60;
}

.detail-drawer {
  width: 640px;
  max-width: 90vw;
  height: 100%;
  background: var(--bg-surface, #fff);
  border-left: 1px solid var(--border-default, #e5e7eb);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-default, #e5e7eb);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.item-identifier {
  font-family: monospace;
  font-size: 0.8rem;
  color: var(--text-secondary, #6b7280);
}

.type-badge,
.status-badge {
  font-size: 0.75rem;
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  font-weight: 500;
  text-transform: capitalize;
}

.type-epic { background: #ddd6fe; color: #5b21b6; }
.type-feature { background: #bfdbfe; color: #1d4ed8; }
.type-pbi { background: #d1fae5; color: #065f46; }
.type-task { background: #e0f2fe; color: #0369a1; }
.type-bug { background: #fee2e2; color: #991b1b; }
.type-spike { background: #fef3c7; color: #92400e; }
.type-subtask { background: #f3f4f6; color: #374151; }
.type-risk { background: #fce7f3; color: #9d174d; }

.status-backlog { background: #f3f4f6; color: #374151; }
.status-ready { background: #e0f2fe; color: #0369a1; }
.status-in_progress { background: #ddd6fe; color: #5b21b6; }
.status-in_review { background: #fef9c3; color: #713f12; }
.status-done { background: #d1fae5; color: #065f46; }
.status-blocked { background: #fee2e2; color: #991b1b; }
.status-cancelled { background: #f3f4f6; color: #9ca3af; }

.close-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.25rem;
  color: var(--text-secondary, #6b7280);
  border-radius: 0.25rem;
  transition: background 0.15s;
}

.close-btn:hover {
  background: var(--bg-hover, #f3f4f6);
}

.close-icon {
  width: 1.25rem;
  height: 1.25rem;
}

.goal-breadcrumb {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1.25rem;
  background: var(--bg-elevated, #f9fafb);
  border-bottom: 1px solid var(--border-default, #e5e7eb);
  font-size: 0.75rem;
  color: var(--text-secondary, #6b7280);
  flex-shrink: 0;
}

.breadcrumb-sep {
  color: var(--border-default, #d1d5db);
}

.title-row {
  padding: 1rem 1.25rem 0.5rem;
  flex-shrink: 0;
}

.item-title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  cursor: text;
  line-height: 1.4;
}

.title-input {
  width: 100%;
  font-size: 1.125rem;
  font-weight: 600;
  border: 1px solid var(--color-primary, #3b82f6);
  border-radius: 0.25rem;
  padding: 0.25rem 0.5rem;
  background: var(--bg-surface, #fff);
  color: var(--text-primary);
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  padding: 0.5rem 1.25rem;
  border-bottom: 1px solid var(--border-default, #e5e7eb);
  flex-shrink: 0;
}

.meta-field {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.meta-label {
  font-size: 0.7rem;
  color: var(--text-secondary, #9ca3af);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.priority-badge {
  font-size: 0.75rem;
  padding: 0.1rem 0.45rem;
  border-radius: 9999px;
  font-weight: 500;
  text-transform: capitalize;
}

.priority-critical { background: #fee2e2; color: #991b1b; }
.priority-high { background: #ffedd5; color: #9a3412; }
.priority-medium { background: #fef9c3; color: #713f12; }
.priority-low { background: #f0fdf4; color: #14532d; }

.assignee-chip {
  font-size: 0.8rem;
  padding: 0.1rem 0.5rem;
  background: var(--bg-elevated, #f3f4f6);
  border-radius: 9999px;
}

.assignee-row {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.assignee-edit {
  font-size: 0.75rem;
  color: var(--text-secondary, #6b7280);
  cursor: pointer;
}

.assignee-picker {
  margin-top: 0.375rem;
  display: flex;
  gap: 0.375rem;
  align-items: center;
}

.assignee-select {
  font-size: 0.8rem;
  padding: 0.25rem;
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: var(--radius-md, 6px);
}

.assignee-cancel {
  font-size: 0.75rem;
  color: var(--text-secondary, #6b7280);
}

.meta-empty {
  font-size: 0.8rem;
  color: var(--text-secondary, #9ca3af);
  font-style: italic;
}

.label-chips {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
}

.label-chip {
  font-size: 0.7rem;
  padding: 0.1rem 0.45rem;
  background: var(--bg-elevated, #f3f4f6);
  border-radius: 9999px;
}

.action-bar {
  display: flex;
  gap: 0.5rem;
  padding: 0.625rem 1.25rem;
  border-bottom: 1px solid var(--border-default, #e5e7eb);
  flex-wrap: wrap;
  flex-shrink: 0;
}

.action-btn {
  font-size: 0.8rem;
  padding: 0.35rem 0.75rem;
  border-radius: 0.375rem;
  border: 1px solid var(--border-default, #d1d5db);
  background: var(--bg-surface, #fff);
  color: var(--text-primary);
  cursor: pointer;
  transition: background 0.15s;
}

.action-btn:hover:not(:disabled) {
  background: var(--bg-hover, #f3f4f6);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-done, .action-ready {
  background: var(--color-primary, #3b82f6);
  color: white;
  border-color: var(--color-primary, #3b82f6);
}

.action-done:hover:not(:disabled), .action-ready:hover:not(:disabled) {
  background: var(--color-primary-hover, #2563eb);
}

.tab-bar {
  display: flex;
  border-bottom: 1px solid var(--border-default, #e5e7eb);
  flex-shrink: 0;
}

.tab-btn {
  padding: 0.625rem 1rem;
  font-size: 0.8rem;
  font-weight: 500;
  border: none;
  background: none;
  color: var(--text-secondary, #6b7280);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: color 0.15s, border-color 0.15s;
}

.tab-btn.active {
  color: var(--color-primary, #3b82f6);
  border-bottom-color: var(--color-primary, #3b82f6);
}

.tab-btn:hover:not(.active) {
  color: var(--text-primary);
}

.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.section-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary, #6b7280);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.description-text {
  font-size: 0.875rem;
  line-height: 1.6;
  cursor: text;
  min-height: 2rem;
}

.desc-textarea {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid var(--color-primary, #3b82f6);
  border-radius: 0.375rem;
  background: var(--bg-surface, #fff);
  color: var(--text-primary);
  font-size: 0.875rem;
  resize: vertical;
}

.ac-list {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.ac-item {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  font-size: 0.875rem;
  cursor: pointer;
}

.ac-done {
  text-decoration: line-through;
  color: var(--text-secondary, #9ca3af);
}

.comments-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  flex: 1;
}

.comment-item {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.comment-author {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.author-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: 50%;
  background: var(--color-primary, #3b82f6);
  color: white;
  font-size: 0.65rem;
  font-weight: 600;
  flex-shrink: 0;
}

.author-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.author-name {
  font-size: 0.8rem;
  font-weight: 600;
}

.comment-time {
  font-size: 0.7rem;
  color: var(--text-secondary, #9ca3af);
}

.agent-chip {
  font-size: 0.65rem;
  padding: 0.05rem 0.35rem;
  background: #ddd6fe;
  color: #5b21b6;
  border-radius: 9999px;
}

.comment-body {
  font-size: 0.875rem;
  line-height: 1.5;
  margin-left: 2.25rem;
}

.comment-input-row {
  display: flex;
  gap: 0.5rem;
  align-items: flex-end;
  flex-shrink: 0;
  padding-top: 0.5rem;
  border-top: 1px solid var(--border-default, #e5e7eb);
}

.comment-textarea {
  flex: 1;
  padding: 0.5rem;
  border: 1px solid var(--border-default, #d1d5db);
  border-radius: 0.375rem;
  background: var(--bg-surface, #fff);
  color: var(--text-primary);
  font-size: 0.875rem;
  resize: none;
}

.artifacts-list,
.activity-list {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.artifact-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: var(--bg-elevated, #f9fafb);
  border-radius: 0.375rem;
  border: 1px solid var(--border-default, #e5e7eb);
}

.artifact-type-icon {
  font-size: 1.25rem;
}

.artifact-info {
  display: flex;
  flex-direction: column;
  flex: 1;
  gap: 0.1rem;
}

.artifact-name {
  font-size: 0.875rem;
  font-weight: 500;
}

.artifact-type-label {
  font-size: 0.7rem;
  color: var(--text-secondary, #9ca3af);
  text-transform: capitalize;
}

.artifact-link {
  font-size: 0.8rem;
  color: var(--color-primary, #3b82f6);
  text-decoration: none;
}

.artifact-link:hover {
  text-decoration: underline;
}

.activity-item {
  display: flex;
  gap: 0.5rem;
  font-size: 0.8rem;
  align-items: baseline;
}

.activity-time {
  color: var(--text-secondary, #9ca3af);
  flex-shrink: 0;
  font-size: 0.7rem;
}

.activity-actor {
  font-weight: 600;
  flex-shrink: 0;
}

.activity-text {
  color: var(--text-primary);
}

.handoff-brief {
  font-size: 0.875rem;
  line-height: 1.6;
}

.btn-primary {
  padding: 0.5rem 1rem;
  background: var(--color-primary, #3b82f6);
  color: white;
  border: none;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover, #2563eb);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
