// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Project, Recording, Segment, Speaker, TranscriptResponse } from '@/composables/transcriber/useTranscriberApi'

export const useTranscriberStore = defineStore('transcriber', () => {
  const projects = ref<Project[]>([])
  const activeProject = ref<Project | null>(null)
  const recordings = ref<Recording[]>([])
  const activeRecording = ref<Recording | null>(null)
  const speakers = ref<Speaker[]>([])
  const segments = ref<Segment[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  function setProjects(list: Project[]) { projects.value = list }
  function setActiveProject(p: Project | null) { activeProject.value = p }
  function setRecordings(list: Recording[]) { recordings.value = list }
  function setActiveRecording(r: Recording | null) { activeRecording.value = r }

  function setTranscript(t: TranscriptResponse) {
    activeRecording.value = t.recording
    speakers.value = t.speakers
    segments.value = t.segments
  }

  function updateSegmentText(segmentId: number, text: string) {
    const seg = segments.value.find(s => s.id === segmentId)
    if (seg) { seg.text = text; seg.is_edited = true }
  }

  function updateSpeakerName(speakerId: number, displayName: string) {
    const spk = speakers.value.find(s => s.id === speakerId)
    if (spk) spk.display_name = displayName
  }

  function updateRecordingStatus(recordingId: number, status: Recording['status']) {
    const rec = recordings.value.find(r => r.id === recordingId)
    if (rec) rec.status = status
  }

  function speakerName(speakerId: number | null): string {
    if (!speakerId) return 'Unknown'
    return speakers.value.find(s => s.id === speakerId)?.display_name ?? 'Unknown'
  }

  return {
    projects, activeProject, recordings, activeRecording,
    speakers, segments, loading, error,
    setProjects, setActiveProject, setRecordings, setActiveRecording,
    setTranscript, updateSegmentText, updateSpeakerName, updateRecordingStatus, speakerName,
  }
})
