/* Shared helpers for the free tool pages.
 *
 * These pages are static HTML emitted by vite-plugin-seo.js; the markup of
 * each tool is already in the document (so crawlers and no-JS clients see the
 * form), and these modules only wire it up. No React, no framework: the
 * biggest of them is the video converter, and that weight is mediabunny.
 */

// Same variable the app uses. Empty means same-origin (self-host behind one host).
export const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

/* OpenPanel events. window.op is the queueing stub the page head defines; it
 * only ever flushes when the analytics init passed its host/placeholder guard,
 * so on localhost, a fork or a preview build this records nothing. */
export function track(event, props) {
  try {
    if (typeof window.op === 'function') window.op('track', event, props || {})
  } catch (_) { /* analytics must never break a tool */ }
}

export const $ = (id) => document.getElementById(id)

export function el(tag, attrs, ...children) {
  const node = document.createElement(tag)
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue
    if (k === 'class') node.className = v
    else if (k === 'text') node.textContent = v
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v)
    else node.setAttribute(k, v === true ? '' : v)
  }
  for (const c of children) {
    if (c === null || c === undefined || c === false) continue
    node.append(c instanceof Node ? c : document.createTextNode(String(c)))
  }
  return node
}

export function setStatus(node, text, kind) {
  node.textContent = text || ''
  node.dataset.kind = kind || ''
  node.hidden = !text
}

export async function copyText(text, button) {
  try {
    await navigator.clipboard.writeText(text)
  } catch (_) {
    // Older browsers / insecure contexts: a hidden textarea still works.
    const ta = el('textarea', { style: 'position:fixed;opacity:0' })
    ta.value = text
    document.body.append(ta)
    ta.select()
    try { document.execCommand('copy') } catch (_) { /* nothing else to try */ }
    ta.remove()
  }
  if (button) {
    const old = button.textContent
    button.textContent = 'Copied'
    setTimeout(() => { button.textContent = old }, 1400)
  }
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = el('a', { href: url, download: filename })
  document.body.append(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10000)
}

export function safeFilename(s, fallback) {
  const out = String(s || '').replace(/[\\/:*?"<>|]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 80)
  return out || fallback
}

/* Error text from our API's {detail: {code, message}} shape, or a generic line. */
export async function apiError(res) {
  try {
    const data = await res.json()
    const d = data && data.detail
    if (d && typeof d === 'object') return { code: d.code || '', message: d.message || '' }
    if (typeof d === 'string') return { code: '', message: d }
  } catch (_) { /* not JSON */ }
  return { code: String(res.status), message: 'Something went wrong. Try again in a moment.' }
}

/* Hand a YouTube link to the app: MediaInput reads os_pending_url on mount,
 * so the visitor lands in the clip generator with their video already in. */
export function openInApp(url, tool) {
  track('tool_cta_click', { tool })
  try { if (url) localStorage.setItem('os_pending_url', url) } catch (_) { /* private mode */ }
  window.location.href = '/#app'
}
