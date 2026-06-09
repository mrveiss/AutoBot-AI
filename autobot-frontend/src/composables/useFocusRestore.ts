// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * useFocusRestore Composable (#5356)
 *
 * Saves the currently-focused HTMLElement when "active" begins, restores
 * focus to it when "active" ends. Sister primitive to useFocusTrap (#5130) —
 * together they cover the keyboard-modality side of dialog accessibility
 * (trap inside, restore on close).
 *
 * Two modes:
 *   1. Mount-based (no argument) — save on onMounted, restore on onUnmounted.
 *      Fits dialogs that mount-on-show (parent gates with v-if).
 *   2. Trigger-based (pass a Ref<boolean>) — save on false→true transition,
 *      restore on true→false transition. Fits dialogs that stay mounted
 *      and toggle a `show`/`modelValue` prop (BaseModal, HostSelectionDialog).
 *
 * The canonical guard covers three edge cases the prior bespoke
 * implementations defended against separately:
 *   1. activeElement is null (rare — happens when no focus history exists)
 *   2. activeElement is document.body (no focused interactive element)
 *   3. activeElement is not an HTMLElement (e.g. SVGElement.focus exists
 *      but doesn't always behave like an HTMLElement; safer to skip)
 */

import { onMounted, onScopeDispose, watch, getCurrentInstance, getCurrentScope, type Ref } from 'vue'

/**
 * @param activeWhen  Optional Ref<boolean>. When provided, the composable
 *                    saves focus on the false→true transition and restores
 *                    it on the true→false transition. Omit for mount/unmount
 *                    semantics.
 */
export function useFocusRestore(activeWhen?: Ref<boolean>): void {
  let previouslyFocused: HTMLElement | null = null

  function save(): void {
    const active = document.activeElement
    if (active instanceof HTMLElement && active !== document.body) {
      previouslyFocused = active
    }
  }

  function restore(): void {
    previouslyFocused?.focus()
    previouslyFocused = null
  }

  if (activeWhen) {
    watch(activeWhen, (isActive, wasActive) => {
      // `wasActive` is undefined on the first run; treat as falsy so that
      // an initial `true` value also triggers a save (consistent with
      // mount-based behavior when the dialog opens immediately).
      if (isActive && !wasActive) save()
      else if (!isActive && wasActive) restore()
    }, { immediate: true })
  } else {
    if (getCurrentInstance()) {
      onMounted(save)
    }
    if (getCurrentScope()) {
      onScopeDispose(restore)
    }
  }
}
