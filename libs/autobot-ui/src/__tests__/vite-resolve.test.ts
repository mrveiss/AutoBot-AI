// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment node
// (createServer loads esbuild, whose Uint8Array invariant fails under the kit's default jsdom.)
// Regression guard (#18240): a string alias on '@autobot/ui' also rewrote the subpath
// exports ('@autobot/ui/adapter' -> '<index.ts>/adapter') and broke every app build.
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { describe, expect, it } from 'vitest'
import pkg from '../../package.json'
import { autobotUiResolve } from '../../vite-resolve'

const kitFile = (relative: string) => fileURLToPath(new URL(`../../${relative}`, import.meta.url))

describe('autobotUiResolve', () => {
  it('declares one exact-match alias per package.json export', () => {
    const { alias } = autobotUiResolve()
    expect(alias).toHaveLength(Object.keys(pkg.exports).length)
    for (const entry of alias) expect(entry.find).toBeInstanceOf(RegExp)
  })

  it.each([
    ['@autobot/ui', 'index.ts'],
    ['@autobot/ui/tokens', 'src/tokens/contract.css'],
    ['@autobot/ui/adapter', 'src/tokens/adapter.css'],
  ])('vite resolves %s to the in-tree kit file', async (specifier, relative) => {
    const server = await createServer({
      configFile: false,
      root: kitFile('.'),
      logLevel: 'silent',
      server: { middlewareMode: true, hmr: false, ws: false },
      optimizeDeps: { noDiscovery: true },
      resolve: autobotUiResolve(),
    })
    try {
      const resolved = await server.pluginContainer.resolveId(specifier, kitFile('index.ts'))
      expect(resolved?.id).toBe(kitFile(relative))
      expect(existsSync(resolved!.id)).toBe(true)
    } finally {
      await server.close()
    }
  })
})
