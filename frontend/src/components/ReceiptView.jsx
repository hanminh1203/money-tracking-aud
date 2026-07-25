import { useEffect, useState } from 'react';
import { Field } from './FormField';
import { getReceipt } from '../lib/api';
import { formatAUD, formatDateShort, parseDate } from '../lib/transform';

const displayClass =
  'w-full bg-bg-raised/50 border border-bg-border/60 rounded-lg px-3 py-2.5 text-text-primary';

function DisplayValue({ children, empty = '—' }) {
  const text = children == null || children === '' ? empty : children;
  return <div className={displayClass}>{text}</div>;
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

  if (loading) {
    return <p className="text-sm text-text-muted py-6 text-center">Loading receipt…</p>;
  }

  if (error) {
    return (
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
  }

  if (!data) return null;

  const dateLabel = formatDateShort(parseDate(data.date)) || data.date || '—';
  const itemsTotal =
    data.items?.reduce((sum, it) => sum + (Math.abs(Number(it.money)) || 0), 0) ?? 0;
  const total = data.total != null ? Number(data.total) : itemsTotal;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label="Store">
          <DisplayValue>{data.store}</DisplayValue>
        </Field>
        <Field label="Date">
          <DisplayValue>{dateLabel}</DisplayValue>
        </Field>
      </div>

      <Field label="Sub Category">
        <DisplayValue>{data.subCategory}</DisplayValue>
      </Field>

      <Field label="Comment">
        <DisplayValue>{data.comment}</DisplayValue>
      </Field>

      <section className="space-y-3">
        <h4 className="text-sm font-medium text-text-secondary">Payment sources</h4>
        <div className="space-y-2">
          {(data.sources || []).length === 0 ? (
            <p className="text-sm text-text-muted">No payment sources</p>
          ) : (
            data.sources.map((s, i) => (
              <div
                key={i}
                className="grid grid-cols-1 min-[400px]:grid-cols-[1fr_7rem] gap-2 items-end rounded-lg border border-bg-border/60 p-3 min-[400px]:border-0 min-[400px]:p-0"
              >
                <Field label="Source">
                  <DisplayValue>{s.source}</DisplayValue>
                </Field>
                <Field label="Amount">
                  <DisplayValue>{formatAUD(Number(s.amount) || 0)}</DisplayValue>
                </Field>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h4 className="text-sm font-medium text-text-secondary">Items</h4>
        <div className="space-y-2">
          {(data.items || []).length === 0 ? (
            <p className="text-sm text-text-muted">No items</p>
          ) : (
            data.items.map((it, i) => (
              <div
                key={i}
                className="grid grid-cols-2 sm:grid-cols-[1fr_5rem_5.5rem_6rem] gap-2 items-end rounded-lg border border-bg-border/60 p-3 sm:border-0 sm:p-0"
              >
                <Field label="Name" className="col-span-2 sm:col-span-1">
                  <DisplayValue>{it.name}</DisplayValue>
                </Field>
                <Field label="Amount">
                  <DisplayValue>{it.amount != null && it.amount !== '' ? it.amount : '—'}</DisplayValue>
                </Field>
                <Field label="Unit">
                  <DisplayValue>{it.unit}</DisplayValue>
                </Field>
                <Field label="Money" className="col-span-2 sm:col-span-1">
                  <DisplayValue>{formatAUD(Number(it.money) || 0)}</DisplayValue>
                </Field>
              </div>
            ))
          )}
        </div>
      </section>

      <div className="flex items-center justify-between px-1">
        <span className="text-sm text-text-secondary">Total</span>
        <span className="text-lg font-semibold text-text-primary tabular-nums">
          {formatAUD(total)}
        </span>
      </div>

      <div className="flex justify-end pt-1">
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
