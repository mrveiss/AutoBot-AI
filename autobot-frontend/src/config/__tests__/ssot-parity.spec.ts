// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Cross-language SSOT parity guard.
 * =================================
 *
 * `autobot_shared/ssot_config.py` is canonical for several vocabularies that
 * the frontend cannot import at runtime, so `src/config/ssot-config.ts`
 * hand-mirrors them.  Both mirrors below measured *zero* drift when their
 * issues were filed — the point of this file is not to fix drift but to make
 * the next divergence fail CI instead of rotting silently, which is exactly
 * how #12662's items drifted.
 *
 * Covered:
 *   #13073 - PermissionMode / PermissionAction value vocabularies.
 *   #13074 - PortConfig literal default values.
 *
 * Mechanism: this reads the *Python source text* and extracts the declarations
 * with anchored regexes.  It deliberately does not execute Python, import
 * `ssot_config.py`, or read a committed generated fixture — a fixture would be
 * a third copy free to drift on its own, and a Python-side test would not run
 * in CI (the backend suite runs only for `tests/migrations/` and the import
 * smoke, #10691).  The frontend unit job already checks out the whole repo, so
 * the canonical file is on disk here.
 *
 * Ports specifically cannot ride the OpenAPI codegen pipeline at all: they are
 * env-driven config defaults and never appear in any API response schema.
 */

import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

import {
  PERMISSION_MODES,
  PERMISSION_ACTIONS,
  PORT_DEFAULTS,
} from '../ssot-config'

const PYTHON_SSOT_RELATIVE = join('autobot_shared', 'ssot_config.py')

/**
 * Locate the canonical Python config by walking up from the working directory.
 *
 * `import.meta.url` is not usable here: under the jsdom environment it is an
 * `http://` URL, not a `file://` one.  Walking up keeps the lookup independent
 * of whether vitest was invoked from `autobot-frontend/` or the repo root.
 */
function findPythonSsotPath(): string {
  let dir = resolve(process.cwd())
  for (;;) {
    const candidate = join(dir, PYTHON_SSOT_RELATIVE)
    if (existsSync(candidate)) return candidate
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(
    `Could not locate ${PYTHON_SSOT_RELATIVE} above ${process.cwd()} — this parity guard requires a full repo checkout, not a frontend-only one.`,
  )
}

const PYTHON_SSOT_PATH = findPythonSsotPath()

function readPythonSsot(): string {
  const source = readFileSync(PYTHON_SSOT_PATH, 'utf-8')
  if (source.length === 0) {
    throw new Error(`Canonical Python config is empty: ${PYTHON_SSOT_PATH}`)
  }
  return source
}

/**
 * Return the indented body of a top-level `class <name>(...)`.
 *
 * Throws when the class is gone — a rename must fail loudly rather than let
 * every assertion below pass vacuously against an empty extraction.
 */
function pythonClassBody(source: string, className: string): string {
  const lines = source.split('\n')
  const start = lines.findIndex((line) =>
    new RegExp(`^class ${className}\\(`).test(line),
  )
  if (start === -1) {
    throw new Error(
      `class ${className} not found in ${PYTHON_SSOT_PATH} — it was renamed or removed; update this parity test alongside it.`,
    )
  }
  const body: string[] = []
  for (let i = start + 1; i < lines.length; i++) {
    if (/^\S/.test(lines[i])) break
    body.push(lines[i])
  }
  return body.join('\n')
}

/** Extract the string values of a `class X(str, Enum)`, in declaration order. */
function pythonEnumValues(source: string, className: string): string[] {
  const body = pythonClassBody(source, className)
  const values: string[] = []
  const member = /^ {4}([A-Z][A-Z0-9_]*)\s*=\s*"([^"]*)"/gm
  let match: RegExpExecArray | null
  while ((match = member.exec(body)) !== null) values.push(match[2])
  if (values.length === 0) {
    throw new Error(
      `Parsed zero members out of Python enum ${className} — the declaration shape changed; fix this parser rather than trusting an empty comparison.`,
    )
  }
  return values
}

/** Extract `name: int = Field(default=N, ...)` pairs from `class PortConfig`. */
function pythonPortDefaults(source: string): Record<string, number> {
  const body = pythonClassBody(source, 'PortConfig')
  const defaults: Record<string, number> = {}
  const field = /^ {4}([a-z][a-z0-9_]*)\s*:\s*int\s*=\s*Field\(\s*default=(\d+)/gm
  let match: RegExpExecArray | null
  while ((match = field.exec(body)) !== null) {
    defaults[match[1]] = Number(match[2])
  }
  if (Object.keys(defaults).length === 0) {
    throw new Error(
      'Parsed zero ports out of Python PortConfig — the declaration shape changed; fix this parser rather than trusting an empty comparison.',
    )
  }
  return defaults
}

/**
 * Ports that legitimately exist on one side only.
 *
 * Python-only: backend-internal services the main frontend never addresses
 * directly. TS-only: a frontend-to-frontend link with no Python analog.
 * Anything appearing on one side that is *not* listed here is unmirrored
 * drift and fails below.
 */
const PYTHON_ONLY_PORTS = ['chromadb', 'tts', 'chrome_cdp'] as const
const TS_ONLY_PORTS = ['slmAdmin'] as const

describe('Python source parser (self-check)', () => {
  it('reads the canonical Python config off disk', () => {
    expect(readPythonSsot()).toContain('class PortConfig(BaseSettings):')
  })

  it('throws instead of returning nothing when a class is missing', () => {
    expect(() => pythonClassBody(readPythonSsot(), 'NoSuchClass')).toThrow(
      /not found/,
    )
  })

  it('extracts a non-empty result from each declaration it parses', () => {
    const source = readPythonSsot()
    expect(pythonEnumValues(source, 'PermissionMode').length).toBeGreaterThan(0)
    expect(pythonEnumValues(source, 'PermissionAction').length).toBeGreaterThan(0)
    expect(Object.keys(pythonPortDefaults(source)).length).toBeGreaterThan(0)
  })
})

describe('SSOT parity: permission vocabulary (#13073)', () => {
  it('PermissionMode matches autobot_shared/ssot_config.py value for value', () => {
    expect([...PERMISSION_MODES]).toEqual(
      pythonEnumValues(readPythonSsot(), 'PermissionMode'),
    )
  })

  it('PermissionAction matches autobot_shared/ssot_config.py value for value', () => {
    expect([...PERMISSION_ACTIONS]).toEqual(
      pythonEnumValues(readPythonSsot(), 'PermissionAction'),
    )
  })
})

describe('SSOT parity: port defaults (#13074)', () => {
  it('every overlapping port default matches the Python literal', () => {
    const pythonPorts = pythonPortDefaults(readPythonSsot())
    const overlapping = Object.keys(PORT_DEFAULTS).filter(
      (name) => name in pythonPorts,
    )
    expect(overlapping.length).toBeGreaterThan(0)

    const tsSide = Object.fromEntries(
      overlapping.map((name) => [
        name,
        PORT_DEFAULTS[name as keyof typeof PORT_DEFAULTS],
      ]),
    )
    const pythonSide = Object.fromEntries(
      overlapping.map((name) => [name, pythonPorts[name]]),
    )
    expect(tsSide).toEqual(pythonSide)
  })

  it('no new Python-only port appears without being mirrored or allow-listed', () => {
    const pythonPorts = pythonPortDefaults(readPythonSsot())
    const unmirrored = Object.keys(pythonPorts).filter(
      (name) =>
        !(name in PORT_DEFAULTS) &&
        !(PYTHON_ONLY_PORTS as readonly string[]).includes(name),
    )
    expect(unmirrored).toEqual([])
  })

  it('no new TS-only port appears without being mirrored or allow-listed', () => {
    const pythonPorts = pythonPortDefaults(readPythonSsot())
    const unmirrored = Object.keys(PORT_DEFAULTS).filter(
      (name) =>
        !(name in pythonPorts) &&
        !(TS_ONLY_PORTS as readonly string[]).includes(name),
    )
    expect(unmirrored).toEqual([])
  })

  it('each allow-listed one-sided port is still genuinely one-sided', () => {
    const pythonPorts = pythonPortDefaults(readPythonSsot())
    for (const name of PYTHON_ONLY_PORTS) {
      expect(pythonPorts).toHaveProperty(name)
      expect(PORT_DEFAULTS).not.toHaveProperty(name)
    }
    for (const name of TS_ONLY_PORTS) {
      expect(PORT_DEFAULTS).toHaveProperty(name)
      expect(pythonPorts).not.toHaveProperty(name)
    }
  })
})
