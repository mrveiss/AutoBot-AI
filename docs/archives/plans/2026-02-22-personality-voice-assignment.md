# Personality Voice Assignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `voice_id` field to personality profiles so each personality can speak with a specific Pocket TTS voice, overriding the user's global voice selection.

**Architecture:** `voice_id` is stored as an optional string on `PersonalityProfile` (JSON file). Backend schema accepts/returns it. SLM frontend personality editor shows a voice dropdown. Main frontend's `useVoiceProfiles` exposes an `effectiveVoiceId` computed that prefers the active personality's voice over the user's global selection; `useVoiceOutput` and `useVoiceConversation` both consume `effectiveVoiceId`.

**Tech Stack:** Python dataclass (no DB migration needed — JSON files), FastAPI/Pydantic, Vue 3 + TypeScript

---

### Task 1: Add `voice_id` to `PersonalityProfile` dataclass

**Files:**
- Modify: `autobot-backend/services/personality_service.py`

**Step 1: Add field to dataclass**

In `PersonalityProfile` (line 50), add `voice_id` after `custom_notes`:

```python
@dataclass
class PersonalityProfile:
    id: str
    name: str
    tagline: str = ""
    tone: str = "direct"
    character_traits: List[str] = field(default_factory=list)
    operating_style: List[str] = field(default_factory=list)
    off_limits: List[str] = field(default_factory=list)
    custom_notes: str = ""
    voice_id: str = ""          # NEW: Pocket TTS voice override (#1135)
    is_system: bool = False
    created_by: str = "system"
    created_at: str = ""
    updated_at: str = ""
```

**Step 2: Add `voice_id` to `update_profile()` allowed set**

In `update_profile()` (line 241), add `"voice_id"` to the `allowed` set:

```python
allowed = {
    "name",
    "tagline",
    "tone",
    "character_traits",
    "operating_style",
    "off_limits",
    "custom_notes",
    "voice_id",
}
```

**Step 3: Add `voice_id` to `create_profile()` kwargs**

In `create_profile()` (line 203), add `voice_id` to the `PersonalityProfile(...)` constructor call:

```python
profile = PersonalityProfile(
    id=pid,
    name=name,
    tagline=kwargs.get("tagline", ""),
    tone=kwargs.get("tone", "direct"),
    character_traits=list(kwargs.get("character_traits", [])),
    operating_style=list(kwargs.get("operating_style", [])),
    off_limits=list(kwargs.get("off_limits", [])),
    custom_notes=kwargs.get("custom_notes", ""),
    voice_id=kwargs.get("voice_id", ""),   # NEW
    is_system=False,
    created_by=created_by,
)
```

**Step 4: Verify ruff passes**

```bash
ruff check autobot-backend/services/personality_service.py
```
Expected: no errors

**Step 5: Commit**

```bash
git add autobot-backend/services/personality_service.py
git commit -m "feat(personality): add voice_id field to PersonalityProfile dataclass (#1135)"
```

---

### Task 2: Add `voice_id` to API schemas and helper

**Files:**
- Modify: `autobot-backend/api/personality.py`

**Step 1: Add `voice_id` to `ProfileDetail` schema**

After `updated_at: str` (line 52) add:

```python
voice_id: str = ""
```

**Step 2: Add `voice_id` to `ProfileCreate` schema**

After `custom_notes: str = ""` (line 62) add:

```python
voice_id: str = ""
```

**Step 3: Add `voice_id` to `ProfileUpdate` schema**

After `custom_notes: Optional[str] = None` (line 78) add:

```python
voice_id: Optional[str] = None
```

**Step 4: Expose `voice_id` in `_profile_to_detail()`**

Add `voice_id=p.voice_id` to the `ProfileDetail(...)` constructor in `_profile_to_detail()`:

```python
def _profile_to_detail(p) -> ProfileDetail:
    return ProfileDetail(
        id=p.id,
        name=p.name,
        tagline=p.tagline,
        tone=p.tone,
        character_traits=p.character_traits,
        operating_style=p.operating_style,
        off_limits=p.off_limits,
        custom_notes=p.custom_notes,
        voice_id=p.voice_id,          # NEW
        is_system=p.is_system,
        created_by=p.created_by,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )
```

**Step 5: Verify ruff passes**

```bash
ruff check autobot-backend/api/personality.py
```
Expected: no errors

**Step 6: Commit**

```bash
git add autobot-backend/api/personality.py
git commit -m "feat(personality): expose voice_id in API schemas (#1135)"
```

---

### Task 3: Add `voice_id` to SLM frontend personality interfaces

**Files:**
- Modify: `autobot-slm-frontend/src/composables/usePersonality.ts`

**Step 1: Add `voice_id` to `PersonalityProfile` interface**

After `custom_notes: string` (line 42) add:

```typescript
voice_id: string
```

**Step 2: Add `voice_id` to `ProfileCreate` interface**

After `custom_notes?: string` (line 52) add:

```typescript
voice_id?: string
```

**Step 3: Add `voice_id` to `ProfileUpdate` interface**

After `custom_notes?: string` (line 62) add:

```typescript
voice_id?: string
```

**Step 4: Verify no type errors**

```bash
cd autobot-slm-frontend && npm run type-check 2>&1 | grep -i "usePersonality\|voice_id" || echo "clean"
```

**Step 5: Commit**

```bash
git add autobot-slm-frontend/src/composables/usePersonality.ts
git commit -m "feat(personality): add voice_id to SLM frontend personality interfaces (#1135)"
```

---

### Task 4: Add voice selector to SLM PersonalitySettings editor

**Files:**
- Modify: `autobot-slm-frontend/src/views/settings/admin/PersonalitySettings.vue`

**Step 1: Add voice list state and fetch in `<script setup>`**

After the existing imports, add a reactive voice list and fetch function. Add after `const confirmDeleteId = ref...`:

```typescript
// ---- voice list for personality voice assignment (#1135) ----
const voiceList = ref<{ id: string; name: string; builtin: boolean }[]>([])

async function fetchVoices() {
  try {
    const token = localStorage.getItem('autobot_access_token') || ''
    const res = await fetch('/autobot-api/voice/voices', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (res.ok) {
      const data = await res.json()
      voiceList.value = Array.isArray(data) ? data : (data.voices || [])
    }
  } catch {
    // voice list unavailable — selector will show empty
  }
}
```

**Step 2: Add `voice_id` to `editForm`**

The `editForm` is typed as `Partial<PersonalityProfile>`. Add `voice_id` population in `selectProfile()`, inside the `Object.assign(editForm, {...})` call (add after `custom_notes`):

```typescript
voice_id: full.voice_id ?? '',
```

**Step 3: Add `voice_id` to `handleSave()` updates**

In `handleSave()`, add `voice_id: editForm.voice_id` to the `updateProfile(...)` call payload (after `custom_notes`):

```typescript
voice_id: editForm.voice_id as string,
```

**Step 4: Add voice dropdown in template**

In the template, inside the `<div class="space-y-5">` block, add a Voice selector section after the Custom Notes block and before the Save button:

```html
<!-- Voice Assignment (#1135) -->
<div>
  <label class="block text-xs font-medium text-gray-600 mb-1">Voice</label>
  <select
    v-model="editForm.voice_id"
    class="w-full px-3 py-2 text-sm border border-gray-200 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400"
  >
    <option value="">None (use user's voice setting)</option>
    <option
      v-for="v in voiceList"
      :key="v.id"
      :value="v.id"
    >{{ v.name }}{{ v.builtin ? ' (built-in)' : '' }}</option>
  </select>
  <p class="mt-1 text-xs text-gray-400">
    When this personality is active, voice output will use the selected voice.
  </p>
</div>
```

**Step 5: Call `fetchVoices()` in `onMounted`**

Add `fetchVoices()` to the `onMounted` block alongside existing calls:

```typescript
onMounted(async () => {
  await Promise.all([fetchProfiles(), fetchActive(), fetchVoices()])
  if (profiles.value.length > 0) {
    await selectProfile(profiles.value[0].id)
  }
})
```

**Step 6: Verify lint/types**

```bash
cd autobot-slm-frontend && npm run type-check 2>&1 | grep -i "PersonalitySettings\|voice_id" || echo "clean"
```

**Step 7: Commit**

```bash
git add autobot-slm-frontend/src/views/settings/admin/PersonalitySettings.vue
git commit -m "feat(personality): add voice selector to SLM personality settings editor (#1135)"
```

---

### Task 5: Add personality voice priority to `useVoiceProfiles`

**Files:**
- Modify: `autobot-frontend/src/composables/useVoiceProfiles.ts`

The `effectiveVoiceId` computed is the key primitive — all voice synthesis reads from it, so personality voice automatically overrides the user's selection without modifying the underlying user preference.

**Step 1: Add module-level personality voice state**

After `const loading = ref(false)` (line 31), add:

```typescript
// Personality-assigned voice — overrides user selection when set (#1135)
const personalityVoiceId = ref<string>('')
```

**Step 2: Add `effectiveVoiceId` computed**

After `personalityVoiceId`, add:

```typescript
import { ref, computed } from 'vue'   // ensure computed is imported (already present)

const effectiveVoiceId = computed<string>(() =>
  personalityVoiceId.value || selectedVoiceId.value
)
```

(Note: `computed` is already imported at line 11 — just add the const.)

**Step 3: Add `setPersonalityVoice` and `fetchPersonalityVoice` to the returned composable**

Inside `useVoiceProfiles()`, add:

```typescript
function setPersonalityVoice(voiceId: string): void {
  personalityVoiceId.value = voiceId
  logger.debug('Personality voice set:', voiceId || '(none)')
}

async function fetchPersonalityVoice(): Promise<void> {
  try {
    const res = await fetchWithAuth('/api/personality/active')
    if (res.ok) {
      const profile = await res.json()
      personalityVoiceId.value = profile?.voice_id ?? ''
    } else {
      personalityVoiceId.value = ''
    }
  } catch {
    personalityVoiceId.value = ''
  }
}
```

**Step 4: Expose new items in return**

Add to the return object:

```typescript
return {
  voices,
  selectedVoiceId,
  personalityVoiceId,
  effectiveVoiceId,
  loading,
  error,
  fetchVoices,
  selectVoice,
  createVoice,
  deleteVoice,
  setPersonalityVoice,
  fetchPersonalityVoice,
}
```

**Step 5: Verify no type errors in changed file**

```bash
cd autobot-frontend && npm run type-check 2>&1 | grep "useVoiceProfiles" || echo "clean"
```

**Step 6: Commit**

```bash
git add autobot-frontend/src/composables/useVoiceProfiles.ts
git commit -m "feat(voice): add effectiveVoiceId with personality override to useVoiceProfiles (#1135)"
```

---

### Task 6: Use `effectiveVoiceId` in voice output + conversation

**Files:**
- Modify: `autobot-frontend/src/composables/useVoiceOutput.ts`
- Modify: `autobot-frontend/src/composables/useVoiceConversation.ts`

**Step 1: Update `useVoiceOutput.ts`**

On line 113, change:
```typescript
const { selectedVoiceId } = useVoiceProfiles()
```
to:
```typescript
const { effectiveVoiceId } = useVoiceProfiles()
```

On line 116, change:
```typescript
if (selectedVoiceId.value) {
  formData.append('voice_id', selectedVoiceId.value)
}
```
to:
```typescript
if (effectiveVoiceId.value) {
  formData.append('voice_id', effectiveVoiceId.value)
}
```

**Step 2: Update `useVoiceConversation.ts`**

On line 394, change:
```typescript
const { selectedVoiceId } = useVoiceProfiles()
_sendWs({ type: 'speak', text: speechText, voice_id: selectedVoiceId.value })
```
to:
```typescript
const { effectiveVoiceId } = useVoiceProfiles()
_sendWs({ type: 'speak', text: speechText, voice_id: effectiveVoiceId.value })
```

**Step 3: Verify no type errors**

```bash
cd autobot-frontend && npm run type-check 2>&1 | grep -E "useVoiceOutput|useVoiceConversation" || echo "clean"
```

**Step 4: Commit**

```bash
git add autobot-frontend/src/composables/useVoiceOutput.ts autobot-frontend/src/composables/useVoiceConversation.ts
git commit -m "feat(voice): use effectiveVoiceId (personality override) in voice output and conversation (#1135)"
```

---

### Task 7: Load personality voice on VoiceSettingsPanel mount

**Files:**
- Modify: `autobot-frontend/src/components/settings/VoiceSettingsPanel.vue`

**Step 1: Import and call `fetchPersonalityVoice` on mount**

Update `<script setup>` to destructure and call `fetchPersonalityVoice`:

```typescript
const {
  voices,
  selectedVoiceId,
  effectiveVoiceId,
  personalityVoiceId,
  loading,
  error,
  fetchVoices,
  selectVoice,
  createVoice,
  deleteVoice,
  fetchPersonalityVoice,
} = useVoiceProfiles()

onMounted(() => {
  fetchVoices()
  fetchPersonalityVoice()
})
```

**Step 2: Add personality override hint in template**

After the voice list `<div v-if="loading">` block, add an informational banner when a personality voice is active:

```html
<div v-if="personalityVoiceId" class="personality-voice-hint">
  <i class="fas fa-user-circle"></i>
  Active personality overrides voice selection:
  <strong>{{ voices.find(v => v.id === personalityVoiceId)?.name ?? personalityVoiceId }}</strong>
</div>
```

Add the corresponding style:

```css
.personality-voice-hint {
  padding: var(--spacing-sm, 8px) var(--spacing-md, 12px);
  background: rgba(96, 165, 250, 0.1);
  border: 1px solid var(--color-primary, #60a5fa);
  border-radius: var(--radius-md, 6px);
  color: var(--text-secondary, #94a3b8);
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs, 6px);
}

.personality-voice-hint strong {
  color: var(--color-primary, #60a5fa);
}
```

**Step 3: Verify no type errors**

```bash
cd autobot-frontend && npm run type-check 2>&1 | grep "VoiceSettingsPanel" || echo "clean"
```

**Step 4: Commit**

```bash
git add autobot-frontend/src/components/settings/VoiceSettingsPanel.vue
git commit -m "feat(voice): show personality voice override hint in VoiceSettingsPanel (#1135)"
```

---

### Task 8: Close issue

**Step 1: Add closing comment to GitHub**

```bash
gh issue comment 1135 --repo mrveiss/AutoBot-AI --body "## Implemented

Commits on Dev_new_gui:
- Task 1: voice_id field in PersonalityProfile dataclass
- Task 2: voice_id in API schemas
- Task 3: voice_id in SLM frontend interfaces
- Task 4: Voice selector in SLM PersonalitySettings editor
- Task 5: effectiveVoiceId in useVoiceProfiles
- Task 6: effectiveVoiceId in useVoiceOutput + useVoiceConversation
- Task 7: fetchPersonalityVoice on VoiceSettingsPanel mount

All acceptance criteria met."
```

**Step 2: Close issue**

```bash
gh issue close 1135 --repo mrveiss/AutoBot-AI
```
