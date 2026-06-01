// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { useApi } from '@/composables/useApi'

export interface Project {
  id: number
  name: string
  description: string
  created_at: string
  user_id: string
}

export interface Recording {
  id: number
  project_id: number
  filename: string
  duration: number | null
  status: 'pending' | 'processing' | 'complete' | 'error'
  speaker_count: number
  process_seconds: number | null
  engine_used: string | null
  language_detected: string | null
  uploaded_at: string
  failure_stage: string | null
  failure_reason: string | null
}

export interface Speaker {
  id: number
  recording_id: number
  label: string
  display_name: string
  language: string | null
}

export interface Segment {
  id: number
  recording_id: number
  speaker_id: number | null
  start_time: number
  end_time: number
  text: string
  original_text: string
  is_edited: boolean
  is_overlap: boolean
}

export interface TranscriptResponse {
  recording: Recording
  speakers: Speaker[]
  segments: Segment[]
}

export interface KbPushStatus {
  pushed: boolean
  pushed_at: string | null
  kb_collection_id: string | null
  pushed_by: string | null
}

export function useTranscriberApi() {
  const api = useApi()
  const base = '/api/transcriber'

  return {
    // Projects
    listProjects: () => api.get<Project[]>(`${base}/projects`),
    getProject: (id: number) => api.get<Project>(`${base}/projects/${id}`),
    createProject: (name: string, description: string) =>
      api.post<Project>(`${base}/projects`, { name, description }),
    updateProject: (id: number, name: string, description: string) =>
      api.patch<Project>(`${base}/projects/${id}`, { name, description }),
    deleteProject: (id: number) => api.delete(`${base}/projects/${id}`),

    // Recordings
    listRecordings: (projectId: number) =>
      api.get<Recording[]>(`${base}/projects/${projectId}/recordings`),
    getRecording: (id: number) => api.get<Recording>(`${base}/recordings/${id}`),
    deleteRecording: (id: number) => api.delete(`${base}/recordings/${id}`),
    uploadRecording: (projectId: number, file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api.post<Recording>(`${base}/projects/${projectId}/recordings`, form)
    },

    // Transcripts
    getTranscript: (recordingId: number) =>
      api.get<TranscriptResponse>(`${base}/recordings/${recordingId}/transcript`),
    updateSegment: (segmentId: number, text: string) =>
      api.patch<Segment>(`${base}/segments/${segmentId}`, { text }),
    updateSpeaker: (speakerId: number, displayName: string) =>
      api.patch<Speaker>(`${base}/speakers/${speakerId}`, { display_name: displayName }),
    createNote: (segmentId: number, content: string) =>
      api.post(`${base}/segments/${segmentId}/notes`, { content }),
    deleteNote: (noteId: number) => api.delete(`${base}/notes/${noteId}`),

    // Export
    exportRecording: (recordingId: number, format: 'docx' | 'pdf' | 'srt' | 'vtt', options = {}) =>
      fetch(`${base}/recordings/${recordingId}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format, ...options }),
      }),

    // AI
    aiAsk: (recordingId: number, action: string, customQuestion?: string) =>
      new EventSource(`${base}/recordings/${recordingId}/ai/ask?action=${action}${customQuestion ? `&q=${encodeURIComponent(customQuestion)}` : ''}`),

    // KB
    kbPush: (recordingId: number, collectionId: string) =>
      api.post(`${base}/recordings/${recordingId}/kb/push`, { collection_id: collectionId }),
    kbStatus: (recordingId: number) =>
      api.get<KbPushStatus>(`${base}/recordings/${recordingId}/kb/status`),
  }
}
