#!/usr/bin/env node
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * TTS fast-start listening test (#13103).
 *
 * Renders a few representative replies through the REAL chunking code
 * (createTtsStream / createSpeechShaper from src/utils/ttsSentences.ts) at
 * several candidate opening thresholds, synthesizes every chunk separately
 * through the backend's /voice/synthesize -- one request per chunk, as the chat
 * does -- and joins each variant's chunks into one labelled WAV. The owner
 * listens and picks the thresholds; this script does not choose them.
 *
 * Requires Node 22.18+ or 24 (it imports the .ts module directly).
 *
 *   AUTOBOT_API_BASE=https://<slm-or-backend-host>/api \
 *   AUTOBOT_TOKEN=<a logged-in user's bearer token> \
 *   [AUTOBOT_TTS_VOICE=<voice id>] [AUTOBOT_TTS_LANGUAGE=en] \
 *   node autobot-frontend/scripts/tts-listening-test.mjs [out-dir]
 *
 * `--dry` writes only manifest.md (the cut points), with no backend calls.
 *
 * A self-signed certificate needs NODE_EXTRA_CA_CERTS=<ca.pem>.
 * [out-dir] defaults to <os temp dir>/autobot-tts-listening-test.
 * Output: <out-dir>/LISTEN.md (what to listen for), <out-dir>/manifest.md
 * (every chunk's text per variant) and <out-dir>/<reply>/<variant>.wav.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createSpeechShaper, createTtsStream } from '../src/utils/ttsSentences.ts'

const CANDIDATES = [
  { id: 'A-clause12-word40', clauseMinChars: 12, wordMinChars: 40 },
  { id: 'B-clause16-word48', clauseMinChars: 16, wordMinChars: 48 },
  { id: 'C-clause24-word64', clauseMinChars: 24, wordMinChars: 64 },
  { id: 'D-clause32-word80', clauseMinChars: 32, wordMinChars: 80 },
]

// Opening clause boundaries at 14, 21, 31 and 48 chars, so each candidate pair
// cuts a different set of replies; plus the no-pause, held-short-sentence and
// link-first shapes the chunker treats specially.
const REPLIES = {
  '1-comma-at-14':
    'Good question, the cache is rebuilt on the next request, so nothing else is needed on your side.',
  '2-comma-at-21':
    'Looking at your logs, the failure starts in the parser. It reads a stray token and gives up. The fix is small: skip the token and carry on.',
  '3-comma-at-31':
    'After checking the deploy logs, the second node never received its certificate, so the service refused to start.',
  '4-comma-at-48':
    'Once the scheduler has looked at every waiting job, it picks the one with the highest priority and runs it first.',
  '5-long-no-pause':
    'The reason the deployment keeps failing on the second node is that the certificate it expects was never copied over by the provisioning step. Copy it and run the step again.',
  '6-short-sentence-first':
    'Sure. Here is how the scheduler decides which job runs first, step by step, using the priority and the age of each job.',
  '7-link-first':
    '[The parser docs](https://example.invalid/docs) explain this in detail, but the short version is that a blank line always ends the block.',
}

const STREAM_STEP = 4 // characters per simulated LLM token
const SPEECH_PLACEHOLDERS = { url: 'a link', path: 'a file path' } // en voice.speech.*

/** Speak `reply` as the chat does while it streams in; returns [{text, releasedAt}]. */
function chunkLikeTheChat(reply, stream) {
  const shaper = createSpeechShaper(SPEECH_PLACEHOLDERS)
  const chunks = []
  let cursor = 0
  for (let shown = STREAM_STEP; cursor < reply.length && shown < reply.length + STREAM_STEP; shown += STREAM_STEP) {
    const { spans, consumed } = stream.next(reply.slice(cursor, Math.min(shown, reply.length)))
    for (const span of spans) chunks.push({ text: shaper.push(span), releasedAt: Math.min(shown, reply.length) })
    cursor += consumed
  }
  const remainder = reply.slice(cursor)
  if (remainder.trim()) chunks.push({ text: shaper.push(remainder), releasedAt: reply.length })
  return chunks.filter((c) => c.text)
}

function variantsFor(reply) {
  const whole = [{ text: createSpeechShaper(SPEECH_PLACEHOLDERS).push(reply), releasedAt: reply.length }]
  const variants = { '0-whole-reply-one-request': whole, '0-today-no-fast-start': chunkLikeTheChat(reply, createTtsStream(true)) }
  for (const c of CANDIDATES) variants[c.id] = chunkLikeTheChat(reply, createTtsStream(false, c))
  return variants
}

async function synthesize(text) {
  const form = new FormData()
  form.append('text', text)
  if (process.env.AUTOBOT_TTS_VOICE) form.append('voice_id', process.env.AUTOBOT_TTS_VOICE)
  if (process.env.AUTOBOT_TTS_LANGUAGE) form.append('language', process.env.AUTOBOT_TTS_LANGUAGE)
  form.append('stream', 'false')
  const res = await fetch(`${process.env.AUTOBOT_API_BASE}/voice/synthesize`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${process.env.AUTOBOT_TOKEN}` },
    body: form,
  })
  const body = Buffer.from(await res.arrayBuffer())
  if (!res.ok || body.toString('ascii', 0, 4) !== 'RIFF') {
    throw new Error(`synthesize failed (HTTP ${res.status}) for "${text}": ${body.toString('utf8', 0, 300)}`)
  }
  return body
}

/** The fmt and data payloads of a RIFF/WAVE buffer. */
function wavParts(buf) {
  const parts = {}
  for (let off = 12; off + 8 <= buf.length; ) {
    const id = buf.toString('ascii', off, off + 4)
    const size = buf.readUInt32LE(off + 4)
    parts[id] = buf.subarray(off + 8, off + 8 + size)
    off += 8 + size + (size % 2)
  }
  if (!parts['fmt '] || !parts.data) throw new Error('worker returned a WAV without fmt/data chunks')
  return parts
}

/** One WAV holding every chunk back to back, as the chat plays them. */
function joinWavs(wavs) {
  const parsed = wavs.map(wavParts)
  const fmt = parsed[0]['fmt ']
  if (parsed.some((p) => !p['fmt '].equals(fmt))) throw new Error('chunks came back in different audio formats')
  const data = Buffer.concat(parsed.map((p) => p.data))
  const head = Buffer.alloc(20)
  head.write('RIFF', 0, 'ascii')
  head.writeUInt32LE(4 + 8 + fmt.length + 8 + data.length, 4)
  head.write('WAVEfmt ', 8, 'ascii')
  head.writeUInt32LE(fmt.length, 16)
  const dataHead = Buffer.alloc(8)
  dataHead.write('data', 0, 'ascii')
  dataHead.writeUInt32LE(data.length, 4)
  return Buffer.concat([head, fmt, dataHead, data])
}

const LISTEN = `# TTS fast-start listening test (#13103)

Each reply folder has one WAV per variant. \`0-whole-reply-one-request\` is the
reference timbre (the whole reply in one request). \`0-today-no-fast-start\` is
current behaviour. A-D release the opening chunk earlier, at the clause/word
minimums in their names; manifest.md shows exactly where each one cut.

**Listen for, in every A-D clip, at the join after the FIRST chunk:**
1. Does the voice change -- pitch, speed, warmth or loudness -- between the
   first chunk and the rest, compared with the reference?
2. Does the first chunk sound clipped, rushed or oddly stressed on its own?
3. Is the pause at the join longer or more abrupt than a natural comma pause?

Pick the SHORTEST pair whose clips you cannot tell apart from the reference at
the join. If even D has the artifact, the fast start is not worth shipping
(#13103 then closes as not-worth-doing, with this finding recorded).
Note the "released after N chars" figures in manifest.md: that is the latency win.
`

async function main() {
  const dry = process.argv.includes('--dry')
  for (const v of dry ? [] : ['AUTOBOT_API_BASE', 'AUTOBOT_TOKEN']) {
    if (!process.env[v]) throw new Error(`${v} is required (see the header of this script)`)
  }
  // Default outside the checkout, so a run never leaves untracked WAVs in the repo.
  const out = process.argv.slice(2).find((a) => !a.startsWith('--')) || join(tmpdir(), 'autobot-tts-listening-test')
  const manifest = ['# Chunks per variant\n']
  for (const [replyId, reply] of Object.entries(REPLIES)) {
    mkdirSync(join(out, replyId), { recursive: true })
    manifest.push(`## ${replyId}\n\n> ${reply}\n`)
    for (const [variant, chunks] of Object.entries(variantsFor(reply))) {
      if (!dry) {
        const wavs = []
        for (const chunk of chunks) wavs.push(await synthesize(chunk.text))
        writeFileSync(join(out, replyId, `${variant}.wav`), joinWavs(wavs))
      }
      manifest.push(`- **${variant}** -- first chunk released after ${chunks[0].releasedAt} chars`)
      for (const c of chunks) manifest.push(`  - \`${c.text}\``)
      if (!dry) process.stdout.write(`wrote ${replyId}/${variant}.wav (${chunks.length} chunks)\n`)
    }
    manifest.push('')
  }
  writeFileSync(join(out, 'manifest.md'), manifest.join('\n'), 'utf8')
  writeFileSync(join(out, 'LISTEN.md'), LISTEN, 'utf8')
  process.stdout.write(`done: open ${join(out, 'LISTEN.md')}\n`)
}

main().catch((err) => {
  process.stderr.write(`${err.message}\n`)
  process.exit(1)
})
