import { useEffect, useRef } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import ThemeToggle from './ThemeToggle';

const TABS = [
  { to: '/', label: 'Overview', short: 'Home', end: true },
  { to: '/sources', label: 'Sources', short: 'Sources' },
  { to: '/transactions', label: 'Transactions', short: 'Txns' },
  { to: '/giftcards', label: 'Giftcards', short: 'Cards' },
  { to: '/chat', label: 'Assistant', short: 'Chat' },
  { to: '/health', label: 'Health', short: 'Health' },
  { to: '/management', label: 'Management', short: 'Manage' },
];

function tabClassName({ isActive }, extra = '') {
  return `px-3 rounded-lg text-sm font-medium transition-colors duration-200 ${extra} ${
    isActive
      ? 'bg-accent-muted text-accent'
      : 'text-text-secondary hover:text-text-primary hover:bg-bg-raised/80'
  }`;
}

function BrandMark() {
  return (
    <div
      className="w-8 h-8 rounded-lg bg-accent text-white flex items-center justify-center shadow-soft"
      aria-hidden
    >
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 7h16M4 12h10M4 17h14" />
      </svg>
    </div>
  );
}

const iconBtnClass =
  'inline-flex items-center justify-center min-h-11 min-w-11 p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-raised transition-colors duration-200 cursor-pointer disabled:opacity-50';

export default function NavBar({ onSignOut }) {
  const { pathname } = useLocation();
  const mobileNavRef = useRef(null);

  useEffect(() => {
    const nav = mobileNavRef.current;
    if (!nav) return;
    const active = nav.querySelector('[aria-current="page"]');
    active?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }, [pathname]);

  return (
    <header className="sticky top-0 z-30 border-b border-bg-border/80 bg-bg-surface/85 backdrop-blur-md pt-safe">
      <div className="max-w-6xl mx-auto px-4 sm:px-6">
        <div className="flex items-center justify-between h-14 sm:h-16">
          <div className="flex items-center gap-2.5 min-w-0">
            <BrandMark />
            <div className="min-w-0">
              <div className="font-semibold text-text-primary tracking-tight truncate leading-tight">
                Money Tracking
              </div>
              <div className="text-[11px] text-text-muted hidden sm:block leading-tight">
                Personal ledger · AUD
              </div>
            </div>
          </div>

          <nav className="hidden lg:flex items-center gap-0.5" aria-label="Primary">
            {TABS.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                end={t.end}
                className={(state) => tabClassName(state, 'py-2')}
              >
                {t.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-0.5 sm:gap-1 shrink-0">
            <ThemeToggle />
            <button type="button" onClick={onSignOut} aria-label="Sign out" className={iconBtnClass}>
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75"
                />
              </svg>
            </button>
          </div>
        </div>

        <nav
          ref={mobileNavRef}
          className="flex lg:hidden gap-1.5 pb-3 -mx-4 px-4 overflow-x-auto scrollbar-thin scroll-smooth snap-x snap-mandatory"
          aria-label="Primary mobile"
        >
          {TABS.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              end={t.end}
              className={(state) =>
                tabClassName(state, 'py-2.5 min-h-11 inline-flex items-center whitespace-nowrap snap-start')
              }
            >
              <span className="sm:hidden">{t.short}</span>
              <span className="hidden sm:inline">{t.label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  );
}
