import React, { useState, useEffect, useCallback } from 'react';
import { KeyRound, Plus, Trash2, Copy, Check, Loader2 } from 'lucide-react';
import { apiJson } from '../lib/api';

// API keys for programmatic access (MCP clients, scripts, n8n). The raw key is
// returned exactly once by POST /api/keys, so it is surfaced in a one-time
// banner the user must copy before it disappears.
export default function ApiKeysCard() {
  const [keys, setKeys] = useState(null);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [freshKey, setFreshKey] = useState(null); // { key, name } shown once
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => {
    apiJson('/api/keys').then((d) => setKeys(d.keys || [])).catch(() => setKeys([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const createKey = useCallback(async () => {
    setBusy(true);
    try {
      const d = await apiJson('/api/keys', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim() || undefined }),
      });
      setFreshKey(d);
      setCopied(false);
      setName('');
      load();
    } catch (e) { alert(e?.detail || 'Could not create the key.'); }
    setBusy(false);
  }, [name, load]);

  const revoke = useCallback(async (k) => {
    if (!window.confirm(`Revoke "${k.name}"? Anything using it stops working immediately.`)) return;
    try {
      await apiJson(`/api/keys/${k.id}`, { method: 'DELETE' });
      load();
    } catch (e) { alert(e?.detail || 'Could not revoke the key.'); }
  }, [load]);

  const copyKey = useCallback(() => {
    navigator.clipboard?.writeText(freshKey.key).then(() => setCopied(true)).catch(() => {});
  }, [freshKey]);

  const active = (keys || []).filter((k) => !k.revoked);

  return (
    <div className="card p-6">
      <h3 className="font-display lowercase text-lg text-ink mb-1 flex items-center gap-2">
        <KeyRound size={16} className="text-brass" /> API keys
      </h3>
      <p className="text-muted text-sm mb-4">
        Keys for CLI clients, scripts and the REST API (see &ldquo;Connect an agent&rdquo; above).
        Apps connected through claude.ai or ChatGPT show up here too: revoking a key disconnects
        that app. Keys use your plan&apos;s minutes.
      </p>

      {freshKey && (
        <div className="mb-4 rounded-card border border-brass/40 bg-brass/5 p-3 text-sm">
          <p className="text-ink mb-2">
            <b>Copy your new key now.</b> For security it will never be shown again.
          </p>
          <div className="flex items-center gap-2">
            <code className="readout flex-1 break-all select-all">{freshKey.key}</code>
            <button onClick={copyKey} className="btn-ghost px-3 py-1.5 shrink-0">
              {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
        </div>
      )}

      {keys === null ? (
        <div className="flex justify-center py-4"><Loader2 className="animate-spin text-brass" size={18} /></div>
      ) : (
        <>
          {active.length > 0 && (
            <div className="space-y-2 mb-4">
              {active.map((k) => (
                <div key={k.id} className="flex items-center justify-between gap-3 border border-rule rounded-card px-3 py-2 text-sm">
                  <div className="min-w-0">
                    <span className="text-ink">{k.name}</span>{' '}
                    <code className="readout">{k.prefix}…</code>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-muted text-xs lowercase">
                      {k.last_used_at ? `used ${new Date(k.last_used_at).toLocaleDateString()}` : 'never used'}
                    </span>
                    <button onClick={() => revoke(k)} title="Revoke key"
                            className="text-muted hover:text-warn transition-colors">
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="flex gap-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') createKey(); }}
              placeholder="Key name (e.g. n8n, claude)"
              className="input-field flex-1 text-sm"
              maxLength={60}
            />
            <button onClick={createKey} disabled={busy} className="btn-ghost px-4 py-2 shrink-0">
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />} Create key
            </button>
          </div>
        </>
      )}
    </div>
  );
}
