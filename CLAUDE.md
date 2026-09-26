# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenShorts is an AI-powered vertical video generator that transforms long YouTube videos or local uploads into viral-ready short clips (9:16 format) for TikTok, Instagram Reels, and YouTube Shorts. Uses Google Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite`, overridable with `GEMINI_MODEL`) for viral moment detection and title generation.

## Development Commands

### Local Development (Docker)
```bash
docker compose up --build   # Build and run full stack
```
- Backend: http://localhost:8000 (FastAPI/Uvicorn)
- Frontend: http://localhost:5175 (Vite proxies API calls to backend)

### Frontend Only (Dashboard)
```bash
cd dashboard
npm install
npm run dev       # Dev server with HMR (port 5173)
npm run build     # Production build
npm run lint      # ESLint (strict, --max-warnings 0)
```

### Backend Only
```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Architecture

### Core Processing Pipeline
1. **Ingest** - YouTube download (yt-dlp) or local upload
2. **Transcription** - faster-whisper with word-level timestamps
3. **Scene Detection** - PySceneDetect for segment boundaries
4. **AI Analysis** - Gemini identifies 3-15 viral moments (15-60 sec each)
5. **FFmpeg Extraction** - Precise clip cutting
6. **AI Cropping** - Vertical reframing with subject tracking
7. **Effects/Subtitles** - Optional AI-generated FFmpeg filters
8. **Hook Overlay** - Text overlays with styled fonts
9. **Voice Dubbing** - Optional ElevenLabs AI translation (30+ languages)
10. **S3 Backup** - Silent background upload
11. **Social Distribution** - Upload-Post API (async upload)

### Key Files
| File | Purpose |
|------|---------|
| `main.py` | Core video processing: transcription, scene detection, clip extraction, vertical reframing |
| `app.py` | FastAPI server with async job queue and REST endpoints |
| `editor.py` | Gemini AI integration for dynamic video effects (FFmpeg filter generation) |
| `hooks.py` | Hook text overlay generation with font rendering |
| `s3_uploader.py` | AWS S3 upload with caching |
| `subtitles.py` | SRT generation, FFmpeg subtitle burning, and dubbed video transcription |
| `translate.py` | ElevenLabs dubbing API for AI voice translation |
| `dashboard/src/App.jsx` | Main React component with state management |
| `dashboard/src/components/TranslateModal.jsx` | Voice dubbing UI with language selection |
| `dashboard/vite-plugin-seo.js` | Build-time SEO surface: injects crawler-visible homepage content, emits static pages, sitemap.xml and llms.txt |
| `dashboard/seo/data.js` | Single source of truth for pricing, pipeline and competitor facts used by every generated page |

### SEO / AI-crawler surface

The dashboard is a client-rendered SPA with hash routing, so the HTML served for
`/` used to contain an empty `<div id="root">`. Googlebot renders JavaScript and
saw the real page; GPTBot, ClaudeBot and PerplexityBot do not and measured the
homepage as zero characters of text. `vite-plugin-seo.js` fixes that at build time:

- Injects the content of `seo/landing-fallback.js` into `#root`. React's
  `createRoot().render()` replaces it on mount, so users get the app and
  non-executing clients get the copy. **Keep it in sync with `Landing.jsx`.**
- Emits the standalone pages (the `/alternatives` cluster, the clip-generator,
  open-source, use-case and automation pages, and `/mcp`; the full list is
  `buildPages()` in `seo/pages.js`) as flat `.html` files.
  nginx resolves the clean URL through `try_files $uri $uri.html`; serving them as
  directories instead makes nginx 301 to a trailing slash and every canonical
  would then point at a redirect.
- Generates `sitemap.xml` and `llms.txt` from the same page list, so they cannot
  drift. Do not add a static `public/sitemap.xml` back.

When editing pricing anywhere, edit `seo/data.js` too. Nothing on the site should
say "OpenShorts is free" without naming the Cloud price in the same breath: both
are true of different editions and quoting only the first one is what makes AI
answers describe the paid product as free.

### Free tools (/tools) and SEO attribution

- `free_tools.py` (router always mounted): `GET /api/tools/youtube-transcript`
  reads the captions a video **already has** on YouTube via yt-dlp (never the
  GPU, never media). Routes: the `STATIC_PROXY_URLS` only (anonymous, then the
  cookies), direct when there are none; **never** the per-GB `PROXY_URL`. A
  static that answers with zero formats and zero captions is a degraded route,
  not a "no captions" verdict (seen on one of the three statics, 23-sep-2026).
  `POST /api/tools/youtube-metadata` = one Gemini text call (tags / titles /
  description) with the managed key. Per-IP windows + global daily cap per tool,
  24 h cache (also for "no captions"/"unavailable").
- Pages: `seo/tools.js` (hub + 3 tools) and `seo/autopilot-pages.js`
  (`/auto-clip`, `/youtube-automation`). A tool page carries `tool: {entry, html}`:
  the form is in the static HTML, the behaviour is a Vite entry in
  `dashboard/tools/*.js` (`vite.config.js` rollupOptions.input) that
  `vite-plugin-seo.js` looks up by name in the bundle. The 9:16 converter runs
  in the browser with mediabunny/WebCodecs (no upload).
- Attribution: `seo/render.js` writes the same first-touch `os_attrib` key the
  app writes, from the static page the visit started on. Before, every signup
  was credited to "/" (7,481/7,481 rows, 30 days to 23-sep-2026). Signup,
  CheckoutStarted and Subscribed carry `landing_path`/`referrer_host`/utm as
  OpenPanel props (`lib/analytics.js`).
- Apex→www: 301 comes from the front app's **stored Coolify custom labels**
  (`redirectregex.permanent=true`, patched 23-sep-2026). The nginx 301 block
  below never sees the apex while that Traefik middleware exists.

### Cómo se elige el layout

`POST /api/process` acepta `layouts`: una lista (JSON) o cadena separada por
comas con `auto`, `split`, `screencast`, `speaker_cut`, `punch_in` y `none`.
Cada nombre enciende su variable de entorno para **ese** trabajo
(`app.py:layout_env`); `none` apaga el picker aunque prod corra con
`AUTO_LAYOUT=1` (recorte simple y nada más). Sin `layouts` manda el env del
despliegue, que desde el 25-ago-2026 es `AUTO_LAYOUT=1`. El dashboard lo expone
en opciones avanzadas ("vertical layout": auto / split / screencast / none,
`MediaInput.jsx`, recordado en `localStorage.os_layout`).

`auto` activa `layout_picker.py`: **una** llamada a Gemini por vídeo de origen
(no por clip) que elige entre `none` / `screencast` / `split`. Medido sobre el
corpus de 48 contra etiquetas revisadas a mano: 94% / 92% / 96% en tres pasadas,
con 0-1 falsos positivos sobre los 28 clips que no deben tocarse, y solo 2 clips
que cambian de respuesta entre pasadas.

**Manda 12 fotogramas a 1024px, no el vídeo.** Gemini factura vídeo a ~300
tokens por segundo: una hora de fuente son ~1,08M de tokens (no cabe en una
ventana de 1M) y una subida de 1-2 GB para recibir una palabra. Doce fotogramas
cuestan ~3k tokens **dure lo que dure la fuente**, que es lo que hace viable
esto con los podcasts de una hora que entran de verdad. La resolución importa y
el número de fotogramas no: a 640px detecta 15 de 20 (una hoja de cálculo es
ilegible), a 1024px sube a 17, y pasar a 24 fotogramas lo empeora. A 1024px la
diferencia con mandar el vídeo entero cae dentro de la varianza que ya tiene el
propio modo vídeo, a 2,2 s por clip en vez de ~15 s.

Lo que hace que funcione, y que conviene no deshacer: se le pide una **decisión
entre opciones cerradas**, no una medida. Los cuatro intentos anteriores (Canny,
MSER, cobertura temporal, anchura) le pedían un número y ninguno separó una hoja
de cálculo de un marcador de esquina. La varianza que este repo atribuía a
Gemini era de las medidas continuas, no del modelo.

`layout_picker.apply()` sólo **añade**: una elección explícita del usuario nunca
se desactiva porque el modelo diga `none`.

### Hook grounding for on-screen clips (`hook_grounding.py`)

The hook and title come from the detail pass, which only reads the
transcript, so on a clip whose meaning is on the screen (a settings dialog,
a spreadsheet) they summarise the video's topic instead of naming what is
shown. After the render, if the `<clip>.layout.json` sidecar says at least
25% of the clip is `screencast` / `wide` / `inset` (plus `general` when the
layout picker called the video a screencast: a face-less scene there is a
slide or a dialog, not a group shot), three frames from those
stretches at 1024px plus the clip's own words go to Gemini
(`GroundedHook`) and `viral_hook_text` / `video_title_for_youtube_short`
are rewritten in place before `auto_hook_clip` burns them; the originals
stay under `hook_grounding.before`. Gemini-only (frames): with just a local
LLM it logs one line and keeps the transcript hook. `HOOK_GROUNDING=0`
disables it. The detail prompt itself now carries the rule "about this
moment, not the video", which is the cheap half of the same fix.

### The quota wall offers the first N minutes (`app.partial_offer`)

The wall (`TopUpModal`, context `wall`) opens on a 402 from `/api/process`.
Measured on 16-sep-2026, 93 of 99 walls were shown to accounts with their
20 free minutes **untouched** that had pasted a 21-90 min video: the user was
asked for $12 before seeing one clip, and 41 of the 68 subscriptions Stripe
created in 30 days expired unpaid, none of them a card decline. So the 402
now carries `partial_minutes` (the floored balance, when it is at least
`PARTIAL_MIN_MINUTES` and shorter than the source), the wall shows "clip the
first N min" next to the plans, and the dashboard resubmits the same job with
`max_minutes=N`. `reserve_process_minutes` then reserves N (never more than
the balance, whatever the client asks) and sets `MAX_SOURCE_MINUTES` for
`main.py`, whose `cap_source_duration` cuts the downloaded/uploaded file **in
place** before anything reads it, so transcription, the layout picker, the
editor and `/api/source` all see a short video. The cut travels in the
resume manifest: a resumed job downloads the source again and would
otherwise process 45 minutes on a 20-minute reservation. `/api/status` and
the process response carry `partial`, and the results view says which part
of the video the clips came from, with the upsell for the rest.

### How many clips a job returns (`clip_selection.py`)

The count is not a setting, it is derived, and every stage of the derivation
used to leak. `get_viral_clips` builds ~90s scoring windows over the
transcript, scores them in batches, shortlists the best `shortlist_target`
(`min(10, duration//90 + 2)`, floor 3) and asks the detail pass for
`clip_count_targets(len(shortlist))` clips — a floor that matters because
users who got 1-3 clips came back a second day 0.4% of the time against
16.1% for 4-9.

Two things broke that chain, both found on a 9:10 source on 22-sep-2026 that
delivered 3 clips in prod:

- **The scoring pass selected instead of ranking.** Its prompt said "choose up
  to 3 windows from this batch", so the shortlist ceiling was
  `3 * n_batches`, not the target: 9 windows batched 8 + 1 gave 3 + 1 = 4
  against a target of 8, and `clip_count_targets` then asked for 4-8 clips
  instead of 6-12. Every source under ~30 min was starved this way — this is
  the mechanism behind "95% of jobs deliver 3 clips or fewer". It also threw
  away the ranking it was computing, since a batch of five great moments
  could still only contribute three. The prompt now scores **every** window
  and the shortlist is the global top N. Batches are near-equal
  (`score_batches`) for the same reason the cap is gone: a trailing batch of
  one window returned that window whatever its score, so the tail of the
  video entered the shortlist by arithmetic.
- **The clip floor was only a sentence in the prompt.** Nothing in code
  checked it, so a detail pass that returned half was shipped as-is. When it
  comes back under `min_clips`, the shortlist windows that produced nothing
  get one more call for the difference. An empty answer is accepted: that is
  material that genuinely holds no more, and padding is worse than a short
  list.

Measured on that source, same transcript, three runs: shortlist 4 → 8 and
4 clips → 6, at the same cost (~$0.005, 3 calls). `target_clips` on
`/api/process` (dashboard: advanced options) still pins both ends via
`CLIP_TARGET_MIN`/`MAX` when the user wants an exact number.

### Silent footage: the vision fallback (`main.get_visual_clips`)

The moment picker reads the transcript, so a video with nothing said in it
would score nothing. `main.py` switches paths by itself instead, and the
switch is the part worth knowing because it is not only "no audio track":
`transcribe_video` raising `NoAudioError`, **and** `speech_is_sparse()`
coming back true, both set `transcript = None` and route to
`get_visual_clips`. Sparse means under `MIN_SPEECH_WORDS` (8) in total or
under `MIN_SPEECH_WORDS_PER_MIN` (5). Music-only footage and a session
recorded with the mic muted transcribe to a handful of stray words, which
is worse than silence: without that second test the picker scores those
words and cuts around them.

The vision pass uploads the video, Gemini watches it and returns the same
`{"shorts"}` shape (`gemini_worker.VisualResponse`) in the same 15-60s
band, so every stage after it is byte-identical: layouts, inset detection,
hooks. `CLIP_TARGET_MIN`/`MAX` apply directly here rather than being
derived from scoring windows, because there are none. The transcript is
stored as `{"language": "none", "segments": []}`, so the clips come out
with no subtitles, which is correct and not a bug.

**This is the one stage that sends Gemini the video instead of frames, and
that is deliberate** — 12 frames can say what kind of video this is (which
is all the layout picker needs), they cannot say which 40 seconds to cut.
The cost is the ceiling: Gemini bills video at ~300 tokens/second, so an
hour is ~1.08M tokens, past a 1M window, and **nothing guards the length**.
A silent multi-hour source fails at the model rather than politely. If that
needs fixing, the answer is a guard or segmenting the source, not porting
the frame trick over from the layout picker. Gemini-only either way: a
text-only `LLM_BASE_URL` server cannot see footage, and with no
`GEMINI_API_KEY` the function logs one line and returns None, which fails
the job outright.

The public `/gta-5-clips` page states these thresholds and this ceiling to
users; if the behaviour changes, change `dashboard/seo/pages.js` too.

### Local LLM for the moment picker (`llm_backend.py`)

`LLM_BASE_URL` (+ `LLM_MODEL`, `LLM_API_KEY`) routes the two transcript
passes of `get_viral_clips` to any OpenAI-compatible `/chat/completions`
instead of Gemini; the response is validated with the same pydantic schemas
Gemini enforces server-side, so `main.py` sees one shape. `main.score_batch_size`
drops to 3 windows per call there (local contexts are 4-8k; a truncated
prompt scores garbage silently). Self-host `/api/process` then accepts a
request without `X-Gemini-Key` and `/api/config.localLlm` tells the dashboard
not to demand one. Frame-based stages (`layout_picker`, `screencast_layout`,
`get_visual_clips`) stay on Gemini and degrade as they always did without a
key. Never wired in cloud mode: `BILLING_ENABLED` ignores it.

### Thumbnail Studio (`thumbnail.py`, `/api/thumbnail/*`)

Titles come from the transcript plus 10 frames at 1024px, never the whole
video (same reasoning as the layout picker: an hour of video is ~1M tokens for
a text task). Two calls: a 25-title brainstorm across fixed styles, then a
critic that scores, dedupes by angle and returns 10, each paired with a 1-4
word `thumbnail_text` that complements the title rather than repeating it.
Rules baked in: payoff inside 50 characters (phones cut there), keyword in the
first 3 words, same language as the transcript. Text model is
`GEMINI_MODEL_THUMBNAIL` (default `gemini-3.7-flash`), deliberately not
`GEMINI_MODEL`: flash-lite is fine for a closed-choice layout pick and visibly
worse at creative titles. Image model is `GEMINI_IMAGE_MODEL` (default
`gemini-3.1-flash-image`).

Thumbnails are `count` **different concepts**, not one prompt repeated: a text
call designs each (hook text, side for the text, palette, scene prompt), then
one image call per concept in parallel. By default (`burn_text=true`) the
image model is told to leave that side as negative space and PIL sets the text
in Anton with a black stroke, so accents and spelling are never wrong; the
`AI painted` toggle lets the model render the text itself. Every output is
cover-cropped to 1280x720 and saved under YouTube's 2 MB limit.
`GET /api/thumbnail/frames/{session}` scores sampled frames by face area and
sharpness (MediaPipe + Laplacian), keeps them spread across the runtime, and
the dashboard offers them as the person reference so the thumbnail shows the
creator instead of a stranger; an uploaded face photo still wins.

### Video Reframing Modes

**A source already shot vertical is passed through untouched.**
`reframe_v2.source_already_fits()` gates it: every layout below reorganises the
frame to buy back width the crop threw away, and on a 9:16 upload there is none
to buy. GENERAL was the visible failure — its 0.42 height ratio, which buys
presence on a landscape source by overflowing the sides, scaled a 1080x1920
source down to a 453px sliver floating over a blurred copy of itself, and the
scene classifier routes every face-less shot (a slide, a screen recording) there.
So the picker is skipped (one Gemini call saved per upload), the classifier is
skipped, and every scene renders TRACK, whose crop is the whole frame.
`general_filtergraph` additionally floors the foreground at the height where the
source fills the output width, so the editor's explicit GENERAL override on a
portrait clip cannot reproduce the shrink either.

- **TRACK Mode** (single subject): MediaPipe face detection + YOLOv8 fallback with "Heavy Tripod" stabilization
- **GENERAL Mode** (groups/landscapes): Blurred background layout preserving full width
- **SPLIT Mode** (two-shot conversation, `split_layout.py`): both speakers stacked
  in half-frames. Off by default (`SPLIT_LAYOUT=1`); v2 engine only, so a
  fallback to the v1 loop silently renders GENERAL instead. It upgrades scenes
  the classifier already sent to GENERAL, never TRACK ones, and needs both faces
  visible **in the same frame** for at least half the sampled frames — that is
  what separates a real two-shot from a plano/contraplano, where stacking would
  show the same person twice. `SPLIT_TIGHTNESS` (default 0.8) trades a little
  upscale for keeping the other speaker out of each half. Captions on a SPLIT
  stretch sit on the seam between the halves (`{\an5}` per word event in
  `subtitles.generate_ass`), the one place they cover nobody; the render
  records which stretches are stacked in a `<clip>.layout.json` sidecar
  (`layout_ranges.py`) and every metadata writer copies it into the clip's
  `layout_ranges`, so `/api/subtitle` finds it after a restyle too. The fast
  rerender (cut without reframe) carries the canonical clip's ranges through
  the new cut (`layout_ranges.remap`, in `recut.perform_recut`). Only the
  ASS path can do this; SRT burns keep one alignment for the whole file.
- **SCREENCAST / WIDE Modes** (`screencast_layout.py`, `SCREENCAST_LAYOUT=1`):
  for scenes whose meaning lives outside the centre. Gemini reports each range's
  **width_fraction**, and that is the gate — coverage was tried before and did
  not separate a spreadsheet from a corner ticker, while width does (a bug spans
  ~15% and survives any crop, a spreadsheet spans ~100% and cannot). Content
  narrower than 0.5 moves nothing. Between 0.5 and 0.85 there is room beside the
  content, so SCREENCAST stacks it over the presenter. Above 0.85 the presenter
  is composited **on top of** the content and stacking would show it twice, so
  those scenes get WIDE: the GENERAL layout with side-cropping disabled.
- **INSET Mode** (`camera_inset.py`): pantalla a ancho completo arriba, el
  recuadro de la webcam ampliado abajo. Para el caso de una sola fuente con la
  cámara compuesta en una esquina (OBS, VOD de stream). Se encadena detrás de
  la decisión `screencast`, **no** se le pregunta a Gemini: ofrecido como cuarta
  opción respondió `screencast` en los 5 clips que tienen recuadro, en dos
  pasadas, y la exactitud global cayó de 92% a 83-85%. El detector geométrico
  encuentra esos 5 sin falsos positivos. Los tres filtros que hacen falta, cada
  uno pagado con una iteración: sujeto **pequeño**, **descentrado en
  horizontal** (una cara de talking head está centrada aunque esté alta), y
  **quieto entre muestras** (3-11px frente a 316px de una persona real).
- **ALTERNATE Mode** (`active_speaker.py`, `SPEAKER_SIGNAL=1` + `SPEAKER_CUT=1`):
  hard cuts to whoever is talking, rendered through the TRACK path as a
  trajectory with jumps. `SPEAKER_SIGNAL=1` alone just gates SPLIT on both people
  actually speaking. Mouth activity **must** be normalised per speaker before
  comparing (`normalise_activity`): raw frame-difference magnitude scales with
  local contrast and lighting, and on a real two-shot it handed one speaker
  90-100% of the scene.
- **Punch-in** (`punch_in.py`, `PUNCH_IN=1`): not a layout. A ~12% push on the
  clip's beats, riding the TRACK path by widening its per-frame crop command
  from x-only to w/h/x/y. Beats currently come from the audio envelope;
  `emphasis_times` is a plain list of seconds so the transcript's hook words can
  replace it without touching the module.

### Key Classes
- `SmoothedCameraman` - Stabilized camera movement with safe zone logic (prevents jitter)
- `SpeakerTracker` - Prevents rapid speaker switching, handles temporary occlusions

### API Endpoints
| Method | Route | Purpose |
|--------|-------|---------|
| POST | `/api/process` | Submit video for processing |
| GET | `/api/status/{job_id}` | Poll job status and logs |
| POST | `/api/edit` | Apply AI video effects |
| POST | `/api/subtitle` | Generate and apply subtitles (auto-transcribes dubbed videos) |
| POST | `/api/hook` | Add text hook overlays |
| POST | `/api/translate` | AI voice dubbing via ElevenLabs |
| GET | `/api/translate/languages` | List supported dubbing languages |
| POST | `/api/social/post` | Post to social media (async upload) |
| POST | `/mcp` | MCP server (JSON-RPC): the pipeline as agent tools |
| POST/GET/DELETE | `/api/keys` | User API keys (cloud mode, session JWT only) |
| DELETE | `/api/account` | Erase the account and everything in it (GDPR art. 17) |
| GET/PUT | `/api/autopilot` | Autopilot settings, connected accounts, recent runs (cloud only) |
| GET | `/api/autopilot/videos` | Latest uploads of the connected YouTube channel + what Autopilot did |
| POST | `/api/autopilot/run` | Clip one channel video now (`{video_id}`) |

### Agent access (MCP, API keys, webhooks)

- **API keys** (`cloud/api_keys.py`): `osk_...` tokens, sha256-stored, created in
  the dashboard account page. `cloud/auth.get_current_user_optional` accepts
  them (`Bearer osk_...` or `X-API-Key`) and resolves the owner, so metering,
  entitlement, plan priority and job ownership apply to agents with zero
  endpoint changes. Key management itself refuses API-key auth: a leaked key
  cannot mint replacements.
- **MCP server** (`mcp_server.py`, mounted always): stateless Streamable-HTTP
  JSON-RPC at `/mcp` — no SDK dependency, ~3 methods + 8 tools. Each tool calls
  back into this same app in-process (`httpx.ASGITransport`) forwarding the
  caller's auth headers, so it can never drift from the REST behavior. Cloud
  mode 401s without a resolvable user; self-host stays BYOK-open.
- **stdio transport** (`mcp_stdio.py`): the same `handle_message` / `call_tool`
  as a subprocess, for hosts that only launch MCP servers as a command (Glama's
  Dockerfile deployments wrap one; a local client can skip the web server).
  Two invariants: `sys.stdout` is swapped for stderr **before `app` is
  imported**, because the pipeline prints everywhere and one stray line
  corrupts the JSON-RPC stream; and the app's lifespan is entered
  (`router.lifespan_context`), which `ASGITransport` does not do on its own.
- **OAuth for MCP clients** (`cloud/mcp_oauth.py`, cloud mode only): claude.ai
  and ChatGPT connect by URL, so the server publishes RFC 9728/8414 metadata
  under `/.well-known/`, accepts dynamic client registration (`POST
  /oauth/register`, public clients, PKCE S256 mandatory) and bounces
  `GET /oauth/authorize` to the dashboard consent screen (`#/oauth/authorize`),
  because the session JWT lives in localStorage on the frontend host and a
  bare API GET cannot see it. `POST /api/oauth/authorize` (session auth) mints
  the code; `POST /oauth/token` redeems it by **minting an ordinary `osk_`
  key** named after the client and returning it as the access token. No new
  auth path, no refresh tokens: the key shows up in Account → API keys and
  revoking it disconnects the app. The `/mcp` 401 carries
  `WWW-Authenticate: Bearer resource_metadata=...` so clients find the flow.
  `oauth_codes` is in `USER_OWNED_TABLES`; `oauth_clients` deliberately not.
- **Webhooks**: `POST /api/process` takes `webhook_url` + optional
  `webhook_secret` (HMAC-SHA256, `X-OpenShorts-Signature`). Validated with
  `security_utils.assert_public_url` at submit AND at delivery (DNS rebinding).
  Fired once per job from `run_job_wrapper` after the R2 archive so the payload
  can carry durable download links; survives redeploys via the resume manifest.
  `PUBLIC_API_URL` env sets the absolute-URL base when behind a proxy.

### Autopilot (`cloud/autopilot.py`, dashboard tab "Autopilot")

Cloud-only retention feature: every new video on the user's connected YouTube
channel becomes clips on its own, and optionally the best ones are scheduled
on their socials, one a day. Paid plans only (it spends minutes unattended).

- **Channel listing** comes from Upload-Post, not scraping:
  `GET /api/uploadposts/media?platform=youtube&user=os_<id>` reads the
  channel's uploads playlist with the user's own OAuth token, so it includes
  videos uploaded straight to YouTube. There is no push from Upload-Post, so a
  loop polls (tick 5 min, each user at most once per 55 min).
- **Jobs go through the normal pipeline**: an in-process `POST /api/process`
  (`httpx.ASGITransport`, like the MCP server) authenticated with a freshly
  issued session JWT for the user. Metering, the probe, the per-plan job
  limit, the quality gate and the download proxies apply unchanged. The
  per-job content attestation is recorded once as `rights_ack_at`.
- **Guard rails**: only videos published after `enabled_at` (switching on never
  clips the back catalogue) and at most 3 days old; 1 automatic job per user
  per 24 h; `max_minutes` per video (default 30, sent as the partial-clip
  `max_minutes`); YouTube Shorts are skipped (`HEAD /shorts/<id>` answers 200
  for a Short and 303 to `/watch` for a regular video; the SOCS consent cookie is required, from the EU servers every request is otherwise a 302 to consent.youtube.com).
- **Dedupe across the deploy handover**: two containers poll at once during a
  rolling deploy, so a video is claimed by INSERTing its `autopilot_runs` row
  (unique `user_id, video_id`) before anything is submitted. A draining
  instance stops polling. A 429 (job limit) or 5xx drops the claim to retry.
- **Completion**: `run_job_wrapper` calls `on_job_finished` after the R2
  archive. A guarded UPDATE (`status='processing'` → final) makes it once-only;
  it sends the Autopilot email (replacing the generic clips-ready one) and,
  with autopublish on, uploads the top `clips_to_publish` clips by
  `predicted_score` to Upload-Post in a background task, scheduled one a day at
  `publish_hour` in the user's IANA `timezone`. Runs stuck in processing for
  6 h are marked `timeout`.
- `AUTOPILOT_DISABLED=1` turns the poller off without touching the API.
- Both tables are in `account.USER_OWNED_TABLES`.

### Account erasure (GDPR art. 17)

`DELETE /api/account` (`cloud/account.py`, dashboard: Account → Delete account)
is immediate and irreversible: there is no recovery window because after the
delete there is nothing left to authenticate a recovery request against. It
refuses API-key auth (a leaked `osk_` must not destroy its own account) and
requires the caller to retype the account email.

The order of the steps is the design, and each one is a failure mode:
**Stripe cancel first**, aborting the whole thing if it fails, so we never erase
a user we are still billing; **R2 before the database**, because those rows are
the only index of which objects are theirs and dropping them first turns a
failed purge into permanent orphans; the DB delete is **one transaction** over
an explicit table list (`USER_OWNED_TABLES`) rather than the declared ON DELETE
CASCADEs, since `create_all` never ALTERs an existing table and a constraint
added after a table shipped exists in the models but not in production.
`tests/test_account_erasure.py` fails if a new table references `users.id`
without joining that list.

`app.py` registers a callback for the local working files, which record
ownership three different ways: the `.owner` file clip jobs write (so jobs
recovered from disk after a restart count too), `saas_jobs`, and
`thumbnail_sessions`. That last one is the only thing that ever deletes
generated thumbnails: the hourly sweep skips their directory and they are
served publicly at `/thumbnails/`.

What deliberately survives: the Stripe customer and its invoices (6-year
retention, Spanish commercial law) and one `account_deletions` row holding a
sha256 of the email as proof the erasure happened, itself purged after 5 years.
The "why are you leaving" answer is a closed list (`DELETION_REASONS`), never
free text — anything the user could type would land in a row designed to
outlive them. Deleting users also made one webhook path reachable that never
was before: `_apply_topup` reads the user id from Stripe metadata, so it now
confirms the row still exists before inserting, or the FK violation makes
Stripe retry the same doomed event for three days.

### Concurrency Model
Async job queue with semaphore-based concurrency control. Configure via `MAX_CONCURRENT_JOBS` env var (default: 5). Jobs auto-cleanup after 1 hour.

The real limit on the GPU box is VRAM, not CPU: each `main.py` job holds
Parakeet (onnxruntime CUDA), TransNetV2 (torch, ~2 GB at peak) and an
NVENC session, and when the card is full a cut fails as "Generic error in
an external library" / exit 187 with 0 bytes, TransNetV2 as CUDA OOM, and
the reframe writer as a broken pipe. The retry in `ffmpeg_utils.cut_clip`
waits for a **busy** GPU; it cannot help with a **full** one. The API
process itself was the biggest tenant (7.7 GB idle on 17-sep-2026): the
thumbnail studio and `/api/subtitle` on a dubbed clip transcribe
in-process and the ASR singletons then lived in uvicorn for good, so both
now call `transcribe_backends.release_models()` when they are done. Size
`MAX_CONCURRENT_JOBS` against the free VRAM first, then check the CPU.

The CPU is the other ceiling (a 20-thread host sat at load ~100 at peak on
22 and 25-sep-2026). Two costs were pure waste and are gone, with the
delivered clips byte-identical (decoded-frame MD5s + audio, 15 clips of 3
real videos, bench of 25-sep-2026):
- **onnxruntime threads spinning** during Parakeet: ~160 CPU-s per 9 min of
  audio while the GPU did the work. `parakeet_session_options()` turns
  spinning off for the ASR session only; the VAD must keep `load_vad`'s
  defaults (see the docstring for why).
- **A seek per sampled frame** in `analyze_scenes_strategy` and
  `split_layout`: each seek re-decoded the GOP. `frame_sampler.read_at`
  reads forward once and returns the same frames.
Net: a job's CPU roughly halves (Python side -65-80%).

Then speed at equal quality (25-sep-2026; SSIM 0.990-0.9998 vs before,
checked by eye, audio identical):
- **Cut on the card** (`ffmpeg_utils.cut_clip`, NVDEC -> NVENC with
  `-hwaccel_output_format cuda`) for 8-bit 4:2:0 sources; byte-identical to
  the CPU cut. Other sources and a failed GPU cut decode on the CPU.
- **Silero VAD on one CPU thread** (`vad_load_kwargs`): on CUDA it ran one
  32 ms chunk per launch and was most of the transcription's wall time.
- **Blur at quarter size** (`ffmpeg_utils.blurred_backdrop`).
- **Watermark inside the reframe encode** (`reframe_v2.render(watermark=)`),
  not a pass of its own (most jobs are free plan).
- **hooked_ + subtitled_ from one ffmpeg** (`hooks.add_hook_to_video(also=)`):
  the editor still needs both files (re-caption walks back to hooked_,
  hook replace to the canonical), so nothing is skipped, only one decode.
- **CLIP_WORKERS=6** by default.
Tried and dropped: NVDEC for the analysis decodes and `scale_cuda` (slower in
wall, and scale_cuda does not match swscale); yt-dlp chunking/concurrent
fragments (YouTube serves DASH over https, no gain beyond network noise).
Measured with a side-by-side bench: Gemini decisions recorded once and
replayed, old and new code run at the same time, clips compared by
decoded-frame MD5 / SSIM.

Three guards keep the card from filling (22-sep-2026: 30-60% of jobs failing
per hour at peak with `MAX_CONCURRENT_JOBS=8`):
- **Job processes release the ASR model after transcribing**
  (`main.transcribe_video` → `release_models()`). Before, a job kept Parakeet's
  onnxruntime CUDA arena (~4-6 GB) for its whole render; TransNetV2 also
  `empty_cache()`s after each pass.
- **Parakeet runs lean** (`transcribe_backends.parakeet_providers`,
  `PARAKEET_VAD_BATCH`=4): 4 VAD segments per encoder batch instead of 8, CUDA
  arena `kSameAsRequested`, no max cuDNN workspace. Peak per transcription
  6.1 → 4.6 GB with the same words (benchmark 22-sep-2026: 10 real videos,
  4,850 words, 1 word changed outside a clip that goes to whisper anyway).
  Batch 2 dropped a sentence and int8 was 11x slower with 11.7% of words
  different: both rejected.
- **Host-wide transcription slots** (`transcribe_backends.host_asr_slot`,
  `ASR_HOST_SLOTS`, default 2): flock files `output/.asr-gpu-N.lock`, shared by
  every job process and by both containers of a deploy.
- **Queue admission** (`app._wait_for_shared_gpu`): a job starts only when
  running-here + running-on-the-draining-instance < `MAX_CONCURRENT_JOBS` and
  `nvidia-smi` reports at least `GPU_MIN_FREE_MB` (4500) free; an idle card
  always starts, and the wait is bounded by the drain timeout.

Failures the user should never see (`app.run_job_wrapper`):
- **Auto-retry**: a failed job whose error text is transient (CUDA/OOM,
  NVENC "Generic error in an external library", cublas, Gemini 5xx, "No clips
  could be rendered") is re-queued once after `AUTO_RETRY_DELAY_SECONDS` (30),
  keeping its reservation and transcript checkpoint (`AUTO_RETRY_LIMIT`=1).
  Content failures (no audio, private video, no clips found, policy block)
  are final as before. Inside a job, `main.py` retries each failed clip once,
  alone, after a pause, and renders clips best-score first.
- **Shutdown is not failure**: when the drain timeout cancels a running job,
  the child is killed and the manifest + reservation are kept, so the next
  instance resumes it. A manifest next to a metadata file means "stopped
  mid-render" and is resumed, not recovered as completed.
- `/api/status` returns `queue: {position, ahead, eta_seconds}` while queued;
  the dashboard shows it with a "paid plans skip the line" upsell (paid plans
  do dispatch first: `PLAN_PRIORITY`).

### Paid proxy accounting (`cloud/proxy_ledger.py`)

Downloads go direct → static ISP proxies (flat rate) → DataImpulse (per GB),
and the duration probe (`cloud/metering.probe_url_minutes`) follows the same
order, with one extra free step before any per-GB attempt: the fallback
clients through a static (`fallback-static`). **The client list is explicit
and shared** (`yt_clients.py`: `default,mweb` + the bgutil PO token
provider): with account cookies yt-dlp's own defaults are `tv_downgraded` +
`web`, and on a share of videos both come back UNPLAYABLE / SABR-only, which
yt-dlp reports as "Video unavailable". That was mistaken for an IP ban for a
week (it happened on every static IP too) and fed ~26 downloads a week to
the per-GB proxy, which then fetched 360p through the same dead list.
Measured in the prod container on 6-sep-2026, same static, same video:
cookies + defaults → unavailable; cookies + `default,mweb` → 1080p; no
cookies → 1080p. `mweb` needs the PO token, and the token needs the
webpage: never put `player_skip: webpage` back. A fallback attempt runs
anonymously when an HD attempt already failed with the cookies on that
route, and every attempt asks for the 1080p format spec (the old
`best[ext=mp4]` fallback spec was itself the 360p progressive file).
Two rules keep the per-GB proxy at zero on a normal day: the probe
reaches it **only** when a static route failed for a reason another IP can
fix (`static_failure_warrants_paid`: bot-check, 403/429, proxy/network
errors), never for a private/removed/members-only video, an uploader's
country block (the residential pool failed identically in 5 of 6 paid
probes, 3-5 sep) or a live stream
with no duration (those failed the same on every IP and used to cost ~1.7 MB
× 2 extractors each), and **never for a non-YouTube URL** (the download
plan already excluded those; Twitch, Kick, Rumble and product pages were
reaching it through the probe). The probe also carries `YOUTUBE_COOKIES`,
like the download does: an anonymous probe from the static IPs gets "Sign in
to confirm you're not a bot" in bursts (4-sep-2026: ~10 probes in one hour,
1.8 MB each on the per-GB proxy) because a datacenter IP's anonymous rate
limit is low and we make ~400 YouTube hits a day from three of them, while
the authenticated download sails through the same IPs. But the **first**
attempt on a route carries them and the second drops them, on the probe as
on the download: with the cookies attached YouTube answers UNPLAYABLE for
every client (`web_embedded`, `tv_downgraded`, `web` **and** `mweb`) on a
share of videos, which yt-dlp reports as "Video unavailable" (9-sep-2026,
same video on all three statics; anonymous on the same IP → 1080p 137+140).
Without that anonymous second attempt the probe read a cookie problem as an
IP problem and escalated to the per-GB proxy, which carries the same cookies
and fails identically, while the download recovered for free on the same
static. `main.py` prints `PROXY_ROUTE=<json>` after
every download (winner, paid bytes across all attempts including failed
paid ones, each free attempt's error); `app.py` persists it as a
`proxy_usage` row at job end and pages Telegram when the paid proxy carried
bytes, folding a burst into one message per 5 min. The in-memory monthly
counter and the container log (rotates within the hour) cannot answer "what
cost $14 on the 28th"; the table can. Both the probe and the download pass `noplaylist`: a
`watch?v=X&list=...` or mix link is the one video the user was watching,
and without it yt-dlp walks the whole list, dies on its first private /
age-gated / bot-checked entry (a video nobody pasted), the probe reads
that as an IP problem and pays the proxy to walk the same list again, and
the user gets a 400 for a valid link (26 of the 37 paid probes between
7 and 17-sep-2026). And the probe keeps **every** attempt's error per
static route, not the last one: the anonymous retry ends in a bot-check
by design, and a "confirm your age" from the cookie attempt is the
verdict, so it must not be overwritten into an escalation. A URL that is
not one video is refused by path before any request
(`yt_clients.youtube_non_video_reason`): `noplaylist` does nothing for
those and yt-dlp walks them entry by entry (one search URL held the
probe thread for 37 min in the prod container). That check is an
**allowlist** of the paths that carry a video id, not a list of the bad
ones: while it named the pages it knew, a hashtag page and the legacy
`/<vanity>` channel URL went straight through, and one of them walked to
page 23 on the static pool and then paid the per-GB proxy to walk it
again (20-sep-2026).
`PAID_PROXY_DAILY_MB` (default
500) is the hard ceiling: past it the paid proxy is dropped from the probe
and from every new job's env until UTC midnight. The watcher probes the
static pool against a real YouTube watch page (playable markers), not
google.com — the 28th happened because YouTube refused the static IPs while
google kept answering 204. On the dev Mac, do not keep
`PROXY_URL` in `.env`: every local `main.py` run then bills DataImpulse.

### Deploys and running jobs (handover + drain)

Every push to `main` redeploys the API container. Coolify starts the NEW
container before stopping the old one (rolling update) and both share
`output/`, so `app.py` coordinates them instead of relying on a fast swap:

- Each instance writes its id to `output/.instance` at startup. An instance
  that sees another id there is the old one and **drains**: it finishes the
  jobs it is running, starts none, and leaves queued manifests on disk.
- A running job heartbeats its `.resume.json` every 10 s. The resume scan
  (startup + every 30 s) re-enqueues only manifests nobody heartbeated for
  60 s, so no job runs twice and none is lost. Max 2 resume attempts.
- SIGTERM (`docker stop`) drains too, up to `DRAIN_TIMEOUT_SECONDS` (840),
  then hands the signal to uvicorn. The app's Coolify stop grace period is
  900 s (`application_settings.stop_grace_period`); keep the timeout below it.
  After the drain hands the signal to uvicorn, `--timeout-graceful-shutdown 15`
  (Dockerfile) caps the wait for in-flight connections: uvicorn's default is
  unbounded, and one open range download kept a drained container alive for
  the full grace period while Traefik still routed half the traffic to its
  closed port.
- `/health/ready` + the Dockerfile `HEALTHCHECK` are what keep Traefik off a
  dying container: its docker provider only routes to `healthy` containers,
  so an instance answers 503 from the moment it gets SIGTERM (out of rotation
  within ~10 s, socket still open) and a booting one gets no traffic until it
  answers. Only SIGTERM flips it, not the marker drain: at that point the new
  container is still booting and nobody else would be routable. The Coolify
  app has its health check enabled on that path so it waits for the new
  container to be `healthy` before stopping the old one. With that option on,
  Coolify replaces the Dockerfile HEALTHCHECK with its own curl/wget command
  AND its own interval/retries (5 s × 3), so the image must ship `curl` or
  every deploy rolls back as unhealthy, and a stopping container takes 15 s
  to turn `unhealthy`. That is why the drain keeps serving for
  `PROXY_DRAIN_SECONDS` (20) after the jobs are done before it hands the
  signal to uvicorn: closing the socket earlier is 502s until Traefik
  notices (measured ~60 s per deploy with retries=12 and no grace). And
  `HARD_EXIT_SECONDS` (30) after that the process is ended outright: uvicorn
  finishing does not end the interpreter while an executor thread hangs in
  a network probe, and that kept a drained container alive for the full 900 s.
  `/health` stays a plain liveness probe for the external watcher.
- `/api/status` answers from disk for a job this instance never held, so a
  poll landing on either container during the handover is fine.
- `main.py` leaves `.transcript_checkpoint.json` in the job dir so a job that
  does get re-run skips the paid transcription (download and Gemini repeat).

Before pushing, still batch small commits (tests, docs) with the next real
change: every deploy is a ~5 min build plus a handover.

## CI: a green pipeline closes the task, not the push
- After every `git push`, wait for the commit's workflow and confirm it is green: `ci-wait` (Victor's Mac) or `gh run watch $(gh run list -c $(git rev-parse HEAD) -L1 --json databaseId -q ".[0].databaseId") --exit-status`.
- If it is red: fix, push, check again. Never report the task as done with a red CI.
- Before pushing, run locally what the CI runs (lint + tests of this repo).
