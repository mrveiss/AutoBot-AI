// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** One right-hand chat panel at a time, with focus handed in and back (#18243). */
import { describe, it, expect, afterEach } from 'vitest'
import { nextTick, ref } from 'vue'
import {
  useChatSidePanels, FILE_PANEL_ID, VOICE_PANEL_ID, COLLABORATION_PANEL_ID, VOICE_OVERLAY_ID,
} from '../useChatSidePanels'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('useChatSidePanels', () => {
  it('starts with every panel closed', () => {
    const p = useChatSidePanels()
    expect([p.showFilePanel.value, p.showVoicePanel.value, p.showCollaborationPanel.value]).toEqual([false, false, false])
  })

  it('opening a panel closes the one that was open', () => {
    const p = useChatSidePanels()
    p.toggle('files')
    p.toggle('voice')
    expect([p.showFilePanel.value, p.showVoicePanel.value, p.showCollaborationPanel.value]).toEqual([false, true, false])
    p.showCollaborationPanel.value = true
    expect(p.active.value).toBe('collaboration')
    expect(p.showVoicePanel.value).toBe(false)
  })

  it('toggling the open panel closes it', () => {
    const p = useChatSidePanels()
    p.toggle('voice')
    p.toggle('voice')
    expect(p.active.value).toBeNull()
  })

  it('closing a panel that is not the open one leaves the open one alone', () => {
    const p = useChatSidePanels()
    p.toggle('voice')
    p.showFilePanel.value = false
    expect(p.showVoicePanel.value).toBe(true)
  })

  it('closeAll closes whichever panel is open', () => {
    const p = useChatSidePanels()
    p.toggle('files')
    p.closeAll()
    expect(p.active.value).toBeNull()
  })

  it('focuses the files panel on open and its button on close', async () => {
    const p = useChatSidePanels()
    const panel = document.createElement('div')
    panel.id = FILE_PANEL_ID
    panel.tabIndex = -1
    const btn = document.createElement('button')
    document.body.append(panel, btn)
    p.fileBtnRef.value = btn

    p.toggle('files')
    await nextTick()
    await nextTick()
    expect(document.activeElement).toBe(panel)

    panel.remove() // the panel unmounts and focus falls to <body>
    p.toggle('files')
    await nextTick()
    await nextTick()
    expect(document.activeElement).toBe(btn)
  })

  it('does not steal focus the user already moved elsewhere', async () => {
    const p = useChatSidePanels()
    const btn = document.createElement('button')
    const other = document.createElement('input')
    document.body.append(btn, other)
    p.voiceBtnRef.value = btn
    p.toggle('voice')
    await nextTick()
    other.focus()
    p.toggle('voice')
    await nextTick()
    await nextTick()
    expect(document.activeElement).toBe(other)
  })

  it.each([
    ['voice', VOICE_PANEL_ID, 'voiceBtnRef'],
    ['collaboration', COLLABORATION_PANEL_ID, 'collabBtnRef'],
  ] as const)('%s panel: focus moves in on open, back to its button if stranded', async (name, id, ref_) => {
    const p = useChatSidePanels()
    const panel = document.createElement('div')
    panel.id = id
    panel.tabIndex = -1
    const btn = document.createElement('button')
    document.body.append(panel, btn)
    p[ref_].value = btn

    p.toggle(name)
    await nextTick()
    await nextTick()
    expect(document.activeElement).toBe(panel)

    panel.remove()
    p.toggle(name)
    await nextTick()
    await nextTick()
    expect(document.activeElement).toBe(btn)
  })

  it('voice button aria reflects the side panel in side-panel mode', () => {
    const p = useChatSidePanels(ref(false))
    expect([p.voiceExpanded.value, p.voiceControlsId.value]).toEqual([false, VOICE_PANEL_ID])
    p.toggle('voice')
    expect([p.voiceExpanded.value, p.voiceControlsId.value]).toEqual([true, VOICE_PANEL_ID])
  })

  it('voice button aria reflects the overlay in overlay mode', () => {
    const overlay = ref(false)
    const p = useChatSidePanels(overlay)
    overlay.value = true
    expect(p.showVoicePanel.value).toBe(false)
    expect([p.voiceExpanded.value, p.voiceControlsId.value]).toEqual([true, VOICE_OVERLAY_ID])
  })
})
