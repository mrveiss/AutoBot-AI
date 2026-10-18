// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** Code-action dispatch for DevSpeedupView.vue (split out for the size ceiling, #18730). */
import type { useDevSpeedup } from '@/composables/useDevSpeedup'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('DevSpeedupCodeAction')

export type CodeActionType = 'refactor' | 'optimize' | 'format' | 'lint' | 'test'

type DevSpeedup = ReturnType<typeof useDevSpeedup>
export type CodeActions = Pick<
  DevSpeedup,
  'suggestRefactor' | 'optimizeCode' | 'formatCode' | 'lintFix' | 'generateTests'
>

/** Runs one code action; resolves to replacement code for the editor, or null to leave it. */
export async function runCodeAction(
  type: CodeActionType,
  code: string,
  language: string,
  actions: CodeActions,
): Promise<string | null> {
  switch (type) {
    case 'refactor':
      await actions.suggestRefactor(code, language)
      return null
    case 'optimize': {
      const optimized = await actions.optimizeCode(code, language)
      if (optimized) {
        alert(`Optimized code:\n\n${optimized}`)
      }
      return null
    }
    case 'format': {
      const formatted = await actions.formatCode(code, language)
      if (formatted) logger.debug('Code formatted')
      return formatted || null
    }
    case 'lint': {
      const fixed = await actions.lintFix(code, language)
      if (fixed) logger.debug('Linting fixed')
      return fixed || null
    }
    case 'test':
      await actions.generateTests(code, language)
      return null
  }
}
