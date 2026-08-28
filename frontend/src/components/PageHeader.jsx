export default function PageHeader({ title, description, children, fill = false }) {
  return (
    <div className="flex flex-col h-full min-h-0">
      <header className="shrink-0 px-4 sm:px-6 lg:px-8 pt-5 sm:pt-6 pb-4 border-b border-bg-border/80 bg-bg-surface/80 backdrop-blur-md">
        <h1 className="text-xl sm:text-2xl font-semibold text-text-primary tracking-tight">{title}</h1>
        {description && (
          <p className="text-sm text-text-secondary mt-1 max-w-3xl leading-relaxed">{description}</p>
        )}
      </header>
      <div
        className={`flex-1 min-h-0 px-4 sm:px-6 lg:px-8 py-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] ${
          fill ? 'overflow-hidden flex flex-col' : 'overflow-y-auto scrollbar-thin'
        }`}
      >
        {children}
      </div>
    </div>
  );
}

export function PageActions({ children }) {
  return (
    <div className="flex flex-col min-[400px]:flex-row min-[400px]:flex-wrap items-stretch min-[400px]:items-center gap-2 [&_button]:w-full min-[400px]:[&_button]:w-auto">
      {children}
    </div>
  );
}
