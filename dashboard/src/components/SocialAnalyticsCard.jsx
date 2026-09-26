import React, { useEffect, useState } from 'react';
import { BarChart3, ExternalLink } from 'lucide-react';
import { apiJson } from '../lib/api';

const fmtNum = (n) => new Intl.NumberFormat('en-US', {
  notation: (n || 0) >= 10000 ? 'compact' : 'standard',
  maximumFractionDigits: 1,
}).format(n || 0);

// Upload-Post metric shapes vary per platform; read the first count that exists.
const postViews = (p) => {
  const m = p.post_metrics || p.metrics || p;
  return Number(m.views || m.impressions || m.plays || 0) || 0;
};
const postTitle = (p) => p.title || p.caption || p.youtube_title || p.tiktok_title || 'untitled post';
const postUrl = (p) => p.post_url || p.url || p.share_url || null;

// Post-publication analytics: what the clips actually did out there.
// Paid-only by nature (social posting itself is paid in cloud): a 402 or any
// other failure simply hides the card — the account page works without it.
export default function SocialAnalyticsCard() {
  const [data, setData] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [imp, postsResp] = await Promise.all([
          apiJson('/api/social/analytics/impressions?period=last_month&breakdown=true'),
          apiJson('/api/social/analytics/posts?limit=50'),
        ]);
        if (!alive) return;
        const posts = (postsResp.posts || postsResp.data || postsResp.items || [])
          .slice()
          .sort((a, b) => postViews(b) - postViews(a));
        setData({ imp, posts });
      } catch (_) { /* free plan, nothing connected, or vendor hiccup — stay hidden */ }
    })();
    return () => { alive = false; };
  }, []);

  if (!data) return null;

  const total = data.imp?.total_impressions
    || data.posts.reduce((s, p) => s + postViews(p), 0);
  const perPlatform = Object.entries(data.imp?.per_platform || {})
    .filter(([, v]) => Number(v) > 0)
    .sort((a, b) => Number(b[1]) - Number(a[1]));
  const top = data.posts.slice(0, 3);

  return (
    <div className="card p-6">
      <div className="flex items-baseline justify-between gap-4 mb-1">
        <h3 className="font-display lowercase text-lg text-ink flex items-center gap-2">
          <BarChart3 size={16} className="text-brass" /> Your posts
        </h3>
        <span className="text-muted text-xs lowercase">last 30 days</span>
      </div>

      {data.posts.length === 0 && !total ? (
        <p className="text-muted text-sm lowercase">
          Nothing published yet. Post a clip from your results and its views show up here.
        </p>
      ) : (
        <>
          <div className="flex items-end gap-3 mb-3">
            <span className="readout text-2xl text-ink">{fmtNum(total)}</span>
            <span className="text-muted text-sm lowercase mb-0.5">impressions</span>
          </div>

          {perPlatform.length > 0 && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 mb-4 text-sm">
              {perPlatform.map(([platform, v]) => (
                <span key={platform} className="text-ink2 lowercase">
                  {platform} <span className="text-brass">{fmtNum(Number(v))}</span>
                </span>
              ))}
            </div>
          )}

          {top.length > 0 && (
            <div className="space-y-2 border-t border-rule pt-3">
              {top.map((p, i) => (
                <div key={p.request_id || p.platform_post_id || i}
                     className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-ink2 truncate">
                    {postTitle(p)}
                    {postUrl(p) && (
                      <a href={postUrl(p)} target="_blank" rel="noreferrer"
                         className="inline-flex align-middle ml-1.5 text-muted hover:text-ink">
                        <ExternalLink size={12} />
                      </a>
                    )}
                  </span>
                  <span className="text-ink shrink-0">{fmtNum(postViews(p))} views</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
