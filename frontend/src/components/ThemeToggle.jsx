import { useTheme } from '../hooks/useTheme';

export default function ThemeToggle({ className = '', labeled = false }) {
  const { isDark, toggleTheme } = useTheme();
  const label = isDark ? 'Light mode' : 'Dark mode';

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={label}
      className={
        labeled
          ? `flex items-center gap-3 w-full min-h-11 px-3 rounded-lg text-sm font-medium text-text-secondary hover:text-text-primary hover:bg-bg-raised/80 transition-colors duration-200 cursor-pointer ${className}`
          : `inline-flex items-center justify-center min-h-11 min-w-11 p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-raised transition-colors duration-200 cursor-pointer ${className}`
      }
    >
      {isDark ? <SunIcon /> : <MoonIcon />}
      {labeled && <span>{label}</span>}
    </button>
  );
}

function SunIcon() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"
      />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"
      />
    </svg>
  );
}
