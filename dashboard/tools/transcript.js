/* YouTube transcript generator (/youtube-transcript-generator).
 *
 * Asks our API for the captions the video already has on YouTube and renders
 * them with timestamps, plus copy / TXT / SRT export. Everything past the
 * fetch happens here in the browser.
 */
import { API_URL, $, el, track, setStatus, copyText, downloadBlob, safeFilename, apiError, openInApp } from './common.js'

const TOOL = 'youtube-transcript'
const form = $('yt-form')
const input = $('yt-url')
const status = $('yt-status')
const result = $('yt-result')
const out = $('yt-text')
const langSel = $('yt-lang')
const tsBox = $('yt-ts')
const submit = form.querySelector('button[type="submit"]')
let current = null
let currentUrl = ''

const clock = (s, srt) => {
  const ms = Math.round(s * 1000)
  const h = Math.floor(ms / 3600000)
  const m = Math.floor((ms % 3600000) / 60000)
  const sec = Math.floor((ms % 60000) / 1000)
  const pad = (n, w = 2) => String(n).padStart(w, '0')
  if (srt) return `${pad(h)}:${pad(m)}:${pad(sec)},${pad(ms % 1000, 3)}`
  return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`
}

const asText = (segs, withTs) =>
  segs.map((s) => (withTs ? `[${clock(s.start)}] ${s.text}` : s.text)).join(withTs ? '\n' : ' ')
    .replace(/ {2,}/g, ' ')

const asSrt = (segs) =>
  segs.map((s, i) => {
    const end = s.start + Math.max(s.dur || 0, 0.5)
    return `${i + 1}\n${clock(s.start, true)} --> ${clock(end, true)}\n${s.text}\n`
  }).join('\n')

function render() {
  if (!current) return
  const withTs = tsBox.checked
  out.replaceChildren()
  if (!withTs) {
    out.append(el('p', { text: asText(current.segments, false) }))
    return
  }
  const frag = document.createDocumentFragment()
  for (const s of current.segments) {
    frag.append(el('p', {},
      el('a', {
        class: 'ts',
        href: `https://www.youtube.com/watch?v=${current.video_id}&t=${Math.floor(s.start)}s`,
        target: '_blank', rel: 'noopener',
        text: clock(s.start),
      }),
      ' ', s.text))
  }
  out.append(frag)
}

function showNoCaptions(message) {
  result.hidden = true
  status.replaceChildren(
    el('p', {}, el('strong', { text: 'No captions to read. ' }), message || ''),
    el('p', { text: 'OpenShorts runs its own speech recognition on the audio, word by word, so it can transcribe this video and cut it into vertical clips with subtitles. 20 free minutes a month, no credit card.' }),
    el('button', {
      type: 'button', class: 'btn-primary',
      onclick: () => openInApp(currentUrl, TOOL),
      text: 'Transcribe and clip it with OpenShorts',
    }),
  )
  status.dataset.kind = 'warn'
  status.hidden = false
}

async function load(url, lang) {
  currentUrl = url
  submit.disabled = true
  setStatus(status, 'Reading the captions from YouTube...', 'busy')
  const t0 = performance.now()
  try {
    const q = new URLSearchParams({ url })
    if (lang) q.set('lang', lang)
    const res = await fetch(`${API_URL}/api/tools/youtube-transcript?${q}`)
    if (!res.ok) {
      const err = await apiError(res)
      track('tool_used', { tool: TOOL, ok: false, code: err.code })
      if (err.code === 'no_captions') return showNoCaptions(err.message)
      setStatus(status, err.message, 'error')
      return
    }
    current = await res.json()
    track('tool_used', { tool: TOOL, ok: true, kind: current.kind, cached: !!current.cached,
      ms: Math.round(performance.now() - t0) })
    $('yt-title').textContent = current.title
    const mins = Math.round((current.duration || 0) / 60)
    const words = current.segments.reduce((n, s) => n + s.text.split(/\s+/).length, 0)
    $('yt-sub').textContent = [
      current.channel,
      mins ? `${mins} min` : '',
      `${words.toLocaleString('en-US')} words`,
      current.kind === 'auto' ? 'YouTube auto-generated captions' : 'captions uploaded by the creator',
    ].filter(Boolean).join(' · ')
    langSel.replaceChildren(...current.languages.map((l) => el('option', {
      value: l.request,
      selected: l.code === current.language && l.kind === current.kind,
      text: l.name,
    })))
    langSel.hidden = current.languages.length < 2
    render()
    setStatus(status, '', '')
    result.hidden = false
  } catch (_) {
    track('tool_used', { tool: TOOL, ok: false, code: 'network' })
    setStatus(status, 'Could not reach the transcript service. Check your connection and try again.', 'error')
  } finally {
    submit.disabled = false
  }
}

form.addEventListener('submit', (e) => {
  e.preventDefault()
  const url = input.value.trim()
  if (!url) return
  load(url)
})
langSel.addEventListener('change', () => load(currentUrl, langSel.value))
tsBox.addEventListener('change', render)
$('yt-copy').addEventListener('click', (e) => current && copyText(asText(current.segments, tsBox.checked), e.currentTarget))
$('yt-txt').addEventListener('click', () => {
  if (!current) return
  downloadBlob(new Blob([asText(current.segments, tsBox.checked)], { type: 'text/plain;charset=utf-8' }),
    `${safeFilename(current.title, current.video_id)}.txt`)
})
$('yt-srt').addEventListener('click', () => {
  if (!current) return
  downloadBlob(new Blob([asSrt(current.segments)], { type: 'application/x-subrip;charset=utf-8' }),
    `${safeFilename(current.title, current.video_id)}.srt`)
})
$('yt-clip').addEventListener('click', () => openInApp(currentUrl, TOOL))

// Example buttons in the page copy fill the form and run it.
document.querySelectorAll('[data-example-url]').forEach((b) => b.addEventListener('click', () => {
  input.value = b.dataset.exampleUrl
  window.scrollTo({ top: 0, behavior: 'smooth' })
  load(input.value)
}))
