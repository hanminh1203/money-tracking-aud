import { useCallback, useEffect, useState } from 'react';
import Card from '../components/Card';
import { inputClass } from '../components/FormField';
import PageHeader, { PageActions } from '../components/PageHeader';
import {
  exportManagement,
  fetchManagementSettings,
  fetchManagementStatus,
  saveManagementSettings,
  syncManagement,
} from '../lib/api';

const TABLES = [
  { key: 'transactions', label: 'Transactions' },
  { key: 'receipt', label: 'Receipt' },
  { key: 'receipt_items', label: 'Receipt Items' },
  { key: 'giftcards', label: 'Giftcards' },
  { key: 'products', label: 'Products' },
  { key: 'product_items', label: 'Product Items' },
];

const SYNC_CONFIRM =
  'This will delete your Transactions, Giftcards, Receipts, Receipt Items, Products, and Product Items in Postgres and reload them from your Google Sheet. Continue?';

function confirmSync() {
  return window.confirm(SYNC_CONFIRM);
}

export default function Management() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [error, setError] = useState(null);
  const [syncMessage, setSyncMessage] = useState(null);
  const [exportResult, setExportResult] = useState(null);
  const [sheetId, setSheetId] = useState('');
  const [savedSheetId, setSavedSheetId] = useState(null);
  const [settingsLoaded, setSettingsLoaded] = useState(false);

  const hasSheet = Boolean((savedSheetId || '').trim());

  const loadSettings = useCallback(async () => {
    try {
      const result = await fetchManagementSettings();
      const id = result?.sheetId || '';
      setSheetId(id);
      setSavedSheetId(id || null);
    } catch (err) {
      setError(err.message || 'Failed to load settings');
    } finally {
      setSettingsLoaded(true);
    }
  }, []);

  const loadStatus = useCallback(async (opts = {}) => {
    const ready = opts.force || hasSheet;
    if (!ready) {
      setData(null);
      setLoading(false);
      return;
    }
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
  }, [hasSheet]);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    if (!settingsLoaded) return;
    loadStatus();
  }, [settingsLoaded, loadStatus]);

  const runSync = async () => {
    setSyncing(true);
    setError(null);
    setSyncMessage(null);
    try {
      const result = await syncManagement();
      const inserted = result?.inserted || {};
      setSyncMessage(
        `Synced ${inserted.transactions ?? 0} transactions, ${inserted.payment ?? 0} payments, ${inserted.giftcard_payment ?? 0} giftcard payments, ${inserted.receipt ?? 0} receipts, ${inserted.receipt_items ?? 0} receipt items, ${inserted.giftcards ?? 0} giftcards, ${inserted.products ?? 0} products, ${inserted.product_items ?? 0} product items.`
      );
      await loadStatus({ force: true });
    } catch (err) {
      setError(err.message || 'Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const handleSaveSettings = async (event) => {
    event.preventDefault();
    const next = sheetId.trim();
    if (!next) {
      setError('Sheet ID is required');
      return;
    }
    if (!confirmSync()) return;

    setSavingSettings(true);
    setError(null);
    setSyncMessage(null);
    setExportResult(null);
    try {
      const result = await saveManagementSettings({ sheetId: next });
      const id = result?.sheetId || next;
      setSheetId(id);
      setSavedSheetId(id);
      setSavingSettings(false);
      await runSync();
    } catch (err) {
      setError(err.message || 'Failed to save sheet ID');
      setSavingSettings(false);
    }
  };

  const handleSync = async () => {
    if (!confirmSync()) return;
    await runSync();
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

  const busy = loading || syncing || exporting || savingSettings;
  const overallStatus = !hasSheet
    ? 'checking'
    : loading
      ? 'checking'
      : data?.matched
        ? 'ok'
        : 'mismatch';

  return (
    <PageHeader
      title="Management"
      description="Set your Google Sheet, compare mirror tables with Postgres, sync when they drift, or export Postgres to a new sheet."
    >
      <div className="space-y-5">
      <PageActions>
        <button
          type="button"
          onClick={loadStatus}
          disabled={busy || !hasSheet}
          className="btn-secondary"
        >
          {loading ? 'Checking…' : 'Refresh status'}
        </button>
        <button
          type="button"
          onClick={handleExport}
          disabled={busy || !hasSheet}
          className="btn-secondary"
        >
          {exporting ? 'Exporting…' : 'Export to Google Sheet'}
        </button>
        <button
          type="button"
          onClick={handleSync}
          disabled={busy || !hasSheet}
          className="btn-primary"
        >
          {syncing ? 'Syncing…' : 'Sync'}
        </button>
      </PageActions>

      <Card title="Google Sheet">
        <form onSubmit={handleSaveSettings} className="space-y-3">
          <p className="text-sm text-text-muted">
            Spreadsheet ID from the sheet URL (<code className="text-xs">/d/&lt;id&gt;/edit</code>).
            Sync and status use this sheet for your account only.
          </p>
          <p className="text-sm text-text-muted">
            For product tracking, add named tables{' '}
            <code className="text-xs">Product</code> (
            <code className="text-xs">Product ID</code>, <code className="text-xs">Name</code>) and{' '}
            <code className="text-xs">Product_Items</code> (
            <code className="text-xs">Product Item ID</code>, <code className="text-xs">Product ID</code>,{' '}
            <code className="text-xs">Price</code>, <code className="text-xs">Transaction ID</code>,{' '}
            <code className="text-xs">Receipt Item ID</code>). Add a{' '}
            <code className="text-xs">Transaction ID</code> column as the first column in{' '}
            <code className="text-xs">Transactions</code>. Add a{' '}
            <code className="text-xs">Receipt Item ID</code> column as the first column in{' '}
            <code className="text-xs">Receipt_Items</code>.
          </p>
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              type="text"
              value={sheetId}
              onChange={(e) => setSheetId(e.target.value)}
              placeholder="Spreadsheet ID"
              className={`${inputClass} flex-1 min-w-0`}
              disabled={savingSettings || syncing}
              autoComplete="off"
            />
            <button
              type="submit"
              disabled={savingSettings || syncing}
              className="btn-secondary shrink-0"
            >
              {savingSettings ? 'Saving…' : syncing ? 'Syncing…' : 'Save sheet ID'}
            </button>
          </div>
          {!hasSheet && settingsLoaded && (
            <p className="text-sm text-amber-700 dark:text-amber-400">
              Save a sheet ID before sync, status, or export.
            </p>
          )}
        </form>
      </Card>

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
            {exportResult.counts?.products ?? 0} products,{' '}
            {exportResult.counts?.product_items ?? 0} product items,{' '}
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

      {hasSheet && (
        <>
          <OverallStatus status={overallStatus} checkedAt={loading ? null : data?.checked_at} />

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {TABLES.map(({ key, label }) => (
              <TableCard
                key={key}
                label={label}
                table={data?.tables?.[key]}
                checking={loading}
              />
            ))}
          </div>
        </>
      )}
    </div>
    </PageHeader>
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
