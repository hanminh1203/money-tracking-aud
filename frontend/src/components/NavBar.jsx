const TABS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'sources', label: 'Sources' },
  { id: 'add', label: 'Add Transaction' },
  { id: 'transfer', label: 'Transfer' },
  { id: 'chat', label: 'Assistant' },
];

export default function NavBar({ active, onChange, onRefresh, refreshing, onSignOut }) {
  return (
    <header className="sticky top-0 z-30 border-b border-bg-border bg-bg/90 backdrop-blur">
      <div className="max-w-6xl mx-auto px-4 sm:px-6">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center font-semibold text-white">
              $
            </div>
            <span className="font-semibold text-text-primary tracking-tight">Money Tracking</span>
            <span className="text-text-muted text-sm hidden sm:inline">AUD</span>
          </div>

          <nav className="hidden md:flex items-center gap-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => onChange(t.id)}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
                  active === t.id
                    ? 'bg-bg-raised text-text-primary'
                    : 'text-text-secondary hover:text-text-primary hover:bg-bg-raised/60'
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>

          <div className="flex items-center gap-1">
            <button
              onClick={onRefresh}
              disabled={refreshing}
              aria-label="Refresh data"
              className="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-raised transition-colors cursor-pointer disabled:opacity-50"
            >
              <svg
                className={`w-5 h-5 ${refreshing ? 'animate-spin' : ''}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12a7.5 7.5 0 0113.5-4.5M19.5 12a7.5 7.5 0 01-13.5 4.5M4.5 4.5v4.5h4.5M19.5 19.5V15h-4.5" />
              </svg>
            </button>
            <button
              onClick={onSignOut}
              aria-label="Sign out"
              className="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-raised transition-colors cursor-pointer"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
              </svg>
            </button>
          </div>
        </div>

        {/* Mobile tabs */}
        <nav className="flex md:hidden gap-1 pb-3 overflow-x-auto scrollbar-thin">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => onChange(t.id)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors cursor-pointer ${
                active === t.id
                  ? 'bg-bg-raised text-text-primary'
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>
    </header>
  );
}
