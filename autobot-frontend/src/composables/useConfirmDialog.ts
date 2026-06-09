// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { ref } from 'vue'

interface ConfirmOptions {
  title: string
  message: string
}

// Module-level singletons so state is shared across all component instances
const dialogVisible = ref(false)
const dialogOptions = ref<ConfirmOptions | null>(null)
const resolveRef = ref<((v: boolean) => void) | null>(null)

function confirm(options: ConfirmOptions): Promise<boolean> {
  dialogOptions.value = options
  dialogVisible.value = true
  return new Promise<boolean>((resolve) => {
    resolveRef.value = resolve
  })
}

function _resolve(value: boolean): void {
  dialogVisible.value = false
  dialogOptions.value = null
  const resolve = resolveRef.value
  resolveRef.value = null
  resolve?.(value)
}

export function useConfirmDialog() {
  return { confirm, dialogVisible, dialogOptions, _resolve }
}
