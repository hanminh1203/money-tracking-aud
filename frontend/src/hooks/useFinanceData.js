import { useCallback, useEffect, useRef, useState } from 'react';
import { isSessionExpiredError } from '../lib/authRedirect';
import { getDashboardData, getMetadata, getTransactionData } from '../lib/api';
import { normalizeRows } from '../lib/transform';

const EMPTY_DASHBOARD = {
  summary: { netWorth: 0, income: 0, expense: 0, saving: 0 },
  months: [],
  incomeBreakdown: [],
  expenseBreakdown: [],
  transactions: [],
};

export function useFinanceData(signedIn) {
  const [transactions, setTransactions] = useState([]);
  const [metadata, setMetadata] = useState({ sources: [], categories: [] });
  const [dashboard, setDashboard] = useState(EMPTY_DASHBOARD);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [listVersion, setListVersion] = useState(0);
  const refreshIdRef = useRef(0);

  const refresh = useCallback(async () => {
    if (!signedIn) return;
    const id = ++refreshIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const [dataRes, metaRes, dashboardRes] = await Promise.all([
        getTransactionData(),
        getMetadata(),
        getDashboardData(),
      ]);
      if (id !== refreshIdRef.current) return;
      setTransactions(normalizeRows(dataRes.rows, metaRes.categories));
      setMetadata(metaRes);
      setDashboard(dashboardRes);
      setListVersion((v) => v + 1);
    } catch (err) {
      if (id !== refreshIdRef.current) return;
      // Session expiry navigates to /login; don't leave a data-load banner up.
      if (isSessionExpiredError(err)) return;
      setError(err.message || String(err));
    } finally {
      if (id === refreshIdRef.current) setLoading(false);
    }
  }, [signedIn]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { transactions, metadata, dashboard, loading, error, refresh, listVersion };
}
