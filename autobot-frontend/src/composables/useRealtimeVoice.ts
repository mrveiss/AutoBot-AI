/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * useRealtimeVoice.ts - WebRTC Realtime voice mode (#7345)
 * RTCPeerConnection to OpenAI Realtime via backend SDP proxy.
 * Tool calls round-trip through POST /api/voice/realtime/tools/call.
 */

import { ref } from 'vue'
import { getApiBase } from '@/config/ssot-config'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useRealtimeVoice')

// ─── Types ───────────────────────────────────────────────

export interface RealtimeTool {
  name: string
  description: string
  parameters: Record<string, unknown>
}

export type RealtimeConnectionState =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'failed'

interface OaiToolCall {
  call_id: string
  name: string
  arguments: string
}

// ─── Module-level state (singleton) ─────────────────────

const connectionState = ref<RealtimeConnectionState>('disconnected')
const errorMessage = ref('')
// Issue #7421: surface disconnect reason from cap-breach events
const disconnectReason = ref<string | null>(null)

let _peerConnection: RTCPeerConnection | null = null
let _dataChannel: RTCDataChannel | null = null
let _localStream: MediaStream | null = null
// Issue #7421: session_id from backend header — used to finalise telemetry on disconnect
let _sessionId: string | null = null
// In-flight tool calls keyed by call_id — aborted on disconnect
const _pendingToolCalls = new Map<string, AbortController>()

// ─── Helpers ─────────────────────────────────────────────

function _cleanup(reason = 'normal'): void {
  _pendingToolCalls.forEach((ctrl) => ctrl.abort())
  _pendingToolCalls.clear()

  // Issue #7421: notify backend to finalise telemetry
  if (_sessionId) {
    const sid = _sessionId
    _sessionId = null
    void fetchWithAuth(`${getApiBase()}/voice/realtime/session/${sid}/end`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    }).catch((e) => logger.debug('telemetry end call failed:', e))
  }

  if (_dataChannel) {
    _dataChannel.close()
    _dataChannel = null
  }
  if (_peerConnection) {
    _peerConnection.close()
    _peerConnection = null
  }
  if (_localStream) {
    _localStream.getTracks().forEach((t) => t.stop())
    _localStream = null
  }
}

function _sendDataChannelEvent(event: Record<string, unknown>): void {
  if (_dataChannel?.readyState !== 'open') {
    logger.warn('Data channel not open — dropping event:', event.type)
    return
  }
  _dataChannel.send(JSON.stringify(event))
}

async function _registerTools(tools: RealtimeTool[]): Promise<void> {
  if (!tools.length) return
  _sendDataChannelEvent({
    type: 'session.update',
    session: {
      tools: tools.map((t) => ({
        type: 'function',
        name: t.name,
        description: t.description,
        parameters: t.parameters,
      })),
      tool_choice: 'auto',
    },
  })
  logger.debug('Registered %d tools via session.update', tools.length)
}

async function _fetchTools(): Promise<RealtimeTool[]> {
  try {
    const res = await fetchWithAuth(`${getApiBase()}/voice/realtime/tools`, {
      method: 'GET',
    })
    if (!res.ok) {
      logger.warn('Failed to fetch realtime tools: %s', res.status)
      return []
    }
    const data = await res.json() as { tools?: RealtimeTool[] }
    return data.tools ?? []
  } catch (e) {
    logger.warn('Tool fetch error:', e)
    return []
  }
}

async function _dispatchToolCall(call: OaiToolCall): Promise<void> {
  const ctrl = new AbortController()
  _pendingToolCalls.set(call.call_id, ctrl)

  try {
    const res = await fetchWithAuth(`${getApiBase()}/voice/realtime/tools/call`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        call_id: call.call_id,
        name: call.name,
        arguments: call.arguments,
      }),
      signal: ctrl.signal,
    })

    if (!res.ok) {
      logger.warn('Tool call %s failed: %s', call.call_id, res.status)
      _sendDataChannelEvent({
        type: 'conversation.item.create',
        item: {
          type: 'function_call_output',
          call_id: call.call_id,
          output: JSON.stringify({ error: `Backend returned ${res.status}` }),
        },
      })
      return
    }

    const result = await res.json() as unknown
    _sendDataChannelEvent({
      type: 'conversation.item.create',
      item: {
        type: 'function_call_output',
        call_id: call.call_id,
        output: JSON.stringify(result),
      },
    })
    // Ask the model to generate a response after tool output
    _sendDataChannelEvent({ type: 'response.create' })
    logger.debug('Tool call %s dispatched and result sent', call.call_id)
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return
    logger.error('Tool call dispatch error:', e)
  } finally {
    _pendingToolCalls.delete(call.call_id)
  }
}

// ─── oai-events handler ──────────────────────────────────

function _handleDataChannelMessage(raw: string): void {
  let event: { type?: string; [k: string]: unknown }
  try {
    event = JSON.parse(raw) as typeof event
  } catch {
    logger.warn('Non-JSON data channel message — ignoring')
    return
  }

  switch (event.type) {
    case 'session.created':
      logger.debug('Realtime session created')
      break
    case 'response.function_call_arguments.done': {
      const call = event as unknown as {
        type: string; call_id: string; name: string; arguments: string
      }
      void _dispatchToolCall({
        call_id: call.call_id,
        name: call.name,
        arguments: call.arguments,
      })
      break
    }
    // Issue #7421: forward response.done usage to backend telemetry
    case 'response.done': {
      if (_sessionId) {
        const usage = (event as { response?: { usage?: Record<string, number> } }).response?.usage
        if (usage) {
          void fetchWithAuth(`${getApiBase()}/voice/realtime/session/${_sessionId}/response_done`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              input_tokens: usage.input_tokens ?? 0,
              output_tokens: usage.output_tokens ?? 0,
              cached_input_tokens: usage.input_token_details?.cached_tokens ?? 0,
            }),
          }).then(async (res) => {
            if (res.ok) {
              const data = await res.json() as { status?: string; reason?: string; message?: string }
              if (data.status === 'cap_breach') {
                // Backend has ended the session — surface reason to user
                disconnectReason.value = data.message ?? 'Session limit reached'
                _cleanup(data.reason ?? 'cap_breach')
                connectionState.value = 'disconnected'
              }
            }
          }).catch((e) => logger.debug('response_done telemetry failed:', e))
        }
      }
      break
    }
    case 'error':
      logger.error('oai-events error:', event)
      errorMessage.value = String((event as { message?: string }).message ?? 'Realtime error')
      break
    default:
      logger.debug('oai-event:', event.type)
  }
}

// ─── Main composable ─────────────────────────────────────

export function useRealtimeVoice() {
  /**
   * Connect to OpenAI Realtime via backend SDP proxy.
   * 1. getUserMedia
   * 2. create RTCPeerConnection + oai-events data channel
   * 3. createOffer → POST /api/voice/realtime/session → setRemoteDescription
   * 4. register tool list via session.update
   */
  async function connect(): Promise<void> {
    if (_peerConnection) {
      logger.warn('Already connected — ignoring connect() call')
      return
    }

    connectionState.value = 'connecting'
    errorMessage.value = ''

    try {
      // Step 1: mic
      if (!navigator.mediaDevices?.getUserMedia || !window.isSecureContext) {
        throw new Error('Microphone unavailable: HTTPS with a trusted cert is required.')
      }
      _localStream = await navigator.mediaDevices.getUserMedia({ audio: true })

      // Step 2: peer + data channel
      _peerConnection = new RTCPeerConnection()

      _localStream.getTracks().forEach((track) => {
        _peerConnection!.addTrack(track, _localStream!)
      })

      _dataChannel = _peerConnection.createDataChannel('oai-events')
      _dataChannel.onopen = () => {
        logger.debug('oai-events data channel open')
        void _fetchTools().then((tools) => _registerTools(tools))
      }
      _dataChannel.onmessage = (ev) => _handleDataChannelMessage(ev.data as string)
      _dataChannel.onclose = () => logger.debug('oai-events data channel closed')

      _peerConnection.onconnectionstatechange = () => {
        const s = _peerConnection?.connectionState
        logger.debug('PeerConnection state:', s)
        if (s === 'connected') {
          connectionState.value = 'connected'
        } else if (s === 'failed' || s === 'closed') {
          connectionState.value = s === 'failed' ? 'failed' : 'disconnected'
          if (s === 'failed') {
            errorMessage.value = 'WebRTC connection failed.'
          }
        }
      }

      // Step 3: SDP exchange
      const offer = await _peerConnection.createOffer()
      await _peerConnection.setLocalDescription(offer)

      const sessionRes = await fetchWithAuth(`${getApiBase()}/voice/realtime/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sdp: offer.sdp }),
      })

      if (!sessionRes.ok) {
        throw new Error(`SDP proxy returned ${sessionRes.status}`)
      }

      // Issue #7421: capture session_id for telemetry
      _sessionId = sessionRes.headers.get('X-Realtime-Session-Id')

      const sessionData = await sessionRes.json() as { sdp: string }
      await _peerConnection.setRemoteDescription(
        new RTCSessionDescription({ type: 'answer', sdp: sessionData.sdp }),
      )

      logger.debug('WebRTC Realtime connection established session_id=%s', _sessionId)
    } catch (e) {
      const err = e instanceof Error ? e : new Error(String(e))
      logger.error('Realtime connect failed:', err)
      errorMessage.value = err.message || 'Realtime connection failed.'
      connectionState.value = 'failed'
      _cleanup()
    }
  }

  function disconnect(reason = 'normal'): void {
    _cleanup(reason)
    connectionState.value = 'disconnected'
    errorMessage.value = ''
    logger.debug('Realtime voice disconnected reason=%s', reason)
  }

  return {
    connectionState,
    errorMessage,
    // Issue #7421: expose disconnect reason (cap breach message) to UI
    disconnectReason,
    connect,
    disconnect,
  }
}
