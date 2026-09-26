"""Free public tools behind the static SEO pages (/tools on openshorts.app).

Two endpoints, both anonymous, both deliberately cheap:

* ``GET /api/tools/youtube-transcript`` reads the captions a video **already
  has** on YouTube (manual subtitles first, then YouTube's own automatic
  track). It never downloads media and never touches the GPU: no Parakeet, no
  render. A video without captions gets an honest "no captions" answer and the
  page points at the clip generator, which does transcribe.
* ``POST /api/tools/youtube-metadata`` writes titles, a description or tags
  for a video from a short brief, with one Gemini text call.

Why yt-dlp and the static proxies. YouTube answers every anonymous request
from a datacenter IP with "Sign in to confirm you're not a bot" (measured from
the prod container on 23-sep-2026: direct = bot check in 0.8 s; the static ISP
pool = full caption list in 1.1 s). So the transcript goes out through the same
flat-rate ``STATIC_PROXY_URLS`` the download uses, anonymous first and with the
account cookies only as the second attempt on a route. It **never** uses the
per-GB ``PROXY_URL``: a free tool must not be able to run up a bandwidth bill.
With no statics configured (self-host) it goes direct.

Cost and abuse guards, all in-process (a restart resets them, which is fine
for limits this coarse): per-IP windows, a global daily cap per tool, a
semaphore on concurrent YouTube lookups, a hard timeout, and a 24 h cache so a
popular video is fetched once.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import tempfile
import threading
import time
from collections import OrderedDict, defaultdict, deque
from typing import Optional
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()

# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #
# (window seconds, max hits) per IP, plus one global cap per UTC day.
LIMITS = {
    "transcript": {"per_ip": [(600, 10), (86400, 60)], "global_day": 1500},
    "metadata": {"per_ip": [(600, 12), (86400, 50)], "global_day": 2000},
}


class RateLimiter:
    """Sliding windows per (tool, ip) and a fixed UTC-day counter per tool."""

    def __init__(self, limits, clock=time.time):
        self.limits = limits
        self.clock = clock
        self._hits = defaultdict(deque)
        self._day = {}
        self._lock = threading.Lock()

    def check(self, tool: str, ip: str) -> Optional[str]:
        """Record a hit and return None, or return the reason it is refused
        (nothing is recorded then)."""
        cfg = self.limits[tool]
        now = self.clock()
        day = int(now // 86400)
        with self._lock:
            d, n = self._day.get(tool, (day, 0))
            if d != day:
                d, n = day, 0
            if n >= cfg["global_day"]:
                return "global"
            hits = self._hits[(tool, ip)]
            longest = max(w for w, _ in cfg["per_ip"])
            while hits and now - hits[0] > longest:
                hits.popleft()
            for window, cap in cfg["per_ip"]:
                if sum(1 for t in hits if now - t <= window) >= cap:
                    return "ip"
            hits.append(now)
            self._day[tool] = (d, n + 1)
            # Keep the map from growing without bound on a long-lived process.
            if len(self._hits) > 20000:
                for key in [k for k, v in self._hits.items() if not v or now - v[-1] > longest]:
                    del self._hits[key]
        return None


_limiter = RateLimiter(LIMITS)


def client_ip(request: Request) -> str:
    # Traefik overwrites X-Forwarded-For from untrusted clients and uvicorn
    # resolves it into request.client, so this is the real peer address.
    return (request.client.host if request.client else "") or "unknown"


def _enforce(tool: str, request: Request):
    reason = _limiter.check(tool, client_ip(request))
    if reason == "ip":
        raise HTTPException(status_code=429, detail={
            "code": "rate_limited",
            "message": "Too many requests from your network. Try again in a few minutes."})
    if reason == "global":
        raise HTTPException(status_code=429, detail={
            "code": "busy",
            "message": "This free tool hit its daily limit. It resets at midnight UTC."})


# --------------------------------------------------------------------------- #
# YouTube transcript
# --------------------------------------------------------------------------- #
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_video_id(raw: str) -> Optional[str]:
    """The 11-character id of one YouTube video, or None.

    Accepts watch / youtu.be / shorts / live / embed links and a bare id. The
    request that goes out is always rebuilt from the id, so nothing the user
    typed (a playlist, another host, a redirect) ever reaches yt-dlp.
    """
    s = (raw or "").strip()
    if _VIDEO_ID.match(s):
        return s
    if not re.match(r"^https?://", s, re.I):
        s = "https://" + s
    try:
        u = urlparse(s)
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    if host == "youtu.be":
        cand = u.path.strip("/").split("/")[0]
        return cand if _VIDEO_ID.match(cand) else None
    if not (host == "youtube.com" or host.endswith(".youtube.com")
            or host == "youtube-nocookie.com" or host.endswith(".youtube-nocookie.com")):
        return None
    parts = [p for p in u.path.split("/") if p]
    if parts and parts[0] in ("watch", "watch_popup"):
        cand = (parse_qs(u.query).get("v") or [""])[0]
        return cand if _VIDEO_ID.match(cand) else None
    if len(parts) >= 2 and parts[0] in ("shorts", "live", "embed", "v", "e"):
        return parts[1] if _VIDEO_ID.match(parts[1]) else None
    return None


def _base_lang(code: str) -> str:
    return (code or "").split("-")[0].lower()


def choose_track(info: dict, lang: Optional[str] = None):
    """Pick the caption track to return: ``(kind, key, languages)``.

    kind is "manual" or "auto" (YouTube's speech recognition), key the entry
    in ``subtitles`` / ``automatic_captions``, languages what the user can
    switch to. Machine translations of the auto track (every other key in
    ``automatic_captions``) are never offered: they are not a transcript.
    Returns ``(None, None, languages)`` when the video has no captions.
    """
    manual = {k: v for k, v in (info.get("subtitles") or {}).items()
              if k != "live_chat" and v}
    auto = info.get("automatic_captions") or {}
    video_lang = info.get("language") or ""
    orig = [k for k in auto if k.endswith("-orig")]
    # Some videos list the ASR track under the plain language code only.
    if not orig and video_lang and video_lang in auto:
        orig = [video_lang]

    # ``request`` is what the page sends back as ``lang`` to switch track:
    # the plain code for a human track, ``<code>-orig`` for YouTube's ASR one.
    languages = [{"code": k, "kind": "manual", "request": k,
                  "name": _track_name(manual[k], k)} for k in manual]
    for k in orig:
        code = k[:-5] if k.endswith("-orig") else k
        languages.append({"code": code, "kind": "auto", "request": f"{code}-orig",
                          "name": _track_name(auto[k], code) + " (auto-generated)"})

    video_base = _base_lang(video_lang)
    languages.sort(key=lambda l: (_base_lang(l["code"]) != video_base,
                                  _base_lang(l["code"]) != "en", l["kind"] != "manual",
                                  l["name"].lower()))

    def auto_key(code):
        for k in orig:
            if k == f"{code}-orig" or k == code:
                return k
        return None

    if lang and lang.endswith("-orig"):
        k = auto_key(lang[:-5])
        if k:
            return "auto", k, languages
        lang = lang[:-5]
    if lang:
        if lang in manual:
            return "manual", lang, languages
        k = auto_key(lang)
        if k:
            return "auto", k, languages
    # Default: a human track in the spoken language, then the auto track in
    # the spoken language, then any human track (English first), then any auto.
    if video_lang:
        for k in manual:
            if k == video_lang or _base_lang(k) == _base_lang(video_lang):
                return "manual", k, languages
    if orig:
        return "auto", orig[0], languages
    if manual:
        for k in manual:
            if _base_lang(k) == "en":
                return "manual", k, languages
        return "manual", next(iter(manual)), languages
    return None, None, languages


def _track_name(formats, code):
    for f in formats or []:
        if f.get("name"):
            return re.sub(r"\s*\(.*?\)\s*$", "", f["name"]).strip() or code
    return code


def parse_json3(data) -> list:
    """YouTube json3 captions -> [{start, dur, text}] in seconds.

    Events without segments are window/style markers; ``\\n``-only events are
    the line breaks of the rolling auto captions. Both are dropped.
    """
    if isinstance(data, (bytes, str)):
        data = json.loads(data)
    out = []
    for ev in data.get("events") or []:
        segs = ev.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs)
        text = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
        if not text:
            continue
        start = (ev.get("tStartMs") or 0) / 1000.0
        dur = (ev.get("dDurationMs") or 0) / 1000.0
        out.append({"start": round(start, 3), "dur": round(dur, 3), "text": text})
    # Auto captions overlap (each line stays on screen until the next one
    # ends); clamp so exported SRT cues never collide.
    for a, b in zip(out, out[1:]):
        if a["start"] + a["dur"] > b["start"]:
            a["dur"] = round(max(0.0, b["start"] - a["start"]), 3)
    return out


def is_degraded(info: dict) -> bool:
    """True for a watch page YouTube served without its player response.

    Keyed on the duration, not on the formats: a finished live stream answers
    with a duration and zero formats, and it genuinely has no captions (that
    one used to be reported as "YouTube is blocking us").
    """
    return not info.get("formats") and not info.get("duration")


class TranscriptError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


_UNAVAILABLE = re.compile(
    r"private video|video unavailable|has been removed|not available|members-only|"
    r"confirm your age|age-restricted|copyright|terminated|does not exist|premieres in",
    re.I)
_BLOCKED = re.compile(r"not a bot|sign in to confirm|429|too many requests|403|"
                      r"unable to download|timed out|proxy|connection", re.I)

_TRANSCRIPT_CACHE: "OrderedDict[tuple, tuple]" = OrderedDict()
_CACHE_TTL = 24 * 3600
_CACHE_MAX = 400
_cache_lock = threading.Lock()
_yt_slots = threading.BoundedSemaphore(int(os.environ.get("FREE_TOOLS_YT_CONCURRENCY", "3")))
TRANSCRIPT_TIMEOUT = float(os.environ.get("FREE_TOOLS_YT_TIMEOUT", "45"))


def _cache_get(key):
    with _cache_lock:
        hit = _TRANSCRIPT_CACHE.get(key)
        if not hit:
            return None
        ts, value = hit
        if time.time() - ts > _CACHE_TTL:
            del _TRANSCRIPT_CACHE[key]
            return None
        _TRANSCRIPT_CACHE.move_to_end(key)
        return value


def _cache_put(key, value):
    with _cache_lock:
        _TRANSCRIPT_CACHE[key] = (time.time(), value)
        _TRANSCRIPT_CACHE.move_to_end(key)
        while len(_TRANSCRIPT_CACHE) > _CACHE_MAX:
            _TRANSCRIPT_CACHE.popitem(last=False)


def transcript_routes():
    """Proxies to try, in order. Statics only (rotated); direct when there are
    none. Never the per-GB PROXY_URL."""
    statics = [p.strip() for p in os.environ.get("STATIC_PROXY_URLS", "").split(",")
               if p.strip()]
    if statics:
        k = random.randrange(len(statics))
        statics = statics[k:] + statics[:k]
        routes = statics[:3]
        if os.environ.get("DIRECT_FIRST", "").strip() == "1":
            routes = [None] + routes
        return routes
    return [None]


class _QuietLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def fetch_transcript(video_id: str, lang: Optional[str] = None) -> dict:
    """Blocking: resolve the caption track and download it. Raises
    TranscriptError with a user-facing message."""
    import yt_dlp

    url = f"https://www.youtube.com/watch?v={video_id}"
    cookies_env = os.environ.get("YOUTUBE_COOKIES")
    ck_path = None
    errors = []
    try:
        if cookies_env:
            fd, ck_path = tempfile.mkstemp(prefix="tool_ck_", suffix=".txt")
            with os.fdopen(fd, "w") as f:
                f.write(cookies_env)
        for proxy in transcript_routes():
            for use_cookies in ([False, True] if ck_path else [False]):
                opts = {"skip_download": True, "quiet": True, "no_warnings": True,
                        "noplaylist": True, "logger": _QuietLogger(),
                        "socket_timeout": 15,
                        # Captions only: without this a video whose formats are
                        # SABR-only fails with "Requested format is not available"
                        # although its caption list came back fine.
                        "ignore_no_formats_error": True,
                        "extractor_args": {"youtube": {"player_client": ["default"]}}}
                if proxy:
                    opts["proxy"] = proxy
                if use_cookies:
                    opts["cookiefile"] = ck_path
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        kind, key, languages = choose_track(info, lang)
                        meta = {
                            "video_id": video_id,
                            "title": info.get("title") or "",
                            "channel": info.get("channel") or info.get("uploader") or "",
                            "duration": info.get("duration") or 0,
                            "languages": languages,
                        }
                        if not kind and is_degraded(info):
                            # A degraded answer: anonymous requests from two
                            # of the three statics got the watch page without
                            # its player response (title, but no duration, no
                            # formats, no captions) for a TED talk with 49
                            # human tracks (23-sep-2026); the same routes with
                            # the cookies answered in full. That is the route,
                            # not the video: try the next attempt.
                            errors.append("empty player response")
                            continue
                        if not kind:
                            raise TranscriptError(
                                "no_captions",
                                "This video has no captions on YouTube, not even automatic ones.",
                                404)
                        pool = (info.get("subtitles") if kind == "manual"
                                else info.get("automatic_captions")) or {}
                        fmt = next((f for f in pool.get(key, []) if f.get("ext") == "json3"), None)
                        if not fmt:
                            raise TranscriptError(
                                "no_captions",
                                "YouTube lists captions for this video but does not serve them in a readable format.",
                                404)
                        raw = ydl.urlopen(fmt["url"]).read()
                    segments = parse_json3(raw)
                    if not segments:
                        raise TranscriptError(
                            "no_captions", "The caption track for this video is empty.", 404)
                    code = key[:-5] if key.endswith("-orig") else key
                    return {**meta, "language": code, "kind": kind, "segments": segments}
                except TranscriptError:
                    raise
                except Exception as e:  # noqa: BLE001 — classified below
                    msg = str(e)
                    errors.append(msg[:300])
                    if _UNAVAILABLE.search(msg) and not re.search(r"not a bot", msg, re.I):
                        raise TranscriptError(
                            "unavailable",
                            "YouTube says this video is private, removed, age-restricted or not "
                            "available, so its captions cannot be read.", 422)
        raise TranscriptError(
            "youtube_blocked",
            "YouTube is not answering our servers right now. Try again in a minute, or open "
            "the video on YouTube and use \"Show transcript\" under the description.", 503)
    finally:
        if ck_path:
            try:
                os.remove(ck_path)
            except OSError:
                pass


def _fetch_with_slot(video_id, lang):
    if not _yt_slots.acquire(timeout=20):
        raise TranscriptError("busy", "The transcript tool is busy. Try again in a few seconds.", 503)
    try:
        return fetch_transcript(video_id, lang)
    finally:
        _yt_slots.release()


@router.get("/api/tools/youtube-transcript")
async def youtube_transcript(request: Request, url: str = "", lang: str = ""):
    video_id = extract_video_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail={
            "code": "bad_url",
            "message": "Paste the link of one YouTube video (youtube.com/watch?v=..., youtu.be/... or a Shorts link)."})
    lang = lang.strip() if re.match(r"^[A-Za-z0-9-]{1,20}$", lang.strip() or "") else None
    key = (video_id, lang or "")
    cached = _cache_get(key)
    if cached and "error" in cached:
        e = cached["error"]
        raise HTTPException(status_code=e["status"], detail={"code": e["code"], "message": e["message"]})
    if cached:
        return {**cached, "cached": True}
    _enforce("transcript", request)
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_fetch_with_slot, video_id, lang), timeout=TRANSCRIPT_TIMEOUT)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail={
            "code": "timeout", "message": "YouTube took too long to answer. Try again."})
    except TranscriptError as e:
        if e.code in ("no_captions", "unavailable"):
            # Cache the verdict about the video itself (not a blocked route):
            # it will not change within the day, and a retry loop on it would
            # spend the static pool for nothing.
            _cache_put(key, {"error": {"code": e.code, "message": e.message, "status": e.status}})
        raise HTTPException(status_code=e.status, detail={"code": e.code, "message": e.message})
    _cache_put(key, result)
    if not lang:
        req = result["language"] + ("-orig" if result["kind"] == "auto" else "")
        _cache_put((video_id, req), result)
    return {**result, "cached": False}


# --------------------------------------------------------------------------- #
# YouTube title / description / tag generator
# --------------------------------------------------------------------------- #
MODES = ("titles", "description", "tags")
MAX_BRIEF = 2000


class MetadataRequest(BaseModel):
    mode: str
    topic: str
    keyword: Optional[str] = ""
    audience: Optional[str] = ""


_COMMON_RULES = """
- Write in the same language as the BRIEF. Never translate it.
- Use only facts present in the BRIEF. Do not invent numbers, results, names, prices, dates or guests.
- No emojis, no ALL CAPS words, no em dashes.
- Plain, specific wording a creator would actually publish. Avoid filler such as "in today's video", "ultimate guide", "you won't believe", "game-changer", "unlock", "dive into".
"""

PROMPTS = {
    "titles": """You write YouTube video titles.

BRIEF (what the video is about):
{topic}
{extra}
Write 10 title options, each with a different angle: specific outcome, how-to with a concrete promise, question the viewer already asks, number or list, contrarian take, curiosity gap that the video actually pays off, short and direct.

Rules:
- Hard limit 100 characters (YouTube's maximum). Aim for 60 or fewer: search results and phones cut long titles, so the payoff must come first.
- Put the main keyword early when it reads naturally, but vary the structure: no more than three titles may start with the same word, and never use a "Keyword: ..." colon pattern more than twice.{keyword_rule}
- Never promise something the brief does not support.
{common}
Return JSON: {{"titles": [{{"title": "...", "angle": "2-4 word label for the angle"}}]}}""",

    "description": """You write YouTube video descriptions.

BRIEF (what the video is about):
{topic}
{extra}
Write one description, 120 to 250 words, structured like this:
1. First two sentences (under 150 characters together): what the viewer gets from the video, with the main keyword in the first sentence. These are the only lines shown before "more", in search results and under the player.
2. A short paragraph with the specifics from the brief: what is covered, for whom.
3. If the BRIEF contains timestamps, a chapter list in "00:00 Title" format starting at 00:00. If it contains no timestamps, write no chapters and no timestamps at all.
4. One line inviting a specific next step (subscribe, comment with a question about the topic). Put placeholders like [link] where the creator should paste links; never invent URLs.
5. A final line with exactly 3 relevant hashtags (YouTube shows up to three next to the title).{keyword_rule}
{common}
Return JSON: {{"description": "..."}}""",

    "tags": """You pick YouTube tags.

BRIEF (what the video is about):
{topic}
{extra}
Return 15 to 25 tags ordered from most to least important:
- the exact main keyword first{keyword_rule_short}
- close variations and long-tail phrasings people type into YouTube search
- common misspellings of names or terms in the brief, if any (YouTube says tags mainly help when the topic is commonly misspelled)
- 2 or 3 broader topic tags
Rules: lowercase unless a proper noun, no hashtags, no duplicates, each tag under 30 characters, and all tags joined with commas must stay under 450 characters (YouTube's limit is 500).
{common}
Return JSON: {{"tags": ["...", "..."]}}""",
}


def build_prompt(mode: str, topic: str, keyword: str = "", audience: str = "") -> str:
    extra = f"TARGET AUDIENCE: {audience}\n" if audience else ""
    kw_rule = (f"\n- The main keyword is \"{keyword}\": use it naturally, exactly once in the "
               f"part that matters most." if keyword else "")
    kw_short = f" (\"{keyword}\")" if keyword else ""
    return PROMPTS[mode].format(topic=topic, extra=extra, keyword_rule=kw_rule,
                                keyword_rule_short=kw_short, common=_COMMON_RULES)


def _clean(s: str) -> str:
    return re.sub(r"\s*—\s*", ", ", (s or "")).strip()


def shape_result(mode: str, data: dict) -> dict:
    """Validate and tidy the model's JSON into what the page renders."""
    if mode == "titles":
        items = []
        for t in (data.get("titles") or [])[:12]:
            if isinstance(t, str):
                t = {"title": t, "angle": ""}
            title = _clean(str(t.get("title", "")))[:100]
            if title:
                items.append({"title": title, "angle": _clean(str(t.get("angle", "")))[:40]})
        if not items:
            raise ValueError("no titles")
        return {"titles": items}
    if mode == "description":
        desc = _clean(str(data.get("description", "")))[:5000]
        if not desc:
            raise ValueError("no description")
        return {"description": desc}
    seen, tags, total = set(), [], 0
    for t in data.get("tags") or []:
        t = re.sub(r"\s+", " ", str(t).replace("#", "").replace(",", " ")).strip()[:60]
        if not t or t.lower() in seen:
            continue
        if total + len(t) + (1 if tags else 0) > 500:
            break
        seen.add(t.lower())
        tags.append(t)
        total += len(t) + (1 if len(tags) > 1 else 0)
    if not tags:
        raise ValueError("no tags")
    return {"tags": tags, "characters": len(",".join(tags))}


def _gemini_key():
    try:
        from cloud import managed_keys
        key = managed_keys.gemini_key()
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY", "").strip() or None


METADATA_MODEL = (os.environ.get("FREE_TOOLS_GEMINI_MODEL")
                  or os.environ.get("GEMINI_MODEL_THUMBNAIL") or "gemini-3.7-flash")


def _thinking_config(types):
    try:
        return types.ThinkingConfig(thinking_level="low")
    except Exception:  # older SDK without thinking_level
        return None


def _generate(prompt: str) -> dict:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=_gemini_key())
    resp = client.models.generate_content(
        model=METADATA_MODEL,
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            # Thinking tokens count against max_output_tokens on the 3.x
            # models; at 2048 with default thinking the description came back
            # cut mid-string. Low thinking + a roomier cap keeps it whole and
            # the cost per call at a few thousand tokens.
            max_output_tokens=6000,
            temperature=0.9,
            thinking_config=_thinking_config(types),
        ),
    )
    text = (resp.text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text).strip()
    return json.loads(text)


@router.post("/api/tools/youtube-metadata")
async def youtube_metadata(payload: MetadataRequest, request: Request):
    mode = (payload.mode or "").strip().lower()
    if mode not in MODES:
        raise HTTPException(status_code=400, detail={"code": "bad_mode", "message": "Unknown mode."})
    topic = (payload.topic or "").strip()
    if len(topic) < 15:
        raise HTTPException(status_code=400, detail={
            "code": "too_short",
            "message": "Describe the video in at least a sentence: what happens in it and who it is for."})
    topic = topic[:MAX_BRIEF]
    keyword = re.sub(r"[\"\n\r{}]", " ", (payload.keyword or "")).strip()[:80]
    audience = re.sub(r"[\n\r{}]", " ", (payload.audience or "")).strip()[:120]
    if not _gemini_key():
        raise HTTPException(status_code=503, detail={
            "code": "not_configured", "message": "This tool needs a Gemini API key on the server."})
    _enforce("metadata", request)
    prompt = build_prompt(mode, topic.replace("{", "(").replace("}", ")"), keyword, audience)
    last = None
    for _ in range(2):
        try:
            data = await asyncio.wait_for(asyncio.to_thread(_generate, prompt), timeout=40)
            return {"mode": mode, **shape_result(mode, data)}
        except asyncio.TimeoutError:
            last = "timeout"
            break
        except Exception as e:  # noqa: BLE001 — model/JSON errors retry once
            last = str(e)[:200]
    print(f"[free_tools] metadata generation failed: {last}")
    raise HTTPException(status_code=502, detail={
        "code": "generation_failed", "message": "The generator did not answer. Try again."})
