import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import Card from '../components/Card';
import Modal from '../components/Modal';
import PageHeader, { PageActions } from '../components/PageHeader';
import StatCard from '../components/StatCard';
import { Field, inputClass } from '../components/FormField';
import {
  createProductItem,
  deleteProductItem,
  getProduct,
  getProductCandidates,
} from '../lib/api';
import { formatAUD, formatDateShort } from '../lib/transform';

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

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const detail = await getProduct(id);
      setData(detail);
    } catch (err) {
      setError(err.message || String(err));
      setData(null);
    } finally {
      setLoading(false);
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
      await load();
    } catch (err) {
      setError(err.message || String(err));
    }
  }

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
                value={data.stats?.costPerDay ?? 0}
                tone="accent"
                sublabel={
                  data.stats?.costPerDay != null
                    ? 'Since last purchase'
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
              {(data.purchases || []).length === 0 ? (
                <p className="text-sm text-text-muted py-4">
                  No purchases linked yet. Attach a transaction or receipt item.
                </p>
              ) : (
                <>
                  <ul className="space-y-2 sm:hidden">
                    {(data.purchases || []).map((p) => (
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
                          <span className="text-sm tabular-money text-expense shrink-0">
                            {formatAUD(p.price)}
                          </span>
                        </div>
                        <div className="mt-2 flex items-center gap-2">
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
                          <th className="py-2 pr-4 font-medium">Source</th>
                          <th className="py-2 pr-4 font-medium text-right">Price</th>
                          <th className="py-2 font-medium">Link</th>
                          <th className="py-2 w-20" />
                        </tr>
                      </thead>
                      <tbody>
                        {(data.purchases || []).map((p) => (
                          <tr key={p.id} className="border-b border-bg-border/60">
                            <td className="py-2.5 pr-4 tabular-nums text-text-secondary">
                              {p.date ? formatDateShort(p.date) : '—'}
                            </td>
                            <td className="py-2.5 pr-4 text-text-primary">{p.label || '—'}</td>
                            <td className="py-2.5 pr-4 text-right tabular-money text-expense">
                              {formatAUD(p.price)}
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
                await load();
              }}
            />
          </>
        )}
      </div>
    </PageHeader>
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
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSelected(null);
    setPrice('');
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
            <input
              className={inputClass}
              type="number"
              min="0"
              step="0.01"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              required
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
