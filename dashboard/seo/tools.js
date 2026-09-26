/* The free tools (/tools) and the two automation pages built around
 * Autopilot (/auto-clip, /youtube-automation).
 *
 * Tool pages carry `tool: { entry, html }`. The html is the tool's real form,
 * rendered straight into the static document right under the H1, so it is in
 * the raw HTML a crawler reads and it is the first thing a visitor sees; the
 * entry (dashboard/tools/*.js, built by Vite) only wires it up.
 *
 * House rules that apply to every line here (seo-work REGLAS.md): nothing
 * invented, every number dated and sourced, no em dashes, no filler copy.
 */

import { SITE } from './data.js'
import { esc } from './render.js'

const PUBLISHED = '2026-09-23'

const faqBlock = (faq) =>
  `<h2>Common questions</h2><dl class="faq">${faq
    .map((f) => `<dt>${esc(f.q)}</dt><dd>${esc(f.a)}</dd>`)
    .join('')}</dl>`

const sources = (items) =>
  `<h2>Sources</h2><ul class="sources">${items.map((s) => `<li>${s}</li>`).join('')}</ul>`

const webApp = (path, name, description, category = 'MultimediaApplication') => ({
  '@type': 'WebApplication',
  '@id': `${SITE.url}${path}#app`,
  name,
  description,
  url: `${SITE.url}${path}`,
  applicationCategory: category,
  operatingSystem: 'Any (runs in the browser)',
  browserRequirements: 'Requires JavaScript',
  isAccessibleForFree: true,
  offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
  publisher: { '@id': `${SITE.url}/#organization` },
})

/* ------------------------------------------------------------------------ */
/* /tools                                                                    */
/* ------------------------------------------------------------------------ */

export const TOOLS = [
  {
    path: '/youtube-transcript-generator',
    name: 'YouTube transcript generator',
    blurb: 'Paste a link, get the transcript with timestamps. Copy it or download TXT and SRT.',
  },
  {
    path: '/youtube-tag-generator',
    name: 'YouTube tag, title and description generator',
    blurb: 'Describe the video in a few lines, get tags, 10 title options or a description.',
  },
  {
    path: '/video-aspect-ratio-converter',
    name: 'Video to 9:16 converter',
    blurb: 'Turn a 16:9 video vertical with a blurred background, a crop or black bars. Runs in your browser.',
  },
]

const toolsHub = () => ({
  path: '/tools',
  title: 'Free Tools for YouTube and Short-Form Video | OpenShorts',
  description:
    'Free YouTube tools with no sign-up: transcript generator, tag, title and description generator, and a video to 9:16 converter that runs in your browser.',
  h1: 'Free tools for YouTube and short-form video',
  lede: 'Three small tools that do one job each, free and without an account. They come from the same team as the OpenShorts clip generator.',
  breadcrumb: [{ name: 'Free tools' }],
  published: PUBLISHED,
  updated: PUBLISHED,
  cta: false,
  relatedTitle: 'Also on this site',
  related: ['/auto-clip', '/youtube-automation', '/free-ai-clip-generator'],
  body: `
<div class="tools-grid">
${TOOLS.map((t) => `<a href="${t.path}"><strong>${esc(t.name)}</strong><span>${esc(t.blurb)}</span></a>`).join('\n')}
</div>

<h2>What each tool does, and what it does not</h2>
<p><a href="/youtube-transcript-generator">The transcript generator</a> reads the
captions a video already has on YouTube, either the ones the creator uploaded or
YouTube's automatic ones. It does not run speech recognition itself, so a video
with no captions at all gets an honest "no captions" instead of a guess.</p>
<p><a href="/youtube-tag-generator">The tag, title and description generator</a>
writes from a short brief you type, using Google Gemini. It follows the limits
YouTube documents: titles up to 100 characters, descriptions up to 5,000, tags up
to 500 characters in total.</p>
<p><a href="/video-aspect-ratio-converter">The 9:16 converter</a> works on your
device. The video is never uploaded, which is why it has no queue and no daily
cap. It keeps the whole frame over a blurred copy, crops to fill, or adds black
bars. It does not follow faces: that is what the clip generator is for.</p>

<h2>Where the paid product starts</h2>
<p>If what you want is not one transcript or one converted file but a long video
cut into several vertical clips with subtitles and the speaker kept in frame,
that is <a href="/free-ai-clip-generator">the free AI clip generator</a>: 20 free
minutes a month on OpenShorts Cloud, or unlimited if you self-host the MIT
licensed code. To have every new upload on your channel clipped without opening
anything, see <a href="/auto-clip">auto clip with Autopilot</a>.</p>
`,
  faq: [],
})

/* ------------------------------------------------------------------------ */
/* /youtube-transcript-generator                                             */
/* ------------------------------------------------------------------------ */

const transcriptTool = `
<section class="tool" id="tool" aria-label="YouTube transcript generator">
  <form id="yt-form" class="tool-row" autocomplete="off">
    <label for="yt-url" class="sr">YouTube video link</label>
    <input id="yt-url" name="url" type="url" inputmode="url" required
      placeholder="https://www.youtube.com/watch?v=...">
    <button type="submit" class="btn-primary">Get transcript</button>
  </form>
  <p class="tool-hint">Any public video with captions, including YouTube's auto-generated ones. Watch, youtu.be, Shorts and live links all work.</p>
  <div id="yt-status" class="tool-status" role="status" aria-live="polite" hidden></div>
  <div id="yt-result" hidden>
    <div class="tool-meta"><strong id="yt-title"></strong><span id="yt-sub"></span></div>
    <div class="tool-actions">
      <select id="yt-lang" aria-label="Caption track"></select>
      <label><input type="checkbox" id="yt-ts" checked> timestamps</label>
      <button type="button" id="yt-copy">Copy</button>
      <button type="button" id="yt-txt">Download TXT</button>
      <button type="button" id="yt-srt">Download SRT</button>
    </div>
    <div id="yt-text" class="transcript" tabindex="0" aria-label="Transcript"></div>
    <div class="cta-inline">
      <p>Want the best moments of this video as vertical clips with subtitles? OpenShorts cuts it into 3 to 15 shorts. 20 free minutes a month.</p>
      <button type="button" id="yt-clip" class="btn-primary">Turn this video into clips</button>
    </div>
  </div>
</section>`

const EXAMPLES = [
  ['arj7oStGLkU', 'Tim Urban, "Inside the Mind of a Master Procrastinator" (TED, 14 min)',
    '315 caption lines from the English track TED uploaded; the menu offers 50 tracks.'],
  ['UF8uR6Z6KLc', 'Steve Jobs, 2005 Stanford commencement address (15 min)',
    '244 caption lines; 9 tracks in the menu.'],
  ['8S0FDjFBj8o', 'Will Stephen, "How to sound smart in your TEDx Talk" (6 min)',
    '128 caption lines, a good short test.'],
]

const transcriptPage = () => ({
  path: '/youtube-transcript-generator',
  title: 'YouTube Transcript Generator: Free, TXT and SRT | OpenShorts',
  description:
    'Paste a YouTube link, get the full transcript with timestamps. Copy it or download TXT or SRT. Free, no sign-up, works with auto-generated captions.',
  h1: 'YouTube transcript generator',
  lede: 'Paste a link to a YouTube video and get its transcript with timestamps. Copy it, or download it as a TXT or SRT file. Free, no account.',
  breadcrumb: [{ name: 'Free tools', path: '/tools' }, { name: 'YouTube transcript generator' }],
  published: PUBLISHED,
  updated: PUBLISHED,
  cta: false,
  tool: { entry: 'tool-transcript', html: transcriptTool },
  relatedTitle: 'More free tools',
  related: ['/youtube-tag-generator', '/video-aspect-ratio-converter', '/youtube-to-shorts-converter'],
  body: `
<h2>How it works</h2>
<p>The tool asks YouTube for the captions the video already has. If the creator
uploaded subtitles in the language spoken in the video, you get those, because a
human wrote them. If not, you get YouTube's automatic captions, which are
speech recognition and read like it: no punctuation on older videos, and names
spelled the way they sound. When a video has several tracks, the menu above the
transcript switches between them. Machine translations are not offered, because
they are not what was said.</p>
<p>Timestamps link to that moment of the video. <strong>Copy</strong> takes the
text as shown (with or without timestamps), <strong>TXT</strong> saves the same
thing to a file, and <strong>SRT</strong> gives you a subtitle file you can load
into Premiere, DaVinci Resolve, CapCut or back into YouTube Studio.</p>

<h2>Try it with a real video</h2>
<p>These were checked on 23 September 2026. Click one to run it:</p>
<ul>
${EXAMPLES.map(([id, label, note]) => `<li><button type="button" class="btn-ghost" data-example-url="https://www.youtube.com/watch?v=${id}">Run</button> ${esc(label)}. ${esc(note)}</li>`).join('\n')}
</ul>

<h2>When there is no transcript</h2>
<p>Some videos have no captions at all: music, very new uploads that YouTube has
not processed yet, and channels that turned automatic captions off. Private,
members-only and age-restricted videos cannot be read either. In those cases the
tool says so rather than inventing text. If you need the words anyway, the
<a href="/free-ai-clip-generator">OpenShorts clip generator</a> runs its own
speech recognition with word-level timing and uses it to cut the video into
subtitled vertical clips.</p>

<h2>What people use a transcript for</h2>
<ul>
<li>Quoting a talk or an interview accurately, with the timestamp as the citation.</li>
<li>Turning a video into a blog post, a newsletter or show notes.</li>
<li>Pasting it into ChatGPT or Claude to summarise, find a moment or draft chapters.</li>
<li>Editing: an SRT lines the words up with the timeline in any video editor.</li>
</ul>

${faqBlock([
  {
    q: 'Is the YouTube transcript generator free?',
    a: 'Yes. There is no account and no payment. To keep it fast for everyone it allows 10 transcripts per 10 minutes from the same network.',
  },
  {
    q: 'Does it work on videos with only auto-generated captions?',
    a: 'Yes. When the creator has not uploaded subtitles, the tool returns YouTube\'s automatic captions in the language spoken in the video and labels them as auto-generated.',
  },
  {
    q: 'Why does it say a video has no captions?',
    a: 'Because YouTube has none for it: no uploaded subtitles and no automatic track. That happens with music, with very recent uploads and when a channel disables automatic captions. Private, members-only and age-restricted videos cannot be read at all.',
  },
  {
    q: 'Can I download the transcript as SRT?',
    a: 'Yes. The SRT button saves a subtitle file with one cue per caption line, which video editors and YouTube Studio can import.',
  },
  {
    q: 'Do you store the transcripts?',
    a: 'The server keeps the result for up to 24 hours so that the same video is not fetched from YouTube twice, and nothing is tied to you.',
  },
])}
`,
  faq: [
    { q: 'Is the YouTube transcript generator free?', a: 'Yes. There is no account and no payment. It allows 10 transcripts per 10 minutes from the same network.' },
    { q: 'Does it work on videos with only auto-generated captions?', a: 'Yes. Without uploaded subtitles it returns YouTube\'s automatic captions in the spoken language, labelled as auto-generated.' },
    { q: 'Why does it say a video has no captions?', a: 'Because YouTube has none for it: no uploaded subtitles and no automatic track. Private, members-only and age-restricted videos cannot be read at all.' },
    { q: 'Can I download the transcript as SRT?', a: 'Yes. The SRT button saves a subtitle file that video editors and YouTube Studio can import.' },
  ],
  extraNodes: [
    webApp('/youtube-transcript-generator', 'YouTube transcript generator',
      'Get the transcript of a YouTube video with timestamps from its existing captions. Copy it or download TXT and SRT.'),
  ],
})

/* ------------------------------------------------------------------------ */
/* /youtube-tag-generator                                                    */
/* ------------------------------------------------------------------------ */

const metadataTool = `
<section class="tool" id="tool" aria-label="YouTube tag, title and description generator">
  <form id="md-form">
    <fieldset class="modes">
      <legend class="sr">What to generate</legend>
      <label><input type="radio" name="mode" value="tags" checked> Tags</label>
      <label><input type="radio" name="mode" value="titles"> Titles</label>
      <label><input type="radio" name="mode" value="description"> Description</label>
    </fieldset>
    <label class="field" for="md-topic"><span>What is the video about? Who is it for? Paste timestamps if you want chapters.</span>
      <textarea id="md-topic" rows="4" maxlength="2000" required
        placeholder="Example: I bake sourdough at home with no stand mixer. I show the stretch and folds, the overnight proof in the fridge and how to tell when the loaf is done."></textarea>
    </label>
    <label class="field" for="md-keyword"><span>Main keyword (optional)</span>
      <input id="md-keyword" type="text" maxlength="80" placeholder="sourdough bread">
    </label>
    <button type="submit" id="md-go" class="btn-primary">Generate tags</button>
  </form>
  <div id="md-status" class="tool-status" role="status" aria-live="polite" hidden></div>
  <div id="md-out" class="out" hidden></div>
  <div id="md-cta" class="cta-inline" hidden>
    <p>Got the long video done? OpenShorts cuts it into vertical Shorts with subtitles, and its YouTube Studio writes titles from the video itself.</p>
    <a id="md-cta-btn" class="btn-primary" href="${SITE.url}/">Clip the video</a>
  </div>
</section>`

const SAMPLE_TAGS = ['procrastination', 'Tim Urban', 'TED talk', 'instant gratification monkey', 'panic monster',
  'why we procrastinate', 'Tim Urban TED talk', 'procrastination TED talk', 'long term goals', 'no deadline',
  'procrastinating', 'how to stop procrastinating', 'gratification monkey', 'Tim Urban procrastination',
  'Tim Urbin', 'procrastionation', 'psychology', 'productivity', 'TED']

const SAMPLE_TITLES = [
  'Why Procrastination Destroys Goals Without Deadlines',
  'How Procrastination Works Inside Your Brain',
  'Deadlines Actually Protect You From Procrastination',
  'The Kind of Procrastination Panic Cannot Fix',
  'Tim Urban on Procrastination',
]

const metadataPage = () => ({
  path: '/youtube-tag-generator',
  title: 'YouTube Tag, Title and Description Generator | OpenShorts',
  description:
    'Free YouTube tag generator that also writes titles and descriptions from a short brief. Stays inside YouTube\'s limits: 100-character titles, 500 for tags.',
  h1: 'YouTube tag, title and description generator',
  lede: 'Describe your video in a few lines and get tags, 10 title options or a full description. Free, no account.',
  breadcrumb: [{ name: 'Free tools', path: '/tools' }, { name: 'YouTube tag, title and description generator' }],
  published: PUBLISHED,
  updated: PUBLISHED,
  cta: false,
  tool: { entry: 'tool-metadata', html: metadataTool },
  relatedTitle: 'More free tools',
  related: ['/youtube-transcript-generator', '/video-aspect-ratio-converter', '/youtube-automation'],
  body: `
<h2>How to use it</h2>
<ol>
<li>Pick <strong>Tags</strong>, <strong>Titles</strong> or <strong>Description</strong>.</li>
<li>Write two or three sentences about the video: what happens in it, who it is for, anything specific (names, tools, places). Specific briefs get specific output.</li>
<li>Add the keyword you want to rank for, if you have one.</li>
<li>Click a tag to copy it, or copy all of them at once and paste them into the Tags field in YouTube Studio. Titles copy with one click; the description is editable before you copy it.</li>
</ol>
<p>Need the brief? Paste the video into the <a href="/youtube-transcript-generator">transcript generator</a> first and summarise from that.</p>

<h2>A real example</h2>
<p>This is unedited output from the generator on 23 September 2026, for the brief
<em>"A TED talk by Tim Urban about procrastination: the instant gratification
monkey, the panic monster, and why long-term goals with no deadline never get
done"</em> with the keyword <em>procrastination</em>.</p>
<p><strong>Tags</strong> (${SAMPLE_TAGS.join(', ').length} characters, note the two deliberate misspellings):</p>
<p><code>${esc(SAMPLE_TAGS.join(', '))}</code></p>
<p><strong>Five of the ten titles:</strong></p>
<ul>${SAMPLE_TITLES.map((t) => `<li>${esc(t)} <span class="sources">(${t.length} characters)</span></li>`).join('')}</ul>
<p><button type="button" class="btn-ghost" data-example-topic="A TED talk by Tim Urban about procrastination: the instant gratification monkey, the panic monster, and why long-term goals with no deadline never get done." data-example-keyword="procrastination">Load this brief</button></p>

<h2>What it follows, and why</h2>
<ul>
<li><strong>Tags matter less than you think.</strong> YouTube's own help page says tags "play a minimal role in your video's discovery" and are mainly useful when your topic is commonly misspelled. So the generator includes likely misspellings of the names in your brief, and the title and description deserve more of your time.</li>
<li><strong>Length limits.</strong> Titles can be up to 100 characters and descriptions up to 5,000. The tags field takes 500 characters in total, and the tool keeps the list under that and shows the count.</li>
<li><strong>The first lines of a description do the work.</strong> They are what shows before "more", so the generator puts the payoff and the keyword there.</li>
<li><strong>Three hashtags.</strong> YouTube shows up to three hashtags from the description next to the title and ignores every hashtag on a video that has more than 60.</li>
<li><strong>Nothing invented.</strong> The model is told to use only facts from your brief: no made-up numbers, guests or results, and no chapters unless you gave timestamps.</li>
</ul>

${faqBlock([
  {
    q: 'Is this YouTube tag generator free?',
    a: 'Yes, with no account. Each click is one call to Google Gemini on our side, so it allows 12 generations per 10 minutes and 50 a day from the same network.',
  },
  {
    q: 'Do YouTube tags still help SEO?',
    a: 'A little. YouTube says tags play a minimal role in discovery and are most useful for commonly misspelled topics. Your title, thumbnail and description matter more.',
  },
  {
    q: 'How long should a YouTube title be?',
    a: 'YouTube allows 100 characters. Search results and phones cut long titles, so the generator aims for about 60 and puts the main point first.',
  },
  {
    q: 'Which AI writes the titles and descriptions?',
    a: 'Google Gemini, the same model family OpenShorts uses to pick clips and write titles in its YouTube Studio.',
  },
  {
    q: 'Does it work in other languages?',
    a: 'Yes. Write the brief in your language and the output comes back in the same language.',
  },
])}

${sources([
  '<a href="https://support.google.com/youtube/answer/146402" rel="noopener">YouTube Help: Add tags to your videos</a> (tags play a minimal role; useful for misspellings), checked 23 September 2026.',
  '<a href="https://support.google.com/youtube/answer/57404" rel="noopener">YouTube Help: Edit video settings</a> (100-character titles, 5,000-character descriptions), checked 23 September 2026.',
  '<a href="https://developers.google.com/youtube/v3/docs/videos" rel="noopener">YouTube Data API: videos resource</a> (tags up to 500 characters), checked 23 September 2026.',
  '<a href="https://support.google.com/youtube/answer/6390658" rel="noopener">YouTube Help: Use hashtags for YouTube search</a> (up to three shown by the title, more than 60 ignored), checked 23 September 2026.',
])}
`,
  faq: [
    { q: 'Is this YouTube tag generator free?', a: 'Yes, with no account. It allows 12 generations per 10 minutes and 50 a day from the same network.' },
    { q: 'Do YouTube tags still help SEO?', a: 'A little. YouTube says tags play a minimal role in discovery and are most useful for commonly misspelled topics.' },
    { q: 'How long should a YouTube title be?', a: 'YouTube allows 100 characters. The generator aims for about 60 and puts the main point first.' },
    { q: 'Which AI writes the titles and descriptions?', a: 'Google Gemini.' },
  ],
  extraNodes: [
    webApp('/youtube-tag-generator', 'YouTube tag, title and description generator',
      'Generate YouTube tags, title options and a description from a short brief, within YouTube\'s length limits.', 'UtilitiesApplication'),
  ],
})

/* ------------------------------------------------------------------------ */
/* /video-aspect-ratio-converter                                             */
/* ------------------------------------------------------------------------ */

const verticalTool = `
<section class="tool" id="tool" aria-label="Video to 9:16 converter">
  <label class="drop" id="vc-drop" for="vc-file">
    <strong>Choose a video or drop it here</strong>
    <small id="vc-name">MP4, MOV or WebM. Up to 5 minutes are converted. The file stays on your device.</small>
    <input id="vc-file" type="file" accept="video/*,.mp4,.mov,.m4v,.webm,.mkv" class="sr">
  </label>
  <div class="opts">
    <fieldset>
      <legend>Fill the vertical frame with</legend>
      <div class="modes">
        <label><input type="radio" name="vc-fit" value="blur" checked> Blurred background</label>
        <label><input type="radio" name="vc-fit" value="crop"> Crop to fill</label>
        <label><input type="radio" name="vc-fit" value="bars"> Black bars</label>
      </div>
      <label class="field" id="vc-pos-wrap" for="vc-pos"><span>Crop position (left to right)</span>
        <input id="vc-pos" type="range" min="0" max="100" value="50">
      </label>
    </fieldset>
    <fieldset>
      <legend>Output size</legend>
      <div class="modes">
        <label><input type="radio" name="vc-size" value="1080" checked> 1080x1920</label>
        <label><input type="radio" name="vc-size" value="720"> 720x1280</label>
      </div>
    </fieldset>
  </div>
  <button type="button" id="vc-go" class="btn-primary" disabled>Convert to 9:16</button>
  <div id="vc-progress" class="progress" hidden><span></span></div>
  <div id="vc-status" class="tool-status" role="status" aria-live="polite" hidden></div>
  <div id="vc-result" class="vc-result" hidden>
    <video id="vc-preview" controls playsinline muted></video>
    <div>
      <p id="vc-info" class="tool-hint"></p>
      <p><button type="button" id="vc-download" class="btn-primary">Download</button></p>
      <div class="cta-inline">
        <p>Is someone talking in it? OpenShorts reframes with face tracking so the speaker stays in the frame, and cuts the long video into clips with subtitles.</p>
        <a id="vc-cta-btn" class="btn-primary" href="${SITE.url}/">Try the clip generator</a>
      </div>
    </div>
  </div>
</section>`

const verticalPage = () => ({
  path: '/video-aspect-ratio-converter',
  title: 'Video Aspect Ratio Converter (16:9 to 9:16) | OpenShorts',
  description:
    'Convert a video to 9:16 for TikTok, Reels and Shorts in your browser: blurred background, crop or black bars. Free, no upload, no watermark.',
  h1: 'Video aspect ratio converter: 16:9 to 9:16 in your browser',
  lede: 'Turn a horizontal video into a vertical 9:16 one for TikTok, Instagram Reels and YouTube Shorts. The conversion runs on your device, so nothing is uploaded.',
  breadcrumb: [{ name: 'Free tools', path: '/tools' }, { name: 'Video to 9:16 converter' }],
  published: PUBLISHED,
  updated: PUBLISHED,
  cta: false,
  tool: { entry: 'tool-vertical', html: verticalTool },
  relatedTitle: 'More free tools',
  related: ['/youtube-transcript-generator', '/youtube-tag-generator', '/youtube-to-shorts-converter'],
  body: `
<h2>The three ways to fill a vertical frame</h2>
<p>A 16:9 video is 1.78 times wider than it is tall; a 9:16 frame is 0.56. Something
has to give, and each option trades a different thing:</p>
<ul>
<li><strong>Blurred background</strong> keeps the whole picture, centred, over a
blurred and darkened copy of itself. Nothing is cut off, but the video only
fills about a third of the screen height. Good for screen recordings, slides and
wide shots.</li>
<li><strong>Crop to fill</strong> uses the full screen and keeps a vertical
slice of the frame, which you can slide left or right. It cuts away about two
thirds of the width, so it only works when the subject stays in one place.</li>
<li><strong>Black bars</strong> is the plain letterbox: the whole picture, with
the rest of the screen left black.</li>
</ul>
<p>The output is 1080x1920 or 720x1280, as MP4 (H.264) in Chrome, Edge and
Safari, or WebM in browsers that cannot encode H.264. Audio is kept.</p>

<h2>Why it runs in your browser</h2>
<p>Your browser already has a hardware video encoder, and the WebCodecs API lets
a page use it. So the file is read, re-framed and encoded on your machine and
never uploaded: no queue, no watermark, no account. The limits are the ones that
keep a browser tab stable: the first 5 minutes of the video and files up to
2 GB. Keep the tab open while it runs.</p>

<h2>When a fixed crop is not enough</h2>
<p>A fixed crop cannot follow a person who moves, and it cannot show two people
talking at the same time. That is what the
<a href="/youtube-to-shorts-converter">OpenShorts YouTube to Shorts converter</a>
does: it tracks faces with MediaPipe so the speaker stays in the frame, can stack
two people talking in a split screen, and cuts the long video into 3 to 15 clips
with subtitles.</p>


${faqBlock([
  {
    q: 'How do I convert a video to 9:16 for free?',
    a: 'Choose the file above, pick blurred background, crop or black bars, and click Convert. The video is processed in your browser and you download a 1080x1920 or 720x1280 file. There is no sign-up and no watermark.',
  },
  {
    q: 'Is my video uploaded anywhere?',
    a: 'No. The conversion runs on your device with your browser\'s own video encoder. The file never leaves your computer or phone.',
  },
  {
    q: 'Why is there a 5 minute limit?',
    a: 'The finished video is held in the browser\'s memory until you download it, and long 1080p videos can exhaust a tab. Short-form platforms rarely take more than a few minutes anyway.',
  },
  {
    q: 'Which browsers work?',
    a: 'Current versions of Chrome, Edge, Safari and Firefox. The tool needs the WebCodecs API; a browser without it shows a message instead of failing silently.',
  },
])}

${sources([
  '<a href="https://developer.mozilla.org/en-US/docs/Web/API/WebCodecs_API" rel="noopener">MDN: WebCodecs API</a>, the browser encoder this tool uses.',
  `<a href="https://github.com/Vanilagy/mediabunny" rel="noopener">Mediabunny</a>, the open source library that reads and writes the video files. Face tracking in the clip generator: the project source at <a href="${SITE.repo}" rel="noopener">github.com/mutonby/openshorts</a>.`,
])}
`,
  faq: [
    { q: 'How do I convert a video to 9:16 for free?', a: 'Choose the file, pick blurred background, crop or black bars, and click Convert. It runs in your browser with no sign-up and no watermark.' },
    { q: 'Is my video uploaded anywhere?', a: 'No. The conversion runs on your device with your browser\'s own video encoder.' },
    { q: 'Why is there a 5 minute limit?', a: 'The finished video is held in the browser\'s memory until you download it, and long 1080p videos can exhaust a tab.' },
    { q: 'Which browsers work?', a: 'Current versions of Chrome, Edge, Safari and Firefox. The tool needs the WebCodecs API.' },
  ],
  extraNodes: [
    webApp('/video-aspect-ratio-converter', 'Video to 9:16 converter',
      'Convert a horizontal video to vertical 9:16 in the browser with a blurred background, a crop or black bars.'),
  ],
})

export function toolPages() {
  return [toolsHub(), transcriptPage(), metadataPage(), verticalPage()]
}
