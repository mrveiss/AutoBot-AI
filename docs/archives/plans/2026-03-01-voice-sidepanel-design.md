# Voice Side Panel Design

**Date:** 2026-03-01
**Status:** Approved

## Problem

The voice conversation interface currently only renders as a full-screen modal overlay (`VoiceConversationOverlay.vue`), which blocks the main chat view. Users want to observe what AutoBot is doing in the background (typing, tool calls, message flow) while using voice — a side panel option solves this.

## Decision

- **Approach A: New panel component** — create a minimal `VoiceConversationPanel.vue` (~120-150 lines) that reuses the `useVoiceConversation` composable but renders only essential controls in a right-side panel.
- **Preference toggle** — `voiceDisplayMode: 'modal' | 'sidepanel'` stored in `usePreferences.ts` (localStorage). Setting accessible from ProfileModal UI preferences section.
- **Mutually exclusive panels** — voice panel and file panel cannot coexist. Opening one closes the other.

## Components

### 1. Preference: `voiceDisplayMode`

- Added to `usePreferences.ts` composable (alongside fontSize, accentColor, layoutDensity)
- Default: `'modal'`
- Persisted in localStorage key `autobot-preferences`
- No backend changes required

### 2. ProfileModal Setting

- New "Voice Display" option in ProfileModal.vue under UI preferences
- Simple radio/toggle: "Full-screen overlay" vs "Side panel"

### 3. `VoiceConversationPanel.vue`

New file: `autobot-frontend/src/components/chat/VoiceConversationPanel.vue`

**Layout** (~280px wide, full height, right side):

```
+----------------------------+
| Voice Chat    [mode v]  X  |  <- Header: title, mode selector, close
+----------------------------+
|                            |
|      * Listening...        |  <- State indicator
|                            |
|  "Live transcript text"    |  <- Current speech transcript
|                            |
+----------------------------+
|  <========>  1.5s          |  <- Audio level + silence slider (hands-free)
+----------------------------+
|         ( mic )            |  <- Mic button with pulse animation
|      Push to talk          |  <- Contextual hint
+----------------------------+
|  ! Error message           |  <- Error/warning (when relevant)
+----------------------------+
```

**Key details:**
- Reuses `useVoiceConversation()` (module-level singleton state)
- Follows `ChatFilePanel` slide-in pattern (`transition name="slide-left"`)
- Dark "comm-station" aesthetic matching the overlay
- Emits `@close` event
- No conversation bubble history — messages flow through main chat
- Mode selector kept (walkie-talkie / hands-free / full-duplex)
- WebSocket indicator in full-duplex mode
- Hands-free controls: audio level meter + silence threshold slider

### 4. ChatInterface Integration

```typescript
function openVoiceConversation(): void {
  if (voiceDisplayMode.value === 'sidepanel') {
    showFilePanel.value = false   // mutually exclusive
    showVoicePanel.value = true
  } else {
    showVoiceOverlay.value = true
  }
  voiceConversation.activate()
}
```

Panel rendered in same slot as ChatFilePanel:
```html
<ChatFilePanel v-if="showFilePanel" @close="..." />
<VoiceConversationPanel v-else-if="showVoicePanel" @close="..." />
```

## Files Modified

| File | Change |
|------|--------|
| `src/composables/usePreferences.ts` | Add `voiceDisplayMode` to state + getter/setter |
| `src/components/profile/ProfileModal.vue` | Add voice display mode toggle |
| `src/components/chat/VoiceConversationPanel.vue` | **NEW** — minimal voice side panel |
| `src/components/chat/ChatInterface.vue` | Branch on preference; mutual exclusion with file panel |

## Non-Goals

- No backend changes
- No modification to the existing VoiceConversationOverlay.vue
- No shared sub-component extraction (YAGNI)
- No conversation bubble history in the panel
