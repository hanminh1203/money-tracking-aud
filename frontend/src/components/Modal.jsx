import { useEffect } from 'react';

export default function Modal({ title, onClose, children, maxWidth = 'max-w-lg', open = true }) {
  useEffect(() => {
    if (!open) return;
    function onKeyDown(e) {
      if (e.key === 'Escape') onClose?.();
    }
    document.addEventListener('keydown', onKeyDown);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = prev;
    };
  }, [onClose, open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 animate-fade-in">
      <button
        type="button"
        aria-label="Close dialog"
        className="absolute inset-0 bg-slate-900/50 cursor-pointer backdrop-blur-[2px]"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`relative w-full ${maxWidth} max-h-[92dvh] sm:max-h-[90vh] flex flex-col rounded-t-2xl sm:rounded-xl border border-bg-border bg-bg-surface shadow-soft animate-fade-up pb-safe`}
      >
        <div className="flex justify-center pt-2 sm:hidden" aria-hidden>
          <div className="h-1 w-10 rounded-full bg-bg-border" />
        </div>
        <div className="flex items-center justify-between gap-3 px-4 sm:px-5 py-3.5 sm:py-4 border-b border-bg-border shrink-0">
          <h2 className="text-sm font-semibold text-text-primary tracking-tight truncate">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="inline-flex items-center justify-center min-h-11 min-w-11 p-1.5 -mr-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-raised cursor-pointer transition-colors duration-200"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="overflow-y-auto overscroll-contain p-4 sm:p-5 scrollbar-thin">{children}</div>
      </div>
    </div>
  );
}
