/* YouTube tag, title and description generator (/youtube-tag-generator).
 *
 * One form, three modes. The brief goes to our API, which makes one Gemini
 * text call per click (rate-limited per IP); rendering and copying are local.
 */
import { API_URL, $, el, track, setStatus, copyText, apiError } from './common.js'

const TOOL = 'youtube-metadata'
const form = $('md-form')
const status = $('md-status')
const out = $('md-out')
const submit = $('md-go')
const LABELS = { tags: 'Generate tags', titles: 'Generate titles', description: 'Generate description' }

const mode = () => form.querySelector('input[name="mode"]:checked')?.value || 'tags'

function syncMode() {
  submit.textContent = LABELS[mode()]
}

// Deep links: /youtube-tag-generator#titles opens the titles mode.
const fromHash = (window.location.hash || '').replace('#', '')
if (LABELS[fromHash]) {
  const radio = form.querySelector(`input[name="mode"][value="${fromHash}"]`)
  if (radio) radio.checked = true
}
syncMode()
form.querySelectorAll('input[name="mode"]').forEach((r) => r.addEventListener('change', () => {
  syncMode()
  history.replaceState(null, '', `#${mode()}`)
}))

function renderTags(data) {
  const joined = data.tags.join(', ')
  out.replaceChildren(
    el('div', { class: 'out-head' },
      el('span', { text: `${data.tags.length} tags · ${data.characters} of 500 characters` }),
      el('button', { type: 'button', class: 'btn-ghost', onclick: (e) => copyText(joined, e.currentTarget), text: 'Copy all' })),
    el('div', { class: 'chips' }, ...data.tags.map((t) =>
      el('button', { type: 'button', class: 'chip', title: 'Copy this tag', onclick: (e) => copyText(t, e.currentTarget), text: t }))),
    el('p', { class: 'tool-hint', text: 'Paste "Copy all" into the Tags field in YouTube Studio (Details, Show more). Remove any tag that does not describe your video.' }),
  )
}

function renderTitles(data) {
  out.replaceChildren(
    el('div', { class: 'out-head' }, el('span', { text: `${data.titles.length} titles. Click one to copy it.` })),
    el('ol', { class: 'title-list' }, ...data.titles.map((t) => el('li', {},
      el('button', { type: 'button', class: 'title-opt', onclick: (e) => copyText(t.title, e.currentTarget.querySelector('.cp')) },
        el('span', { class: 'tt', text: t.title }),
        el('span', { class: 'meta', text: `${t.title.length} chars${t.angle ? ` · ${t.angle}` : ''}` }),
        el('span', { class: 'cp', text: 'Copy' }))))),
  )
}

function renderDescription(data) {
  const ta = el('textarea', { class: 'desc-out', rows: '14', 'aria-label': 'Generated description' })
  ta.value = data.description
  out.replaceChildren(
    el('div', { class: 'out-head' },
      el('span', { text: `${data.description.length} of 5,000 characters. Edit it here, then copy.` }),
      el('button', { type: 'button', class: 'btn-ghost', onclick: (e) => copyText(ta.value, e.currentTarget), text: 'Copy' })),
    ta,
  )
}

form.addEventListener('submit', async (e) => {
  e.preventDefault()
  const m = mode()
  const topic = $('md-topic').value.trim()
  if (topic.length < 15) {
    setStatus(status, 'Describe the video in at least a sentence: what happens in it and who it is for.', 'error')
    return
  }
  submit.disabled = true
  setStatus(status, 'Writing...', 'busy')
  try {
    const res = await fetch(`${API_URL}/api/tools/youtube-metadata`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: m, topic, keyword: $('md-keyword').value.trim() }),
    })
    if (!res.ok) {
      const err = await apiError(res)
      track('tool_used', { tool: TOOL, mode: m, ok: false, code: err.code })
      setStatus(status, err.message, 'error')
      return
    }
    const data = await res.json()
    track('tool_used', { tool: TOOL, mode: m, ok: true })
    setStatus(status, '', '')
    if (m === 'tags') renderTags(data)
    else if (m === 'titles') renderTitles(data)
    else renderDescription(data)
    out.hidden = false
    $('md-cta').hidden = false
  } catch (_) {
    track('tool_used', { tool: TOOL, mode: m, ok: false, code: 'network' })
    setStatus(status, 'Could not reach the generator. Check your connection and try again.', 'error')
  } finally {
    submit.disabled = false
  }
})

document.querySelectorAll('[data-example-topic]').forEach((b) => b.addEventListener('click', () => {
  $('md-topic').value = b.dataset.exampleTopic
  $('md-keyword').value = b.dataset.exampleKeyword || ''
  window.scrollTo({ top: 0, behavior: 'smooth' })
  $('md-topic').focus()
}))

$('md-cta-btn')?.addEventListener('click', () => track('tool_cta_click', { tool: TOOL }))
