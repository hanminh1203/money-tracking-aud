import ThemeToggle from './ThemeToggle';

export default function SignInScreen({ onSignIn, error, ready }) {
  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12 pt-safe pb-safe relative">
      <div className="absolute top-4 right-4 sm:top-6 sm:right-6 pt-safe pr-safe">
        <ThemeToggle />
      </div>
      <div className="max-w-md w-full animate-fade-up">
        <div className="rounded-2xl border border-bg-border bg-bg-surface shadow-soft p-8 sm:p-10 text-center">
          <div
            className="w-14 h-14 rounded-2xl bg-accent text-white flex items-center justify-center mx-auto mb-6 shadow-soft"
            aria-hidden
          >
            <svg className="w-7 h-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 7h16M4 12h10M4 17h14" />
            </svg>
          </div>

          <p className="text-xs font-medium uppercase tracking-[0.14em] text-accent mb-2">AUD · Personal</p>
          <h1 className="text-2xl sm:text-3xl font-semibold text-text-primary tracking-tight mb-2">
            Money Tracking
          </h1>
          <p className="text-text-secondary text-sm leading-relaxed mb-8 max-w-sm mx-auto">
            Sign in with the Google account that can access your Money Tracking spreadsheet to review balances,
            spending, and transfers.
          </p>

          <button
            type="button"
            onClick={() => onSignIn()}
            disabled={!ready}
            className="btn-primary w-full"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" aria-hidden>
              <path
                fill="currentColor"
                d="M21.35 11.1h-9.17v2.73h6.51c-.33 3.81-3.5 5.44-6.5 5.44C8.36 19.27 5 16.25 5 12s3.36-7.27 7.19-7.27c3.08 0 4.9 1.97 4.9 1.97L19 4.72S16.56 2 12.19 2C6.42 2 2.03 6.8 2.03 12s4.39 10 10.16 10c5.05 0 9.81-3.44 9.81-10.45 0-.79-.09-1.45-.65-1.45Z"
              />
            </svg>
            Sign in with Google
          </button>

          {error && <p className="mt-5 text-sm text-expense">{error}</p>}
          {!ready && !error && <p className="mt-5 text-sm text-text-muted">Checking session…</p>}
        </div>

        <p className="mt-6 text-center text-xs text-text-muted">
          Your data stays in your sheet — this app is a private ledger view.
        </p>
      </div>
    </div>
  );
}
