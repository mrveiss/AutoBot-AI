# Transcriber Module — Plan 4: Frontend

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Vue 3 + TypeScript frontend — Projects list, Project detail with upload/progress, Transcript workspace (waveform, segments, AI panel, export), DocumentsView integration, i18n label keys.

**Architecture:** Three views under `TranscriberLayout.vue` with internal sidebar. All HTTP via `useApi()` from AutoBot's ApiClient — no raw fetch. All logging via `createLogger('Transcriber')`. Pinia store manages active project/recording/segments. WaveSurfer.js 7 wrapped in a composable. SSE progress via `useSseProgress` composable. Uses AutoBot design tokens throughout.

**Tech Stack:** Vue 3, TypeScript, Pinia, WaveSurfer.js 7, AutoBot useApi(), AutoBot design system, Vitest

**Prerequisite:** Plan 1 complete (frontend route scaffolding). Plans 2 and 3 complete (backend API).

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `autobot-frontend/src/stores/transcriber/useTranscriberStore.ts` | Pinia: projects, recordings, segments, speakers |
| Create | `autobot-frontend/src/composables/transcriber/useTranscriberApi.ts` | Typed API client wrappers |
| Create | `autobot-frontend/src/composables/transcriber/useSseProgress.ts` | SSE → reactive progress |
| Create | `autobot-frontend/src/composables/transcriber/useWaveform.ts` | WaveSurfer.js lifecycle |
| Replace | `autobot-frontend/src/views/transcriber/TranscriberLayout.vue` | Sidebar + router-outlet |
| Replace | `autobot-frontend/src/views/transcriber/ProjectsView.vue` | Project grid, create modal |
| Replace | `autobot-frontend/src/views/transcriber/ProjectDetailView.vue` | Recordings list, upload, SSE progress |
| Replace | `autobot-frontend/src/views/transcriber/TranscriptView.vue` | Waveform, segments, AI panel, export |
| Create | `autobot-frontend/src/components/transcriber/WaveformPlayer.vue` | WaveSurfer wrapper component |
| Create | `autobot-frontend/src/components/transcriber/SegmentTable.vue` | Inline-editable segment rows |
| Create | `autobot-frontend/src/components/transcriber/SpeakerLabel.vue` | Editable speaker chip |
| Create | `autobot-frontend/src/components/transcriber/AiAnalysisPanel.vue` | Slide-in AI panel with SSE |
| Create | `autobot-frontend/src/components/transcriber/ExportMenu.vue` | Format dropdown |
| Create | `autobot-frontend/src/components/transcriber/KbPushButton.vue` | Push to KB + status |
| Create | `autobot-frontend/src/components/transcriber/UploadModal.vue` | Drag-drop upload |
| Create | `autobot-frontend/src/components/transcriber/ProcessingProgress.vue` | SSE pipeline progress bar |
| Modify | `autobot-frontend/src/views/DocumentsView.vue` | Add TranscriberProjectsCard section |
| Modify | `autobot-frontend/src/i18n/` | Add transcriber label keys |
| Create | `autobot-frontend/src/__tests__/transcriber/useTranscriberApi.test.ts` | API composable tests |
| Create | `autobot-frontend/src/__tests__/transcriber/useSseProgress.test.ts` | SSE composable tests |

---

### Task 1: Types + API composable

**Files:**
- Create: `autobot-frontend/src/composables/transcriber/useTranscriberApi.ts`
- Create: `autobot-frontend/src/__tests__/transcriber/useTranscriberApi.test.ts`

- [ ] **Step 1: Write failing test**

```typescript
// autobot-frontend/src/__tests__/transcriber/useTranscriberApi.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPatch = vi.fn()
const mockDelete = vi.fn()

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({ get: mockGet, post: mockPost, patch: mockPatch, delete: mockDelete }),
}))

describe('useTranscriberApi', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('listProjects calls GET /api/transcriber/projects', async () => {
    mockGet.mockResolvedValue([])
    const api = useTranscriberApi()
    await api.listProjects()
    expect(mockGet).toHaveBeenCalledWith('/api/transcriber/projects')
  })

  it('createProject calls POST /api/transcriber/projects', async () => {
    mockPost.mockResolvedValue({ id: 1, name: 'P', description: '' })
    const api = useTranscriberApi()
    await api.createProject('P', '')
    expect(mockPost).toHaveBeenCalledWith('/api/transcriber/projects', { name: 'P', description: '' })
  })

  it('getTranscript calls GET /api/transcriber/recordings/:id/transcript', async () => {
    mockGet.mockResolvedValue({ recording: {}, speakers: [], segments: [] })
    const api = useTranscriberApi()
    await api.getTranscript(42)
    expect(mockGet).toHaveBeenCalledWith('/api/transcriber/recordings/42/transcript')
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-frontend
npm run test -- --run src/__tests__/transcriber/useTranscriberApi.test.ts
```
Expected: `Cannot find module '@/composables/transcriber/useTranscriberApi'`

- [ ] **Step 3: Define TypeScript interfaces + implement composable**

```typescript
// autobot-frontend/src/composables/transcriber/useTranscriberApi.ts
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { useApi } from '@/composables/useApi'

export interface Project {
  id: number
  name: string
  description: string
  created_at: string
  user_id: string
}

export interface Recording {
  id: number
  project_id: number
  filename: string
  duration: number | null
  status: 'pending' | 'processing' | 'complete' | 'error'
  speaker_count: number
  process_seconds: number | null
  engine_used: string | null
  language_detected: string | null
  uploaded_at: string
  failure_stage: string | null
  failure_reason: string | null
}

export interface Speaker {
  id: number
  recording_id: number
  label: string
  display_name: string
  language: string | null
}

export interface Segment {
  id: number
  recording_id: number
  speaker_id: number | null
  start_time: number
  end_time: number
  text: string
  original_text: string
  is_edited: boolean
  is_overlap: boolean
}

export interface TranscriptResponse {
  recording: Recording
  speakers: Speaker[]
  segments: Segment[]
}

export interface KbPushStatus {
  pushed: boolean
  pushed_at: string | null
  kb_collection_id: string | null
  pushed_by: string | null
}

export function useTranscriberApi() {
  const api = useApi()
  const base = '/api/transcriber'

  return {
    // Projects
    listProjects: () => api.get<Project[]>(`${base}/projects`),
    getProject: (id: number) => api.get<Project>(`${base}/projects/${id}`),
    createProject: (name: string, description: string) =>
      api.post<Project>(`${base}/projects`, { name, description }),
    updateProject: (id: number, name: string, description: string) =>
      api.patch<Project>(`${base}/projects/${id}`, { name, description }),
    deleteProject: (id: number) => api.delete(`${base}/projects/${id}`),

    // Recordings
    listRecordings: (projectId: number) =>
      api.get<Recording[]>(`${base}/projects/${projectId}/recordings`),
    getRecording: (id: number) => api.get<Recording>(`${base}/recordings/${id}`),
    deleteRecording: (id: number) => api.delete(`${base}/recordings/${id}`),
    uploadRecording: (projectId: number, file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api.post<Recording>(`${base}/projects/${projectId}/recordings`, form)
    },

    // Transcripts
    getTranscript: (recordingId: number) =>
      api.get<TranscriptResponse>(`${base}/recordings/${recordingId}/transcript`),
    updateSegment: (segmentId: number, text: string) =>
      api.patch<Segment>(`${base}/segments/${segmentId}`, { text }),
    updateSpeaker: (speakerId: number, displayName: string) =>
      api.patch<Speaker>(`${base}/speakers/${speakerId}`, { display_name: displayName }),
    createNote: (segmentId: number, content: string) =>
      api.post(`${base}/segments/${segmentId}/notes`, { content }),
    deleteNote: (noteId: number) => api.delete(`${base}/notes/${noteId}`),

    // Export
    exportRecording: (recordingId: number, format: 'docx' | 'pdf' | 'srt' | 'vtt', options = {}) =>
      fetch(`${base}/recordings/${recordingId}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format, ...options }),
      }),

    // AI
    aiAsk: (recordingId: number, action: string, customQuestion?: string) =>
      new EventSource(`${base}/recordings/${recordingId}/ai/ask?action=${action}${customQuestion ? `&q=${encodeURIComponent(customQuestion)}` : ''}`),

    // KB
    kbPush: (recordingId: number, collectionId: string) =>
      api.post(`${base}/recordings/${recordingId}/kb/push`, { collection_id: collectionId }),
    kbStatus: (recordingId: number) =>
      api.get<KbPushStatus>(`${base}/recordings/${recordingId}/kb/status`),
  }
}
```

- [ ] **Step 4: Run tests**

```bash
cd autobot-frontend
npm run test -- --run src/__tests__/transcriber/useTranscriberApi.test.ts
```
Expected: 3 PASSED

- [ ] **Step 5: Type-check**

```bash
cd autobot-frontend
npm run type-check
```
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
git add autobot-frontend/src/composables/transcriber/ \
        autobot-frontend/src/__tests__/transcriber/useTranscriberApi.test.ts
git commit -m "feat(transcriber/frontend): add typed API composable"
```

---

### Task 2: SSE progress composable + Pinia store

**Files:**
- Create: `autobot-frontend/src/composables/transcriber/useSseProgress.ts`
- Create: `autobot-frontend/src/stores/transcriber/useTranscriberStore.ts`
- Create: `autobot-frontend/src/__tests__/transcriber/useSseProgress.test.ts`

- [ ] **Step 1: Write failing test**

```typescript
// autobot-frontend/src/__tests__/transcriber/useSseProgress.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useSseProgress } from '@/composables/transcriber/useSseProgress'

describe('useSseProgress', () => {
  it('initialises with 0 progress and idle status', () => {
    const { percent, step, status } = useSseProgress(1)
    expect(percent.value).toBe(0)
    expect(step.value).toBe('')
    expect(status.value).toBe('idle')
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-frontend
npm run test -- --run src/__tests__/transcriber/useSseProgress.test.ts
```
Expected: `Cannot find module`

- [ ] **Step 3: Implement SSE composable**

```typescript
// autobot-frontend/src/composables/transcriber/useSseProgress.ts
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { ref, onUnmounted } from 'vue'
import { getBackendUrl } from '@/config/ssot-config'

export type ProgressStatus = 'idle' | 'running' | 'complete' | 'error'

export function useSseProgress(recordingId: number) {
  const percent = ref(0)
  const step = ref('')
  const status = ref<ProgressStatus>('idle')
  let source: EventSource | null = null

  function connect() {
    const url = `${getBackendUrl()}/api/transcriber/recordings/${recordingId}/progress`
    source = new EventSource(url)
    status.value = 'running'

    source.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        percent.value = data.percent ?? percent.value
        step.value = data.step ?? step.value
        if (data.percent === 100) {
          status.value = 'complete'
          source?.close()
        }
        if (data.error) {
          status.value = 'error'
          source?.close()
        }
      } catch {
        // non-JSON heartbeat — ignore
      }
    }
    source.onerror = () => {
      status.value = 'error'
      source?.close()
    }
  }

  function disconnect() {
    source?.close()
    source = null
  }

  onUnmounted(disconnect)
  return { percent, step, status, connect, disconnect }
}
```

- [ ] **Step 4: Implement Pinia store**

```typescript
// autobot-frontend/src/stores/transcriber/useTranscriberStore.ts
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Project, Recording, Segment, Speaker, TranscriptResponse } from '@/composables/transcriber/useTranscriberApi'

export const useTranscriberStore = defineStore('transcriber', () => {
  const projects = ref<Project[]>([])
  const activeProject = ref<Project | null>(null)
  const recordings = ref<Recording[]>([])
  const activeRecording = ref<Recording | null>(null)
  const speakers = ref<Speaker[]>([])
  const segments = ref<Segment[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  function setProjects(list: Project[]) { projects.value = list }
  function setActiveProject(p: Project | null) { activeProject.value = p }
  function setRecordings(list: Recording[]) { recordings.value = list }
  function setActiveRecording(r: Recording | null) { activeRecording.value = r }

  function setTranscript(t: TranscriptResponse) {
    activeRecording.value = t.recording
    speakers.value = t.speakers
    segments.value = t.segments
  }

  function updateSegmentText(segmentId: number, text: string) {
    const seg = segments.value.find(s => s.id === segmentId)
    if (seg) { seg.text = text; seg.is_edited = true }
  }

  function updateSpeakerName(speakerId: number, displayName: string) {
    const spk = speakers.value.find(s => s.id === speakerId)
    if (spk) spk.display_name = displayName
  }

  function updateRecordingStatus(recordingId: number, status: Recording['status']) {
    const rec = recordings.value.find(r => r.id === recordingId)
    if (rec) rec.status = status
  }

  function speakerName(speakerId: number | null): string {
    if (!speakerId) return 'Unknown'
    return speakers.value.find(s => s.id === speakerId)?.display_name ?? 'Unknown'
  }

  return {
    projects, activeProject, recordings, activeRecording,
    speakers, segments, loading, error,
    setProjects, setActiveProject, setRecordings, setActiveRecording,
    setTranscript, updateSegmentText, updateSpeakerName, updateRecordingStatus, speakerName,
  }
})
```

- [ ] **Step 5: Run tests**

```bash
cd autobot-frontend
npm run test -- --run src/__tests__/transcriber/useSseProgress.test.ts
```
Expected: 1 PASSED

- [ ] **Step 6: Commit**

```bash
git add autobot-frontend/src/composables/transcriber/useSseProgress.ts \
        autobot-frontend/src/stores/transcriber/ \
        autobot-frontend/src/__tests__/transcriber/useSseProgress.test.ts
git commit -m "feat(transcriber/frontend): add SSE progress composable and Pinia store"
```

---

### Task 3: WaveSurfer composable + WaveformPlayer component

**Files:**
- Create: `autobot-frontend/src/composables/transcriber/useWaveform.ts`
- Create: `autobot-frontend/src/components/transcriber/WaveformPlayer.vue`

- [ ] **Step 1: Implement WaveSurfer composable**

```typescript
// autobot-frontend/src/composables/transcriber/useWaveform.ts
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { ref, onUnmounted } from 'vue'
import type { Ref } from 'vue'

export function useWaveform(container: Ref<HTMLElement | null>) {
  const currentTime = ref(0)
  const duration = ref(0)
  const isPlaying = ref(false)
  let ws: import('wavesurfer.js').default | null = null

  async function init(audioUrl: string) {
    const WaveSurfer = (await import('wavesurfer.js')).default
    if (!container.value) return
    ws?.destroy()
    ws = WaveSurfer.create({
      container: container.value,
      waveColor: 'var(--color-primary-300, #93c5fd)',
      progressColor: 'var(--color-primary-600, #2563eb)',
      height: 64,
      normalize: true,
    })
    ws.on('timeupdate', (t: number) => { currentTime.value = t })
    ws.on('ready', () => { duration.value = ws!.getDuration() })
    ws.on('play', () => { isPlaying.value = true })
    ws.on('pause', () => { isPlaying.value = false })
    await ws.load(audioUrl)
  }

  function seekTo(seconds: number) {
    if (ws && duration.value > 0) ws.seekTo(seconds / duration.value)
  }

  function togglePlay() { ws?.playPause() }

  onUnmounted(() => { ws?.destroy(); ws = null })

  return { currentTime, duration, isPlaying, init, seekTo, togglePlay }
}
```

- [ ] **Step 2: Implement WaveformPlayer component**

```vue
<!-- autobot-frontend/src/components/transcriber/WaveformPlayer.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useWaveform } from '@/composables/transcriber/useWaveform'

const props = defineProps<{ audioUrl: string }>()
const emit = defineEmits<{ (e: 'seek', seconds: number): void }>()

const container = ref<HTMLElement | null>(null)
const { currentTime, duration, isPlaying, init, togglePlay } = useWaveform(container)

onMounted(() => init(props.audioUrl))
watch(() => props.audioUrl, (url) => init(url))

function fmt(s: number) {
  const m = Math.floor(s / 60), sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}
</script>

<template>
  <div class="waveform-player">
    <div ref="container" class="waveform-container" />
    <div class="waveform-controls">
      <button class="btn btn-icon" @click="togglePlay" :aria-label="isPlaying ? 'Pause' : 'Play'">
        <span v-if="isPlaying">⏸</span>
        <span v-else>▶</span>
      </button>
      <span class="waveform-time">{{ fmt(currentTime) }} / {{ fmt(duration) }}</span>
    </div>
  </div>
</template>
```

- [ ] **Step 3: Type-check**

```bash
cd autobot-frontend
npm run type-check
```
Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
git add autobot-frontend/src/composables/transcriber/useWaveform.ts \
        autobot-frontend/src/components/transcriber/WaveformPlayer.vue
git commit -m "feat(transcriber/frontend): add WaveSurfer composable and WaveformPlayer component"
```

---

### Task 4: Core components (SegmentTable, SpeakerLabel, AiAnalysisPanel)

**Files:**
- Create: `autobot-frontend/src/components/transcriber/SegmentTable.vue`
- Create: `autobot-frontend/src/components/transcriber/SpeakerLabel.vue`
- Create: `autobot-frontend/src/components/transcriber/AiAnalysisPanel.vue`

- [ ] **Step 1: SegmentTable**

```vue
<!-- autobot-frontend/src/components/transcriber/SegmentTable.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref } from 'vue'
import type { Segment, Speaker } from '@/composables/transcriber/useTranscriberApi'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import { useTranscriberStore } from '@/stores/transcriber/useTranscriberStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SegmentTable')
const props = defineProps<{ segments: Segment[]; speakers: Speaker[]; currentTime?: number }>()
const emit = defineEmits<{ (e: 'seek', seconds: number): void }>()

const api = useTranscriberApi()
const store = useTranscriberStore()
const editingId = ref<number | null>(null)
const editText = ref('')

function fmt(s: number) {
  const m = Math.floor(s / 60), sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function startEdit(seg: Segment) {
  editingId.value = seg.id
  editText.value = seg.text
}

async function saveEdit(seg: Segment) {
  if (editText.value === seg.text) { editingId.value = null; return }
  try {
    await api.updateSegment(seg.id, editText.value)
    store.updateSegmentText(seg.id, editText.value)
  } catch (err) {
    logger.error('Failed to save segment', err)
  }
  editingId.value = null
}

function speakerName(speakerId: number | null) {
  return store.speakerName(speakerId)
}

function isActive(seg: Segment) {
  const t = props.currentTime ?? 0
  return t >= seg.start_time && t < seg.end_time
}
</script>

<template>
  <div class="segment-table">
    <div
      v-for="seg in segments"
      :key="seg.id"
      class="segment-row"
      :class="{ 'segment-active': isActive(seg), 'segment-edited': seg.is_edited }"
    >
      <span class="segment-speaker">{{ speakerName(seg.speaker_id) }}</span>
      <button class="segment-time btn-link" @click="emit('seek', seg.start_time)">
        {{ fmt(seg.start_time) }}
      </button>
      <div class="segment-text-cell">
        <textarea
          v-if="editingId === seg.id"
          v-model="editText"
          class="segment-edit-input"
          rows="2"
          @blur="saveEdit(seg)"
          @keydown.enter.exact.prevent="saveEdit(seg)"
          @keydown.escape="editingId = null"
          autofocus
        />
        <span
          v-else
          class="segment-text"
          @dblclick="startEdit(seg)"
          :title="'Double-click to edit'"
        >{{ seg.text }}</span>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: SpeakerLabel**

```vue
<!-- autobot-frontend/src/components/transcriber/SpeakerLabel.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref } from 'vue'
import type { Speaker } from '@/composables/transcriber/useTranscriberApi'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import { useTranscriberStore } from '@/stores/transcriber/useTranscriberStore'

const props = defineProps<{ speaker: Speaker }>()
const api = useTranscriberApi()
const store = useTranscriberStore()
const editing = ref(false)
const name = ref(props.speaker.display_name)

async function save() {
  editing.value = false
  if (name.value === props.speaker.display_name) return
  await api.updateSpeaker(props.speaker.id, name.value)
  store.updateSpeakerName(props.speaker.id, name.value)
}
</script>

<template>
  <span class="speaker-label">
    <input
      v-if="editing"
      v-model="name"
      class="speaker-edit-input"
      @blur="save"
      @keydown.enter.prevent="save"
      @keydown.escape="editing = false"
      autofocus
    />
    <span v-else class="speaker-chip" @dblclick="editing = true" :title="'Double-click to rename'">
      {{ speaker.display_name }}
    </span>
  </span>
</template>
```

- [ ] **Step 3: AiAnalysisPanel**

```vue
<!-- autobot-frontend/src/components/transcriber/AiAnalysisPanel.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref } from 'vue'
import { getBackendUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AiAnalysisPanel')
const props = defineProps<{ recordingId: number; open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const streaming = ref(false)
const content = ref('')
const customQuestion = ref('')
const activeAction = ref('')

async function ask(action: string) {
  activeAction.value = action
  streaming.value = true
  content.value = ''
  const url = `${getBackendUrl()}/api/transcriber/recordings/${props.recordingId}/ai/ask`
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, custom_question: action === 'custom' ? customQuestion.value : null }),
    })
    const reader = resp.body?.getReader()
    const decoder = new TextDecoder()
    if (!reader) return
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const text = decoder.decode(value)
      for (const line of text.split('\n')) {
        if (!line.startsWith('data:')) continue
        const data = line.slice(5).trim()
        if (data === '[DONE]') { streaming.value = false; return }
        try {
          const parsed = JSON.parse(data)
          if (parsed.content) content.value += parsed.content
          if (parsed.error) { content.value = `Error: ${parsed.error}`; streaming.value = false; return }
        } catch { /* ignore */ }
      }
    }
  } catch (err) {
    logger.error('AI ask failed', err)
    content.value = 'Analysis failed. Please try again.'
  } finally {
    streaming.value = false
  }
}
</script>

<template>
  <Transition name="slide">
    <div v-if="open" class="ai-panel">
      <div class="ai-panel-header">
        <span>AI Analysis</span>
        <button class="btn-icon" @click="emit('close')">✕</button>
      </div>
      <div class="ai-panel-actions">
        <button class="btn btn-sm" @click="ask('summarize')" :disabled="streaming">Summarize</button>
        <button class="btn btn-sm" @click="ask('key_facts')" :disabled="streaming">Key Facts</button>
        <button class="btn btn-sm" @click="ask('protocol')" :disabled="streaming">Protocol</button>
      </div>
      <div class="ai-panel-custom">
        <input v-model="customQuestion" placeholder="Custom question…" class="input" />
        <button class="btn btn-sm" @click="ask('custom')" :disabled="streaming || !customQuestion.trim()">
          Ask
        </button>
      </div>
      <div class="ai-panel-content">
        <span v-if="streaming" class="ai-streaming-cursor">▌</span>
        <pre v-if="content" class="ai-result">{{ content }}</pre>
        <span v-else-if="!streaming" class="ai-empty">Choose an action above to analyze the transcript.</span>
      </div>
    </div>
  </Transition>
</template>
```

- [ ] **Step 4: Type-check**

```bash
cd autobot-frontend
npm run type-check
```
Expected: 0 errors

- [ ] **Step 5: Commit**

```bash
git add autobot-frontend/src/components/transcriber/
git commit -m "feat(transcriber/frontend): add SegmentTable, SpeakerLabel, AiAnalysisPanel components"
```

---

### Task 5: Export + KB components

**Files:**
- Create: `autobot-frontend/src/components/transcriber/ExportMenu.vue`
- Create: `autobot-frontend/src/components/transcriber/KbPushButton.vue`

- [ ] **Step 1: ExportMenu**

```vue
<!-- autobot-frontend/src/components/transcriber/ExportMenu.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref } from 'vue'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ExportMenu')
const props = defineProps<{ recordingId: number; filename: string }>()
const api = useTranscriberApi()
const open = ref(false)
const exporting = ref(false)

const FORMATS = [
  { key: 'docx', label: 'Word Document (.docx)' },
  { key: 'pdf', label: 'PDF Document (.pdf)' },
  { key: 'srt', label: 'Subtitles (.srt)' },
  { key: 'vtt', label: 'WebVTT (.vtt)' },
] as const

async function doExport(format: 'docx' | 'pdf' | 'srt' | 'vtt') {
  open.value = false
  exporting.value = true
  try {
    const resp = await api.exportRecording(props.recordingId, format)
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${props.filename}.${format}`
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    logger.error('Export failed', err)
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div class="export-menu" v-click-outside="() => (open = false)">
    <button class="btn btn-sm" @click="open = !open" :disabled="exporting">
      {{ exporting ? 'Exporting…' : 'Export ▾' }}
    </button>
    <div v-if="open" class="export-dropdown">
      <button
        v-for="fmt in FORMATS"
        :key="fmt.key"
        class="export-option"
        @click="doExport(fmt.key)"
      >{{ fmt.label }}</button>
    </div>
  </div>
</template>
```

- [ ] **Step 2: KbPushButton**

```vue
<!-- autobot-frontend/src/components/transcriber/KbPushButton.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import type { KbPushStatus } from '@/composables/transcriber/useTranscriberApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KbPushButton')
const props = defineProps<{ recordingId: number }>()
const api = useTranscriberApi()

const status = ref<KbPushStatus | null>(null)
const pushing = ref(false)
const collectionId = ref('default')
const showInput = ref(false)

onMounted(async () => {
  status.value = await api.kbStatus(props.recordingId)
})

async function push() {
  pushing.value = true
  try {
    await api.kbPush(props.recordingId, collectionId.value)
    status.value = await api.kbStatus(props.recordingId)
    showInput.value = false
  } catch (err) {
    logger.error('KB push failed', err)
  } finally {
    pushing.value = false
  }
}
</script>

<template>
  <div class="kb-push">
    <div v-if="status?.pushed" class="kb-pushed-badge">
      ✅ In Knowledge Base
      <button class="btn-link btn-xs" @click="showInput = true">Re-index</button>
    </div>
    <div v-else>
      <button class="btn btn-sm btn-outline" @click="showInput = !showInput">Push to KB</button>
    </div>
    <div v-if="showInput" class="kb-push-form">
      <input v-model="collectionId" placeholder="Collection ID" class="input input-sm" />
      <button class="btn btn-sm btn-primary" @click="push" :disabled="pushing">
        {{ pushing ? 'Pushing…' : 'Confirm' }}
      </button>
    </div>
  </div>
</template>
```

- [ ] **Step 3: Type-check**

```bash
cd autobot-frontend
npm run type-check
```
Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
git add autobot-frontend/src/components/transcriber/ExportMenu.vue \
        autobot-frontend/src/components/transcriber/KbPushButton.vue
git commit -m "feat(transcriber/frontend): add ExportMenu and KbPushButton components"
```

---

### Task 6: UploadModal + ProcessingProgress components

**Files:**
- Create: `autobot-frontend/src/components/transcriber/UploadModal.vue`
- Create: `autobot-frontend/src/components/transcriber/ProcessingProgress.vue`

- [ ] **Step 1: UploadModal**

```vue
<!-- autobot-frontend/src/components/transcriber/UploadModal.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref } from 'vue'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import type { Recording } from '@/composables/transcriber/useTranscriberApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('UploadModal')
const props = defineProps<{ projectId: number; open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'uploaded', r: Recording): void }>()
const api = useTranscriberApi()
const file = ref<File | null>(null)
const uploading = ref(false)
const dragover = ref(false)

const ACCEPT = '.wav,.mp3,.mp4,.m4a,.ogg,.flac,.webm'

function onDrop(e: DragEvent) {
  dragover.value = false
  const f = e.dataTransfer?.files[0]
  if (f) file.value = f
}

async function upload() {
  if (!file.value) return
  uploading.value = true
  try {
    const rec = await api.uploadRecording(props.projectId, file.value)
    emit('uploaded', rec)
    emit('close')
  } catch (err) {
    logger.error('Upload failed', err)
  } finally {
    uploading.value = false
    file.value = null
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="modal-overlay" @click.self="emit('close')">
      <div class="modal">
        <div class="modal-header">
          <h3>Upload Recording</h3>
          <button class="btn-icon" @click="emit('close')">✕</button>
        </div>
        <div
          class="drop-zone"
          :class="{ 'drop-zone-active': dragover }"
          @dragover.prevent="dragover = true"
          @dragleave="dragover = false"
          @drop.prevent="onDrop"
          @click="($refs.fileInput as HTMLInputElement).click()"
        >
          <input
            ref="fileInput"
            type="file"
            :accept="ACCEPT"
            class="hidden"
            @change="file = ($event.target as HTMLInputElement).files?.[0] ?? null"
          />
          <span v-if="file">{{ file.name }}</span>
          <span v-else>Drag audio file here or click to browse</span>
        </div>
        <div class="modal-footer">
          <button class="btn btn-primary" @click="upload" :disabled="!file || uploading">
            {{ uploading ? 'Uploading…' : 'Upload & Process' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
```

- [ ] **Step 2: ProcessingProgress**

```vue
<!-- autobot-frontend/src/components/transcriber/ProcessingProgress.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { onMounted } from 'vue'
import { useSseProgress } from '@/composables/transcriber/useSseProgress'

const props = defineProps<{ recordingId: number }>()
const emit = defineEmits<{ (e: 'complete'): void; (e: 'error'): void }>()

const { percent, step, status, connect } = useSseProgress(props.recordingId)

onMounted(() => {
  connect()
})

function onStatusChange() {
  if (status.value === 'complete') emit('complete')
  if (status.value === 'error') emit('error')
}
</script>

<template>
  <div class="processing-progress" @vue:updated="onStatusChange">
    <div class="progress-bar-track">
      <div class="progress-bar-fill" :style="{ width: `${percent}%` }" />
    </div>
    <span class="progress-step">{{ step || 'Processing…' }} {{ percent }}%</span>
  </div>
</template>
```

- [ ] **Step 3: Commit**

```bash
git add autobot-frontend/src/components/transcriber/UploadModal.vue \
        autobot-frontend/src/components/transcriber/ProcessingProgress.vue
git commit -m "feat(transcriber/frontend): add UploadModal and ProcessingProgress components"
```

---

### Task 7: Assemble the three main views

**Files:**
- Replace: `autobot-frontend/src/views/transcriber/TranscriberLayout.vue`
- Replace: `autobot-frontend/src/views/transcriber/ProjectsView.vue`
- Replace: `autobot-frontend/src/views/transcriber/ProjectDetailView.vue`
- Replace: `autobot-frontend/src/views/transcriber/TranscriptView.vue`

- [ ] **Step 1: TranscriberLayout.vue (sidebar)**

```vue
<!-- autobot-frontend/src/views/transcriber/TranscriberLayout.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { useRouter } from 'vue-router'
const router = useRouter()
</script>

<template>
  <div class="transcriber-layout">
    <aside class="transcriber-sidebar">
      <RouterLink :to="{ name: 'transcriber-projects' }" class="sidebar-link">
        Projects
      </RouterLink>
    </aside>
    <main class="transcriber-content">
      <RouterView />
    </main>
  </div>
</template>
```

- [ ] **Step 2: ProjectsView.vue**

```vue
<!-- autobot-frontend/src/views/transcriber/ProjectsView.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import { useTranscriberStore } from '@/stores/transcriber/useTranscriberStore'
import type { Project } from '@/composables/transcriber/useTranscriberApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ProjectsView')
const api = useTranscriberApi()
const store = useTranscriberStore()
const router = useRouter()

const showCreate = ref(false)
const newName = ref('')
const newDesc = ref('')
const creating = ref(false)

onMounted(async () => {
  try {
    store.setProjects(await api.listProjects())
  } catch (err) {
    logger.error('Failed to load projects', err)
  }
})

async function createProject() {
  if (!newName.value.trim()) return
  creating.value = true
  try {
    const p = await api.createProject(newName.value.trim(), newDesc.value.trim())
    store.setProjects([p, ...store.projects])
    showCreate.value = false
    newName.value = ''
    newDesc.value = ''
    router.push({ name: 'transcriber-project-detail', params: { projectId: p.id } })
  } catch (err) {
    logger.error('Failed to create project', err)
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="projects-view">
    <div class="projects-header">
      <h1>Projects</h1>
      <button class="btn btn-primary" @click="showCreate = true">New Project</button>
    </div>

    <div v-if="showCreate" class="create-project-form card">
      <input v-model="newName" placeholder="Project name" class="input" />
      <input v-model="newDesc" placeholder="Description (optional)" class="input" />
      <div class="form-actions">
        <button class="btn btn-primary" @click="createProject" :disabled="creating || !newName.trim()">
          Create
        </button>
        <button class="btn btn-ghost" @click="showCreate = false">Cancel</button>
      </div>
    </div>

    <div class="projects-grid">
      <RouterLink
        v-for="project in store.projects"
        :key="project.id"
        :to="{ name: 'transcriber-project-detail', params: { projectId: project.id } }"
        class="project-card card"
      >
        <h3>{{ project.name }}</h3>
        <p v-if="project.description" class="text-muted">{{ project.description }}</p>
        <time class="text-xs text-muted">{{ new Date(project.created_at).toLocaleDateString() }}</time>
      </RouterLink>
    </div>

    <p v-if="store.projects.length === 0" class="empty-state">
      No projects yet. Create your first project to get started.
    </p>
  </div>
</template>
```

- [ ] **Step 3: ProjectDetailView.vue**

```vue
<!-- autobot-frontend/src/views/transcriber/ProjectDetailView.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import { useTranscriberStore } from '@/stores/transcriber/useTranscriberStore'
import type { Recording } from '@/composables/transcriber/useTranscriberApi'
import UploadModal from '@/components/transcriber/UploadModal.vue'
import ProcessingProgress from '@/components/transcriber/ProcessingProgress.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ProjectDetailView')
const route = useRoute()
const router = useRouter()
const api = useTranscriberApi()
const store = useTranscriberStore()

const projectId = Number(route.params.projectId)
const showUpload = ref(false)
const processingIds = ref<Set<number>>(new Set())

onMounted(async () => {
  try {
    const [project, recordings] = await Promise.all([
      api.getProject(projectId),
      api.listRecordings(projectId),
    ])
    store.setActiveProject(project)
    store.setRecordings(recordings)
    recordings.filter(r => r.status === 'processing' || r.status === 'pending')
      .forEach(r => processingIds.value.add(r.id))
  } catch (err) {
    logger.error('Failed to load project', err)
  }
})

function onUploaded(rec: Recording) {
  store.setRecordings([rec, ...store.recordings])
  processingIds.value.add(rec.id)
}

function onProcessingComplete(recId: number) {
  processingIds.value.delete(recId)
  api.getRecording(recId).then(r => store.updateRecordingStatus(r.id, r.status))
}

const STATUS_LABEL: Record<string, string> = {
  pending: 'Queued',
  processing: 'Processing',
  complete: 'Ready',
  error: 'Failed',
}
</script>

<template>
  <div class="project-detail-view">
    <div class="detail-header">
      <RouterLink :to="{ name: 'transcriber-projects' }" class="btn-link">← Projects</RouterLink>
      <h2>{{ store.activeProject?.name }}</h2>
      <button class="btn btn-primary" @click="showUpload = true">Upload Recording</button>
    </div>

    <UploadModal
      :project-id="projectId"
      :open="showUpload"
      @close="showUpload = false"
      @uploaded="onUploaded"
    />

    <div class="recordings-list">
      <div v-for="rec in store.recordings" :key="rec.id" class="recording-row card">
        <div class="recording-info">
          <span class="recording-name">{{ rec.filename }}</span>
          <span class="recording-status" :class="`status-${rec.status}`">
            {{ STATUS_LABEL[rec.status] }}
          </span>
          <span v-if="rec.language_detected" class="recording-lang">{{ rec.language_detected }}</span>
          <span v-if="rec.speaker_count" class="recording-speakers">{{ rec.speaker_count }} speakers</span>
        </div>
        <ProcessingProgress
          v-if="processingIds.has(rec.id)"
          :recording-id="rec.id"
          @complete="onProcessingComplete(rec.id)"
          @error="onProcessingComplete(rec.id)"
        />
        <RouterLink
          v-if="rec.status === 'complete'"
          :to="{ name: 'transcriber-transcript', params: { projectId, recordingId: rec.id } }"
          class="btn btn-sm"
        >Open Transcript</RouterLink>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 4: TranscriptView.vue**

```vue
<!-- autobot-frontend/src/views/transcriber/TranscriptView.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import { useTranscriberStore } from '@/stores/transcriber/useTranscriberStore'
import WaveformPlayer from '@/components/transcriber/WaveformPlayer.vue'
import SegmentTable from '@/components/transcriber/SegmentTable.vue'
import AiAnalysisPanel from '@/components/transcriber/AiAnalysisPanel.vue'
import ExportMenu from '@/components/transcriber/ExportMenu.vue'
import KbPushButton from '@/components/transcriber/KbPushButton.vue'
import { getBackendUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('TranscriptView')
const route = useRoute()
const api = useTranscriberApi()
const store = useTranscriberStore()

const recordingId = Number(route.params.recordingId)
const aiOpen = ref(false)
const currentTime = ref(0)

onMounted(async () => {
  try {
    const transcript = await api.getTranscript(recordingId)
    store.setTranscript(transcript)
  } catch (err) {
    logger.error('Failed to load transcript', err)
  }
})

function audioUrl() {
  return `${getBackendUrl()}/api/transcriber/recordings/${recordingId}/audio`
}
</script>

<template>
  <div class="transcript-view">
    <div class="transcript-toolbar">
      <RouterLink
        :to="{ name: 'transcriber-project-detail', params: { projectId: route.params.projectId } }"
        class="btn-link"
      >← Project</RouterLink>
      <h2 class="transcript-title">{{ store.activeRecording?.filename }}</h2>
      <div class="transcript-actions">
        <KbPushButton :recording-id="recordingId" />
        <ExportMenu
          :recording-id="recordingId"
          :filename="store.activeRecording?.filename ?? 'transcript'"
        />
        <button class="btn btn-sm btn-outline" @click="aiOpen = !aiOpen">AI Analysis</button>
      </div>
    </div>

    <WaveformPlayer :audio-url="audioUrl()" @seek="currentTime = $event" />

    <div class="transcript-body">
      <SegmentTable
        :segments="store.segments"
        :speakers="store.speakers"
        :current-time="currentTime"
        @seek="currentTime = $event"
      />
    </div>

    <AiAnalysisPanel
      :recording-id="recordingId"
      :open="aiOpen"
      @close="aiOpen = false"
    />
  </div>
</template>
```

- [ ] **Step 5: Type-check**

```bash
cd autobot-frontend
npm run type-check
```
Expected: 0 errors

- [ ] **Step 6: Run all frontend tests**

```bash
cd autobot-frontend
npm run test -- --run
```
Expected: All PASSED, 0 failed

- [ ] **Step 7: Commit**

```bash
git add autobot-frontend/src/views/transcriber/
git commit -m "feat(transcriber/frontend): assemble ProjectsView, ProjectDetailView, TranscriptView"
```

---

### Task 8: DocumentsView integration + i18n

**Files:**
- Modify: `autobot-frontend/src/views/DocumentsView.vue`
- Modify or create: i18n locale file for `nav.transcriber` key

- [ ] **Step 1: Add TranscriberProjectsCard to DocumentsView**

In [autobot-frontend/src/views/DocumentsView.vue](autobot-frontend/src/views/DocumentsView.vue), find the main content section and add before the existing content:

```vue
<script setup lang="ts">
// Add at top of existing script setup:
import { ref, onMounted } from 'vue'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import type { Project } from '@/composables/transcriber/useTranscriberApi'
const transcriberProjects = ref<Project[]>([])
onMounted(async () => {
  try {
    const api = useTranscriberApi()
    transcriberProjects.value = (await api.listProjects()).slice(0, 4)
  } catch { /* transcriber may be disabled */ }
})
</script>
```

In the template, add a section (after existing content, before closing):

```vue
<section v-if="transcriberProjects.length" class="documents-section">
  <div class="section-header">
    <h3>Transcriber Projects</h3>
    <RouterLink :to="{ name: 'transcriber-projects' }" class="btn-link btn-sm">View all</RouterLink>
  </div>
  <div class="projects-mini-grid">
    <RouterLink
      v-for="p in transcriberProjects"
      :key="p.id"
      :to="{ name: 'transcriber-project-detail', params: { projectId: p.id } }"
      class="mini-card"
    >
      🎙 {{ p.name }}
    </RouterLink>
  </div>
</section>
```

- [ ] **Step 2: Add i18n key**

Find the English locale file (typically `src/i18n/en.ts` or `src/i18n/locales/en.json`) and add under the `nav` section:

```json
"transcriber": "Transcriber"
```

- [ ] **Step 3: Type-check**

```bash
cd autobot-frontend
npm run type-check
```
Expected: 0 errors

- [ ] **Step 4: Run nav-items coverage test**

```bash
cd autobot-frontend
npm run test -- --run src/__tests__/nav-items-coverage.test.ts
```
Expected: PASS

- [ ] **Step 5: Final full test run**

```bash
cd autobot-frontend
npm run test -- --run
```
Expected: All PASSED

- [ ] **Step 6: Final commit**

```bash
git add autobot-frontend/src/views/DocumentsView.vue autobot-frontend/src/i18n/
git commit -m "feat(transcriber/frontend): integrate into DocumentsView and add i18n key"
git tag transcriber-plan4-complete
```

---

### Task 9: End-to-end smoke test

- [ ] **Step 1: Start AutoBot backend with transcriber enabled**

```bash
TRANSCRIBER_ENABLED=true uvicorn app_factory:create_app --factory --host 0.0.0.0 --port 8001 --reload
```
Expected: Log line `Transcriber extension started` and `Registered speech provider 'late' for lang='lv'`

- [ ] **Step 2: Verify routes are mounted**

```bash
curl http://localhost:8001/api/transcriber/projects
```
Expected: `[]` (empty list, 200 OK)

- [ ] **Step 3: Start frontend dev server**

```bash
cd autobot-frontend
VITE_FEATURE_TRANSCRIBER=true npm run dev
```

- [ ] **Step 4: Manual golden path test**

1. Navigate to `/transcriber`
2. Create a new project — should appear in the grid
3. Open project — should see upload button
4. Upload a small WAV file — should see ProcessingProgress bar animate
5. After processing completes — "Open Transcript" button appears
6. Open transcript — waveform loads, segments visible, speaker names editable
7. Double-click a segment — inline edit works, blur saves
8. Click "AI Analysis" — panel slides in, "Summarize" fires SSE stream
9. Click "Export ▾" → choose SRT — file downloads
10. Navigate to `/documents` — transcriber projects card visible

---

**Plan 4 complete.** Full Vue 3 frontend assembled and wired end-to-end. All four plans together deliver the complete Transcriber module.
