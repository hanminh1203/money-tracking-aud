import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import Card from '../components/Card';
import { DecimalInput, Field, inputClass, selectClass } from '../components/FormField';
import Modal from '../components/Modal';
import PageHeader from '../components/PageHeader';
import ReceiptItemsEditor, {
  emptyReceiptItem,
  toReceiptItemForm,
} from '../components/ReceiptItemsEditor';
import {
  deleteTransaction,
  getGiftcards,
  getMetadata,
  getTransaction,
  updateTransaction,
} from '../lib/api';
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

function initialPayments(data) {
  const rows = (data.payments || []).map((p) => ({
    source: p.source || '',
    amount: p.amount == null ? '' : String(p.amount),
  }));
  if (!rows.length && !(data.giftcardPayments || []).length && data.source) {
    const firstSource = String(data.source).split(' + ')[0] || '';
    rows.push({
      source: firstSource,
      amount: data.change == null ? '' : String(Math.abs(Number(data.change))),
    });
  }
  if (rows.length) return rows;
  if ((data.giftcardPayments || []).length) return [];
  return [{ source: '', amount: '' }];
}

function initialGiftcardPayments(data) {
  return (data.giftcardPayments || []).map((gp) => ({
    giftcardId: gp.giftcardId || '',
    shop: gp.shop || '',
    amount: gp.amount == null ? '' : String(gp.amount),
  }));
}

function TransactionEditForm({ data, metadata, onSaved, onUpdated }) {
  const navigate = useNavigate();
  const hasReceipt = Boolean(data.receiptId && data.receipt);
  const initialType =
    data.type === 'Income' || data.type === 'Expense'
      ? data.type
      : data.change < 0
        ? 'Expense'
        : 'Income';
  const type = initialType;
  const [date, setDate] = useState(toInputDate(data.date));
  const [amount, setAmount] = useState(
    data.change == null ? '' : String(Math.abs(Number(data.change)))
  );
  const [payments, setPayments] = useState(initialPayments(data));
  const [giftcardPayments, setGiftcardPayments] = useState(initialGiftcardPayments(data));
  const [giftcards, setGiftcards] = useState([]);
  const [subCategory, setSubCategory] = useState(data.subCategory || '');
  const [comment, setComment] = useState(data.comment || '');
  const [items, setItems] = useState(
    hasReceipt ? (data.receipt.items || []).map(toReceiptItemForm) : []
  );
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    getGiftcards()
      .then((rows) => setGiftcards(Array.isArray(rows) ? rows : []))
      .catch(() => setGiftcards([]));
  }, []);

  const paymentSources = useMemo(
    () => (metadata.sources || []).filter((s) => s.name !== 'Giftcard'),
    [metadata.sources]
  );

  const giftcardOptions = useMemo(() => {
    const byId = new Map();
    for (const g of giftcards) {
      byId.set(String(g.id), {
        id: String(g.id),
        shop: g.shop,
        balance: Number(g.balance) || 0,
      });
    }
    for (const gp of data.giftcardPayments || []) {
      const id = String(gp.giftcardId || '');
      if (!id || byId.has(id)) continue;
      byId.set(id, {
        id,
        shop: gp.shop || 'Giftcard',
        balance: 0,
      });
    }
    return Array.from(byId.values());
  }, [giftcards, data.giftcardPayments]);

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

  const paymentsTotal = useMemo(
    () =>
      payments.reduce((sum, p) => sum + (Math.abs(Number(p.amount)) || 0), 0)
      + giftcardPayments.reduce((sum, p) => sum + (Math.abs(Number(p.amount)) || 0), 0),
    [payments, giftcardPayments]
  );

  const effectiveAmount = hasReceipt ? itemsTotal : Math.abs(Number(amount)) || 0;

  const fundingMatch =
    effectiveAmount > 0 && Math.abs(effectiveAmount - paymentsTotal) < 0.009;

  const canSubmit =
    date &&
    effectiveAmount > 0 &&
    (payments.some((p) => p.source && Number(p.amount) > 0)
      || giftcardPayments.some((p) => p.giftcardId && Number(p.amount) > 0)) &&
    subCategory &&
    fundingMatch &&
    !submitting &&
    (!hasReceipt || items.some((it) => it.name.trim() && Number(it.money) > 0));

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setStatus(null);
    try {
      const payload = {
        date,
        amount: hasReceipt ? itemsTotal : amount,
        type,
        subCategory,
        comment,
        payments: payments
          .filter((p) => p.source && Number(p.amount) > 0)
          .map((p) => ({ source: p.source, amount: Number(p.amount) })),
        giftcardPayments: giftcardPayments
          .filter((p) => p.giftcardId && Number(p.amount) > 0)
          .map((p) => ({ giftcardId: p.giftcardId, amount: Number(p.amount) })),
      };
      if (hasReceipt) {
        payload.items = items
          .filter((it) => it.name.trim() && Number(it.money) > 0)
          .map((it) => ({
            id: it.id || undefined,
            name: it.name.trim(),
            amount: it.amount === '' ? 0 : Number(it.amount),
            unit: it.unit,
            money: Number(it.money),
          }));
      }
      await updateTransaction(data.id, payload);

      const refreshed = await getTransaction(data.id);
      onUpdated?.(refreshed);
      onSaved?.();
      setStatus({ ok: true, msg: hasReceipt ? 'Transaction and receipt saved.' : 'Transaction saved.' });
    } catch (err) {
      setStatus({ ok: false, msg: err.message || String(err) });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    setStatus(null);
    try {
      await deleteTransaction(data.id);
      onSaved?.();
      navigate('/transactions');
    } catch (err) {
      setConfirmDelete(false);
      setStatus({ ok: false, msg: err.message || String(err) });
    } finally {
      setDeleting(false);
    }
  }

  const isTransfer = (data.subCategory || '') === 'Exchange (self)';
  const hasGiftcardPayments = (data.giftcardPayments || []).length > 0;
  const hasProductLinks = (data.products || []).length > 0
    || (data.receipt?.items || []).some((it) => it.productId);

  return (
    <>
    <form onSubmit={handleSubmit} className="space-y-5">
      <div
        className={
          hasReceipt ? 'grid grid-cols-1 md:grid-cols-2 gap-4 items-start' : 'max-w-xl'
        }
      >
        <Card title="Transaction details">
          <div className="space-y-4">
            <div
              className={`inline-flex items-center min-h-11 px-3 rounded-md text-sm font-medium ${
                type === 'Income' ? 'bg-income/20 text-income' : 'bg-expense/20 text-expense'
              }`}
              aria-label={`Transaction type ${type}`}
            >
              {type}
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

            <Field label="Payments">
              <div className="space-y-2">
                {payments.length === 0 ? (
                  <p className="text-sm text-text-muted">
                    {type === 'Expense'
                      ? 'Optional when paid fully with giftcards.'
                      : 'Add at least one payment source.'}
                  </p>
                ) : (
                  payments.map((p, index) => (
                    <div key={index} className="grid grid-cols-[1fr_7rem_auto] gap-2 items-center">
                      <select
                        value={p.source}
                        onChange={(e) =>
                          setPayments((prev) =>
                            prev.map((row, i) => (i === index ? { ...row, source: e.target.value } : row))
                          )
                        }
                        className={selectClass}
                      >
                        <option value="">Source</option>
                        {paymentSources.map((s) => (
                          <option key={s.name} value={s.name}>
                            {s.name}
                          </option>
                        ))}
                      </select>
                      <DecimalInput
                        value={p.amount}
                        onChange={(e) =>
                          setPayments((prev) =>
                            prev.map((row, i) => (i === index ? { ...row, amount: e.target.value } : row))
                          )
                        }
                        className={inputClass}
                        placeholder="0.00"
                      />
                      <button
                        type="button"
                        className="text-xs text-text-muted hover:text-expense px-2"
                        disabled={type === 'Income' && payments.length === 1 && !giftcardPayments.length}
                        onClick={() => setPayments((prev) => prev.filter((_, i) => i !== index))}
                      >
                        Remove
                      </button>
                    </div>
                  ))
                )}
                <button
                  type="button"
                  className="text-sm text-accent hover:text-accent-hover"
                  onClick={() => setPayments((prev) => [...prev, { source: '', amount: '' }])}
                >
                  + Add payment
                </button>
              </div>
            </Field>

            {type === 'Expense' && (
              <Field label="Giftcards">
                <div className="space-y-2">
                  {giftcardPayments.length === 0 ? (
                    <p className="text-sm text-text-muted">No giftcard payments.</p>
                  ) : (
                    giftcardPayments.map((p, index) => {
                      const selected = giftcardOptions.find((g) => String(g.id) === String(p.giftcardId));
                      return (
                        <div key={index} className="grid grid-cols-[1fr_7rem_auto] gap-2 items-center">
                          <select
                            value={p.giftcardId}
                            onChange={(e) => {
                              const next = giftcardOptions.find((g) => String(g.id) === e.target.value);
                              setGiftcardPayments((prev) =>
                                prev.map((row, i) =>
                                  i === index
                                    ? {
                                        ...row,
                                        giftcardId: e.target.value,
                                        shop: next?.shop || row.shop || '',
                                      }
                                    : row
                                )
                              );
                            }}
                            className={selectClass}
                          >
                            <option value="">Giftcard</option>
                            {giftcardOptions.map((g) => (
                              <option key={g.id} value={g.id}>
                                {g.shop}
                                {g.balance > 0 ? ` — remaining ${formatAUD(g.balance)}` : ''}
                              </option>
                            ))}
                          </select>
                          <DecimalInput
                            value={p.amount}
                            onChange={(e) =>
                              setGiftcardPayments((prev) =>
                                prev.map((row, i) =>
                                  i === index ? { ...row, amount: e.target.value } : row
                                )
                              )
                            }
                            className={inputClass}
                            placeholder="0.00"
                          />
                          <button
                            type="button"
                            className="text-xs text-text-muted hover:text-expense px-2"
                            onClick={() =>
                              setGiftcardPayments((prev) => prev.filter((_, i) => i !== index))
                            }
                          >
                            Remove
                          </button>
                        </div>
                      );
                    })
                  )}
                  <button
                    type="button"
                    className="text-sm text-accent hover:text-accent-hover disabled:opacity-40 disabled:cursor-not-allowed"
                    disabled={giftcardOptions.length === 0}
                    onClick={() =>
                      setGiftcardPayments((prev) => [
                        ...prev,
                        { giftcardId: '', shop: '', amount: '' },
                      ])
                    }
                  >
                    + Add giftcard
                  </button>
                </div>
              </Field>
            )}

            {!hasReceipt && (
              <Field label="Amount (AUD)">
                <DecimalInput
                  placeholder="0.00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className={inputClass}
                  required
                />
              </Field>
            )}

            {hasReceipt && (
              <p className="text-sm text-text-muted">
                Total: {formatAUD(itemsTotal)} · Payments: {formatAUD(paymentsTotal)}
              </p>
            )}

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
              <ReceiptItemsEditor
                items={items}
                onChange={setItems}
                total={itemsTotal}
              />
            )}
          </Card>
        )}
      </div>

      {hasReceipt && itemsTotal > 0 && !fundingMatch && (
        <p className="text-sm text-expense">
          Payment total ({formatAUD(paymentsTotal)}) must equal items total ({formatAUD(itemsTotal)}).
        </p>
      )}
      {!hasReceipt && effectiveAmount > 0 && !fundingMatch && (
        <p className="text-sm text-expense">
          Payment total ({formatAUD(paymentsTotal)}) must equal amount ({formatAUD(effectiveAmount)}).
        </p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          className="btn-secondary text-expense border-expense/40 hover:border-expense hover:bg-expense/10"
          onClick={() => setConfirmDelete(true)}
          disabled={submitting || deleting}
        >
          Delete
        </button>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Link to="/transactions" className="btn-secondary">
            Cancel
          </Link>
          <button type="submit" disabled={!canSubmit} className="btn-primary">
            {submitting ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      {status && (
        <p className={`text-sm ${status.ok ? 'text-income' : 'text-expense'}`}>{status.msg}</p>
      )}
    </form>

      {confirmDelete && (
        <Modal
          title="Delete this transaction?"
          onClose={() => {
            if (!deleting) setConfirmDelete(false);
          }}
          maxWidth="max-w-lg"
        >
          <div className="space-y-4">
            <p className="text-sm text-text-secondary">
              This cannot be undone. The app will remove this row from Google Sheets and Postgres
              together.
            </p>
            <ul className="list-disc pl-5 space-y-1.5 text-sm text-text-primary">
              <li>The transaction and its payment rows are deleted.</li>
              {hasReceipt ? (
                <li>
                  The linked receipt and its line items are deleted. Receipts belong to exactly one
                  transaction.
                </li>
              ) : null}
              {hasGiftcardPayments ? (
                <li>Giftcard amounts spent on this transaction are credited back to those cards.</li>
              ) : null}
              <li>
                Product links for this purchase are removed
                {hasProductLinks ? '. The product names stay in your catalog' : ''}.
              </li>
              {isTransfer ? (
                <li>
                  Transfers are stored as two independent transactions. The other side is not
                  deleted — remove it separately if needed.
                </li>
              ) : null}
              <li>Giftcard catalog rows (bought cards) are kept even if this was a giftcard purchase.</li>
            </ul>
            {status && !status.ok && (
              <p className="text-sm text-expense">{status.msg}</p>
            )}
            <div className="flex flex-wrap items-center justify-end gap-2">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setConfirmDelete(false)}
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary bg-expense hover:bg-expense"
                onClick={handleDelete}
                disabled={deleting}
              >
                {deleting ? 'Deleting…' : 'Delete transaction'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
