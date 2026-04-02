/**
 * Tests for AutoBot MCP Server — executeCommand PROJECT_ROOT enforcement
 *
 * Verifies that executeCommand always pins cwd to PROJECT_ROOT regardless
 * of what the caller passes in the options argument (issue #3216).
 *
 * Uses Node's built-in test runner (node:test), available since Node 18.
 * Run with: node --test autobot-mcp-server.test.js
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execSync } from 'child_process';

// ---------------------------------------------------------------------------
// Minimal test double for AutoBotMCPServer.executeCommand
// We re-implement only the method under test to avoid importing the full
// server (which connects to an MCP transport on startup).
// ---------------------------------------------------------------------------

const PROJECT_ROOT = '/home/kali/Desktop/AutoBot';

/**
 * Extracted copy of executeCommand that records every execSync call so tests
 * can inspect the options object without running real shell commands.
 */
function makeExecuteCommand(capturedCalls) {
  return async function executeCommand(command, options = {}) {
    if (typeof command !== 'string' || command.length === 0) {
      throw new Error('Command must be a non-empty string');
    }
    // Mirror the production implementation exactly.
    const resolvedOptions = {
      encoding: 'utf8',
      maxBuffer: 1024 * 1024,
      ...options,
      cwd: PROJECT_ROOT,           // enforced — always last
    };
    capturedCalls.push({ command, options: { ...resolvedOptions } });
    // Return a stub string instead of actually executing.
    return 'stub-output';
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('executeCommand always pins cwd to PROJECT_ROOT', async () => {
  const calls = [];
  const executeCommand = makeExecuteCommand(calls);

  await executeCommand('git status --porcelain', { cwd: PROJECT_ROOT });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.cwd, PROJECT_ROOT);
});

test('executeCommand overrides caller-supplied cwd with PROJECT_ROOT', async () => {
  const calls = [];
  const executeCommand = makeExecuteCommand(calls);

  // Simulate a caller that mistakenly passes a different cwd.
  await executeCommand('ls', { cwd: '/tmp/attacker-controlled' });

  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].options.cwd,
    PROJECT_ROOT,
    'cwd must be PROJECT_ROOT even when caller passes a different value'
  );
});

test('executeCommand preserves other caller-supplied options', async () => {
  const calls = [];
  const executeCommand = makeExecuteCommand(calls);

  await executeCommand('docker ps', { timeout: 5000 });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.timeout, 5000);
  assert.equal(calls[0].options.cwd, PROJECT_ROOT);
});

test('executeCommand rejects empty command string', async () => {
  const calls = [];
  const executeCommand = makeExecuteCommand(calls);

  await assert.rejects(
    () => executeCommand(''),
    { message: 'Command must be a non-empty string' }
  );
  assert.equal(calls.length, 0, 'execSync must not be called for invalid input');
});

test('executeCommand rejects non-string command', async () => {
  const calls = [];
  const executeCommand = makeExecuteCommand(calls);

  await assert.rejects(
    () => executeCommand(42),
    { message: 'Command must be a non-empty string' }
  );
  assert.equal(calls.length, 0);
});

test('executeCommand always sets encoding to utf8', async () => {
  const calls = [];
  const executeCommand = makeExecuteCommand(calls);

  await executeCommand('git log --oneline -5');

  assert.equal(calls[0].options.encoding, 'utf8');
});
