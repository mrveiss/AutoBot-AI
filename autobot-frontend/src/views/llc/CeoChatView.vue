<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="ceo-chat-view">
    <!-- Thread sidebar -->
    <div class="thread-sidebar">
      <div class="sidebar-header">
        <span class="sidebar-title">Threads</span>
        <button class="btn-new-thread" @click="showNewThread = true">+ New</button>
      </div>
      <div v-if="!companyId" class="state-msg-sm">Select a company to view threads.</div>
      <div v-else-if="threadsLoading" class="state-msg-sm">Loading...</div>
      <div v-else-if="threads.length === 0" class="state-msg-sm">No threads yet.</div>
      <div class="thread-list">
        <div
          v-for="t in threads"
          :key="t.id"
          class="thread-item"
          :class="{ active: activeThread?.id === t.id }"
          @click="selectThread(t)"
        >
          <div class="thread-title">{{ t.title }}</div>
          <div v-if="t.resolved_entity_type" class="thread-entity">
            {{ t.resolved_entity_type }}
          </div>
          <div class="thread-date">{{ formatDate(t.updated_at) }}</div>
        </div>
      </div>
    </div>

    <!-- Chat window -->
    <div class="chat-window">
      <div v-if="!activeThread" class="chat-empty">
        <p>Select a thread or create a new one.</p>
      </div>

      <template v-else>
        <div class="chat-header">
          <span class="chat-title">{{ activeThread.title }}</span>
          <span v-if="activeThread.resolved_entity_type" class="entity-chip">
            {{ activeThread.resolved_entity_type }}
            <span v-if="activeThread.resolved_entity_id">
              #{{ activeThread.resolved_entity_id }}
            </span>
          </span>
        </div>

        <div class="messages-area" ref="messagesArea">
          <div v-if="messagesLoading" class="state-msg-sm">Loading messages...</div>
          <template v-else>
            <div
              v-for="msg in messages"
              :key="msg.id"
              class="message-row"
              :class="msg.author_type === 'human' ? 'row-right' : 'row-left'"
            >
              <div class="message-bubble" :class="msg.author_type === 'human' ? 'bubble-human' : 'bubble-system'">
                <div class="message-body">{{ msg.body }}</div>
                <div v-if="msg.author_type === 'system' && activeThread.resolved_entity_type" class="entity-link">
                  {{ activeThread.resolved_entity_type }}
                  <template v-if="activeThread.resolved_entity_id">
                    #{{ activeThread.resolved_entity_id }}
                  </template>
                </div>
                <div class="message-time">{{ formatTime(msg.created_at) }}</div>
              </div>
            </div>
            <div v-if="messages.length === 0" class="state-msg-sm">No messages yet.</div>
          </template>
        </div>

        <div class="message-input-area">
          <textarea
            v-model="inputText"
            class="message-input"
            placeholder="Type a message..."
            rows="2"
            @keydown.enter.exact.prevent="sendMessage"
          />
          <button
            class="btn-send"
            :disabled="!inputText.trim() || sending"
            @click="sendMessage"
          >
            {{ sending ? '...' : 'Send' }}
          </button>
        </div>
      </template>
    </div>

    <!-- New thread modal -->
    <div v-if="showNewThread" class="modal-overlay" @click.self="showNewThread = false">
      <div class="modal-panel">
        <h3>New Thread</h3>
        <div class="form-field">
          <label>Title</label>
          <input v-model="newThreadTitle" type="text" class="form-input" placeholder="Thread title..." />
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="showNewThread = false">Cancel</button>
          <button
            class="btn-primary"
            :disabled="!newThreadTitle.trim() || creatingThread"
            @click="createThread"
          >
            {{ creatingThread ? 'Creating...' : 'Create' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CeoChatView')
const api = useApiClient()
const route = useRoute()

const props = defineProps<{ companyId?: string }>()
const companyId = computed(() => (route.params.companyId as string) ?? props.companyId ?? '')

interface ChatMessage {
  id: string
  thread_id: string
  author_type: 'human' | 'system'
  author_user_id?: string
  body: string
  created_at: string
}

interface ChatThread {
  id: string
  company_id: string
  title: string
  resolved_entity_type?: string
  resolved_entity_id?: string
  created_by_user_id?: string
  created_at: string
  updated_at: string
  messages?: ChatMessage[]
}

const threads = ref<ChatThread[]>([])
const threadsLoading = ref(false)
const activeThread = ref<ChatThread | null>(null)
const messages = ref<ChatMessage[]>([])
const messagesLoading = ref(false)
const inputText = ref('')
const sending = ref(false)
const showNewThread = ref(false)
const newThreadTitle = ref('')
const creatingThread = ref(false)
const messagesArea = ref<HTMLElement | null>(null)

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString()
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

async function scrollToBottom() {
  await nextTick()
  if (messagesArea.value) {
    messagesArea.value.scrollTop = messagesArea.value.scrollHeight
  }
}

async function fetchThreads() {
  if (!companyId.value) return
  threadsLoading.value = true
  try {
    const data = await api.get<ChatThread[] | { items: ChatThread[] }>(
      `/api/llc/companies/${companyId.value}/ceo-chat/threads`
    )
    threads.value = Array.isArray(data) ? data : (data as { items: ChatThread[] }).items ?? []
  } catch (err) {
    logger.error('Failed to fetch threads', err)
  } finally {
    threadsLoading.value = false
  }
}

async function selectThread(thread: ChatThread) {
  activeThread.value = thread
  messagesLoading.value = true
  messages.value = []
  try {
    const data = await api.get<ChatThread>(`/api/llc/ceo-chat/threads/${thread.id}`)
    activeThread.value = data
    messages.value = data.messages ?? []
    scrollToBottom()
  } catch (err) {
    logger.error('Failed to load thread', err)
  } finally {
    messagesLoading.value = false
  }
}

async function sendMessage() {
  if (!inputText.value.trim() || !activeThread.value || sending.value) return
  sending.value = true
  const body = inputText.value.trim()
  inputText.value = ''
  try {
    const msg = await api.post<ChatMessage>(`/api/llc/ceo-chat/threads/${activeThread.value.id}/messages`, {
      message: body,
      company_name: companyId.value,
    })
    messages.value.push(msg)
    scrollToBottom()
  } catch (err) {
    logger.error('Failed to send message', err)
    inputText.value = body
  } finally {
    sending.value = false
  }
}

async function createThread() {
  if (!newThreadTitle.value.trim()) return
  creatingThread.value = true
  try {
    const thread = await api.post<ChatThread>(
      `/api/llc/companies/${companyId.value}/ceo-chat/threads`,
      { title: newThreadTitle.value.trim() }
    )
    threads.value.unshift(thread)
    showNewThread.value = false
    newThreadTitle.value = ''
    await selectThread(thread)
  } catch (err) {
    logger.error('Failed to create thread', err)
  } finally {
    creatingThread.value = false
  }
}

onMounted(() => {
  if (!companyId.value) return
  fetchThreads()
})
</script>

<style scoped>
.ceo-chat-view {
  display: flex;
  height: 100%;
  background: var(--color-background);
  color: var(--color-text);
  overflow: hidden;
}

.thread-sidebar {
  width: 260px;
  flex-shrink: 0;
  border-right: 1px solid var(--color-border, #e5e7eb);
  display: flex;
  flex-direction: column;
  background: var(--color-surface, #fff);
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
}

.sidebar-title {
  font-weight: 600;
  font-size: 0.875rem;
}

.btn-new-thread {
  font-size: 0.8rem;
  padding: 0.25rem 0.625rem;
  background: var(--color-primary, #3b82f6);
  color: white;
  border: none;
  border-radius: 0.375rem;
  cursor: pointer;
}

.thread-list {
  flex: 1;
  overflow-y: auto;
}

.thread-item {
  padding: 0.75rem 1rem;
  cursor: pointer;
  border-bottom: 1px solid var(--color-border, #f3f4f6);
  transition: background 0.1s;
}

.thread-item:hover {
  background: var(--color-surface-hover, #f9fafb);
}

.thread-item.active {
  background: var(--color-primary-subtle, #eff6ff);
}

.thread-title {
  font-size: 0.875rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.thread-entity {
  font-size: 0.75rem;
  color: var(--color-primary, #3b82f6);
  margin-top: 0.125rem;
}

.thread-date {
  font-size: 0.75rem;
  color: var(--color-text-secondary, #9ca3af);
  margin-top: 0.125rem;
}

.chat-window {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary, #9ca3af);
}

.chat-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1.25rem;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
  background: var(--color-surface, #fff);
}

.chat-title {
  font-weight: 600;
  font-size: 1rem;
}

.entity-chip {
  font-size: 0.75rem;
  padding: 0.125rem 0.5rem;
  background: #ddd6fe;
  color: #5b21b6;
  border-radius: 9999px;
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.message-row {
  display: flex;
}

.row-right {
  justify-content: flex-end;
}

.row-left {
  justify-content: flex-start;
}

.message-bubble {
  max-width: 70%;
  padding: 0.625rem 0.875rem;
  border-radius: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.bubble-human {
  background: var(--color-primary, #3b82f6);
  color: white;
  border-bottom-right-radius: 0.25rem;
}

.bubble-system {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e5e7eb);
  color: var(--color-text);
  border-bottom-left-radius: 0.25rem;
}

.message-body {
  font-size: 0.875rem;
  white-space: pre-wrap;
  word-break: break-word;
}

.entity-link {
  font-size: 0.75rem;
  color: var(--color-primary, #3b82f6);
  text-decoration: underline;
  cursor: default;
}

.bubble-human .entity-link {
  color: rgba(255, 255, 255, 0.75);
}

.message-time {
  font-size: 0.7rem;
  opacity: 0.6;
  align-self: flex-end;
}

.message-input-area {
  display: flex;
  gap: 0.5rem;
  padding: 0.875rem 1.25rem;
  border-top: 1px solid var(--color-border, #e5e7eb);
  background: var(--color-surface, #fff);
}

.message-input {
  flex: 1;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  background: var(--color-background);
  color: var(--color-text);
  font-size: 0.875rem;
  resize: none;
  line-height: 1.4;
}

.btn-send {
  padding: 0.5rem 1.25rem;
  background: var(--color-primary, #3b82f6);
  color: white;
  border: none;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  align-self: flex-end;
}

.btn-send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.state-msg-sm {
  text-align: center;
  padding: 1.5rem;
  color: var(--color-text-secondary, #9ca3af);
  font-size: 0.875rem;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}

.modal-panel {
  background: var(--color-surface, #fff);
  border-radius: 0.75rem;
  padding: 1.5rem;
  width: 100%;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.modal-panel h3 {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.form-field label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--color-text-secondary, #6b7280);
}

.form-input {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  background: var(--color-surface, #fff);
  color: var(--color-text);
  font-size: 0.875rem;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
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
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 0.5rem 1rem;
  background: var(--color-surface, #fff);
  color: var(--color-text);
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
}
</style>
