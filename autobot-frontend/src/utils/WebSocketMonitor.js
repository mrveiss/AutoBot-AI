/**
 * WebSocket Monitor - Tracks WebSocket events for RUM
 */

import rumAgent from './RumAgent.js'

export function createMonitoredWebSocket(url, protocols) {
  const ws = new WebSocket(url, protocols)

  // Track connection attempt
  rumAgent.trackWebSocketEvent('connection_attempt', { url })

  const originalAddEventListener = ws.addEventListener.bind(ws)
  const _originalRemoveEventListener = ws.removeEventListener.bind(ws) // Reserved for future unsubscribe support

  // Override addEventListener to track all events
  ws.addEventListener = function(type, listener, options) {
    const wrappedListener = function(event) {
      // Track the event
      rumAgent.trackWebSocketEvent(type, {
        readyState: ws.readyState,
        url: ws.url,
        timestamp: Date.now()
      })

      // Handle specific events
      if (type === 'error') {
        rumAgent.reportCriticalIssue('websocket_error', {
          url: ws.url,
          readyState: ws.readyState,
          error: event.error || 'WebSocket error'
        })
      } else if (type === 'close') {
        rumAgent.trackWebSocketEvent('connection_closed', {
          code: event.code,
          reason: event.reason,
          wasClean: event.wasClean
        })
      } else if (type === 'open') {
        rumAgent.trackWebSocketEvent('connection_opened', {
          readyState: ws.readyState
        })
      }

      // Call original listener
      return listener.call(this, event)
    }

    return originalAddEventListener(type, wrappedListener, options)
  }

  // Track message sending
  const originalSend = ws.send.bind(ws)
  ws.send = function(data) {
    rumAgent.trackWebSocketEvent('message_sent', {
      dataType: typeof data,
      dataSize: data.length || 0
    })
    return originalSend(data)
  }

  // Track close calls
  const originalClose = ws.close.bind(ws)
  ws.close = function(code, reason) {
    rumAgent.trackWebSocketEvent('close_initiated', { code, reason })
    return originalClose(code, reason)
  }

  return ws
}
