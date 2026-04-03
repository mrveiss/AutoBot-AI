# Voice Side Panel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a side panel alternative to the voice conversation overlay, with a user preference toggle in the profile modal.

**Architecture:** New `VoiceConversationPanel.vue` component (~280px right side panel) reuses `useVoiceConversation` composable. `usePreferences.ts` gains a `voiceDisplayMode` preference. `ChatInterface.vue` branches on the preference to show overlay or panel (mutually exclusive with file panel).

**Tech Stack:** Vue 3 + TypeScript, existing composables (`useVoiceConversation`, `usePreferences`), localStorage persistence.

**Design doc:** `docs/plans/2026-03-01-voice-sidepanel-design.md`

---

### Task 1: Add `voiceDisplayMode` preference to `usePreferences.ts`

**Files:**
- Modify: `autobot-frontend/src/composables/usePreferences.ts`

**Step 1: Add the type and state**

Add the type export, update the interface, default, module-level ref, and load/save logic:

```typescript
// After line 18 (after LayoutDensity type)
export type VoiceDisplayMode = 'modal' | 'sidepanel'

// Update UserPreferences interface (line 20-24) to include:
//   voiceDisplayMode: VoiceDisplayMode

// Update DEFAULT_PREFERENCES (line 27-31) to include:
//   voiceDisplayMode: 'modal'

// Add module-level ref after line 36:
// const voiceDisplayMode = ref<VoiceDisplayMode>('modal')

// Update loadPreferences (line 48-51) to load voiceDisplayMode
// Update savePreferences (line 71-75) to save voiceDisplayMode
```

Specifically, edit `usePreferences.ts`:

After line 18 (`export type LayoutDensity = ...`), add:
```typescript
export type VoiceDisplayMode = 'modal' | 'sidepanel'
```

Update interface (lines 20-24):
```typescript
export interface UserPreferences {
  fontSize: FontSize
  accentColor: AccentColor
  layoutDensity: LayoutDensity
  voiceDisplayMode: VoiceDisplayMode
}
```

Update defaults (lines 27-31):
```typescript
const DEFAULT_PREFERENCES: UserPreferences = {
  fontSize: 'medium',
  accentColor: 'teal',
  layoutDensity: 'comfortable',
  voiceDisplayMode: 'modal'
}
```

Add module-level ref after line 36:
```typescript
const voiceDisplayMode = ref<VoiceDisplayMode>('modal')
```

In `loadPreferences()`, add after line 51:
```typescript
voiceDisplayMode.value = parsed.voiceDisplayMode || DEFAULT_PREFERENCES.voiceDisplayMode
```

In `savePreferences()`, update the preferences object (lines 71-75):
```typescript
const preferences: UserPreferences = {
  fontSize: fontSize.value,
  accentColor: accentColor.value,
  layoutDensity: layoutDensity.value,
  voiceDisplayMode: voiceDisplayMode.value
}
```

**Step 2: Add watcher and setter**

In `usePreferences()` function body, add a watcher after the layoutDensity watcher (after line 136):
```typescript
watch(voiceDisplayMode, () => {
  savePreferences()
})
```

Add setter function after `setLayoutDensity` (after line 157):
```typescript
function setVoiceDisplayMode(mode: VoiceDisplayMode): void {
  voiceDisplayMode.value = mode
}
```

Update `resetPreferences()` (line 162-166) to include:
```typescript
voiceDisplayMode.value = DEFAULT_PREFERENCES.voiceDisplayMode
```

Update the return object (lines 169-180) to include:
```typescript
voiceDisplayMode,
setVoiceDisplayMode,
```

**Step 3: Verify**

Run: `cd /home/kali/Desktop/AutoBot/autobot-frontend && npx vue-tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors related to usePreferences

**Step 4: Commit**

```bash
git add autobot-frontend/src/composables/usePreferences.ts
git commit -m "feat(voice): add voiceDisplayMode preference to usePreferences"
```

---

### Task 2: Add voice display mode toggle to `ProfileModal.vue`

**Files:**
- Modify: `autobot-frontend/src/components/profile/ProfileModal.vue`

**Step 1: Import usePreferences**

Add import after line 168:
```typescript
import { usePreferences } from '@/composables/usePreferences'
```

Add in script setup after line 178:
```typescript
const { voiceDisplayMode, setVoiceDisplayMode } = usePreferences()
```

**Step 2: Add the UI toggle**

Insert a new pref-group inside the "Interface" section (after line 93, after the animations toggle-item):

```html
          <!-- Voice Display Mode -->
          <div class="pref-group">
            <label class="pref-label">Voice Chat Display</label>
            <div class="option-row">
              <button
                @click="setVoiceDisplayMode('modal')"
                class="option-btn"
                :class="{ active: voiceDisplayMode === 'modal' }"
                type="button"
              >
                <i class="fas fa-expand-alt mr-1"></i>
                Full-screen
              </button>
              <button
                @click="setVoiceDisplayMode('sidepanel')"
                class="option-btn"
                :class="{ active: voiceDisplayMode === 'sidepanel' }"
                type="button"
              >
                <i class="fas fa-columns mr-1"></i>
                Side panel
              </button>
            </div>
          </div>
```

**Step 3: Verify**

Run: `cd /home/kali/Desktop/AutoBot/autobot-frontend && npx vue-tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors related to ProfileModal

**Step 4: Commit**

```bash
git add autobot-frontend/src/components/profile/ProfileModal.vue
git commit -m "feat(voice): add voice display mode toggle to ProfileModal"
```

---

### Task 3: Create `VoiceConversationPanel.vue`

**Files:**
- Create: `autobot-frontend/src/components/chat/VoiceConversationPanel.vue`

**Step 1: Write the component**

Create the file with this content:

```vue
<template>
  <div class="voice-panel h-full flex flex-col bg-autobot-bg-card border-l border-autobot-border">
    <!-- Header -->
    <div class="flex items-center justify-between p-3 border-b border-autobot-border flex-shrink-0">
      <div class="flex items-center gap-2">
        <div class="voice-panel__icon">
          <i class="fas fa-headset"></i>
        </div>
        <div>
          <h3 class="text-sm font-semibold text-autobot-text-primary">Voice Chat</h3>
          <p class="text-xs text-autobot-text-muted">
            {{ voiceConversation.stateLabel.value }}
          </p>
        </div>
      </div>
      <div class="flex items-center gap-1">
        <!-- Mode Selector -->
        <select
          :value="voiceConversation.mode.value"
          @change="handleModeChange"
          class="voice-panel__mode-select"
          aria-label="Conversation mode"
        >
          <option value="walkie-talkie">Walkie-talkie</option>
          <option value="hands-free">Hands-free</option>
          <option value="full-duplex">Full-duplex</option>
        </select>

        <!-- WS indicator (full-duplex) -->
        <div
          v-if="voiceConversation.mode.value === 'full-duplex'"
          class="voice-panel__ws-dot"
          :class="{ 'voice-panel__ws-dot--connected': voiceConversation.wsConnected.value }"
          :title="voiceConversation.wsConnected.value ? 'Connected' : 'Disconnected'"
        ></div>

        <!-- Close -->
        <button @click="close" class="action-btn" title="Close voice panel">
          <i class="fas fa-times text-xs"></i>
        </button>
      </div>
    </div>

    <!-- State + Transcript area -->
    <div class="flex-1 flex flex-col items-center justify-center p-4 gap-4 overflow-y-auto">
      <!-- State indicator -->
      <div class="voice-panel__state-ring" :class="stateClass">
        <i :class="stateIcon" class="text-lg"></i>
      </div>

      <p class="text-sm font-medium" :class="stateTextClass">
        {{ voiceConversation.stateLabel.value }}
      </p>

      <!-- Live transcript -->
      <div
        v-if="voiceConversation.currentTranscript.value"
        class="voice-panel__transcript"
      >
        <i class="fas fa-ellipsis-h animate-pulse mr-1 text-xs"></i>
        {{ voiceConversation.currentTranscript.value }}
      </div>
    </div>

    <!-- Error banner -->
    <div
      v-if="voiceConversation.errorMessage.value"
      class="voice-panel__error"
    >
      <i class="fas fa-exclamation-triangle mr-1"></i>
      {{ voiceConversation.errorMessage.value }}
    </div>

    <!-- Insecure context warning -->
    <div
      v-if="showInsecureContextWarning"
      class="voice-panel__cert-warning"
    >
      <p class="font-semibold text-xs">
        <i class="fas fa-lock-open mr-1"></i>Mic blocked
      </p>
      <p class="text-xs opacity-80">
        Trusted HTTPS cert required. Use walkie-talkie mode as fallback.
      </p>
    </div>

    <!-- Hands-free controls -->
    <div
      v-if="voiceConversation.mode.value === 'hands-free'"
      class="voice-panel__hf-controls"
    >
      <div class="voice-panel__amplitude">
        <div
          class="voice-panel__amplitude-bar"
          :style="{ width: `${voiceConversation.audioLevel.value * 100}%` }"
        ></div>
      </div>
      <div class="flex items-center gap-2">
        <label class="text-xs text-autobot-text-muted whitespace-nowrap">Silence</label>
        <input
          type="range"
          min="500"
          max="3000"
          step="100"
          :value="voiceConversation.silenceThreshold.value"
          @input="voiceConversation.silenceThreshold.value = Number(($event.target as HTMLInputElement).value)"
          class="voice-panel__slider flex-1"
        />
        <span class="text-xs text-autobot-text-secondary tabular-nums min-w-[2rem] text-right">
          {{ (voiceConversation.silenceThreshold.value / 1000).toFixed(1) }}s
        </span>
      </div>
    </div>

    <!-- Mic control -->
    <div class="voice-panel__controls">
      <div class="voice-panel__mic-container">
        <div
          v-if="voiceConversation.state.value === 'listening'"
          class="voice-panel__pulse voice-panel__pulse--1"
        ></div>
        <div
          v-if="voiceConversation.state.value === 'listening'"
          class="voice-panel__pulse voice-panel__pulse--2"
        ></div>

        <button
          @click="handleMicClick"
          class="voice-panel__mic-btn"
          :class="{
            'voice-panel__mic-btn--listening': voiceConversation.state.value === 'listening',
            'voice-panel__mic-btn--processing': voiceConversation.state.value === 'processing',
            'voice-panel__mic-btn--speaking': voiceConversation.state.value === 'speaking',
          }"
          :disabled="
            voiceConversation.state.value === 'processing' ||
            (voiceConversation.state.value === 'speaking' && !isFullDuplex)
          "
          :aria-label="voiceConversation.stateLabel.value"
        >
          <i :class="micIcon" class="text-base"></i>
        </button>
      </div>

      <p class="text-xs text-autobot-text-muted text-center mt-1">
        {{ micHint }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount } from 'vue'
import { useVoiceConversation } from '@/composables/useVoiceConversation'

const emit = defineEmits<{
  (e: 'close'): void
}>()

const voiceConversation = useVoiceConversation()

const isFullDuplex = computed(
  () => voiceConversation.mode.value === 'full-duplex',
)
const isHandsFree = computed(
  () => voiceConversation.mode.value === 'hands-free',
)
const isAutoMode = computed(
  () => isFullDuplex.value || isHandsFree.value,
)

const showInsecureContextWarning = computed(
  () => isAutoMode.value && !voiceConversation.micAccessAvailable.value,
)

const stateClass = computed(() => ({
  'voice-panel__state-ring--idle': voiceConversation.state.value === 'idle',
  'voice-panel__state-ring--listening': voiceConversation.state.value === 'listening',
  'voice-panel__state-ring--processing': voiceConversation.state.value === 'processing',
  'voice-panel__state-ring--speaking': voiceConversation.state.value === 'speaking',
}))

const stateTextClass = computed(() => {
  switch (voiceConversation.state.value) {
    case 'listening': return 'text-red-400'
    case 'processing': return 'text-blue-400'
    case 'speaking': return 'text-emerald-400'
    default: return 'text-autobot-text-secondary'
  }
})

const stateIcon = computed(() => {
  switch (voiceConversation.state.value) {
    case 'listening': return 'fas fa-microphone'
    case 'processing': return 'fas fa-spinner fa-spin'
    case 'speaking': return 'fas fa-volume-up'
    default: return 'fas fa-microphone-slash'
  }
})

const micIcon = computed(() => {
  switch (voiceConversation.state.value) {
    case 'listening':
      return isAutoMode.value ? 'fas fa-microphone' : 'fas fa-stop'
    case 'processing': return 'fas fa-spinner fa-spin'
    case 'speaking':
      return isFullDuplex.value ? 'fas fa-hand-paper' : 'fas fa-volume-up'
    default: return 'fas fa-microphone'
  }
})

const micHint = computed(() => {
  switch (voiceConversation.state.value) {
    case 'listening':
      return isAutoMode.value
        ? 'Auto-detects when you stop'
        : 'Tap to stop'
    case 'processing':
      return isHandsFree.value ? 'Transcribing...' : 'Processing...'
    case 'speaking':
      return isFullDuplex.value
        ? 'Tap or speak to interrupt'
        : 'Responding...'
    default:
      return isAutoMode.value
        ? 'Listening starts automatically'
        : 'Tap to speak'
  }
})

function handleMicClick(): void {
  voiceConversation.toggleListening()
}

function handleModeChange(event: Event): void {
  const target = event.target as HTMLSelectElement
  voiceConversation.setMode(
    target.value as 'walkie-talkie' | 'hands-free' | 'full-duplex',
  )
}

function close(): void {
  voiceConversation.deactivate()
  emit('close')
}

onBeforeUnmount(() => {
  voiceConversation.cleanup()
})
</script>

<style scoped>
.voice-panel {
  width: 280px;
  max-width: 280px;
  min-width: 280px;
}

.voice-panel__icon {
  width: 1.75rem;
  height: 1.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.375rem;
  background: rgba(37, 99, 235, 0.15);
  color: #60a5fa;
  font-size: 0.75rem;
}

.voice-panel__mode-select {
  appearance: none;
  padding: 0.2rem 1.5rem 0.2rem 0.4rem;
  border-radius: 0.25rem;
  border: 1px solid var(--border-subtle, rgba(148, 163, 184, 0.15));
  background: var(--bg-tertiary, #1e293b)
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2394a3b8' d='M3 4.5L6 8l3-3.5H3z'/%3E%3C/svg%3E")
    no-repeat right 0.35rem center;
  color: var(--text-secondary, #94a3b8);
  font-size: 0.6875rem;
  cursor: pointer;
}

.voice-panel__ws-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(239, 68, 68, 0.6);
  transition: background 0.2s;
}

.voice-panel__ws-dot--connected {
  background: rgba(34, 197, 94, 0.8);
}

.action-btn {
  @apply w-6 h-6 flex items-center justify-center rounded transition-colors text-autobot-text-muted hover:text-autobot-text-secondary hover:bg-autobot-bg-secondary;
}

/* State indicator ring */
.voice-panel__state-ring {
  width: 4rem;
  height: 4rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 2px solid var(--border-subtle, rgba(148, 163, 184, 0.15));
  color: var(--text-muted, #64748b);
  transition: all 0.3s ease;
}

.voice-panel__state-ring--listening {
  border-color: rgba(239, 68, 68, 0.5);
  color: #f87171;
  box-shadow: 0 0 20px -4px rgba(239, 68, 68, 0.25);
  animation: ring-glow-red 1.5s ease-in-out infinite alternate;
}

.voice-panel__state-ring--processing {
  border-color: rgba(37, 99, 235, 0.3);
  color: #93c5fd;
}

.voice-panel__state-ring--speaking {
  border-color: rgba(16, 185, 129, 0.4);
  color: #34d399;
  box-shadow: 0 0 20px -4px rgba(16, 185, 129, 0.2);
  animation: ring-glow-green 1s ease-in-out infinite alternate;
}

@keyframes ring-glow-red {
  0% { box-shadow: 0 0 16px -4px rgba(239, 68, 68, 0.15); }
  100% { box-shadow: 0 0 28px -4px rgba(239, 68, 68, 0.35); }
}

@keyframes ring-glow-green {
  0% { box-shadow: 0 0 16px -4px rgba(16, 185, 129, 0.1); }
  100% { box-shadow: 0 0 28px -4px rgba(16, 185, 129, 0.3); }
}

/* Live transcript */
.voice-panel__transcript {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  background: rgba(37, 99, 235, 0.06);
  border: 1px dashed rgba(37, 99, 235, 0.2);
  color: #93c5fd;
  font-size: 0.75rem;
  font-style: italic;
  word-break: break-word;
}

/* Error */
.voice-panel__error {
  margin: 0 0.75rem;
  padding: 0.375rem 0.5rem;
  border-radius: 0.375rem;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: #fca5a5;
  font-size: 0.75rem;
}

/* Cert warning */
.voice-panel__cert-warning {
  margin: 0 0.75rem;
  padding: 0.5rem 0.625rem;
  border-radius: 0.375rem;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.25);
  color: #fcd34d;
  font-size: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

/* Hands-free controls */
.voice-panel__hf-controls {
  padding: 0.5rem 0.75rem 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.voice-panel__amplitude {
  height: 3px;
  border-radius: 1.5px;
  background: rgba(148, 163, 184, 0.1);
  overflow: hidden;
}

.voice-panel__amplitude-bar {
  height: 100%;
  border-radius: 1.5px;
  background: linear-gradient(90deg, #60a5fa, #818cf8);
  transition: width 0.1s ease-out;
  min-width: 0;
}

.voice-panel__slider {
  height: 3px;
  appearance: none;
  background: rgba(148, 163, 184, 0.15);
  border-radius: 1.5px;
  outline: none;
  cursor: pointer;
}

.voice-panel__slider::-webkit-slider-thumb {
  appearance: none;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #60a5fa;
  border: 2px solid var(--bg-card, #0f172a);
  cursor: pointer;
}

.voice-panel__slider::-moz-range-thumb {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #60a5fa;
  border: 2px solid var(--bg-card, #0f172a);
  cursor: pointer;
}

/* Mic controls */
.voice-panel__controls {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 1rem 0.75rem 1.25rem;
  border-top: 1px solid var(--border-subtle, rgba(148, 163, 184, 0.08));
}

.voice-panel__mic-container {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
}

/* Pulse rings */
.voice-panel__pulse {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid rgba(37, 99, 235, 0.3);
  animation: panel-pulse 2s ease-out infinite;
}

.voice-panel__pulse--2 {
  animation-delay: 0.6s;
}

@keyframes panel-pulse {
  0% { transform: scale(0.7); opacity: 0.8; }
  100% { transform: scale(1.3); opacity: 0; }
}

/* Mic button */
.voice-panel__mic-btn {
  position: relative;
  z-index: 1;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid rgba(37, 99, 235, 0.3);
  background: rgba(37, 99, 235, 0.1);
  color: #60a5fa;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 0 16px -4px rgba(37, 99, 235, 0.2);
}

.voice-panel__mic-btn:hover:not(:disabled) {
  background: rgba(37, 99, 235, 0.2);
  border-color: rgba(37, 99, 235, 0.5);
  transform: scale(1.05);
}

.voice-panel__mic-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.voice-panel__mic-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.voice-panel__mic-btn--listening {
  background: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.5);
  color: #f87171;
  box-shadow: 0 0 24px -4px rgba(239, 68, 68, 0.3);
  animation: mic-glow-red 1.5s ease-in-out infinite alternate;
}

@keyframes mic-glow-red {
  0% { box-shadow: 0 0 16px -4px rgba(239, 68, 68, 0.2); }
  100% { box-shadow: 0 0 28px -4px rgba(239, 68, 68, 0.4); }
}

.voice-panel__mic-btn--processing {
  background: rgba(37, 99, 235, 0.08);
  border-color: rgba(37, 99, 235, 0.2);
  color: #93c5fd;
}

.voice-panel__mic-btn--speaking {
  background: rgba(16, 185, 129, 0.12);
  border-color: rgba(16, 185, 129, 0.4);
  color: #34d399;
  box-shadow: 0 0 24px -4px rgba(16, 185, 129, 0.25);
  animation: mic-glow-green 1s ease-in-out infinite alternate;
}

@keyframes mic-glow-green {
  0% { box-shadow: 0 0 16px -4px rgba(16, 185, 129, 0.15); }
  100% { box-shadow: 0 0 28px -4px rgba(16, 185, 129, 0.35); }
}

/* Scrollbar */
.overflow-y-auto::-webkit-scrollbar {
  width: 4px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: transparent;
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: var(--border-default, rgba(148, 163, 184, 0.15));
  border-radius: 2px;
}
</style>
```

**Step 2: Verify**

Run: `cd /home/kali/Desktop/AutoBot/autobot-frontend && npx vue-tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors related to VoiceConversationPanel

**Step 3: Commit**

```bash
git add autobot-frontend/src/components/chat/VoiceConversationPanel.vue
git commit -m "feat(voice): create VoiceConversationPanel side panel component"
```

---

### Task 4: Integrate side panel into `ChatInterface.vue`

**Files:**
- Modify: `autobot-frontend/src/components/chat/ChatInterface.vue`

**Step 1: Add imports and state**

Add import for the preference composable after line 153 (after useToast import):
```typescript
import { usePreferences } from '@/composables/usePreferences'
```

Add import for the panel component after line 176 (after VoiceConversationOverlay import):
```typescript
import VoiceConversationPanel from './VoiceConversationPanel.vue'
```

Add after line 189 (after `const showVoiceOverlay = ref(false)`):
```typescript
const showVoicePanel = ref(false)
const { voiceDisplayMode } = usePreferences()
```

**Step 2: Update `openVoiceConversation()` to branch on preference**

Replace the function at lines 190-193:
```typescript
function openVoiceConversation(): void {
  if (voiceDisplayMode.value === 'sidepanel') {
    showFilePanel.value = false
    showVoicePanel.value = true
  } else {
    showVoiceOverlay.value = true
  }
  voiceConversation.activate()
}
```

**Step 3: Add close handler and mutual exclusion**

Add after `openVoiceConversation`:
```typescript
function closeVoicePanel(): void {
  showVoicePanel.value = false
}
```

Update `toggleFilePanel` (line 361-363) to close voice panel:
```typescript
const toggleFilePanel = () => {
  showVoicePanel.value = false
  showFilePanel.value = !showFilePanel.value
}
```

**Step 4: Update the header button active state**

Update the voice button (around line 44-51) — change the `:class` binding to highlight when either overlay or panel is active:
```html
:class="{ 'bg-electric-100 text-electric-600': showVoiceOverlay || showVoicePanel }"
```

**Step 5: Add VoiceConversationPanel to template**

Replace the file panel Transition block (lines 92-98) with:
```html
      <!-- Right side panels (mutually exclusive) -->
      <Transition name="slide-left">
        <ChatFilePanel
          v-if="showFilePanel && store.currentSessionId"
          :session-id="store.currentSessionId"
          @close="showFilePanel = false"
        />
        <VoiceConversationPanel
          v-else-if="showVoicePanel"
          @close="closeVoicePanel"
        />
      </Transition>
```

**Step 6: Close voice panel on session change**

Update the session change watcher (around line 836) — add after `showFilePanel.value = false`:
```typescript
showVoicePanel.value = false
```

**Step 7: Verify**

Run: `cd /home/kali/Desktop/AutoBot/autobot-frontend && npx vue-tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

**Step 8: Build**

Run: `cd /home/kali/Desktop/AutoBot/autobot-frontend && npm run build 2>&1 | tail -10`
Expected: Build succeeds

**Step 9: Commit**

```bash
git add autobot-frontend/src/components/chat/ChatInterface.vue
git commit -m "feat(voice): integrate voice side panel into ChatInterface with preference branching"
```

---

### Task 5: Create GitHub issue and link commits

**Step 1: Create issue**

```bash
gh issue create --title "feat: voice chat side panel option with user preference toggle" \
  --body "## Summary
Add a side panel alternative for the voice conversation overlay so users can observe AutoBot's background activity while using voice. User preference stored in localStorage via usePreferences.

## Changes
- [x] Add \`voiceDisplayMode\` to usePreferences.ts
- [x] Add toggle in ProfileModal.vue
- [x] Create VoiceConversationPanel.vue
- [x] Integrate into ChatInterface.vue (mutually exclusive with file panel)

## Design doc
docs/plans/2026-03-01-voice-sidepanel-design.md"
```

**Step 2: Close issue**

```bash
gh issue close <number> -c "Implemented voice side panel. Commits: <list>"
```
