import React, { useState } from 'react';
import Modal from './ui/Modal';

const DISMISS_KEY = 'os_watermark_notice_dismissed';

// eslint-disable-next-line react-refresh/only-export-components
export function watermarkNoticeDismissed() {
  try { return localStorage.getItem(DISMISS_KEY) === '1'; } catch { return false; }
}

// Shown to free users before their first download: the clip carries a
// watermark, and upgrading removes it. Dismissible for good, like OpusClip's.
export default function WatermarkModal({ onClose, onContinue }) {
  const [dontShow, setDontShow] = useState(false);

  const close = (proceed) => {
    if (dontShow) {
      try { localStorage.setItem(DISMISS_KEY, '1'); } catch { /* ignore */ }
    }
    if (proceed) onContinue?.();
    onClose();
  };

  return (
    <Modal isOpen onClose={() => close(false)} eyebrow="FREE PLAN" title="Upgrade to remove the watermark" size="md">
      <p className="text-muted text-sm mb-4">
        Clips on the free plan carry the OpenShorts mark in the corner, and are
        kept for 7 days. Any paid plan exports them clean and keeps them for good.
      </p>

      <div className="rounded-card border border-rule overflow-hidden bg-paper mb-5">
        <video
          src="/demo/clip-vertical.mp4"
          autoPlay
          muted
          loop
          playsInline
          className="w-full max-h-56 object-cover"
        />
      </div>

      <div className="flex items-center justify-between gap-4 flex-wrap">
        <label className="flex items-center gap-2 text-sm text-muted cursor-pointer">
          <input
            type="checkbox"
            checked={dontShow}
            onChange={(e) => setDontShow(e.target.checked)}
            className="accent-brass"
          />
          Don't show this again
        </label>
        <div className="flex items-center gap-2">
          <button onClick={() => close(true)} className="btn-ghost px-4 py-2 text-sm">
            Download anyway
          </button>
          <button
            onClick={() => { close(false); window.location.hash = '#/pricing'; }}
            className="btn-primary px-4 py-2 text-sm"
          >
            Upgrade
          </button>
        </div>
      </div>
    </Modal>
  );
}
