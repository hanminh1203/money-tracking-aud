import { useCallback, useEffect, useState } from 'react';
import Card from '../components/Card';
import PageHeader, { PageActions } from '../components/PageHeader';
import { fetchHealth } from '../lib/api';

const SERVICES = [
  {
    key: 'google_sheet',
    name: 'Google Sheet',
    details: (check) => (check?.title ? [{ label: 'Spreadsheet', value: check.title }] : []),
  },
  {
    key: 'database',
    name: 'Database',
    details: () => [{ label: 'Engine', value: 'PostgreSQL' }],
  },
];

export default function Health() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const runCheck = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchHealth();
      setData(result);
    } catch (err) {
      setError(err.message || 'Health check failed');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    runCheck();
  }, [runCheck]);

  const overallStatus = loading ? 'checking' : data?.status === 'ok' ? 'ok' : 'fail';

  return (
    <PageHeader
      title="System Health"
      description="Connection status for Google Sheet and PostgreSQL database."
    >
      <div className="space-y-5">
      <PageActions>
        <button type="button" onClick={runCheck} disabled={loading} className="btn-primary">
          <svg
            className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M4.5 12a7.5 7.5 0 0113.5-4.5M19.5 12a7.5 7.5 0 01-13.5 4.5M4.5 4.5v4.5h4.5M19.5 19.5V15h-4.5"
            />
          </svg>
          {loading ? 'Checking…' : 'Refresh'}
        </button>
      </PageActions>

      {error && (
        <div className="p-4 rounded-xl border border-expense/30 bg-expense/5 text-expense text-sm">
          {error}
        </div>
      )}

      <OverallStatus status={overallStatus} checkedAt={loading ? null : data?.checked_at} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {SERVICES.map(({ key, name, details }) => (
          <CheckCard
            key={key}
            name={name}
            check={data?.checks?.[key]}
            checking={loading}
            details={details(data?.checks?.[key])}
          />
        ))}
      </div>
    </div>
    </PageHeader>
  );
}

const STATUS_STYLES = {
  ok: {
    border: 'border-income/40 bg-income/10',
    text: 'text-income',
    dot: 'bg-income',
    label: 'All systems operational',
  },
  fail: {
    border: 'border-expense/40 bg-expense/10',
    text: 'text-expense',
    dot: 'bg-expense',
    label: 'One or more checks failed',
  },
  checking: {
    border: 'border-amber-500/40 bg-amber-500/10',
    text: 'text-amber-700 dark:text-amber-400',
    dot: 'bg-amber-500',
    label: 'Checking connections…',
  },
};

function OverallStatus({ status, checkedAt }) {
  const styles = STATUS_STYLES[status] || STATUS_STYLES.checking;

  return (
    <div className={`flex items-center gap-3 p-4 rounded-xl border ${styles.border}`}>
      <StatusDot colorClass={styles.dot} large />
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

function CheckCard({ name, check, checking, details }) {
  const status = checking ? 'checking' : check?.ok ? 'ok' : 'fail';
  const styles = STATUS_STYLES[status];

  const message = checking
    ? 'Checking'
    : check?.message || (check?.ok ? 'Connected' : 'Failed');

  return (
    <Card title={name} action={<StatusDot colorClass={styles.dot} />}>
      <div className="space-y-3">
        <p className={`text-sm font-medium ${styles.text}`}>{message}</p>
        {!checking && check?.latency_ms != null && (
          <p className="text-xs text-text-muted">Response time: {check.latency_ms} ms</p>
        )}
        {!checking &&
          details?.map(({ label, value }) =>
            value ? (
              <div key={label} className="text-sm">
                <span className="text-text-muted">{label}: </span>
                <span className="text-text-primary">{value}</span>
              </div>
            ) : null
          )}
      </div>
    </Card>
  );
}

function StatusDot({ colorClass, large }) {
  const size = large ? 'w-3 h-3' : 'w-2.5 h-2.5';
  return <span className={`inline-block rounded-full ${size} ${colorClass} shrink-0`} aria-hidden />;
}

function formatCheckedAt(iso) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
