// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Test helper (#17564): resolves a custom property the way the cascade does for an
// element under a density scope, from the real stylesheets (jsdom does not resolve
// custom properties across files, so a computed-style read would prove nothing).
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const libTokens = resolve(here, '../../tokens')
const appCss = resolve(here, '../../../../../autobot-frontend/src/assets/css')

export type Density = 'comfortable' | 'compact' | 'spacious'
type Decls = Map<string, string>

const strip = (css: string): string => css.replace(/\/\*[\s\S]*?\*\//g, '')

function declsFor(files: string[], selector: string): Decls {
  const out: Decls = new Map()
  for (const file of files) {
    for (const rule of strip(readFileSync(file, 'utf-8')).matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      if (rule[1].replace(/\s+/g, ' ').trim() !== selector) continue
      for (const d of rule[2].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out.set(d[1], d[2].trim())
    }
  }
  return out
}

const SOURCES = [`${libTokens}/contract.css`, `${libTokens}/adapter.css`, `${appCss}/design-tokens.css`]
const PREFS = `${appCss}/themes/preferences.css`

function scopeDecls(density: Density): Decls {
  const base = declsFor(SOURCES, ':root')
  if (density === 'comfortable') return base
  const scoped = declsFor([PREFS], `[data-layout-density="${density}"]`)
  return new Map([...base, ...scoped])
}

/** The resolved value of `name` for an element under the given density scope. */
export function resolveToken(name: string, density: Density): string {
  const decls = scopeDecls(density)
  const walk = (value: string, depth: number): string => {
    if (depth > 20) throw new Error(`var() cycle resolving ${name}`)
    return value.replace(/var\(\s*(--[\w-]+)\s*(?:,[^)]*)?\)/g, (_m, ref: string) => {
      const next = decls.get(ref)
      if (next === undefined) throw new Error(`${ref} is not declared (resolving ${name})`)
      return walk(next, depth + 1)
    })
  }
  const own = decls.get(name)
  if (own === undefined) throw new Error(`${name} is not declared`)
  return walk(own, 0)
}
