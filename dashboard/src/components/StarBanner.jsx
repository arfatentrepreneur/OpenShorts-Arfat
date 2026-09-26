import { Github } from 'lucide-react';

export const REPO_URL = 'https://github.com/mutonby/openshorts';

// Small "star us" ask, once per job, while the clips render: that wait is the
// only dead time in the flow. Asking again on the finished clips made it two
// asks for the same job, and the old "free while it renders" wording put the
// word free next to the product name for anyone who missed the pun — the one
// thing our copy must never do. No incentive attached.
export default function StarBanner({ message = 'Enjoying OpenShorts?' }) {
  return (
    <a
      href={REPO_URL}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-2 px-3 py-2 rounded-input bg-paper3 border border-rule text-sm text-muted hover:text-ink transition-colors"
    >
      <Github size={14} className="shrink-0" />
      <span>{message} <span className="text-brass">Star us on GitHub ⭐</span></span>
    </a>
  );
}
