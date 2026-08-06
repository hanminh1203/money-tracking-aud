import { useEffect, useState } from 'react';
import Modal from './Modal';
import { getReceipt } from '../lib/api';
import { formatAUD, formatDateShort, parseDate } from '../lib/transform';

function DetailRow({ label, children, className = '' }) {
  const value = children == null || children === '' ? '—' : children;
  return (
    <div className="flex gap-3 items-baseline justify-between py-1.5 border-b border-bg-border/50 last:border-b-0">
      <dt className="shrink-0 text-xs font-medium uppercase tracking-[0.05em] text-text-muted">
        {label}
      </dt>
      <dd className={`text-sm text-text-primary text-right break-words min-w-0 ${className}`.trim()}>
        {value}
      </dd>
    </div>
  );
}

function receiptTitle(data) {
  if (!data) return 'Receipt';
  const store = String(data.store || '').trim() || 'Receipt';
  const dateLabel = formatDateShort(parseDate(data.date)) || data.date;
  return dateLabel ? `${store} (${dateLabel})` : store;
}

export default function ReceiptView({ receiptId, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    getReceipt(receiptId)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [receiptId]);

  let body;
  if (loading) {
    body = <p className="text-sm text-text-muted py-6 text-center">Loading receipt…</p>;
  } else if (error) {
    body = (
      <div className="space-y-4">
        <p className="text-sm text-expense">{error}</p>
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => onClose?.()}
            className="px-3 py-2.5 rounded-lg border border-bg-border bg-bg-raised text-text-secondary hover:text-text-primary font-medium transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    );
  } else if (!data) {
    body = null;
  } else {
    const itemsTotal =
      data.items?.reduce((sum, it) => sum + (Math.abs(Number(it.money)) || 0), 0) ?? 0;
    const total = data.total != null ? Number(data.total) : itemsTotal;
    const sources = data.sources || [];
    const items = data.items || [];

    body = (
      <div className="space-y-4">
        <dl>
          <DetailRow label="Sub Category">{data.subCategory}</DetailRow>
          <DetailRow label="Comment">{data.comment}</DetailRow>
        </dl>

        <section>
          <h4 className="text-xs font-medium uppercase tracking-[0.05em] text-text-muted mb-1">
            Payment sources
          </h4>
          {sources.length === 0 ? (
            <p className="text-sm text-text-muted py-1.5">No payment sources</p>
          ) : (
            <ul className="divide-y divide-bg-border/50">
              {sources.map((s, i) => (
                <li key={i} className="flex gap-3 justify-between py-1.5 text-sm">
                  <span className="text-text-primary min-w-0 break-words">{s.source || '—'}</span>
                  <span className="shrink-0 tabular-money text-text-primary">
                    {formatAUD(Number(s.amount) || 0)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h4 className="text-xs font-medium uppercase tracking-[0.05em] text-text-muted mb-1">
            Items
          </h4>
          {items.length === 0 ? (
            <p className="text-sm text-text-muted py-1.5">No items</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-medium uppercase tracking-[0.05em] text-text-muted border-b border-bg-border/50">
                  <th className="py-1.5 pr-2 font-medium">Name</th>
                  <th className="py-1.5 px-2 font-medium text-right whitespace-nowrap">Amount</th>
                  <th className="py-1.5 px-2 font-medium whitespace-nowrap">Unit</th>
                  <th className="py-1.5 pl-2 font-medium text-right whitespace-nowrap">Money</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-bg-border/50">
                {items.map((it, i) => (
                  <tr key={i}>
                    <td className="py-1.5 pr-2 text-text-primary break-words min-w-0">
                      {it.name || '—'}
                    </td>
                    <td className="py-1.5 px-2 text-text-primary text-right tabular-nums whitespace-nowrap">
                      {it.amount != null && it.amount !== '' ? it.amount : '—'}
                    </td>
                    <td className="py-1.5 px-2 text-text-primary whitespace-nowrap">
                      {it.unit || '—'}
                    </td>
                    <td className="py-1.5 pl-2 text-text-primary text-right tabular-money whitespace-nowrap">
                      {formatAUD(Number(it.money) || 0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <div className="flex items-center justify-between pt-1 border-t border-bg-border">
          <span className="text-xs font-medium uppercase tracking-[0.05em] text-text-muted">Total</span>
          <span className="text-base font-semibold text-text-primary tabular-nums">
            {formatAUD(total)}
          </span>
        </div>

        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => onClose?.()}
            className="px-3 py-2.5 rounded-lg border border-bg-border bg-bg-raised text-text-secondary hover:text-text-primary font-medium transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  return (
    <Modal title={receiptTitle(data)} onClose={onClose} maxWidth="max-w-2xl">
      {body}
    </Modal>
  );
}
