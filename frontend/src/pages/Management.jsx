import { useCallback, useEffect, useState } from 'react';
import Card from '../components/Card';
import { fetchManagementStatus, syncManagement } from '../lib/api';

const TABLES = [
  { key: 'transactions', label: 'Transactions' },
  { key: 'receipt', label: 'Receipt' },
  { key: 'receipt_items', label: 'Receipt Items' },
  { key: 'category', label: 'Category' },
  { key: 'sources', label: 'Sources' },
];

export default function Management() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState(null);
  const [syncMessage, setSyncMessage] = useState(null);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchManagementStatus();
      setData(result);
    } catch (err) {
      setError(err.message || 'Failed to load status');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const handleSync = async () => {
    const confirmed = window.confirm(
      'This will delete all Postgres mirror data and reload from Google Sheet. Continue?'
    );
    if (!confirmed) return;

    setSyncing(true);
    setError(null);
    setSyncMessage(null);
    try {
      const result = await syncManagement();
      const inserted = result?.inserted || {};
      setSyncMessage(
        `Synced ${inserted.transactions ?? 0} transactions, ${inserted.receipt ?? 0} receipts, ${inserted.receipt_items ?? 0} receipt items, ${inserted.category ?? 0} categories, ${inserted.sources ?? 0} sources.`
      );
      await loadStatus();
    } catch (err) {
      setError(err.message || 'Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const busy = loading || syncing;
  const overallStatus = loading ? 'checking' : data?.matched ? 'ok' : 'mismatch';

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Management</h1>
          <p className="text-sm text-text-muted mt-1">
            Compare Google Sheet mirror tables with Postgres, and sync when they drift.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={loadStatus}
            disabled={busy}
            className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg border border-bg-border bg-bg-surface text-text-primary text-sm font-medium hover:bg-bg-border/40 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Checking…' : 'Refresh status'}
          </button>
          <button
            type="button"
            onClick={handleSync}
            disabled={busy}
            className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent-hover transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {syncing ? 'Syncing…' : 'Sync'}
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-lg border border-expense/40 bg-expense/10 text-expense text-sm">
          {error}
        </div>
      )}

      {syncMessage && (
        <div className="p-4 rounded-lg border border-income/40 bg-income/10 text-income text-sm">
          {syncMessage}
        </div>
      )}

      <OverallStatus status={overallStatus} checkedAt={loading ? null : data?.checked_at} />

      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {TABLES.map(({ key, label }) => (
          <TableCard
            key={key}
            label={label}
            table={data?.tables?.[key]}
            checking={loading}
          />
        ))}
      </div>
    </div>
  );
}

const STATUS_STYLES = {
  ok: {
    border: 'border-income/40 bg-income/10',
    text: 'text-income',
    dot: 'bg-income',
    label: 'In sync',
  },
  mismatch: {
    border: 'border-expense/40 bg-expense/10',
    text: 'text-expense',
    dot: 'bg-expense',
    label: 'Mismatch',
  },
  checking: {
    border: 'border-orange-500/40 bg-orange-500/10',
    text: 'text-orange-400',
    dot: 'bg-orange-500',
    label: 'Checking…',
  },
};

function OverallStatus({ status, checkedAt }) {
  const styles = STATUS_STYLES[status] || STATUS_STYLES.checking;

  return (
    <div className={`flex items-center gap-3 p-4 rounded-xl border ${styles.border}`}>
      <span className={`inline-block w-3 h-3 rounded-full ${styles.dot} shrink-0`} aria-hidden />
      <div>
        <div className={`font-medium ${styles.text}`}>{styles.label}</div>
        {checkedAt && (
          <div className="text-xs text-text-muted mt-0.5">
            Last checked {formatCheckedAt(checkedAt)}
          </div>
        )}
      </div>
    </div>
  );
}

function TableCard({ label, table, checking }) {
  const matched = !checking && table?.matched;
  const status = checking ? 'checking' : matched ? 'ok' : 'mismatch';
  const styles = STATUS_STYLES[status];

  return (
    <Card
      title={label}
      action={
        <span className={`inline-block w-2.5 h-2.5 rounded-full ${styles.dot}`} aria-hidden />
      }
    >
      <div className="space-y-2 text-sm">
        <p className={`font-medium ${styles.text}`}>
          {checking ? 'Checking' : matched ? 'Matched' : 'Mismatch'}
        </p>
        {!checking && table && (
          <>
            <div>
              <span className="text-text-muted">Google Sheet: </span>
              <span className="text-text-primary">{table.sheet_count}</span>
            </div>
            <div>
              <span className="text-text-muted">Postgres: </span>
              <span className="text-text-primary">{table.db_count}</span>
            </div>
          </>
        )}
      </div>
    </Card>
  );
}

function formatCheckedAt(iso) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
