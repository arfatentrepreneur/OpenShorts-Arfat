"""Who is talking, from mouth movement plus audio energy.

The SPLIT layout shipped without this and it is the thing that decides whether
the format lands or grates: stacking is only worth half the frame when both
people actually take turns. Geometry alone will stack a scene where one person
sits silent for thirty seconds.

Full diarisation is not needed to answer "which of these two faces is moving its
mouth right now". This measures frame-to-frame change in the mouth region of
each known face box, and only trusts the comparison in windows where the audio
says somebody is speaking at all — otherwise a nod, a laugh or a chewed sweet
scores as speech.

The two faces come from split_layout's medians, so no per-frame face detection
runs here: the subjects of a two-shot are seated and the boxes hold.

Everything in this module is pure enough to unit-test except decode_activity(),
which needs ffmpeg.
"""
import os
import subprocess

import numpy as np

# Seconds per decision window. Short enough to catch a one-word interjection,
# long enough that a single blurred frame cannot flip the answer.
WINDOW_SECONDS = 0.4

# Off by default like every other new routing signal here. SPEAKER_SIGNAL=1
# gates SPLIT on both people actually talking; SPEAKER_CUT=1 additionally
# replaces the stack with hard cuts to whoever holds the floor.
ENABLED = os.environ.get("SPEAKER_SIGNAL", "0") == "1"
CUT_MODE = os.environ.get("SPEAKER_CUT", "0") == "1"

# A window counts as speech only if its audio RMS clears this fraction of the
# scene's loudest window. Silence and room tone sit far below it.
AUDIO_FLOOR = 0.18

# The winner's mouth must be this much more active than the other's, relative to
# the pair's total, before the window is attributed. Below it the window is
# "unclear" and simply does not vote — which is the honest answer when both are
# still or both are moving.
MIN_MARGIN = 0.15

# Share of attributed windows each speaker needs before a two-shot counts as a
# conversation. At 0.2 a listener who chips in every fifth window still counts;
# a genuinely silent listener does not.
MIN_SHARE = float(os.environ.get("SPLIT_MIN_SHARE", "0.2"))

ANALYSIS_WIDTH = 480


def mouth_region(box, frame_w, frame_h, scale=1.0):
    """Pixel rect (x0, y0, x1, y1) around the mouth of a face box.

    MediaPipe boxes cover brow to chin, so the mouth sits low and central. The
    region is deliberately wider than the lips: jaw movement carries as much
    signal as the lips themselves and survives a box that drifts a little.
    """
    x, y, w, h = [v / scale for v in box]
    cx = x + w / 2.0
    mouth_y = y + h * 0.72
    half_w = w * 0.36
    half_h = h * 0.22

    x0 = int(max(0, min(cx - half_w, frame_w - 1)))
    x1 = int(max(x0 + 1, min(cx + half_w, frame_w)))
    y0 = int(max(0, min(mouth_y - half_h, frame_h - 1)))
    y1 = int(max(y0 + 1, min(mouth_y + half_h, frame_h)))
    return x0, y0, x1, y1


def audio_envelope(video_path, start_s, duration_s, window_s=WINDOW_SECONDS):
    """Per-window RMS of the clip's audio, normalised to its own peak.

    Returns [] when the source has no audio track, which makes every window
    eligible rather than none: a silent source should fall back to mouth
    movement alone, not refuse to decide.
    """
    try:
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{start_s:.4f}",
             "-t", f"{duration_s:.4f}", "-i", video_path,
             "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=300).stdout
    except (subprocess.SubprocessError, OSError):
        return []
    if not raw:
        return []

    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    per_window = max(1, int(8000 * window_s))
    n = len(samples) // per_window
    if n < 1:
        return []

    windows = samples[:n * per_window].reshape(n, per_window)
    rms = np.sqrt(np.mean(windows ** 2, axis=1))
    peak = rms.max()
    return (rms / peak).tolist() if peak > 0 else [0.0] * n


def normalise_activity(activity):
    """Rescale each speaker's mouth activity onto its own quiet-to-loud range.

    Raw frame-difference magnitude is not comparable between two faces: it
    scales with the local contrast, the lighting and the size of the box, so
    whichever speaker happens to be better lit wins every window. Measured on a
    real two-shot, the raw signal handed one speaker 90-100% of the scene.

    Subtracting each speaker's own 20th percentile (their resting state) and
    dividing by their own 20-80 spread compares "how active is this mouth for
    this person" instead. Windows where nobody speaks are already dropped by the
    audio gate, so a silent listener's amplified noise never gets a vote.
    """
    if not activity:
        return []
    columns = np.asarray(activity, dtype=float)
    if columns.ndim != 2 or columns.shape[1] < 2:
        return activity

    low = np.percentile(columns, 20, axis=0)
    high = np.percentile(columns, 80, axis=0)
    spread = np.where(high - low > 1e-6, high - low, 1.0)
    return np.clip((columns - low) / spread, 0.0, None).tolist()


def attribute_windows(activity, loudness, min_margin=MIN_MARGIN):
    """Which speaker owns each window, or None when it is not clear.

    ``activity`` is [[a0, a1], ...], one mouth-movement score per speaker per
    window; ``loudness`` is the normalised audio envelope (or [] for none).
    """
    verdicts = []
    for i, pair in enumerate(activity):
        if loudness and i < len(loudness) and loudness[i] < AUDIO_FLOOR:
            verdicts.append(None)          # nobody is talking here
            continue
        a, b = pair
        total = a + b
        if total <= 0:
            verdicts.append(None)
            continue
        margin = abs(a - b) / total
        verdicts.append(None if margin < min_margin else (0 if a > b else 1))
    return verdicts


def shares(verdicts):
    """Fraction of attributed windows held by each speaker: (share0, share1).

    Returns (0.0, 0.0) when nothing was attributed, so callers see "no evidence"
    rather than a spurious 50/50.
    """
    counted = [v for v in verdicts if v is not None]
    if not counted:
        return 0.0, 0.0
    n = float(len(counted))
    return counted.count(0) / n, counted.count(1) / n


def is_conversation(verdicts, min_share=None):
    """True when both speakers hold enough of the attributed windows."""
    min_share = MIN_SHARE if min_share is None else min_share
    a, b = shares(verdicts)
    return min(a, b) >= min_share


def hold(verdicts, min_windows=3):
    """Smooth the per-window verdicts so the answer cannot flap.

    A cut back and forth every 0.4s is unwatchable, and a listener's single
    "yeah" should not steal the frame. Unclear windows inherit the current
    speaker, and a new speaker must hold ``min_windows`` in a row to take over.
    """
    out = []
    current = None
    pending = None
    run = 0
    for v in verdicts:
        if v is None or v == current:
            if v == current:
                pending, run = None, 0
            out.append(current)
            continue
        if v == pending:
            run += 1
        else:
            pending, run = v, 1
        if current is None or run >= min_windows:
            current, pending, run = v, None, 0
        out.append(current)

    # Nothing was ever confident enough to start: leave it to the caller.
    if all(v is None for v in out):
        return out

    # Backfill the lead-in with whoever spoke first.
    first = next(v for v in out if v is not None)
    return [first if v is None else v for v in out]


def speaker_xs(held, centres, crop_w, orig_w, n_frames, fps,
               window_s=WINDOW_SECONDS):
    """Per-frame crop x that cuts to whoever is speaking.

    Reuses the TRACK render path: a camera trajectory with hard jumps is still
    just a list of x positions, so no new filtergraph is needed.
    """
    xs = []
    for f in range(n_frames):
        idx = min(int((f / fps) / window_s), len(held) - 1) if held else 0
        who = held[idx] if held else 0
        cx = centres[who if who is not None else 0][0]
        x = int(round(cx - crop_w / 2.0))
        xs.append(max(0, min(x, orig_w - crop_w)))
    return xs


def verdicts_for_scene(video_path, start_f, end_f, fps, centres):
    """Per-window speaker verdicts for one scene, from its two face centres."""
    import split_layout

    start_s = start_f / fps
    duration_s = (end_f - start_f) / fps
    boxes = [split_layout.as_box(c) for c in centres]
    activity = decode_activity(video_path, start_s, duration_s, boxes, fps)
    loudness = audio_envelope(video_path, start_s, duration_s)
    return attribute_windows(normalise_activity(activity), loudness)


def decode_activity(video_path, start_s, duration_s, boxes, fps,
                    window_s=WINDOW_SECONDS):
    """Mouth-movement score per speaker per window over one scene.

    Decodes the scene once at ANALYSIS_WIDTH and measures mean absolute
    frame-to-frame change inside each speaker's mouth region.
    """
    import cv2

    probe = cv2.VideoCapture(video_path)
    orig_w = int(probe.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h = int(probe.get(cv2.CAP_PROP_FRAME_HEIGHT))
    probe.release()
    if not orig_w or not orig_h:
        return []

    small_w = min(ANALYSIS_WIDTH, orig_w)
    small_w -= small_w % 2
    small_h = max(int(orig_h * small_w / orig_w), 2)
    small_h += small_h % 2
    scale = orig_w / float(small_w)
    frame_bytes = small_w * small_h * 3

    regions = [mouth_region(b, small_w, small_h, scale) for b in boxes]

    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-ss", f"{start_s:.4f}",
         "-t", f"{duration_s:.4f}", "-i", video_path,
         "-vf", f"scale={small_w}:{small_h}", "-f", "rawvideo",
         "-pix_fmt", "gray", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        bufsize=small_w * small_h * 4)

    per_window = max(1, int(round(fps * window_s)))
    activity, bucket, prev = [], [], None
    try:
        while True:
            buf = proc.stdout.read(small_w * small_h)
            if len(buf) < small_w * small_h:
                break
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(small_h, small_w)
            if prev is not None:
                bucket.append([
                    float(np.mean(np.abs(
                        frame[y0:y1, x0:x1].astype(np.int16)
                        - prev[y0:y1, x0:x1].astype(np.int16))))
                    for x0, y0, x1, y1 in regions])
            prev = frame
            if len(bucket) >= per_window:
                activity.append(np.mean(bucket, axis=0).tolist())
                bucket = []
    finally:
        proc.stdout.close()
        proc.wait()

    if bucket:
        activity.append(np.mean(bucket, axis=0).tolist())
    return activity
