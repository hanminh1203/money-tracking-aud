import { useEffect, useMemo } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import NavBar from './components/NavBar';
import SignInScreen from './components/SignInScreen';
import Dashboard from './pages/Dashboard';
import Sources from './pages/Sources';
import Health from './pages/Health';
import Management from './pages/Management';
import Transactions from './pages/Transactions';
import TransactionDetail from './pages/TransactionDetail';
import Giftcards from './pages/Giftcards';
import Products from './pages/Products';
import ProductDetail from './pages/ProductDetail';
import { useAuth } from './hooks/useAuth';
import { useFinanceData } from './hooks/useFinanceData';
import { currentBalances } from './lib/transform';
import ChatBot from './components/ChatBot';

export default function App() {
  const { signedIn, ready, error: authError, signIn, signOut } = useAuth();
  const { transactions, metadata, dashboard, error, refresh, listVersion } = useFinanceData(signedIn);
  const { pathname } = useLocation();
  const balances = useMemo(() => currentBalances(transactions), [transactions]);
  const isTransactionDetail = /^\/transactions\/[^/]+$/.test(pathname);
  const isProductDetail = /^\/products\/[^/]+$/.test(pathname);
  const skipLoading =
    pathname === '/health' ||
    pathname === '/management' ||
    isTransactionDetail ||
    isProductDetail;

  useEffect(() => {
    if (!signedIn) return;
    if (pathname === '/health' || pathname === '/management') return;
    if (isTransactionDetail) return;
    if (isProductDetail) return;
    refresh();
  }, [pathname, refresh, signedIn, isTransactionDetail, isProductDetail]);

  if (!signedIn) {
    return <SignInScreen onSignIn={signIn} error={authError} ready={ready} />;
  }

  return (
    <div className="h-dvh flex flex-col md:flex-row overflow-hidden">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:top-2 focus:left-2 focus:px-3 focus:py-2 focus:rounded-lg focus:bg-bg-surface focus:text-text-primary focus:shadow-soft"
      >
        Skip to content
      </a>
      <NavBar onSignOut={signOut} />

      <main id="main-content" className="flex-1 min-w-0 min-h-0 flex flex-col overflow-hidden">
        {error && (
          <div className="shrink-0 px-4 sm:px-6 lg:px-8 pt-5">
            <div className="p-4 rounded-xl border border-expense/30 bg-expense/5 text-expense text-sm">
              Failed to load data: {error}
              {error.toLowerCase().includes('permission') && (
                <> — make sure this Google account has at least Viewer access to the spreadsheet.</>
              )}
            </div>
          </div>
        )}

        <div className="flex-1 min-h-0 [&>*]:h-full">
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
            <Route path="/transactions/:id" element={<TransactionDetail onSaved={refresh} />} />
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
            <Route
              path="/products"
              element={<Products onSaved={refresh} listVersion={listVersion} />}
            />
            <Route path="/products/:id" element={<ProductDetail onSaved={refresh} />} />
            <Route path="/chat" element={<ChatBot metadata={metadata} onSaved={refresh} />} />
            <Route path="/health" element={<Health />} />
            <Route path="/management" element={<Management />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          )}
        </div>
      </main>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="h-full min-h-0 overflow-y-auto scrollbar-thin px-4 sm:px-6 lg:px-8 py-5 space-y-5">
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
