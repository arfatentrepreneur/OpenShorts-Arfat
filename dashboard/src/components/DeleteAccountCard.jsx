import React, { useState, useRef, useCallback } from 'react';
import { Trash2, AlertTriangle, Loader2 } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { apiJson } from '../lib/api';

// Mirrors cloud/account.DELETION_REASONS. A closed list rather than a text
// box, because the answer is stored in a record that outlives the account and
// free text is how personal data gets into one by accident.
const REASONS = [
  ['too_expensive', 'Too expensive'],
  ['not_using_it', "I'm not using it"],
  ['clip_quality', "The clips weren't good enough"],
  ['missing_feature', 'Missing a feature I need'],
  ['found_alternative', 'I found something better'],
  ['privacy', 'Privacy concerns'],
  ['other', 'Something else'],
];

// GDPR Art. 17 erasure, self-service (backend: cloud/account.py). The privacy
// policy tells users they can delete their account from the dashboard, so this
// has to be findable — but it is also irreversible, hence: collapsed by
// default, an itemised list of what actually goes, and typing the account email
// as the confirmation step (there is no password to re-enter; sign-in is a
// magic link).
export default function DeleteAccountCard() {
  const { me, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  // setBusy only disables the button on the next render, which a fast double
  // click beats. The server survives a duplicate call, but each one re-runs a
  // Stripe cancel and an R2 prefix delete for nothing.
  const sending = useRef(false);

  const email = me?.user?.email || '';
  // `!!email` matters: without it an account page rendered before /api/me
  // resolves would treat an empty box as a match and arm the delete button.
  const matches = !!email && confirm.trim().toLowerCase() === email.toLowerCase();

  const remove = useCallback(async () => {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setError('');
    try {
      await apiJson('/api/account', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm_email: confirm.trim(), reason: reason || undefined }),
      });
      // The session token now points at nothing. Drop it before navigating, or
      // the landing page spends a request discovering that for itself. The
      // funnel flags go too: they are the only reason a re-signup with the same
      // address would behave like a returning user rather than a fresh one.
      logout();
      try {
        localStorage.removeItem('os_socials_prompted');
        localStorage.removeItem('os_pending_checkout');
      } catch (_) { /* ignore */ }
      window.location.hash = '#/deleted';
      window.location.reload();
    } catch (e) {
      setError(e?.detail || 'Could not delete your account. Please try again or email info@openshorts.app.');
      sending.current = false;
      setBusy(false);
    }
  }, [confirm, reason, logout]);

  return (
    <div className="card p-6">
      <h3 className="font-display lowercase text-lg text-ink mb-1 flex items-center gap-2">
        <Trash2 size={16} className="text-danger" /> Delete account
      </h3>
      <p className="text-muted text-sm">
        Close your OpenShorts account and erase everything we hold about you. This
        cannot be undone.
      </p>

      {!open ? (
        <button onClick={() => setOpen(true)} className="btn-danger px-4 py-2 mt-4">
          <Trash2 size={16} /> Delete my account
        </button>
      ) : (
        <div className="mt-4 space-y-4">
          <div className="rounded-card border border-danger/40 bg-danger/5 p-3 text-sm text-ink2">
            <p className="flex items-start gap-2 text-ink">
              <AlertTriangle size={16} className="text-danger shrink-0 mt-0.5" />
              <b>This is permanent. There is no recovery.</b>
            </p>
            <p className="mt-2">Deleted immediately:</p>
            <ul className="list-disc pl-5 mt-1 space-y-0.5">
              <li>your account and sign-in</li>
              <li>every project, clip and transcript, here and in our storage</li>
              <li>your API keys, so anything using them stops working</li>
              <li>the link to any social accounts you connected</li>
            </ul>
            <p className="mt-2">
              Any active subscription is cancelled as part of this. We keep your
              invoices for six years because Spanish law requires it, plus a
              one-way hash of your email address, instead of the address, as
              proof the deletion happened.
            </p>
          </div>

          <label className="block">
            <span className="text-sm text-muted lowercase">Why are you leaving? (optional)</span>
            <select
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="input-field w-full text-sm mt-1"
            >
              <option value="">Prefer not to say</option>
              {REASONS.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-sm text-muted">
              Type <b className="text-ink">{email}</b> to confirm
            </span>
            <input
              value={confirm}
              onChange={(e) => { setConfirm(e.target.value); setError(''); }}
              autoComplete="off"
              spellCheck={false}
              className="input-field w-full text-sm mt-1"
            />
          </label>

          {error && <p className="text-sm text-danger">{error}</p>}

          <div className="flex items-center gap-2">
            <button onClick={remove} disabled={!matches || busy} className="btn-danger px-4 py-2">
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
              {busy ? 'Deleting…' : 'Permanently delete my account'}
            </button>
            <button onClick={() => { setOpen(false); setConfirm(''); setError(''); }}
                    disabled={busy} className="btn-quiet">
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
