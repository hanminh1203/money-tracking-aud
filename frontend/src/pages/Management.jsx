import { useCallback, useEffect, useState } from 'react';
import Card from '../components/Card';
import PageHeader from '../components/PageHeader';
import { exportManagement, fetchManagementStatus, syncManagement } from '../lib/api';

const TABLES = [
  { key: 'transactions', label: 'Transactions' },
  { key: 'receipt', label: 'Receipt' },
  { key: 'receipt_items', label: 'Receipt Items' },
  { key: 'giftcards', label: 'Giftcards' },
  { key: 'category', label: 'Category' },
  { key: 'sources', label: 'Sources' },
];

export default function Management() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);
  const [syncMessage, setSyncMessage] = useState(null);
  const [exportResult, setExportResult] = useState(null);

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
        `Synced ${inserted.transactions ?? 0} transactions, ${inserted.receipt ?? 0} receipts, ${inserted.receipt_items ?? 0} receipt items, ${inserted.giftcards ?? 0} giftcards, ${inserted.category ?? 0} categories, ${inserted.sources ?? 0} sources.`
      );
      await loadStatus();
    } catch (err) {
      setError(err.message || 'Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    setError(null);
    setExportResult(null);
    try {
      const result = await exportManagement();
      setExportResult(result);
      if (result?.url) {
        window.open(result.url, '_blank', 'noopener,noreferrer');
      }
    } catch (err) {
      setError(err.message || 'Export failed');
    } finally {
      setExporting(false);
    }
  };

  const busy = loading || syncing || exporting;
  const overallStatus = loading ? 'checking' : data?.matched ? 'ok' : 'mismatch';

  return (
    <div className="space-y-5">
      <PageHeader
        title="Management"
        description="Compare Google Sheet mirror tables with Postgres, sync when they drift, or export Postgres to a new sheet."
        action={
          <>
            <button type="button" onClick={loadStatus} disabled={busy} className="btn-secondary">
              {loading ? 'Checking…' : 'Refresh status'}
            </button>
            <button type="button" onClick={handleExport} disabled={busy} className="btn-secondary">
              {exporting ? 'Exporting…' : 'Export to Google Sheet'}
            </button>
            <button type="button" onClick={handleSync} disabled={busy} className="btn-primary">
              {syncing ? 'Syncing…' : 'Sync'}
            </button>
          </>
        }
      />

      {error && (
        <div className="p-4 rounded-xl border border-expense/30 bg-expense/5 text-expense text-sm">
          {error}
        </div>
      )}

      {syncMessage && (
        <div className="p-4 rounded-xl border border-income/30 bg-income/5 text-income text-sm">
          {syncMessage}
        </div>
      )}

      {exportResult && (
        <div className="p-4 rounded-xl border border-income/30 bg-income/5 text-income text-sm space-y-1">
          <p>
            Exported {exportResult.counts?.transactions ?? 0} transactions,{' '}
            {exportResult.counts?.receipt ?? 0} receipts,{' '}
            {exportResult.counts?.receipt_items ?? 0} receipt items,{' '}
            {exportResult.counts?.giftcards ?? 0} giftcards,{' '}
            {exportResult.counts?.category ?? 0} categories,{' '}
            {exportResult.counts?.sources ?? 0} sources.
          </p>
          {exportResult.url && (
            <p>
              <a
                href={exportResult.url}
                target="_blank"
                rel="noopener noreferrer"
                className="underline font-medium"
              >
                Open exported Google Sheet
              </a>
            </p>
          )}
        </div>
      )}

      <OverallStatus status={overallStatus} checkedAt={loading ? null : data?.checked_at} />

      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
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
    border: 'border-amber-500/40 bg-amber-500/10',
    text: 'text-amber-700 dark:text-amber-400',
    dot: 'bg-amber-500',
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
