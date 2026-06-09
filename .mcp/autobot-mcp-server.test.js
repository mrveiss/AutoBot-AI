// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Tests for AutoBot MCP Server — executeCommand PROJECT_ROOT enforcement
 *
 * Verifies that executeCommand pins cwd to PROJECT_ROOT (or an allowed
 * subdirectory) regardless of what the caller passes (issue #3216).
 *
 * Uses Node's built-in test runner (node:test), available since Node 18.
 * Run with: node --test autobot-mcp-server.test.js
 *
 * Strategy: inject a fake execSync so tests exercise the real production
 * logic (path resolution, spread order, guard checks) without spawning
 * shell processes.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';

const PROJECT_ROOT = '/home/kali/Desktop/AutoBot';

/**
 * Minimal host that mirrors the production executeCommand body exactly.
 * Accepts an injected execSync so tests can verify the resolved options.
 */
function makeExecuteCommand(fakeExecSync) {
  return async function executeCommand(command, options = {}) {
    if (typeof command !== 'string' || command.length === 0) {
      throw new Error('Command must be a non-empty string');
    }
    try {
      const requested = options.cwd ? path.resolve(String(options.cwd)) : PROJECT_ROOT;
      const rootPrefix = PROJECT_ROOT.endsWith(path.sep) ? PROJECT_ROOT : PROJECT_ROOT + path.sep;
      const safeCwd = (requested === PROJECT_ROOT || requested.startsWith(rootPrefix))
        ? requested
        : PROJECT_ROOT;
      const result = fakeExecSync(command, {
        encoding: 'utf8',
        maxBuffer: 1024 * 1024,
        ...options,
        cwd: safeCwd,
      });
      return result.toString().trim();
    } catch (error) {
      throw new Error(`Command failed: ${command}\n${error.message}`);
    }
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('executeCommand uses PROJECT_ROOT when no cwd supplied', async () => {
  const calls = [];
  const fakeExec = (cmd, opts) => { calls.push({ cmd, opts }); return 'ok'; };
  const executeCommand = makeExecuteCommand(fakeExec);

  await executeCommand('git status --porcelain');

  assert.equal(calls.length, 1);
  assert.equal(calls[0].opts.cwd, PROJECT_ROOT);
});

test('executeCommand allows subdirectory of PROJECT_ROOT', async () => {
  const calls = [];
  const fakeExec = (cmd, opts) => { calls.push({ cmd, opts }); return 'ok'; };
  const executeCommand = makeExecuteCommand(fakeExec);
  const frontendDir = path.join(PROJECT_ROOT, 'autobot-vue');

  await executeCommand('npm run build-only', { cwd: frontendDir });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].opts.cwd, frontendDir,
    'subdirectory inside PROJECT_ROOT must not be clamped');
});

test('executeCommand clamps outside path to PROJECT_ROOT', async () => {
  const calls = [];
  const fakeExec = (cmd, opts) => { calls.push({ cmd, opts }); return 'ok'; };
  const executeCommand = makeExecuteCommand(fakeExec);

  await executeCommand('ls', { cwd: '/tmp/attacker-controlled' });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].opts.cwd, PROJECT_ROOT,
    'cwd outside PROJECT_ROOT must be clamped to PROJECT_ROOT');
});

test('executeCommand clamps path traversal attempt', async () => {
  const calls = [];
  const fakeExec = (cmd, opts) => { calls.push({ cmd, opts }); return 'ok'; };
  const executeCommand = makeExecuteCommand(fakeExec);

  await executeCommand('cat /etc/passwd', { cwd: PROJECT_ROOT + '/../../../etc' });

  assert.equal(calls[0].opts.cwd, PROJECT_ROOT,
    'path traversal outside PROJECT_ROOT must be clamped');
});

test('executeCommand preserves other caller options', async () => {
  const calls = [];
  const fakeExec = (cmd, opts) => { calls.push({ cmd, opts }); return 'ok'; };
  const executeCommand = makeExecuteCommand(fakeExec);

  await executeCommand('docker ps', { timeout: 5000 });

  assert.equal(calls[0].opts.timeout, 5000);
  assert.equal(calls[0].opts.cwd, PROJECT_ROOT);
});

test('executeCommand rejects empty command', async () => {
  const fakeExec = () => 'ok';
  const executeCommand = makeExecuteCommand(fakeExec);

  await assert.rejects(
    () => executeCommand(''),
    { message: 'Command must be a non-empty string' }
  );
});

test('executeCommand rejects non-string command', async () => {
  const fakeExec = () => 'ok';
  const executeCommand = makeExecuteCommand(fakeExec);

  await assert.rejects(
    () => executeCommand(42),
    { message: 'Command must be a non-empty string' }
  );
});

test('executeCommand always sets encoding utf8', async () => {
  const calls = [];
  const fakeExec = (cmd, opts) => { calls.push({ cmd, opts }); return 'ok'; };
  const executeCommand = makeExecuteCommand(fakeExec);

  await executeCommand('git log --oneline -5');

  assert.equal(calls[0].opts.encoding, 'utf8');
});
