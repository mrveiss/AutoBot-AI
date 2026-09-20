// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Say, right beside the local vitest result, when the environment is below floor (#16919).
 *
 * The frontend twin of `repo_tests/dependency_floor_banner.py` (#15091) -- same failure
 * mode, same fix shape: a developer or agent runs the suite, sees it pass (or fail), and
 * reads that as evidence about the change. When installed packages are older than what
 * `package.json` declares, that reading is about a different environment than the one CI
 * builds with `npm ci`, and nothing said so. #16919 was filed after exactly that: a fresh
 * `new URL(relative, import.meta.url)` call threw under a jsdom 4 versions below the
 * declared `^30.0.1` floor, and nothing local said the environment -- not the test -- was
 * the problem.
 *
 * Like the Python banner, this never fails the run: a box below floor is still usable for
 * ordinary work, and a gate that blocked every local run on it would be removed within a
 * day. `onTestRunEnd` (not a `setupFiles` script) is the placement that matters -- a
 * setup file runs once per test FILE, so it would print the same banner dozens of times;
 * this hook fires exactly once, after the run's own pass/fail summary, so it lands where
 * `pytest_terminal_summary`'s Python counterpart does: immediately after the line actually
 * read, not scrolled away behind it.
 *
 * Only a lower bound is checked (installed >= the numeric floor `^`/`~`/`>=`/an exact
 * version declares), matching `check_dependency_floors.py`'s own scope -- neither checker
 * models the upper bound a caret or tilde range also implies, because the failure mode
 * both exist to catch is "older than declared", never "newer than declared".
 */

import type { Reporter, SerializedError, TestModule, TestRunEndReason } from 'vitest/node'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const FRONTEND_ROOT = dirname(dirname(dirname(fileURLToPath(import.meta.url))))

interface PackageJson {
  dependencies?: Record<string, string>
  devDependencies?: Record<string, string>
}

interface Shortfall {
  name: string
  declared: string
  installed: string | null
}

export function numericFloor(range: string): number[] | null {
  const match = range.match(/(\d+)\.(\d+)\.(\d+)/)
  if (!match) return null
  return [Number(match[1]), Number(match[2]), Number(match[3])]
}

export function meetsFloor(installed: number[], floor: number[]): boolean {
  for (let i = 0; i < 3; i++) {
    if (installed[i] > floor[i]) return true
    if (installed[i] < floor[i]) return false
  }
  return true
}

function installedVersion(name: string): string | null {
  const pkgPath = join(FRONTEND_ROOT, 'node_modules', name, 'package.json')
  if (!existsSync(pkgPath)) return null
  try {
    const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8')) as { version?: string }
    return pkg.version ?? null
  } catch {
    return null
  }
}

/** Exported for the guard test — the reporter itself never returns this, it only prints it. */
export function findShortfalls(): Shortfall[] {
  const pkgJsonPath = join(FRONTEND_ROOT, 'package.json')
  const pkgJson = JSON.parse(readFileSync(pkgJsonPath, 'utf-8')) as PackageJson
  const declared = { ...pkgJson.dependencies, ...pkgJson.devDependencies }

  const shortfalls: Shortfall[] = []
  for (const [name, range] of Object.entries(declared)) {
    const floor = numericFloor(range)
    if (!floor) continue // workspace/git/file-protocol deps carry no numeric floor to check

    const installed = installedVersion(name)
    if (installed === null) {
      shortfalls.push({ name, declared: range, installed: null })
      continue
    }
    const installedNumbers = numericFloor(installed)
    if (!installedNumbers || !meetsFloor(installedNumbers, floor)) {
      shortfalls.push({ name, declared: range, installed })
    }
  }
  return shortfalls
}

class DependencyFloorReporter implements Reporter {
  onTestRunEnd(_testModules: ReadonlyArray<TestModule>, _unhandledErrors: ReadonlyArray<SerializedError>, _reason: TestRunEndReason) {
    const shortfalls = findShortfalls()
    if (shortfalls.length === 0) return

    console.warn(
      `\n⚠ ${shortfalls.length} installed package(s) are below what package.json declares — ` +
        'a pass or fail here is not evidence about what CI (which runs `npm ci`) will do:',
    )
    for (const s of shortfalls.slice(0, 20)) {
      console.warn(`  ${s.name}: installed ${s.installed ?? '(not installed)'}, declared ${s.declared}`)
    }
    if (shortfalls.length > 20) {
      console.warn(`  ... and ${shortfalls.length - 20} more`)
    }
  }
}

export default new DependencyFloorReporter()
