// First-touch attribution: where a visitor came from, captured before anything
// can overwrite it.
//
// `document.referrer` is only populated on the very first page of a session and
// is wiped by our own auth redirects (Google bounces through accounts.google.com,
// magic links arrive from the mail client). So we snapshot it on the first load
// and keep it in localStorage until the user actually signs up, which can be
// several navigations later.
//
// First touch wins: once stored, capture() never overwrites. That way a visitor
// who arrives from GitHub, wanders off and comes back via a Google search is
// still attributed to GitHub.

const KEY = 'os_attrib';
const SENT_KEY = 'os_attrib_sent';

const read = (k) => { try { return localStorage.getItem(k); } catch (_) { return null; } };
const write = (k, v) => { try { localStorage.setItem(k, v); } catch (_) { /* private mode */ } };

/** Snapshot the entry point. Safe to call on every load; only the first sticks. */
export function capture() {
  if (read(KEY)) return;
  try {
    const params = new URLSearchParams(window.location.search);
    const referrer = document.referrer || '';
    // Ignore self-referrals: an internal navigation is not an acquisition source.
    const sameOrigin = referrer.startsWith(window.location.origin);
    const data = {
      referrer: sameOrigin ? '' : referrer,
      landing_path: window.location.pathname + window.location.search,
      utm_source: params.get('utm_source') || '',
      utm_medium: params.get('utm_medium') || '',
      utm_campaign: params.get('utm_campaign') || '',
    };
    // Nothing worth storing (direct hit, no campaign): still record it, so a
    // genuine direct visit is distinguishable from "we failed to capture".
    write(KEY, JSON.stringify(data));
  } catch (_) { /* never break boot over analytics */ }
}

/**
 * The first-touch snapshot flattened into event props: which page the visit
 * started on (the static SEO pages write this same key, see seo/render.js),
 * where from, and the campaign. Empty object when nothing was captured.
 */
export function firstTouchProps() {
  try {
    const raw = read(KEY);
    if (!raw) return {};
    const d = JSON.parse(raw);
    let host = '';
    try { host = d.referrer ? new URL(d.referrer).hostname : ''; } catch (_) { /* malformed */ }
    const props = {
      landing_path: String(d.landing_path || '').split('?')[0] || '/',
      referrer_host: host || 'direct',
    };
    if (d.utm_source) props.utm_source = d.utm_source;
    if (d.utm_medium) props.utm_medium = d.utm_medium;
    if (d.utm_campaign) props.utm_campaign = d.utm_campaign;
    return props;
  } catch (_) {
    return {};
  }
}

/**
 * Post the snapshot for a freshly signed-up user. Fire-and-forget: the server
 * drops it if the account is not brand new or already has a row.
 */
export async function report(apiJson) {
  if (read(SENT_KEY) === '1') return;
  const raw = read(KEY);
  if (!raw) return;
  try {
    await apiJson('/api/auth/attribution', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: raw,
    });
    write(SENT_KEY, '1');
  } catch (_) { /* attribution must never affect the sign-in */ }
}
