// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Speech shaping (#13102): markdown, URLs, paths and fenced code are shaped
 * for the SPOKEN copy only; ordinary prose survives untouched.
 */
import { describe, it, expect } from 'vitest'
import { createSpeechShaper, extractCompleteSentences, shapeForSpeech } from '../ttsSentences'

const PH = { url: 'LINK', path: 'PATH' }
const shape = (text: string) => shapeForSpeech(text, PH)

describe('shapeForSpeech — markdown (#13102)', () => {
  it('speaks link text, inline-code contents, and drops emphasis, headings, quotes and list markers', () => {
    const md = '## Setup\n> Note: **read** the [guide](https://x.io/g) first.\n- run `make` _now_\n1. done ~~old~~'
    expect(shape(md)).toBe('Setup Note: read the guide first. run make now done old')
  })

  it('repairs a missing space at a sentence join', () => {
    expect(shape('It works now.Right after that, restart.')).toBe('It works now. Right after that, restart.')
  })
})

describe('shapeForSpeech — URLs and paths (#13102)', () => {
  it('replaces a URL with the placeholder and keeps the sentence punctuation', () => {
    expect(shape('See https://example.com/docs?a=1.')).toBe('See LINK.')
    expect(shape('Visit www.example.org, then return.')).toBe('Visit LINK, then return.')
  })

  it('replaces path-shaped tokens and code filenames', () => {
    expect(shape('Edit autobot-backend/llc/adapters/base.py today.')).toBe('Edit PATH today.')
    expect(shape('Open /etc/hosts and ./run.sh and ~/notes/todo.')).toBe('Open PATH and PATH and PATH.')
    expect(shape('The bug is in ChatInterface.vue.')).toBe('The bug is in PATH.')
    expect(shape('Open C:\\Users\\Alex\\report.txt now.')).toBe('Open PATH now.')
  })
})

describe('shapeForSpeech — prose false positives survive (#13102)', () => {
  it.each([
    'Choose cats and/or dogs.',
    'Support runs 24/7.',
    'Use a tool, e.g. a hammer.',
    'Pi is about 3.14 today.',
    'Read arr[0] first.',
    'It runs on Node.js now.',
    'Set my_var to 2 * 3.',
    'The /etc folder holds config.',
    'It shipped on 2024/01/02.',
    'Ask he/she/they first.',
    'It speaks TCP/IP/UDP fluently.',
  ])('%s', (prose) => {
    expect(shape(prose)).toBe(prose)
  })
})

describe('createSpeechShaper — fenced code (#13102)', () => {
  it('drops a fenced block entirely', () => {
    expect(shape('Before.\n```python\nsecret()\n```\nAfter.')).toBe('Before. After.')
  })

  it('drops the block when the ``` marker splits across two streamed deltas', () => {
    const shaper = createSpeechShaper(PH)
    const spoken = [
      shaper.push('Before\n``'),
      shaper.push('`py\nsecret()\n`'),
      shaper.push('``\nAfter.'),
      shaper.flush(),
    ].filter(Boolean)

    expect(spoken).toEqual(['Before', 'After.'])
  })

  it('keeps fence state across slices: nothing inside an open fence is spoken', () => {
    const shaper = createSpeechShaper(PH)
    expect(shaper.push('Code:\n```')).toBe('Code:')
    expect(shaper.push('rm -rf build. ')).toBe('')
    expect(shaper.flush()).toBe('')
  })

  it('does not treat ``` in the middle of a line as a fence', () => {
    expect(shape('Use ``` to mark code. Then continue.')).toBe('Use to mark code. Then continue.')
  })

  it('keeps a four-backtick block closed against an inner ``` line', () => {
    expect(shape('Intro.\n````md\n```\nsecret()\n```\n````\nAfter.')).toBe('Intro. After.')
  })

  it('drops a ~~~ fence, including when its marker splits across slices', () => {
    expect(shape('Intro.\n~~~\nsecret()\n~~~\nOutro.')).toBe('Intro. Outro.')
    const shaper = createSpeechShaper(PH)
    expect([shaper.push('Intro\n~~'), shaper.push('~\nsecret()\n~~~\nOutro.')]).toEqual(['Intro', 'Outro.'])
  })

  it('does not swallow ~~strikethrough~~ at the start of a slice', () => {
    const shaper = createSpeechShaper(PH)
    expect([shaper.push('Intro\n~~'), shaper.push('old~~ news.')]).toEqual(['Intro', 'old news.'])
  })

  it('knows a fence is open after being primed with skipped text', () => {
    // ChatInterface primes the shaper with the text voice was enabled after
    const shaper = createSpeechShaper(PH)
    shaper.push('Setup:\n```bash\nmake')
    expect(shaper.push('\nrm -rf build\n```\nDone.')).toBe('Done.')
  })

  it('treats a split single backtick as inline code', () => {
    const shaper = createSpeechShaper(PH)
    expect(shaper.push('Run `')).toBe('Run')
    expect(shaper.push('ls` now.')).toBe('ls now.')
  })

  it('never speaks a held partial marker, even when the reply ends on it', () => {
    const shaper = createSpeechShaper(PH)
    expect(shaper.push('odd ``')).toBe('odd')
    expect(shaper.flush()).toBe('')
  })

  it('keeps the sentence period after a path at the end of a sentence', () => {
    expect(shape('Now edit src/app/main.py.')).toBe('Now edit PATH.')
  })

  it('speaks a slice that ends on a closing inline-code backtick without leaking it', () => {
    const shaper = createSpeechShaper(PH)
    expect(shaper.push('Then use `ls`')).toBe('Then use ls')
    expect(shaper.push(' to list.')).toBe('to list.')
  })
})

describe('transcript is unaffected by shaping (#13102)', () => {
  it('advances the streaming cursor over the RAW text while only the spoken copy is shaped', () => {
    // Mirrors ChatInterface's watcher: cursor accounting runs on the displayed
    // message content; the shaper only sees the slices handed to TTS.
    const transcript = 'First see [docs](https://a.io/x) now. Then edit src/app/main.py please. '
    const before = transcript
    const shaper = createSpeechShaper(PH)

    const { sentences, spans, consumed } = extractCompleteSentences(transcript, 20)
    const spoken = spans.map((span) => shaper.push(span))

    expect(transcript).toBe(before)
    expect(consumed).toBe(transcript.length)
    expect(sentences.map((s) => s.trim()).join(' ')).toBe(transcript.trim())
    expect(spans.join('')).toBe(transcript.slice(0, consumed))
    expect(spoken).toEqual(['First see docs now.', 'Then edit PATH please.'])
  })
})
