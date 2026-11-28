// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest'

// The floor is read once at module load, so each case stubs the env and re-imports.
async function loadLogger(dev: boolean) {
  vi.stubEnv('DEV', dev)
  vi.resetModules()
  return import('../logger')
}

afterEach(() => {
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe('createLogger level floor (#14908)', () => {
  it('drops debug in a production build but keeps info, warn and error', async () => {
    const { createLogger, MIN_LOG_LEVEL } = await loadLogger(false)
    const debug = vi.spyOn(console, 'debug').mockImplementation(() => {})
    const info = vi.spyOn(console, 'info').mockImplementation(() => {})
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})
    const logger = createLogger('scope')
    logger.debug('hidden')
    logger.info('shown')
    logger.error('shown too')
    expect(MIN_LOG_LEVEL).toBe('info')
    expect(debug).not.toHaveBeenCalled()
    expect(info).toHaveBeenCalledOnce()
    expect(info.mock.calls[0][1]).toBe('[scope] shown')
    expect(error).toHaveBeenCalledOnce()
  })

  it('logs debug in a dev build', async () => {
    const { createLogger, MIN_LOG_LEVEL } = await loadLogger(true)
    const debug = vi.spyOn(console, 'debug').mockImplementation(() => {})
    createLogger('scope').debug('visible', 42)
    expect(MIN_LOG_LEVEL).toBe('debug')
    expect(debug).toHaveBeenCalledOnce()
    expect(debug.mock.calls[0].slice(1)).toEqual(['[scope] visible', 42])
  })
})
