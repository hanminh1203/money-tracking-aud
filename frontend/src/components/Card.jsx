export default function Card({ children, className = '', title, action }) {
  return (
    <div
      className={`bg-bg-surface border border-bg-border rounded-xl shadow-card p-4 sm:p-5 ${className}`}
    >
      {(title || action) && (
        <div className="flex items-center justify-between gap-3 mb-3.5 shrink-0">
          {title && (
            <h3 className="text-xs font-semibold text-text-muted uppercase tracking-[0.08em] leading-snug">
              {title}
            </h3>
          )}
          {action}
        </div>
      )}
      {children}
    </div>
  );
}
