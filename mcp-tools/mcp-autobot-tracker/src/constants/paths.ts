/**
 * Path Constants for MCP AutoBot Tracker
 * ======================================
 * 
 * Centralized path configuration to eliminate hardcoded paths.
 * Paths are resolved relative to PROJECT_ROOT for portability.
 * 
 * Usage:
 *   import { PathConstants } from './constants/paths';
 *   const logPath = PathConstants.BACKEND_LOG;
 */

import * as path from 'path';
import * as os from 'os';

/**
 * Detect project root directory dynamically
 * Assumes MCP tracker is in mcp-tools/mcp-autobot-tracker/
 */
const PROJECT_ROOT = path.resolve(__dirname, '..', '..', '..', '..');

/**
 * Centralized path constants - NO HARDCODED PATHS
 */
export const PathConstants = {
  // Project root
  PROJECT_ROOT,

  // Core directories
  CONFIG_DIR: path.join(PROJECT_ROOT, 'config'),
  DATA_DIR: path.join(PROJECT_ROOT, 'data'),
  LOGS_DIR: path.join(PROJECT_ROOT, 'logs'),
  DOCS_DIR: path.join(PROJECT_ROOT, 'docs'),
  SRC_DIR: path.join(PROJECT_ROOT, 'src'),
  TESTS_DIR: path.join(PROJECT_ROOT, 'tests'),
  BACKEND_DIR: path.join(PROJECT_ROOT, 'backend'),
  FRONTEND_DIR: path.join(PROJECT_ROOT, 'autobot-vue'),

  // Data subdirectories
  CONVERSATIONS_DIR: path.join(PROJECT_ROOT, 'data', 'conversations'),
  CHAT_HISTORY_DIR: path.join(PROJECT_ROOT, 'data', 'chat_history'),
  SYSTEM_KNOWLEDGE_DIR: path.join(PROJECT_ROOT, 'data', 'system_knowledge'),
  SECURITY_DATA_DIR: path.join(PROJECT_ROOT, 'data', 'security'),
  CHECKPOINTS_DIR: path.join(PROJECT_ROOT, 'data', 'checkpoints'),

  // Log file paths
  BACKEND_LOG: path.join(PROJECT_ROOT, 'logs', 'backend.log'),
  FRONTEND_LOG: path.join(PROJECT_ROOT, 'logs', 'frontend.log'),
  REDIS_LOG: path.join(PROJECT_ROOT, 'logs', 'redis.log'),
  CHAT_LOG: path.join(PROJECT_ROOT, 'data', 'logs', 'chat.log'),

  // User home directory
  USER_HOME: os.homedir(),
} as const;

/**
 * Helper function to get config file path
 */
export function getConfigPath(...parts: string[]): string {
  return path.join(PathConstants.CONFIG_DIR, ...parts);
}

/**
 * Helper function to get data file path
 */
export function getDataPath(...parts: string[]): string {
  return path.join(PathConstants.DATA_DIR, ...parts);
}

/**
 * Helper function to get log file path
 */
export function getLogPath(...parts: string[]): string {
  return path.join(PathConstants.LOGS_DIR, ...parts);
}
