// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Chat right-hand panels (#18243): Session files, Voice chat and Collaboration
 * share one slot, so at most one is open. The state is a single `active` value
 * rather than three booleans kept exclusive by hand, which makes "two open at
 * once" unrepresentable.
 *
 * Focus: a panel's header button gets focus back when its panel closes, but
 * only if focus was stranded on <body> -- never pulled from wherever the user
 * moved on to (switching session closes every panel).
 */
import { computed, nextTick, ref, watch, type ComputedRef, type Ref, type WritableComputedRef } from 'vue'

export type ChatSidePanel = 'files' | 'voice' | 'collaboration'

export const FILE_PANEL_ID = 'chat-panel-files'
export const VOICE_PANEL_ID = 'chat-panel-voice'
export const COLLABORATION_PANEL_ID = 'chat-panel-collaboration'
export const VOICE_OVERLAY_ID = 'chat-overlay-voice'

const PANEL_IDS: Record<ChatSidePanel, string> = {
  files: FILE_PANEL_ID,
  voice: VOICE_PANEL_ID,
  collaboration: COLLABORATION_PANEL_ID,
}

export interface UseChatSidePanels {
  active: Ref<ChatSidePanel | null>
  showFilePanel: WritableComputedRef<boolean>
  showVoicePanel: WritableComputedRef<boolean>
  showCollaborationPanel: WritableComputedRef<boolean>
  fileBtnRef: Ref<HTMLElement | null>
  voiceBtnRef: Ref<HTMLElement | null>
  collabBtnRef: Ref<HTMLElement | null>
  /** Whether the voice header button's target (panel or overlay) is showing. */
  voiceExpanded: ComputedRef<boolean>
  /** Id of the element the voice header button actually controls. */
  voiceControlsId: ComputedRef<string>
  toggle: (panel: ChatSidePanel) => void
  closeAll: () => void
}

export function useChatSidePanels(
  voiceOverlayOpen: Ref<boolean> = ref(false),
): UseChatSidePanels {
  const active = ref<ChatSidePanel | null>(null)
  const fileBtnRef = ref<HTMLElement | null>(null)
  const voiceBtnRef = ref<HTMLElement | null>(null)
  const collabBtnRef = ref<HTMLElement | null>(null)
  const btnRefs: Record<ChatSidePanel, Ref<HTMLElement | null>> = {
    files: fileBtnRef,
    voice: voiceBtnRef,
    collaboration: collabBtnRef,
  }

  const flag = (panel: ChatSidePanel) =>
    computed({
      get: () => active.value === panel,
      set: (open: boolean) => {
        if (open) active.value = panel
        else if (active.value === panel) active.value = null
      },
    })

  const toggle = (panel: ChatSidePanel): void => {
    active.value = active.value === panel ? null : panel
  }
  const closeAll = (): void => {
    active.value = null
  }

  const restoreFocus = (el: HTMLElement | null): void => {
    const current = document.activeElement
    if (!current || current === document.body) el?.focus()
  }

  // Open: focus moves into the panel (every panel root is tabindex=-1).
  // Close: the button gets focus back only if it was stranded on <body>.
  watch(active, async (now, before) => {
    await nextTick()
    if (now) document.getElementById(PANEL_IDS[now])?.focus()
    else if (before) restoreFocus(btnRefs[before].value)
  })

  const voiceExpanded = computed(() => active.value === 'voice' || voiceOverlayOpen.value)
  const voiceControlsId = computed(() =>
    voiceOverlayOpen.value ? VOICE_OVERLAY_ID : VOICE_PANEL_ID,
  )

  return {
    active,
    showFilePanel: flag('files'),
    showVoicePanel: flag('voice'),
    showCollaborationPanel: flag('collaboration'),
    fileBtnRef,
    voiceBtnRef,
    collabBtnRef,
    voiceExpanded,
    voiceControlsId,
    toggle,
    closeAll,
  }
}
