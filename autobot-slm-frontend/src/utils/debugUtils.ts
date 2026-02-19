// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Debug Utilities
 *
 * Provides structured logging for the SLM Admin frontend.
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error'

interface Logger {
  debug: (...args: unknown[]) => void
  info: (...args: unknown[]) => void
  warn: (...args: unknown[]) => void
  error: (...args: unknown[]) => void
}

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
}

// Default to 'info' in production, 'debug' in development
const currentLevel: LogLevel = import.meta.env.DEV ? 'debug' : 'info'

function shouldLog(level: LogLevel): boolean {
  return LOG_LEVELS[level] >= LOG_LEVELS[currentLevel]
}

function formatMessage(component: string, level: LogLevel, _args: unknown[]): string {
  const timestamp = new Date().toISOString()
  const prefix = `[${timestamp}] [${level.toUpperCase()}] [${component}]`
  return prefix
}

/**
 * Create a logger instance for a component
 */
export function createLogger(componentName: string): Logger {
  return {
    debug: (...args: unknown[]) => {
      if (shouldLog('debug')) {
        // eslint-disable-next-line no-console
        console.debug(formatMessage(componentName, 'debug', args), ...args)
      }
    },
    info: (...args: unknown[]) => {
      if (shouldLog('info')) {
        // eslint-disable-next-line no-console
        console.info(formatMessage(componentName, 'info', args), ...args)
      }
    },
    warn: (...args: unknown[]) => {
      if (shouldLog('warn')) {
        // eslint-disable-next-line no-console
        console.warn(formatMessage(componentName, 'warn', args), ...args)
      }
    },
    error: (...args: unknown[]) => {
      if (shouldLog('error')) {
        // eslint-disable-next-line no-console
        console.error(formatMessage(componentName, 'error', args), ...args)
      }
    },
  }
}
