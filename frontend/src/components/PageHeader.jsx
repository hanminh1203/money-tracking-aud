export default function PageHeader({ title, description, action }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 mb-1">
      <div className="min-w-0">
        <h1 className="text-xl sm:text-2xl font-semibold text-text-primary tracking-tight">{title}</h1>
        {description && (
          <p className="text-sm text-text-secondary mt-1 max-w-2xl leading-relaxed">{description}</p>
        )}
      </div>
      {action && (
        <div className="grid grid-cols-1 min-[400px]:grid-cols-2 sm:flex sm:flex-wrap items-stretch sm:items-center gap-2 shrink-0 w-full sm:w-auto [&_button]:w-full sm:[&_button]:w-auto">
          {action}
        </div>
      )}
    </div>
  );
}
