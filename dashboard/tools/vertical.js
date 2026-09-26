/* Video to 9:16 converter (/video-aspect-ratio-converter).
 *
 * Runs entirely in the visitor's browser: mediabunny demuxes the file, the
 * browser's WebCodecs decoder/encoder do the heavy lifting (hardware-
 * accelerated where available), and each frame is composed on a canvas. The
 * file never leaves the device, so there is no upload, no server cost and
 * nothing to rate-limit.
 */
import {
  Input, Output, Conversion, BlobSource, BufferTarget, ALL_FORMATS,
  Mp4OutputFormat, WebMOutputFormat, QUALITY_HIGH,
  getFirstEncodableVideoCodec, getFirstEncodableAudioCodec,
} from 'mediabunny'
import { $, track, setStatus, downloadBlob, safeFilename } from './common.js'

const TOOL = 'video-9-16'
const MAX_SECONDS = 5 * 60
const MAX_BYTES = 2 * 1024 * 1024 * 1024

const fileInput = $('vc-file')
const drop = $('vc-drop')
const status = $('vc-status')
const go = $('vc-go')
const progress = $('vc-progress')
const bar = progress.querySelector('span')
const result = $('vc-result')
const preview = $('vc-preview')
const posWrap = $('vc-pos-wrap')
let file = null
let running = null

const option = (name) => document.querySelector(`input[name="${name}"]:checked`)?.value

function syncOptions() {
  posWrap.hidden = option('vc-fit') !== 'crop'
}
document.querySelectorAll('input[name="vc-fit"]').forEach((r) => r.addEventListener('change', syncOptions))
syncOptions()

function pick(f) {
  if (!f) return
  if (!/^video\//.test(f.type) && !/\.(mp4|mov|m4v|webm|mkv)$/i.test(f.name)) {
    setStatus(status, 'That does not look like a video file. MP4, MOV and WebM work best.', 'error')
    return
  }
  if (f.size > MAX_BYTES) {
    setStatus(status, 'That file is over 2 GB. Trim it first or use a shorter export.', 'error')
    return
  }
  file = f
  $('vc-name').textContent = `${f.name} · ${(f.size / 1048576).toFixed(1)} MB`
  go.disabled = false
  result.hidden = true
  setStatus(status, '', '')
}

fileInput.addEventListener('change', () => pick(fileInput.files[0]))
;['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.dataset.over = '1' }))
;['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); delete drop.dataset.over }))
drop.addEventListener('drop', (e) => pick(e.dataTransfer.files[0]))

const supported = typeof window.VideoEncoder === 'function' && typeof window.VideoDecoder === 'function'
if (!supported) {
  setStatus(status, 'This browser cannot encode video on the page (it lacks the WebCodecs API). Current Chrome, Edge, Safari and Firefox can.', 'error')
  go.disabled = true
}

/* One frame of output. `fit` is blur (whole frame over a blurred copy of
 * itself), crop (fill the frame, cut the sides at `pos`) or bars (whole frame
 * on black). The blur is a downscale-then-upscale, not ctx.filter: Safari's
 * canvas had no filter support until 18, and this is cheaper everywhere. */
function makeComposer(W, H, fit, pos, srcW, srcH) {
  const canvas = new OffscreenCanvas(W, H)
  const ctx = canvas.getContext('2d', { alpha: false })
  const small = new OffscreenCanvas(27, 48)
  const sctx = small.getContext('2d', { alpha: false })
  ctx.imageSmoothingQuality = 'high'
  let crop = null
  if (fit === 'crop' && srcW && srcH) {
    const target = W / H
    if (srcW / srcH > target) {
      const cw = Math.round(srcH * target)
      crop = { left: Math.round((srcW - cw) * pos), top: 0, width: cw, height: srcH }
    } else {
      const ch = Math.round(srcW / target)
      crop = { left: 0, top: Math.round((srcH - ch) * 0.5), width: srcW, height: ch }
    }
  }
  return (sample) => {
    if (fit === 'crop') {
      sample.drawWithFit(ctx, crop ? { fit: 'cover', crop } : { fit: 'cover' })
    } else {
      if (fit === 'blur') {
        sample.drawWithFit(sctx, { fit: 'cover' })
        ctx.drawImage(small, 0, 0, W, H)
        ctx.fillStyle = 'rgba(0,0,0,0.28)'
        ctx.fillRect(0, 0, W, H)
      } else {
        ctx.fillStyle = '#000'
        ctx.fillRect(0, 0, W, H)
      }
      sample.drawWithFit(ctx, { fit: 'contain' })
    }
    return canvas
  }
}

async function convert() {
  if (!file || running) return
  const size = option('vc-size') === '720' ? [720, 1280] : [1080, 1920]
  const [W, H] = size
  const fit = option('vc-fit') || 'blur'
  const pos = Number($('vc-pos').value) / 100
  go.disabled = true
  result.hidden = true
  progress.hidden = false
  bar.style.width = '0%'
  setStatus(status, 'Reading the video...', 'busy')
  const t0 = performance.now()
  let input
  try {
    input = new Input({ source: new BlobSource(file), formats: ALL_FORMATS })
    const vt = await input.getPrimaryVideoTrack()
    if (!vt) throw new Error('This file has no video track.')
    if (!(await vt.canDecode())) {
      throw new Error(`This browser cannot decode the video in this file (${vt.codec || 'unknown codec'}). Try Chrome or Edge, or export the video as H.264 MP4 first.`)
    }
    const duration = await input.computeDuration()
    const end = Math.min(duration, MAX_SECONDS)

    // MP4/H.264 when the browser can encode it (Chrome, Edge, Safari), WebM
    // otherwise (Firefox on Linux, Chromium builds without H.264).
    let format = new Mp4OutputFormat({ fastStart: 'in-memory' })
    let codec = await getFirstEncodableVideoCodec(['avc', 'hevc'], { width: W, height: H })
    if (!codec) {
      format = new WebMOutputFormat()
      codec = await getFirstEncodableVideoCodec(['vp9', 'vp8', 'av1'], { width: W, height: H })
    }
    if (!codec) throw new Error('This browser cannot encode video on the page. Try a recent Chrome or Edge.')

    // Audio: AAC in MP4 is what every platform and Safari accept. An AAC
    // source is copied untouched (no trim below the cap, same codec); anything
    // else is encoded to AAC when this browser can, and left to mediabunny's
    // default (Opus) only when it cannot.
    let audioCodec
    if (format instanceof Mp4OutputFormat) {
      audioCodec = (await getFirstEncodableAudioCodec(['aac'])) || undefined
    }

    const output = new Output({ format, target: new BufferTarget() })
    const compose = makeComposer(W, H, fit, pos, vt.displayWidth, vt.displayHeight)
    const conversion = await Conversion.init({
      input,
      output,
      // Trimming forces the audio through a re-encode, so only trim when the
      // video is actually over the cap.
      ...(duration > MAX_SECONDS ? { trim: { start: 0, end } } : {}),
      ...(audioCodec ? { audio: { codec: audioCodec } } : {}),
      video: {
        codec,
        bitrate: QUALITY_HIGH,
        forceTranscode: true,
        process: compose,
        processedWidth: W,
        processedHeight: H,
      },
      showWarnings: false,
    })
    if (!conversion.isValid) {
      const why = conversion.discardedTracks.map((d) => `${d.track.type}: ${d.reason}`).join(', ')
      throw new Error(`This file cannot be converted in the browser (${why}).`)
    }
    const dropped = conversion.discardedTracks.filter((d) => d.track.type === 'audio')
    conversion.onProgress = (p) => {
      bar.style.width = `${Math.round(p * 100)}%`
      setStatus(status, `Converting... ${Math.round(p * 100)}%`, 'busy')
    }
    running = conversion
    await conversion.execute()
    const blob = new Blob([output.target.buffer], { type: format.mimeType })
    const ext = format instanceof Mp4OutputFormat ? 'mp4' : 'webm'
    const url = URL.createObjectURL(blob)
    // Show a frame instead of a black box until the visitor presses play.
    preview.addEventListener('loadeddata', () => { try { preview.currentTime = Math.min(1, end / 2) } catch (_) { /* ignore */ } }, { once: true })
    preview.src = url
    const name = `${safeFilename(file.name.replace(/\.[^.]+$/, ''), 'video')}-9x16.${ext}`
    $('vc-download').onclick = () => {
      track('tool_download', { tool: TOOL })
      downloadBlob(blob, name)
    }
    const secs = ((performance.now() - t0) / 1000).toFixed(1)
    $('vc-info').textContent = [
      `${W}x${H} ${ext.toUpperCase()}`,
      `${(blob.size / 1048576).toFixed(1)} MB`,
      `converted in ${secs} s on this device`,
      duration > MAX_SECONDS ? `first ${MAX_SECONDS / 60} minutes only` : '',
      dropped.length ? 'no audio (this browser could not re-encode it)' : '',
    ].filter(Boolean).join(' · ')
    result.hidden = false
    setStatus(status, '', '')
    track('tool_used', { tool: TOOL, ok: true, fit, size: String(H), ext,
      seconds: Math.round(end), ms: Math.round(performance.now() - t0) })
  } catch (e) {
    track('tool_used', { tool: TOOL, ok: false, code: String((e && e.name) || 'error').slice(0, 40) })
    setStatus(status, (e && e.message) || 'The conversion failed.', 'error')
  } finally {
    running = null
    progress.hidden = true
    go.disabled = !file || !supported
    try { input && input.dispose && input.dispose() } catch (_) { /* ignore */ }
  }
}

go.addEventListener('click', convert)
$('vc-cta-btn')?.addEventListener('click', () => track('tool_cta_click', { tool: TOOL }))
