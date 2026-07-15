import { useMemo } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import NavBar from './components/NavBar';
import SignInScreen from './components/SignInScreen';
import Dashboard from './pages/Dashboard';
import Sources from './pages/Sources';
import Health from './pages/Health';
import Management from './pages/Management';
import Transactions from './pages/Transactions';
import { useAuth } from './hooks/useAuth';
import { useFinanceData } from './hooks/useFinanceData';
import { currentBalances } from './lib/transform';
import ChatBot from './components/ChatBot';

export default function App() {
  const { signedIn, ready, error: authError, signIn, signOut } = useAuth();
  const { transactions, metadata, monthlySummary, loading, error, refresh, listVersion } = useFinanceData(signedIn);
  const { pathname } = useLocation();
  const balances = useMemo(() => currentBalances(transactions), [transactions]);
  const skipLoading = pathname === '/health' || pathname === '/management';

  if (!signedIn) {
    return <SignInScreen onSignIn={signIn} error={authError} ready={ready} />;
  }

  return (
    <div className="min-h-screen bg-bg">
      <NavBar onRefresh={refresh} refreshing={loading} onSignOut={signOut} />

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
        {error && (
          <div className="mb-6 p-4 rounded-lg border border-expense/40 bg-expense/10 text-expense text-sm">
            Failed to load data: {error}
            {error.toLowerCase().includes('permission') && (
              <> — make sure this Google account has at least Viewer access to the spreadsheet.</>
            )}
          </div>
        )}

        {/* Avoid mounting routes until first load so Dashboard is not remounted mid-fetch. */}
        {!skipLoading && listVersion === 0 && !error ? (
          <LoadingState />
        ) : (
          <Routes>
            <Route
              path="/"
              element={<Dashboard transactions={transactions} monthlySummary={monthlySummary} listVersion={listVersion} />}
            />
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
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="h-24 rounded-xl bg-bg-surface border border-bg-border animate-pulse" />
      ))}
      <div className="sm:col-span-3 h-80 rounded-xl bg-bg-surface border border-bg-border animate-pulse" />
    </div>
  );
}
