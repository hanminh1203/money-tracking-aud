import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import Card from '../components/Card';
import Modal from '../components/Modal';
import PageHeader, { PageActions } from '../components/PageHeader';
import { Field, inputClass } from '../components/FormField';
import { createProduct, getProducts } from '../lib/api';
import { formatAUD, formatDateShort } from '../lib/transform';

export default function Products({ onSaved, listVersion }) {
  const [modalOpen, setModalOpen] = useState(false);
  const [name, setName] = useState('');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getProducts();
        if (!cancelled) setRows(Array.isArray(data) ? data : []);
      } catch (err) {
        if (!cancelled) setError(err.message || String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [listVersion]);

  async function handleCreate(e) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setSubmitting(true);
    setError(null);
    try {
      await createProduct({ name: trimmed });
      setModalOpen(false);
      setName('');
      onSaved?.();
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PageHeader
      title="Products"
      description="Track recurring purchases and see cost-per-day over time."
    >
      <div className="space-y-5">
        <PageActions>
          <button type="button" onClick={() => setModalOpen(true)} className="btn-primary">
            Add product
          </button>
        </PageActions>

        {rows.length === 0 && !loading && (
          <Card>
            <p className="text-sm text-text-muted">
              No products yet. Add named tables <code className="text-xs">Product</code> and{' '}
              <code className="text-xs">Product_Items</code> to your spreadsheet (see Management),
              then create your first product here.
            </p>
          </Card>
        )}

        <Card title="Products">
          {error && <div className="mb-3 text-sm text-expense">{error}</div>}
          {loading && rows.length === 0 ? (
            <p className="text-sm text-text-muted py-6">Loading…</p>
          ) : rows.length === 0 ? (
            <p className="text-sm text-text-muted py-6">No products yet.</p>
          ) : (
            <>
              <ul className="space-y-2 sm:hidden">
                {rows.map((p) => (
                  <li key={p.id}>
                    <Link
                      to={`/products/${p.id}`}
                      className="flex items-center justify-between gap-3 rounded-lg border border-bg-border/70 bg-bg-raised/20 px-3 py-3 hover:border-accent/40 transition-colors"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-text-primary truncate">{p.name}</p>
                        <p className="text-xs text-text-muted tabular-nums mt-0.5">
                          {p.purchaseCount} purchase{p.purchaseCount === 1 ? '' : 's'}
                          {p.lastPurchaseDate ? ` · ${formatDateShort(p.lastPurchaseDate)}` : ''}
                        </p>
                      </div>
                      {p.costPerDay != null && (
                        <span className="text-sm tabular-money text-text-secondary shrink-0">
                          {formatAUD(p.costPerDay)}/day
                        </span>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
              <div className="hidden sm:block overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wide text-text-muted border-b border-bg-border">
                      <th className="py-2 pr-4 font-medium">Name</th>
                      <th className="py-2 pr-4 font-medium">Purchases</th>
                      <th className="py-2 pr-4 font-medium">Last purchase</th>
                      <th className="py-2 font-medium text-right">Cost / day</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((p) => (
                      <tr key={p.id} className="border-b border-bg-border/60 hover:bg-bg-raised/30">
                        <td className="py-2.5 pr-4">
                          <Link
                            to={`/products/${p.id}`}
                            className="font-medium text-text-primary hover:text-accent"
                          >
                            {p.name}
                          </Link>
                        </td>
                        <td className="py-2.5 pr-4 tabular-nums text-text-secondary">
                          {p.purchaseCount}
                        </td>
                        <td className="py-2.5 pr-4 tabular-nums text-text-secondary">
                          {p.lastPurchaseDate ? formatDateShort(p.lastPurchaseDate) : '—'}
                        </td>
                        <td className="py-2.5 text-right tabular-money text-text-secondary">
                          {p.costPerDay != null ? formatAUD(p.costPerDay) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Card>

        <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Add product">
          <form onSubmit={handleCreate} className="space-y-4">
            <Field label="Name">
              <input
                className={inputClass}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Toothpaste"
                autoFocus
              />
            </Field>
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={() => setModalOpen(false)}>
                Cancel
              </button>
              <button type="submit" className="btn-primary" disabled={submitting || !name.trim()}>
                {submitting ? 'Saving…' : 'Create'}
              </button>
            </div>
          </form>
        </Modal>
      </div>
    </PageHeader>
  );
}
