import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import Card from '../components/Card';
import Modal from '../components/Modal';
import PageHeader, { PageActions } from '../components/PageHeader';
import StatCard from '../components/StatCard';
import { DecimalInput, Field, inputClass } from '../components/FormField';
import {
  createProductItem,
  deleteProductItem,
  getProduct,
  getProductCandidates,
  updateProductItem,
} from '../lib/api';
import { formatAUD, formatDateShort, parseDate } from '../lib/transform';

function parseIsoDate(value) {
  if (!value) return null;
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) return new Date(+match[1], +match[2] - 1, +match[3]);
  return parseDate(value);
}

function localDateIso(date = new Date()) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function daysBetween(fromValue, toValue) {
  const from = parseIsoDate(fromValue);
  const to = parseIsoDate(toValue);
  if (!from || !to) return null;
  return Math.round((to - from) / 86400000);
}

/** Price ÷ days until end date, next purchase, or today. */
function purchaseCostPerDay(purchase, { nextDate, todayIso } = {}) {
  if (purchase?.price == null || !purchase.date) return null;
  const until = purchase.endDate || nextDate || todayIso;
  const days = daysBetween(purchase.date, until);
  if (days == null || days < 0) return null;
  return purchase.price / Math.max(days, 1);
}

function PencilIcon() {
  return (
    <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L6.832 19.82a4.5 4.5 0 01-1.897 1.13L2.25 21.75l.8-2.685a4.5 4.5 0 011.13-1.897L16.863 4.487z"
      />
    </svg>
  );
}

function EndDateButton({ purchase, onEdit }) {
  const hasDate = Boolean(purchase.endDate);
  return (
    <button
      type="button"
      onClick={() => onEdit(purchase)}
      className="inline-flex items-center gap-1.5 min-h-11 sm:min-h-0 sm:py-1 text-sm text-accent hover:text-accent-hover"
      aria-label={hasDate ? `Edit end date ${formatDateShort(purchase.endDate)}` : 'Set end date'}
    >
      <span className="tabular-nums">
        {hasDate ? formatDateShort(purchase.endDate) : 'Set date'}
      </span>
      <PencilIcon />
    </button>
  );
}

function BackLink() {
  return (
    <Link
      to="/products"
      className="inline-flex items-center gap-1.5 min-h-11 text-sm text-text-secondary hover:text-text-primary transition-colors duration-200"
    >
      <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
      </svg>
      Products
    </Link>
  );
}

export default function ProductDetail({ onSaved }) {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [attachOpen, setAttachOpen] = useState(false);
  const [editingPurchase, setEditingPurchase] = useState(null);

  const load = useCallback(async ({ silent } = {}) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const detail = await getProduct(id);
      setData(detail);
    } catch (err) {
      setError(err.message || String(err));
      if (!silent) setData(null);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const description = data
    ? `${data.stats?.totalPurchases ?? 0} purchase${data.stats?.totalPurchases === 1 ? '' : 's'} tracked`
    : 'Product purchase history and cost statistics.';

  async function handleDetach(productItemId) {
    if (!window.confirm('Remove this purchase link?')) return;
    try {
      await deleteProductItem(productItemId);
      onSaved?.();
      await load({ silent: true });
    } catch (err) {
      setError(err.message || String(err));
    }
  }

  const purchases = data?.purchases || [];
  const todayIso = localDateIso();
  const purchaseRows = purchases.map((p, index) => ({
    ...p,
    costPerDay: purchaseCostPerDay(p, {
      // Newest-first: the next purchase after this one is the previous row.
      nextDate: index === 0 ? null : purchases[index - 1]?.date,
      todayIso,
    }),
  }));

  return (
    <PageHeader title={data?.name || 'Product'} description={description}>
      <div className="space-y-5">
        <BackLink />

        {loading && (
          <div className="max-w-3xl h-56 rounded-xl bg-bg-surface border border-bg-border animate-pulse" />
        )}

        {!loading && error && (
          <Card>
            <p className="text-sm text-expense">{error}</p>
          </Card>
        )}

        {!loading && !error && data && (
          <>
            <PageActions>
              <button type="button" className="btn-primary" onClick={() => setAttachOpen(true)}>
                Attach purchase
              </button>
            </PageActions>

            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
              <StatCard
                label="Cost per day"
                value={purchaseRows[0]?.costPerDay ?? 0}
                tone="accent"
                sublabel={
                  purchaseRows[0]?.costPerDay != null
                    ? purchases[0]?.endDate
                      ? 'Last purchase to end date'
                      : 'Since last purchase'
                    : 'Add a purchase to calculate'
                }
              />
              <StatCard
                label="Avg days between"
                value={data.stats?.avgDaysBetweenPurchases ?? 0}
                tone="default"
                format="number"
                sublabel={
                  data.stats?.avgDaysBetweenPurchases != null
                    ? 'days between purchases'
                    : 'Needs 2+ purchases'
                }
              />
              <StatCard
                label="Total spent"
                value={data.stats?.totalSpent ?? 0}
                tone="expense"
                sublabel={`${data.stats?.totalPurchases ?? 0} purchases`}
              />
              <StatCard
                label="Purchases"
                value={data.stats?.totalPurchases ?? 0}
                tone="default"
                format="number"
                sublabel={
                  data.stats?.lastPurchaseDate
                    ? `Last: ${formatDateShort(data.stats.lastPurchaseDate)}`
                    : 'None yet'
                }
              />
            </div>

            <Card title="Purchase history">
              {purchaseRows.length === 0 ? (
                <p className="text-sm text-text-muted py-4">
                  No purchases linked yet. Attach a transaction or receipt item.
                </p>
              ) : (
                <>
                  <ul className="space-y-2 sm:hidden">
                    {purchaseRows.map((p) => (
                      <li
                        key={p.id}
                        className="rounded-lg border border-bg-border/70 bg-bg-raised/20 px-3 py-3"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-text-primary truncate">
                              {p.label || 'Purchase'}
                            </p>
                            <p className="text-xs text-text-muted tabular-nums mt-0.5">
                              {p.date ? formatDateShort(p.date) : '—'}
                            </p>
                          </div>
                          <div className="text-right shrink-0">
                            <span className="text-sm tabular-money text-expense">
                              {formatAUD(p.price)}
                            </span>
                            <p className="text-xs tabular-money text-text-secondary mt-0.5">
                              {p.costPerDay != null ? `${formatAUD(p.costPerDay)}/day` : '—'}
                            </p>
                          </div>
                        </div>
                        <div className="mt-2">
                          <p className="text-xs font-medium uppercase tracking-[0.05em] text-text-muted">
                            End date
                          </p>
                          <EndDateButton purchase={p} onEdit={setEditingPurchase} />
                        </div>
                        <div className="mt-1 flex items-center gap-2">
                          {p.transactionId && (
                            <Link
                              to={`/transactions/${p.transactionId}`}
                              className="text-xs text-accent hover:underline"
                            >
                              View transaction
                            </Link>
                          )}
                          <button
                            type="button"
                            onClick={() => handleDetach(p.id)}
                            className="text-xs text-text-muted hover:text-expense ml-auto"
                          >
                            Remove
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                  <div className="hidden sm:block overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-xs uppercase tracking-wide text-text-muted border-b border-bg-border">
                          <th className="py-2 pr-4 font-medium">Date</th>
                          <th className="py-2 pr-4 font-medium">End date</th>
                          <th className="py-2 pr-4 font-medium">Source</th>
                          <th className="py-2 pr-4 font-medium text-right">Price</th>
                          <th className="py-2 pr-4 font-medium text-right">Cost / day</th>
                          <th className="py-2 font-medium">Link</th>
                          <th className="py-2 w-20" />
                        </tr>
                      </thead>
                      <tbody>
                        {purchaseRows.map((p) => (
                          <tr key={p.id} className="border-b border-bg-border/60">
                            <td className="py-2.5 pr-4 tabular-nums text-text-secondary">
                              {p.date ? formatDateShort(p.date) : '—'}
                            </td>
                            <td className="py-2.5 pr-4">
                              <EndDateButton purchase={p} onEdit={setEditingPurchase} />
                            </td>
                            <td className="py-2.5 pr-4 text-text-primary">{p.label || '—'}</td>
                            <td className="py-2.5 pr-4 text-right tabular-money text-expense">
                              {formatAUD(p.price)}
                            </td>
                            <td className="py-2.5 pr-4 text-right tabular-money text-text-secondary">
                              {p.costPerDay != null ? `${formatAUD(p.costPerDay)}/day` : '—'}
                            </td>
                            <td className="py-2.5">
                              {p.transactionId ? (
                                <Link
                                  to={`/transactions/${p.transactionId}`}
                                  className="text-accent hover:underline"
                                >
                                  Transaction
                                </Link>
                              ) : (
                                <span className="text-text-muted">Receipt item</span>
                              )}
                            </td>
                            <td className="py-2.5 text-right">
                              <button
                                type="button"
                                onClick={() => handleDetach(p.id)}
                                className="text-xs text-text-muted hover:text-expense"
                              >
                                Remove
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </Card>

            <AttachPurchaseModal
              open={attachOpen}
              onClose={() => setAttachOpen(false)}
              productId={id}
              onAttached={async () => {
                setAttachOpen(false);
                onSaved?.();
                await load({ silent: true });
              }}
            />

            <EditEndDateModal
              open={Boolean(editingPurchase)}
              purchase={editingPurchase}
              onClose={() => setEditingPurchase(null)}
              onSaved={async () => {
                setEditingPurchase(null);
                onSaved?.();
                await load({ silent: true });
              }}
            />
          </>
        )}
      </div>
    </PageHeader>
  );
}

function EditEndDateModal({ open, purchase, onClose, onSaved }) {
  const [endDate, setEndDate] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) return;
    setEndDate(purchase?.endDate || '');
    setError(null);
    setSubmitting(false);
  }, [open, purchase]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!purchase) return;
    setSubmitting(true);
    setError(null);
    try {
      await updateProductItem(purchase.id, { endDate: endDate || null });
      await onSaved?.();
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Edit end date" maxWidth="max-w-md">
      <form onSubmit={handleSubmit} className="space-y-4">
        {purchase?.date && (
          <p className="text-sm text-text-secondary">
            Purchased {formatDateShort(purchase.date)}
            {purchase.label ? ` · ${purchase.label}` : ''}
          </p>
        )}
        <Field label="End date">
          <input
            className={inputClass}
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            autoFocus
          />
        </Field>
        <p className="text-xs text-text-muted">
          When this purchase is expected to run out. Cost per day uses this date when set.
        </p>
        {error && <p className="text-sm text-expense">{error}</p>}
        <div className="flex justify-end gap-2">
          {endDate && (
            <button
              type="button"
              className="btn-secondary mr-auto"
              disabled={submitting}
              onClick={() => setEndDate('')}
            >
              Clear
            </button>
          )}
          <button type="button" className="btn-secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={submitting || !purchase}>
            {submitting ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function AttachPurchaseModal({ open, onClose, productId, onAttached }) {
  const [linkType, setLinkType] = useState('transaction');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState([]);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [price, setPrice] = useState('');
  const [endDate, setEndDate] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSelected(null);
    setPrice('');
    setEndDate('');
    setPage(1);
    setQuery('');
    setLinkType('transaction');
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getProductCandidates(productId, {
          type: linkType,
          q: query,
          page,
        });
        if (cancelled) return;
        setRows(data.rows || []);
        setTotalPages(data.totalPages || 1);
      } catch (err) {
        if (!cancelled) setError(err.message || String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, productId, linkType, query, page]);

  async function handleAttach(e) {
    e.preventDefault();
    if (!selected) return;
    setSubmitting(true);
    setError(null);
    try {
      const payload = { productId };
      if (linkType === 'transaction') {
        payload.transactionId = selected.id;
        payload.price = Number(price);
      } else {
        payload.receiptItemId = selected.id;
        if (price) payload.price = Number(price);
      }
      if (endDate) payload.endDate = endDate;
      await createProductItem(payload);
      onAttached?.();
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Attach purchase">
      <form onSubmit={handleAttach} className="space-y-4">
        <div className="flex gap-2">
          <button
            type="button"
            className={linkType === 'transaction' ? 'btn-primary' : 'btn-secondary'}
            onClick={() => {
              setLinkType('transaction');
              setPage(1);
              setSelected(null);
            }}
          >
            Transactions
          </button>
          <button
            type="button"
            className={linkType === 'receipt_item' ? 'btn-primary' : 'btn-secondary'}
            onClick={() => {
              setLinkType('receipt_item');
              setPage(1);
              setSelected(null);
            }}
          >
            Receipt items
          </button>
        </div>

        <Field label="Search">
          <input
            className={inputClass}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Filter by name or comment…"
          />
        </Field>

        {error && <p className="text-sm text-expense">{error}</p>}

        <div className="max-h-56 overflow-y-auto border border-bg-border rounded-lg divide-y divide-bg-border/60">
          {loading && rows.length === 0 ? (
            <p className="text-sm text-text-muted p-3">Loading…</p>
          ) : rows.length === 0 ? (
            <p className="text-sm text-text-muted p-3">No matches.</p>
          ) : (
            rows.map((row) => (
              <label
                key={row.id}
                className={`flex items-center gap-3 p-3 cursor-pointer hover:bg-bg-raised/40 ${
                  selected?.id === row.id ? 'bg-accent-muted/40' : ''
                }`}
              >
                <input
                  type="radio"
                  name="candidate"
                  checked={selected?.id === row.id}
                  onChange={() => {
                    setSelected(row);
                    if (linkType === 'transaction') {
                      setPrice(String(row.amount ?? ''));
                    } else {
                      setPrice('');
                    }
                  }}
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-text-primary truncate">{row.label}</p>
                  <p className="text-xs text-text-muted tabular-nums">
                    {row.date ? formatDateShort(row.date) : '—'} · {formatAUD(row.amount)}
                  </p>
                </div>
              </label>
            ))
          )}
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between text-sm">
            <button
              type="button"
              className="btn-secondary"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </button>
            <span className="text-text-muted tabular-nums">
              Page {page} of {totalPages}
            </span>
            <button
              type="button"
              className="btn-secondary"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        )}

        {linkType === 'transaction' && selected && (
          <Field label="Price (required for transactions)">
            <DecimalInput
              className={inputClass}
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              required
            />
          </Field>
        )}

        {selected && (
          <Field label="End date (optional)">
            <input
              className={inputClass}
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </Field>
        )}

        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            className="btn-primary"
            disabled={submitting || !selected || (linkType === 'transaction' && !price)}
          >
            {submitting ? 'Saving…' : 'Attach'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
