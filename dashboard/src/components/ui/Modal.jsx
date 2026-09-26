import { X } from 'lucide-react';

/**
 * The single modal shell for the app (design.md).
 * Plain dark overlay (no backdrop-blur), hairline paper2 panel.
 *
 * Props:
 *  - isOpen / onClose
 *  - title (string, rendered lowercase serif) — optional
 *  - eyebrow (string, mono UPPERCASE micro label above title) — optional
 *  - size: 'sm' | 'md' | 'lg' | 'xl' (max width; default 'md')
 *  - children: body content
 *  - footer: optional node pinned under the body
 *  - hideClose: hide the X button
 */
const SIZES = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-2xl',
  xl: 'max-w-5xl',
};

export default function Modal({ isOpen, onClose, title, eyebrow, size = 'md', children, footer, hideClose = false }) {
  if (!isOpen) return null;

  return (
    /* Phone: a bottom sheet — anchored to the thumb, edge to edge, and free to
       run taller than a centred dialog whose 4px side margins wasted the only
       width there was. From sm up it is the centred dialog it always was. */
    <div
      className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center bg-black/70 p-0 sm:p-4 animate-fade"
      onMouseDown={(e) => { if (e.target === e.currentTarget && onClose) onClose(); }}
      role="dialog"
      aria-modal="true"
    >
      <div
        className={`card relative w-full ${SIZES[size] || SIZES.md} max-h-[92vh] sm:max-h-[90vh] flex flex-col
          rounded-b-none sm:rounded-card animate-sheet-up sm:animate-none`}
      >
        {/* Grab handle: the affordance that says "this sheet closes downward". */}
        <div className="sm:hidden pt-2.5 pb-1 flex justify-center shrink-0" aria-hidden="true">
          <span className="w-9 h-1 rounded-full bg-[color:var(--color-rule-2)]" />
        </div>
        {!hideClose && onClose && (
          <button
            onClick={onClose}
            aria-label="close"
            className="absolute top-3 right-3 sm:top-4 sm:right-4 z-10 p-2 rounded-full text-muted hover:text-ink hover:bg-paper3 transition-colors"
          >
            <X size={18} />
          </button>
        )}
        {(title || eyebrow) && (
          <div className="px-4 sm:px-6 pt-3 sm:pt-6 pb-4 border-b border-rule shrink-0">
            {eyebrow && <p className="eyebrow mb-1.5">{eyebrow}</p>}
            {title && <h2 className="font-display lowercase text-xl sm:text-2xl text-ink leading-tight break-words pr-10">{title}</h2>}
          </div>
        )}
        <div className="px-4 sm:px-6 py-5 overflow-y-auto overscroll-contain custom-scrollbar grow">
          {children}
        </div>
        {footer && (
          <div className="px-4 sm:px-6 py-4 border-t border-rule shrink-0 safe-bottom">
            {footer}
          </div>
        )}
        {!footer && <div className="sm:hidden safe-bottom" />}
      </div>
    </div>
  );
}
