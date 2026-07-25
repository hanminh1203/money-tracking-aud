import { useEffect, useMemo } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import NavBar from './components/NavBar';
import SignInScreen from './components/SignInScreen';
import Dashboard from './pages/Dashboard';
import Sources from './pages/Sources';
import Health from './pages/Health';
import Management from './pages/Management';
import Transactions from './pages/Transactions';
import Giftcards from './pages/Giftcards';
import { useAuth } from './hooks/useAuth';
import { useFinanceData } from './hooks/useFinanceData';
import { currentBalances } from './lib/transform';
import ChatBot from './components/ChatBot';

export default function App() {
  const { signedIn, ready, error: authError, signIn, signOut } = useAuth();
  const { transactions, metadata, dashboard, error, refresh, listVersion } = useFinanceData(signedIn);
  const { pathname } = useLocation();
  const balances = useMemo(() => currentBalances(transactions), [transactions]);
  const skipLoading = pathname === '/health' || pathname === '/management';

  useEffect(() => {
    if (!signedIn) return;
    if (pathname === '/health' || pathname === '/management') return;
    refresh();
  }, [pathname, refresh, signedIn]);

  if (!signedIn) {
    return <SignInScreen onSignIn={signIn} error={authError} ready={ready} />;
  }

  return (
    <div className="min-h-screen">
      <NavBar onSignOut={signOut} />

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-5 sm:py-6 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
        {error && (
          <div className="mb-5 p-4 rounded-xl border border-expense/30 bg-expense/5 text-expense text-sm">
            Failed to load data: {error}
            {error.toLowerCase().includes('permission') && (
              <> — make sure this Google account has at least Viewer access to the spreadsheet.</>
            )}
          </div>
        )}

        {!skipLoading && listVersion === 0 && !error ? (
          <LoadingState />
        ) : (
          <Routes>
            <Route path="/" element={<Dashboard data={dashboard} />} />
            <Route
              path="/sources"
              element={
                <Sources transactions={transactions} metadata={metadata} listVersion={listVersion} />
              }
            />
            <Route
              path="/transactions"
              element={
                <Transactions
                  metadata={metadata}
                  balances={balances}
                  onSaved={refresh}
                  listVersion={listVersion}
                />
              }
            />
            <Route
              path="/giftcards"
              element={
                <Giftcards
                  metadata={metadata}
                  balances={balances}
                  onSaved={refresh}
                  listVersion={listVersion}
                />
              }
            />
            <Route path="/chat" element={<ChatBot metadata={metadata} onSaved={refresh} />} />
            <Route path="/health" element={<Health />} />
            <Route path="/management" element={<Management />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        )}
      </main>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-5">
      <div className="h-14 rounded-xl bg-bg-surface border border-bg-border animate-pulse" />
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        {[...Array(4)].map((_, i) => (
          <div
            key={i}
            className="h-24 rounded-xl bg-bg-surface border border-bg-border animate-pulse"
            style={{ animationDelay: `${i * 60}ms` }}
          />
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="h-72 rounded-xl bg-bg-surface border border-bg-border animate-pulse" />
        <div className="h-72 rounded-xl bg-bg-surface border border-bg-border animate-pulse" />
      </div>
      <div className="h-64 rounded-xl bg-bg-surface border border-bg-border animate-pulse" />
    </div>
  );
}
