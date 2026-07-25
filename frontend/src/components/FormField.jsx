export function Field({ label, children, className = '' }) {
  return (
    <label className={`block ${className}`}>
      {label != null && label !== '' && (
        <span className="block text-xs font-medium uppercase tracking-[0.05em] text-text-muted mb-1.5">
          {label}
        </span>
      )}
      {children}
    </label>
  );
}

export const inputClass =
  'w-full bg-bg-surface border border-bg-border rounded-lg px-3 py-2.5 min-h-11 text-base sm:text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:ring-2 focus:ring-accent/15 transition-colors duration-200 outline-none';

export const selectClass = `${inputClass} cursor-pointer`;
