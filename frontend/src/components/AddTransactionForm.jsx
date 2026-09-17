import { useEffect, useMemo, useRef, useState } from 'react';
import { Field, inputClass, selectClass } from './FormField';
import { addTransaction, getGiftcards } from '../lib/api';
import { formatAUD } from '../lib/transform';

const todayISO = () => new Date().toISOString().slice(0, 10);
const emptyPayment = () => ({ source: '', amount: '' });
const emptyGiftcardPayment = () => ({ giftcardId: '', amount: '' });

const cancelClass = 'btn-secondary';
const submitClass = 'btn-secondary';
const primaryClass = 'btn-primary';

export default function AddTransactionForm({ metadata, onSaved, onClose }) {
  const [type, setType] = useState('Expense');
  const [date, setDate] = useState(todayISO());
  const [amount, setAmount] = useState('');
  const [payments, setPayments] = useState([emptyPayment()]);
  const [giftcardPayments, setGiftcardPayments] = useState([]);
  const [giftcards, setGiftcards] = useState([]);
  const [subCategory, setSubCategory] = useState('');
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState(null);
  const closeAfterRef = useRef(false);

  const paymentSources = useMemo(
    () => (metadata.sources || []).filter((s) => s.name !== 'Giftcard'),
    [metadata.sources]
  );

  const categoryOptions = useMemo(
    () => metadata.categories.filter((c) => c.type === type),
    [metadata.categories, type]
  );

  const amountValue = Math.abs(Number(amount)) || 0;

  const paymentsTotal = useMemo(
    () => payments.reduce((sum, p) => sum + (Math.abs(Number(p.amount)) || 0), 0),
    [payments]
  );

  const giftcardTotal = useMemo(
    () => giftcardPayments.reduce((sum, p) => sum + (Math.abs(Number(p.amount)) || 0), 0),
    [giftcardPayments]
  );

  const fundingTotal = paymentsTotal + giftcardTotal;

  const fundingMatch =
    amountValue > 0 && Math.abs(amountValue - fundingTotal) < 0.009;

  const giftcardBalanceById = useMemo(() => {
    const map = new Map();
    for (const g of giftcards) {
      map.set(String(g.id), Number(g.balance) || 0);
    }
    return map;
  }, [giftcards]);

  const giftcardOverBalance = useMemo(() => {
    const used = new Map();
    for (const row of giftcardPayments) {
      if (!row.giftcardId) continue;
      const amt = Math.abs(Number(row.amount)) || 0;
      if (!amt) continue;
      used.set(row.giftcardId, (used.get(row.giftcardId) || 0) + amt);
    }
    for (const [id, total] of used) {
      const balance = giftcardBalanceById.get(String(id)) || 0;
      if (total > balance + 0.009) {
        const card = giftcards.find((g) => String(g.id) === String(id));
        return {
          id,
          total,
          balance,
          label: card ? card.shop : id,
        };
      }
    }
    return null;
  }, [giftcardPayments, giftcardBalanceById, giftcards]);

  const hasFunding =
    payments.some((p) => p.source && Number(p.amount) > 0) ||
    giftcardPayments.some((p) => p.giftcardId && Number(p.amount) > 0);

  const canSubmit =
    amountValue > 0 &&
    subCategory &&
    hasFunding &&
    fundingMatch &&
    !giftcardOverBalance &&
    !submitting;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await getGiftcards();
        if (!cancelled) setGiftcards(Array.isArray(rows) ? rows : []);
      } catch {
        if (!cancelled) setGiftcards([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function updatePayment(index, patch) {
    setPayments((prev) => prev.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  }

  function updateGiftcardPayment(index, patch) {
    setGiftcardPayments((prev) =>
      prev.map((p, i) => (i === index ? { ...p, ...patch } : p))
    );
  }

  function resetForm() {
    setType('Expense');
    setDate(todayISO());
    setAmount('');
    setPayments([emptyPayment()]);
    setGiftcardPayments([]);
    setSubCategory('');
    setComment('');
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    const shouldClose = closeAfterRef.current;
    closeAfterRef.current = false;
    setSubmitting(true);
    setStatus(null);
    try {
      const paymentRows = payments
        .filter((p) => p.source && Number(p.amount) > 0)
        .map((p) => ({ source: p.source, amount: Number(p.amount) }));
      const giftcardRows =
        type === 'Expense'
          ? giftcardPayments
              .filter((p) => p.giftcardId && Number(p.amount) > 0)
              .map((p) => ({ giftcardId: p.giftcardId, amount: Number(p.amount) }))
          : [];
      await addTransaction({
        date,
        amount: amountValue,
        type,
        payments: paymentRows,
        giftcardPayments: giftcardRows,
        subCategory,
        comment,
      });
      setStatus({ ok: true, msg: 'Transaction added.' });
      onSaved?.();
      if (shouldClose) {
        onClose?.();
      } else {
        resetForm();
      }
    } catch (err) {
      setStatus({ ok: false, msg: err.message || String(err) });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-2 p-1 bg-bg-raised rounded-lg">
        {['Expense', 'Income'].map((t) => (
          <button
            type="button"
            key={t}
            onClick={() => {
              setType(t);
              setSubCategory('');
              if (t === 'Income') {
                setGiftcardPayments([]);
                setPayments((prev) => (prev.length === 0 ? [emptyPayment()] : prev));
              }
            }}
            className={`min-h-11 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer ${
              type === t
                ? t === 'Income' ? 'bg-income/20 text-income' : 'bg-expense/20 text-expense'
                : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Date">
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={inputClass} required />
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
      </div>

      <Field label="Category">
        <select value={subCategory} onChange={(e) => setSubCategory(e.target.value)} className={selectClass} required>
          <option value="" disabled>Select a category</option>
          {categoryOptions.map((c) => (
            <option key={`${c.mainCategory}-${c.subCategory}`} value={c.subCategory}>
              {c.mainCategory} — {c.subCategory}
            </option>
          ))}
        </select>
      </Field>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-medium text-text-secondary">Payment sources</h4>
          <button
            type="button"
            onClick={() => setPayments((prev) => [...prev, emptyPayment()])}
            className="text-sm text-accent hover:text-accent-hover cursor-pointer"
          >
            + Add source
          </button>
        </div>
        {payments.length === 0 ? (
          <p className="text-sm text-text-muted">
            {type === 'Expense'
              ? 'Optional when the full amount is paid with giftcards.'
              : 'Add at least one payment source.'}
          </p>
        ) : (
          <div className="space-y-2">
            {payments.map((p, i) => (
              <div
                key={i}
                className="grid grid-cols-1 min-[400px]:grid-cols-[1fr_7rem_auto] gap-2 items-stretch min-[400px]:items-end rounded-lg border border-bg-border/60 p-3 min-[400px]:border-0 min-[400px]:p-0"
              >
                <Field label="Source">
                  <select
                    value={p.source}
                    onChange={(e) => updatePayment(i, { source: e.target.value })}
                    className={selectClass}
                  >
                    <option value="" disabled>Select source</option>
                    {paymentSources.map((s) => (
                      <option key={s.name} value={s.name}>{s.name}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Amount">
                  <input
                    type="number"
                    inputMode="decimal"
                    step="0.01"
                    min="0"
                    placeholder="0.00"
                    value={p.amount}
                    onChange={(e) => updatePayment(i, { amount: e.target.value })}
                    className={inputClass}
                  />
                </Field>
                <button
                  type="button"
                  disabled={type === 'Income' && payments.length === 1}
                  onClick={() => setPayments((prev) => prev.filter((_, j) => j !== i))}
                  aria-label="Remove source"
                  className="inline-flex items-center justify-center min-h-11 min-w-11 self-end justify-self-end rounded-lg text-text-muted hover:text-expense hover:bg-expense/10 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {type === 'Expense' && (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium text-text-secondary">Giftcards</h4>
            <button
              type="button"
              onClick={() => setGiftcardPayments((prev) => [...prev, emptyGiftcardPayment()])}
              disabled={giftcards.length === 0}
              className="text-sm text-accent hover:text-accent-hover cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            >
              + Add giftcard
            </button>
          </div>
          {giftcards.length === 0 ? (
            <p className="text-sm text-text-muted">No giftcards with remaining balance.</p>
          ) : (
            <div className="space-y-2">
              {giftcardPayments.map((p, i) => {
                const selected = giftcards.find((g) => String(g.id) === String(p.giftcardId));
                const maxBalance = selected ? Number(selected.balance) || 0 : undefined;
                return (
                  <div
                    key={i}
                    className="grid grid-cols-1 min-[400px]:grid-cols-[1fr_7rem_auto] gap-2 items-stretch min-[400px]:items-end rounded-lg border border-bg-border/60 p-3 min-[400px]:border-0 min-[400px]:p-0"
                  >
                    <Field label="Giftcard">
                      <select
                        value={p.giftcardId}
                        onChange={(e) => updateGiftcardPayment(i, { giftcardId: e.target.value })}
                        className={selectClass}
                      >
                        <option value="" disabled>Select giftcard</option>
                        {giftcards.map((g) => (
                          <option key={g.id} value={g.id}>
                            {g.shop} — remaining {formatAUD(g.balance)}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Amount">
                      <input
                        type="number"
                        inputMode="decimal"
                        step="0.01"
                        min="0"
                        max={maxBalance || undefined}
                        placeholder="0.00"
                        value={p.amount}
                        onChange={(e) => updateGiftcardPayment(i, { amount: e.target.value })}
                        className={inputClass}
                      />
                    </Field>
                    <button
                      type="button"
                      onClick={() => setGiftcardPayments((prev) => prev.filter((_, j) => j !== i))}
                      aria-label="Remove giftcard"
                      className="inline-flex items-center justify-center min-h-11 min-w-11 self-end justify-self-end rounded-lg text-text-muted hover:text-expense hover:bg-expense/10 cursor-pointer"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {amountValue > 0 && !fundingMatch && (
        <p className="text-sm text-expense">
          Payments ({formatAUD(fundingTotal)}) must equal transaction amount ({formatAUD(amountValue)}).
        </p>
      )}

      {giftcardOverBalance && (
        <p className="text-sm text-expense">
          Giftcard {giftcardOverBalance.label} payment ({formatAUD(giftcardOverBalance.total)}) exceeds
          remaining balance ({formatAUD(giftcardOverBalance.balance)}).
        </p>
      )}

      <Field label="Comment (optional)">
        <input
          type="text"
          placeholder="e.g. Woolworths groceries"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          className={inputClass}
        />
      </Field>

      <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
        <button type="button" onClick={() => onClose?.()} className={cancelClass}>
          Cancel
        </button>
        <button
          type="submit"
          disabled={!canSubmit}
          onClick={() => { closeAfterRef.current = false; }}
          className={submitClass}
        >
          {submitting ? 'Saving…' : 'Submit'}
        </button>
        <button
          type="submit"
          disabled={!canSubmit}
          onClick={() => { closeAfterRef.current = true; }}
          className={primaryClass}
        >
          {submitting ? 'Saving…' : 'Submit and Close'}
        </button>
      </div>

      {status && (
        <p className={`text-sm ${status.ok ? 'text-income' : 'text-expense'}`}>{status.msg}</p>
      )}
    </form>
  );
}
