import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import Card from '../components/Card';
import { Field, inputClass, selectClass } from '../components/FormField';
import PageHeader from '../components/PageHeader';
import ReceiptItemsEditor, {
  emptyReceiptItem,
  toReceiptItemForm,
} from '../components/ReceiptItemsEditor';
import { getMetadata, getTransaction, updateTransaction } from '../lib/api';
import { formatAUD, formatDateShort, parseDate } from '../lib/transform';

function BackLink() {
  return (
    <Link
      to="/transactions"
      className="inline-flex items-center gap-1.5 min-h-11 text-sm text-text-secondary hover:text-text-primary transition-colors duration-200"
    >
      <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
      </svg>
      Transactions
    </Link>
  );
}

function toInputDate(value) {
  if (!value) return '';
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value)) return value.slice(0, 10);
  const d = parseDate(value);
  if (!d) return '';
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

export default function TransactionDetail({ onSaved }) {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [metadata, setMetadata] = useState({ sources: [], categories: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    Promise.all([getTransaction(id), getMetadata()])
      .then(([tx, meta]) => {
        if (cancelled) return;
        setData(tx);
        setMetadata(meta || { sources: [], categories: [] });
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
  }, [id]);

  const description = data
    ? [formatDateShort(data.date), data.subCategory, formatAUD(data.change)].filter(Boolean).join(' · ')
    : 'Edit date, category, source, amount, and linked receipt items.';

  return (
    <PageHeader title="Transaction" description={description}>
      <div className="space-y-5">
        <BackLink />

        {loading && (
          <div className="max-w-xl h-56 rounded-xl bg-bg-surface border border-bg-border animate-pulse" />
        )}

        {!loading && error && (
          <Card>
            <p className="text-sm text-expense">{error}</p>
          </Card>
        )}

        {!loading && !error && data && (
          <TransactionEditForm
            key={data.id}
            data={data}
            metadata={metadata}
            onSaved={onSaved}
            onUpdated={setData}
          />
        )}
      </div>
    </PageHeader>
  );
}

function TransactionEditForm({ data, metadata, onSaved, onUpdated }) {
  const hasReceipt = Boolean(data.receiptId && data.receipt);
  const [type, setType] = useState(
    data.type === 'Income' || data.type === 'Expense'
      ? data.type
      : data.change < 0
        ? 'Expense'
        : 'Income'
  );
  const [date, setDate] = useState(toInputDate(data.date));
  const [amount, setAmount] = useState(
    data.change == null ? '' : String(Math.abs(Number(data.change)))
  );
  const [source, setSource] = useState(data.source || '');
  const [subCategory, setSubCategory] = useState(data.subCategory || '');
  const [comment, setComment] = useState(data.comment || '');
  const [items, setItems] = useState(
    hasReceipt
      ? (data.receipt.items || []).map(toReceiptItemForm)
      : []
  );
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState(null);

  const categoryOptions = useMemo(() => {
    const filtered = (metadata.categories || []).filter((c) => c.type === type);
    if (subCategory && !filtered.some((c) => c.subCategory === subCategory)) {
      const current = (metadata.categories || []).find((c) => c.subCategory === subCategory);
      if (current) return [current, ...filtered];
    }
    return filtered;
  }, [metadata.categories, type, subCategory]);

  const itemsTotal = useMemo(
    () => items.reduce((sum, it) => sum + (Math.abs(Number(it.money)) || 0), 0),
    [items]
  );

  const siblingTotal = useMemo(
    () =>
      (data.receipt?.sources || [])
        .filter((s) => s.transactionId !== data.id)
        .reduce((sum, s) => sum + (Math.abs(Number(s.amount)) || 0), 0),
    [data]
  );

  const sourcesMatch =
    !hasReceipt ||
    (itemsTotal > 0 && Math.abs(itemsTotal - (Math.abs(Number(amount)) || 0) - siblingTotal) < 0.009);

  const canSubmit =
    date &&
    amount &&
    Number(amount) > 0 &&
    source &&
    subCategory &&
    !submitting &&
    (!hasReceipt ||
      (items.some((it) => it.name.trim() && Number(it.money) > 0) && sourcesMatch));

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setStatus(null);
    try {
      const payload = {
        date,
        amount,
        type,
        source,
        subCategory,
        comment,
      };
      if (hasReceipt) {
        payload.items = items
          .filter((it) => it.name.trim() && Number(it.money) > 0)
          .map((it) => ({
            name: it.name.trim(),
            amount: it.amount === '' ? 0 : Number(it.amount),
            unit: it.unit,
            money: Number(it.money),
          }));
      }
      await updateTransaction(data.id, payload);
      const fresh = await getTransaction(data.id);
      onUpdated?.(fresh);
      onSaved?.();
      setStatus({ ok: true, msg: hasReceipt ? 'Transaction and receipt saved.' : 'Transaction saved.' });
    } catch (err) {
      setStatus({ ok: false, msg: err.message || String(err) });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div
        className={
          hasReceipt ? 'grid grid-cols-1 md:grid-cols-2 gap-4 items-start' : 'max-w-xl'
        }
      >
        <Card title="Transaction details">
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-2 p-1 bg-bg-raised rounded-lg">
              {['Expense', 'Income'].map((t) => (
                <button
                  type="button"
                  key={t}
                  onClick={() => {
                    setType(t);
                    if (subCategory) {
                      const stillValid = (metadata.categories || []).some(
                        (c) => c.subCategory === subCategory && c.type === t
                      );
                      if (!stillValid) setSubCategory('');
                    }
                  }}
                  className={`min-h-11 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer ${
                    type === t
                      ? t === 'Income'
                        ? 'bg-income/20 text-income'
                        : 'bg-expense/20 text-expense'
                      : 'text-text-secondary hover:text-text-primary'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>

            <Field label="Date">
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className={inputClass}
                required
              />
            </Field>

            <Field label="Category">
              <select
                value={subCategory}
                onChange={(e) => setSubCategory(e.target.value)}
                className={selectClass}
                required
              >
                <option value="" disabled>
                  Select a category
                </option>
                {categoryOptions.map((c) => (
                  <option key={`${c.mainCategory}-${c.subCategory}`} value={c.subCategory}>
                    {c.mainCategory} — {c.subCategory}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Source">
              <select
                value={source}
                onChange={(e) => setSource(e.target.value)}
                className={selectClass}
                required
              >
                <option value="" disabled>
                  Select a source
                </option>
                {(source && !(metadata.sources || []).some((s) => s.name === source)
                  ? [{ name: source }, ...(metadata.sources || [])]
                  : metadata.sources || []
                ).map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.name}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Amount (AUD)">
              <input
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className={inputClass}
                required
              />
            </Field>

            <Field label="Comment">
              <input
                type="text"
                placeholder="e.g. Woolworths groceries"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                className={inputClass}
              />
            </Field>
          </div>
        </Card>

        {hasReceipt && (
          <Card title="Receipt items">
            {items.length === 0 ? (
              <div className="space-y-3">
                <p className="text-sm text-text-muted">No items</p>
                <button
                  type="button"
                  onClick={() => setItems([emptyReceiptItem()])}
                  className="text-sm text-accent hover:text-accent-hover cursor-pointer"
                >
                  + Add item
                </button>
              </div>
            ) : (
              <ReceiptItemsEditor items={items} onChange={setItems} total={itemsTotal} />
            )}
          </Card>
        )}
      </div>

      {hasReceipt && itemsTotal > 0 && !sourcesMatch && (
        <p className="text-sm text-expense">
          {siblingTotal > 0
            ? `This payment (${formatAUD(Math.abs(Number(amount)) || 0)}) plus other receipt payments (${formatAUD(siblingTotal)}) must equal items total (${formatAUD(itemsTotal)}).`
            : `Amount (${formatAUD(Math.abs(Number(amount)) || 0)}) must equal items total (${formatAUD(itemsTotal)}).`}
        </p>
      )}

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Link to="/transactions" className="btn-secondary">
          Cancel
        </Link>
        <button type="submit" disabled={!canSubmit} className="btn-primary">
          {submitting ? 'Saving…' : 'Save'}
        </button>
      </div>

      {status && (
        <p className={`text-sm ${status.ok ? 'text-income' : 'text-expense'}`}>{status.msg}</p>
      )}
    </form>
  );
}
