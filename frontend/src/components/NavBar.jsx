import { useEffect, useId, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import ThemeToggle from './ThemeToggle';

const SIDEBAR_STORAGE_KEY = 'sidebar-collapsed';
const DESKTOP_MQ = '(min-width: 768px)';

const TABS = [
  { to: '/', label: 'Overview', end: true, icon: OverviewIcon },
  { to: '/sources', label: 'Sources', icon: SourcesIcon },
  { to: '/transactions', label: 'Transactions', icon: TransactionsIcon },
  { to: '/giftcards', label: 'Giftcards', icon: GiftcardsIcon },
  { to: '/products', label: 'Products', icon: ProductsIcon },
  { to: '/chat', label: 'Assistant', icon: AssistantIcon },
  { to: '/health', label: 'Health', icon: HealthIcon, section: 'system' },
  { to: '/management', label: 'Management', icon: ManagementIcon, section: 'system' },
];

function readCollapsed() {
  try {
    return localStorage.getItem(SIDEBAR_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function persistCollapsed(collapsed) {
  try {
    localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? '1' : '0');
  } catch {
    /* private mode / blocked storage */
  }
}

function desktopNavClass({ isActive }, collapsed) {
  return [
    'group relative flex items-center rounded-lg text-sm font-medium transition-colors duration-200',
    collapsed ? 'justify-center h-11 w-full' : 'gap-3 px-3 min-h-11',
    isActive
      ? 'bg-accent-muted text-accent'
      : 'text-text-secondary hover:text-text-primary hover:bg-bg-raised/80',
  ].join(' ');
}

function mobileNavClass({ isActive }) {
  return [
    'flex items-center gap-3 min-h-11 px-3 rounded-lg text-sm font-medium transition-colors duration-200',
    isActive
      ? 'bg-accent-muted text-accent'
      : 'text-text-secondary hover:text-text-primary hover:bg-bg-raised/80',
  ].join(' ');
}

const iconBtnClass =
  'inline-flex items-center justify-center min-h-11 min-w-11 p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-raised transition-colors duration-200 cursor-pointer disabled:opacity-50';

export default function NavBar({ onSignOut }) {
  const { pathname } = useLocation();
  const collapseId = useId();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    const mq = window.matchMedia(DESKTOP_MQ);
    const onChange = () => {
      if (mq.matches) setMobileOpen(false);
    };
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  useEffect(() => {
    if (!mobileOpen) return;
    function onKeyDown(e) {
      if (e.key === 'Escape') setMobileOpen(false);
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [mobileOpen]);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      persistCollapsed(next);
      return next;
    });
  }

  return (
    <>
      <MobileNav
        collapseId={collapseId}
        mobileOpen={mobileOpen}
        setMobileOpen={setMobileOpen}
        onSignOut={onSignOut}
      />
      <DesktopSidebar collapsed={collapsed} onToggleCollapsed={toggleCollapsed} onSignOut={onSignOut} />
    </>
  );
}

function MobileNav({ collapseId, mobileOpen, setMobileOpen, onSignOut }) {
  return (
    <header className="md:hidden shrink-0 sticky top-0 z-30 border-b border-bg-border/80 bg-bg-surface/85 backdrop-blur-md pt-safe">
      <div className="flex items-center justify-between gap-2 h-14 pl-[max(0.75rem,env(safe-area-inset-left))] pr-[max(0.75rem,env(safe-area-inset-right))]">
        <div className="flex items-center gap-2.5 min-w-0">
          <BrandMark />
          <div className="min-w-0">
            <div className="font-semibold text-text-primary tracking-tight truncate leading-tight">
              Money Tracking
            </div>
            <div className="text-[11px] text-text-muted leading-tight truncate hidden min-[420px]:block">
              Personal ledger · AUD
            </div>
          </div>
        </div>

        <div className="flex items-center gap-0.5 shrink-0">
          <ThemeToggle />
          <SignOutButton onSignOut={onSignOut} />
          <button
            type="button"
            className={iconBtnClass}
            aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={mobileOpen}
            aria-controls={collapseId}
            onClick={() => setMobileOpen((open) => !open)}
          >
            <HamburgerIcon open={mobileOpen} />
          </button>
        </div>
      </div>

      <div
        className="nav-collapse"
        data-open={mobileOpen ? 'true' : 'false'}
        inert={mobileOpen ? undefined : true}
      >
        <div>
          <nav
            id={collapseId}
            className="px-3 pb-3 pt-1 space-y-1 border-t border-bg-border/80 max-h-[min(70dvh,24rem)] overflow-y-auto scrollbar-thin"
            aria-label="Primary"
            aria-hidden={!mobileOpen}
          >
            {TABS.map((tab, index) => (
              <div key={tab.to}>
                {tab.section === 'system' && TABS[index - 1]?.section !== 'system' && (
                  <div className="my-2 mx-3 border-t border-bg-border/80" role="separator" />
                )}
                <NavLink to={tab.to} end={tab.end} className={mobileNavClass} onClick={() => setMobileOpen(false)}>
                  <tab.icon className="w-5 h-5 shrink-0" />
                  {tab.label}
                </NavLink>
              </div>
            ))}
          </nav>
        </div>
      </div>
    </header>
  );
}

function DesktopSidebar({ collapsed, onToggleCollapsed, onSignOut }) {
  return (
    <aside
      className={`hidden md:flex md:flex-col h-full shrink-0 overflow-x-hidden border-r border-bg-border/80 bg-bg-surface/85 backdrop-blur-md transition-[width] duration-200 ease-out ${
        collapsed ? 'w-[4.5rem]' : 'w-60'
      }`}
    >
      <div className={`flex items-center shrink-0 h-16 ${collapsed ? 'justify-center px-2' : 'gap-2.5 px-3'}`}>
        <BrandMark />
        {!collapsed && (
          <div className="min-w-0 flex-1">
            <div className="font-semibold text-text-primary tracking-tight truncate leading-tight">Money Tracking</div>
            <div className="text-[11px] text-text-muted leading-tight truncate">Personal ledger · AUD</div>
          </div>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto scrollbar-thin px-2 py-1 space-y-1" aria-label="Primary">
        {TABS.map((tab, index) => (
          <div key={tab.to}>
            {tab.section === 'system' && TABS[index - 1]?.section !== 'system' && (
              <div className={`my-2 ${collapsed ? 'mx-2' : 'mx-3'} border-t border-bg-border/80`} role="separator" />
            )}
            <NavLink
              to={tab.to}
              end={tab.end}
              title={collapsed ? tab.label : undefined}
              className={(state) => desktopNavClass(state, collapsed)}
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span
                      className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-0.5 rounded-full bg-accent"
                      aria-hidden
                    />
                  )}
                  <tab.icon className="w-5 h-5 shrink-0" />
                  {collapsed ? <span className="sr-only">{tab.label}</span> : tab.label}
                </>
              )}
            </NavLink>
          </div>
        ))}
      </nav>

      <div className="shrink-0 border-t border-bg-border/80 py-2 px-2 space-y-1">
        <ThemeToggle labeled={!collapsed} className={collapsed ? 'w-full' : ''} />
        <SignOutButton onSignOut={onSignOut} labeled={!collapsed} className="w-full" />
        <CollapseToggle collapsed={collapsed} onToggle={onToggleCollapsed} labeled={!collapsed} />
      </div>
    </aside>
  );
}

function CollapseToggle({ collapsed, onToggle, labeled = false }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={collapsed ? 'Expand menu' : 'Collapse menu'}
      aria-expanded={!collapsed}
      title={collapsed ? 'Expand menu' : 'Collapse menu'}
      className={
        labeled
          ? 'flex items-center gap-3 w-full min-h-11 px-3 rounded-lg text-sm font-medium text-text-secondary hover:text-text-primary hover:bg-bg-raised/80 transition-colors duration-200 cursor-pointer'
          : `${iconBtnClass} w-full`
      }
    >
      <CollapseIcon collapsed={collapsed} />
      {labeled && <span>Collapse</span>}
    </button>
  );
}

function SignOutButton({ onSignOut, labeled = false, className = '' }) {
  return (
    <button
      type="button"
      onClick={onSignOut}
      aria-label="Sign out"
      title="Sign out"
      className={
        labeled
          ? `flex items-center gap-3 w-full min-h-11 px-3 rounded-lg text-sm font-medium text-text-secondary hover:text-text-primary hover:bg-bg-raised/80 transition-colors duration-200 cursor-pointer ${className}`
          : `${iconBtnClass} ${className}`
      }
    >
      <SignOutIcon />
      {labeled && <span>Sign out</span>}
    </button>
  );
}

function BrandMark() {
  return (
    <div
      className="w-8 h-8 rounded-lg bg-accent text-white flex items-center justify-center shadow-soft shrink-0"
      aria-hidden
    >
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 7h16M4 12h10M4 17h14" />
      </svg>
    </div>
  );
}

function HamburgerIcon({ open }) {
  return (
    <span className="relative block w-5 h-3.5" aria-hidden>
      <span
        className={`absolute left-0 top-0 block h-0.5 w-5 rounded-full bg-current transition-transform duration-200 origin-center ${
          open ? 'translate-y-[6px] rotate-45' : ''
        }`}
      />
      <span
        className={`absolute left-0 top-[6px] block h-0.5 w-5 rounded-full bg-current transition-opacity duration-200 ${
          open ? 'opacity-0' : ''
        }`}
      />
      <span
        className={`absolute left-0 top-[12px] block h-0.5 w-5 rounded-full bg-current transition-transform duration-200 origin-center ${
          open ? '-translate-y-[6px] -rotate-45' : ''
        }`}
      />
    </span>
  );
}

function CollapseIcon({ collapsed }) {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
      {collapsed ? (
        <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 4.5l7.5 7.5-7.5 7.5M4.5 4.5l7.5 7.5-7.5 7.5" />
      ) : (
        <path strokeLinecap="round" strokeLinejoin="round" d="M18.75 19.5l-7.5-7.5 7.5-7.5M11.25 19.5l-7.5-7.5 7.5-7.5" />
      )}
    </svg>
  );
}

function SignOutIcon() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75"
      />
    </svg>
  );
}

function OverviewIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"
      />
    </svg>
  );
}

function SourcesIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M21 12a2.25 2.25 0 00-2.25-2.25H15a3 3 0 11-6 0H5.25A2.25 2.25 0 003 12m18 0v6a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 18v-6m18 0V9M3 12V9m18 0a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 9m18 0V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v3"
      />
    </svg>
  );
}

function TransactionsIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5"
      />
    </svg>
  );
}

function ProductsIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z"
      />
    </svg>
  );
}

function GiftcardsIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M21 11.25v8.25a1.5 1.5 0 01-1.5 1.5H4.5a1.5 1.5 0 01-1.5-1.5v-8.25M12 4.875A2.625 2.625 0 109.375 7.5H12m0-2.625V7.5m0-2.625A2.625 2.625 0 1114.625 7.5H12m0 0V21m-8.625-9.75h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z"
      />
    </svg>
  );
}

function AssistantIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m7.5 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H16.5m-6.75 3.75h.008v.008H9.75v-.008zm3.75 0h.008v.008H13.5v-.008zM21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z"
      />
    </svg>
  );
}

function HealthIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3 12h3.75l2.25-6 3 12 2.25-6H21"
      />
    </svg>
  );
}

function ManagementIcon({ className }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.094.565.54 1.002 1.076 1.186.104.036.2.082.29.138.291.196.616.263.94.213l1.27-.196c.546-.084 1.08.248 1.246.78l1.296 3.88c.166.496-.066 1.04-.546 1.27l-1.123.54c-.5.24-.78.78-.708 1.328.016.122.016.246 0 .368-.072.549.207 1.087.708 1.328l1.123.54c.48.23.712.774.546 1.27l-1.296 3.88c-.166.532-.7.864-1.246.78l-1.27-.196c-.324-.05-.649.017-.94.213a2.39 2.39 0 01-.29.138c-.536.184-.982.62-1.076 1.186l-.213 1.281c-.09.542-.56.94-1.11.94h-2.593c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.094-.565-.54-1.002-1.076-1.186a2.39 2.39 0 01-.29-.138c-.291-.196-.616-.263-.94-.213l-1.27.196c-.546.084-1.08-.248-1.246-.78l-1.296-3.88c-.166-.496.066-1.04.546-1.27l1.123-.54c.5-.24.78-.78.708-1.328a2.47 2.47 0 010-.368c.072-.549-.207-1.087-.708-1.328l-1.123-.54c-.48-.23-.712-.774-.546-1.27l1.296-3.88c.166-.532.7-.864 1.246-.78l1.27.196c.324.05.649-.017.94-.213.097-.056.193-.102.29-.138.536-.184.982-.62 1.076-1.186l.213-1.281z"
      />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}
