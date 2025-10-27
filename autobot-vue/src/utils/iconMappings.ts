/**
 * Icon Mappings Utility
 *
 * Centralized icon mappings for status indicators, connections, and common UI elements.
 * This eliminates duplicate icon mapping logic across 10+ components.
 *
 * @see analysis/frontend-refactoring/FRONTEND_REFACTORING_EXAMPLES.md
 *
 * Usage:
 * ```typescript
 * import { getStatusIcon, getConnectionIcon, getActionIcon } from '@/utils/iconMappings'
 *
 * // Get icon class for status
 * const icon = getStatusIcon('healthy') // 'fas fa-check-circle'
 *
 * // Get icon with color
 * const iconWithColor = getStatusIcon('error', { withColor: true }) // 'fas fa-times-circle text-danger'
 *
 * // Get connection icon
 * const connIcon = getConnectionIcon('testing') // 'fas fa-spinner fa-spin'
 * ```
 */

export type StatusType =
  | 'healthy'
  | 'warning'
  | 'error'
  | 'degraded'
  | 'critical'
  | 'offline'
  | 'unknown'

export type ConnectionType =
  | 'connected'
  | 'disconnected'
  | 'testing'
  | 'connecting'
  | 'unknown'

export type ActionType =
  | 'loading'
  | 'refreshing'
  | 'play'
  | 'stop'
  | 'pause'
  | 'sync'
  | 'save'
  | 'edit'
  | 'delete'
  | 'add'

export interface IconOptions {
  /**
   * Include Tailwind color classes (text-success, text-danger, etc.)
   */
  withColor?: boolean

  /**
   * Use alternative icon style (outlined, solid, etc.)
   */
  style?: 'solid' | 'outlined'

  /**
   * Additional CSS classes to append
   */
  extraClasses?: string
}

// ========================================
// Status Icon Mappings
// ========================================

/**
 * Health/Status icon mappings
 * Used in: BackendSettings, MonitoringDashboard, MCPDashboard, SystemStatusIndicator
 */
const statusIconMap: Record<StatusType, string> = {
  healthy: 'fas fa-check-circle',
  warning: 'fas fa-exclamation-triangle',
  error: 'fas fa-times-circle',
  degraded: 'fas fa-exclamation-triangle',
  critical: 'fas fa-times-circle',
  offline: 'fas fa-power-off',
  unknown: 'fas fa-question-circle'
}

/**
 * Status color class mappings for Tailwind
 */
const statusColorMap: Record<StatusType, string> = {
  healthy: 'text-success',
  warning: 'text-warning',
  error: 'text-danger',
  degraded: 'text-warning',
  critical: 'text-danger',
  offline: 'text-muted',
  unknown: 'text-muted'
}

// ========================================
// Connection Icon Mappings
// ========================================

/**
 * Connection status icon mappings
 * Used in: BackendSettings, Terminal, ToolsTerminal, MultiMachineHealth
 */
const connectionIconMap: Record<ConnectionType, string> = {
  connected: 'fas fa-check-circle',
  disconnected: 'fas fa-times-circle',
  testing: 'fas fa-spinner fa-spin',
  connecting: 'fas fa-spinner fa-spin',
  unknown: 'fas fa-question-circle'
}

/**
 * Connection color class mappings
 */
const connectionColorMap: Record<ConnectionType, string> = {
  connected: 'text-success',
  disconnected: 'text-danger',
  testing: 'text-info',
  connecting: 'text-info',
  unknown: 'text-muted'
}

// ========================================
// Action Icon Mappings
// ========================================

/**
 * Common action icon mappings
 * Used throughout the application for buttons and indicators
 */
const actionIconMap: Record<ActionType, string> = {
  loading: 'fas fa-spinner fa-spin',
  refreshing: 'fas fa-sync fa-spin',
  play: 'fas fa-play',
  stop: 'fas fa-stop',
  pause: 'fas fa-pause',
  sync: 'fas fa-sync',
  save: 'fas fa-save',
  edit: 'fas fa-edit',
  delete: 'fas fa-trash',
  add: 'fas fa-plus'
}

// ========================================
// Public API Functions
// ========================================

/**
 * Get icon class for health/status indicators
 *
 * @param status - Status type
 * @param options - Icon options (color, extra classes)
 * @returns CSS class string for the icon
 *
 * @example
 * ```typescript
 * getStatusIcon('healthy') // 'fas fa-check-circle'
 * getStatusIcon('error', { withColor: true }) // 'fas fa-times-circle text-danger'
 * getStatusIcon('warning', { extraClasses: 'mr-2' }) // 'fas fa-exclamation-triangle mr-2'
 * ```
 */
export function getStatusIcon(status: StatusType | string, options: IconOptions = {}): string {
  const normalizedStatus = (String(status || '').toLowerCase() || 'unknown') as StatusType
  const iconClass = statusIconMap[normalizedStatus] || statusIconMap.unknown

  const classes = [iconClass]

  if (options.withColor) {
    classes.push(statusColorMap[normalizedStatus] || statusColorMap.unknown)
  }

  if (options.extraClasses) {
    classes.push(options.extraClasses)
  }

  return classes.join(' ')
}

/**
 * Get icon class for connection status indicators
 *
 * @param status - Connection status type
 * @param options - Icon options
 * @returns CSS class string for the icon
 *
 * @example
 * ```typescript
 * getConnectionIcon('connected') // 'fas fa-check-circle'
 * getConnectionIcon('testing') // 'fas fa-spinner fa-spin'
 * getConnectionIcon('disconnected', { withColor: true }) // 'fas fa-times-circle text-danger'
 * ```
 */
export function getConnectionIcon(status: ConnectionType | string, options: IconOptions = {}): string {
  const normalizedStatus = (String(status || '').toLowerCase() || 'unknown') as ConnectionType
  const iconClass = connectionIconMap[normalizedStatus] || connectionIconMap.unknown

  const classes = [iconClass]

  if (options.withColor) {
    classes.push(connectionColorMap[normalizedStatus] || connectionColorMap.unknown)
  }

  if (options.extraClasses) {
    classes.push(options.extraClasses)
  }

  return classes.join(' ')
}

/**
 * Get icon class for action buttons and indicators
 *
 * @param action - Action type
 * @param options - Icon options
 * @returns CSS class string for the icon
 *
 * @example
 * ```typescript
 * getActionIcon('loading') // 'fas fa-spinner fa-spin'
 * getActionIcon('save', { extraClasses: 'mr-1' }) // 'fas fa-save mr-1'
 * ```
 */
export function getActionIcon(action: ActionType | string, options: IconOptions = {}): string {
  const normalizedAction = (String(action || '').toLowerCase() || 'loading') as ActionType
  const iconClass = actionIconMap[normalizedAction] || actionIconMap.loading

  const classes = [iconClass]

  if (options.extraClasses) {
    classes.push(options.extraClasses)
  }

  return classes.join(' ')
}

/**
 * Generic icon getter - auto-detects type based on status value
 *
 * @param status - Status string (auto-detects if it's health, connection, or action)
 * @param options - Icon options
 * @returns CSS class string for the icon
 *
 * @example
 * ```typescript
 * getIcon('healthy') // Auto-detects as status -> 'fas fa-check-circle'
 * getIcon('testing') // Auto-detects as connection -> 'fas fa-spinner fa-spin'
 * getIcon('loading') // Auto-detects as action -> 'fas fa-spinner fa-spin'
 * ```
 */
export function getIcon(status: string, options: IconOptions = {}): string {
  const normalized = String(status || '').toLowerCase() || 'unknown'

  // Try status mapping first
  if (normalized in statusIconMap) {
    return getStatusIcon(normalized as StatusType, options)
  }

  // Try connection mapping
  if (normalized in connectionIconMap) {
    return getConnectionIcon(normalized as ConnectionType, options)
  }

  // Try action mapping
  if (normalized in actionIconMap) {
    return getActionIcon(normalized as ActionType, options)
  }

  // Fallback to unknown status
  return getStatusIcon('unknown', options)
}

// ========================================
// Export Mappings (for advanced usage)
// ========================================

/**
 * Export raw mappings for direct access if needed
 */
export const iconMappings = {
  status: statusIconMap,
  statusColors: statusColorMap,
  connection: connectionIconMap,
  connectionColors: connectionColorMap,
  action: actionIconMap
} as const
