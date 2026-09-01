import { useEffect, useState } from 'react';
import Card from '../components/Card';
import Modal from '../components/Modal';
import PageHeader, { PageActions } from '../components/PageHeader';
import BuyGiftcardForm from '../components/BuyGiftcardForm';
import UseGiftcardForm from '../components/UseGiftcardForm';
import { getGiftcards } from '../lib/api';
import { formatAUD, formatDateShort } from '../lib/transform';

const actionClass =
  'px-2.5 py-1 rounded-md text-xs font-medium border border-bg-border bg-bg-surface text-text-primary hover:border-accent/50 cursor-pointer transition-colors duration-200 disabled:opacity-40 disabled:cursor-not-allowed';

export default function Giftcards({ metadata, balances, onSaved, listVersion }) {
  const [modal, setModal] = useState(null);
  const [useCard, setUseCard] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getGiftcards();
        if (cancelled) return;
        setRows(Array.isArray(data) ? data : []);
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

  function closeModal() {
    setModal(null);
    setUseCard(null);
  }

  function handleSaved() {
    onSaved?.();
  }

  return (
    <PageHeader
      title="Giftcards"
      description="Track store credit balances and record redemptions."
    >
      <div className="space-y-5">
      <PageActions>
        <button type="button" onClick={() => setModal('buy')} className="btn-primary">
          Buy giftcard
        </button>
      </PageActions>

      <Card title="Giftcards">
        {error && <div className="mb-3 text-sm text-expense">{error}</div>}
        {loading && rows.length === 0 ? (
          <p className="text-sm text-text-muted py-6">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-text-muted py-6">No giftcards yet.</p>
        ) : (
          <>
            <ul className="space-y-2 sm:hidden">
              {rows.map((g) => (
                <li
                  key={g.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-bg-border/70 bg-bg-raised/20 px-3 py-3"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-text-primary truncate">{g.shop}</p>
                    <p className="text-xs text-text-muted tabular-nums mt-0.5">
                      {formatDateShort(g.date)}
                    </p>
                  </div>
                  <div className="shrink-0 text-right space-y-1.5">
                    <div className="text-sm font-medium tabular-money text-text-primary">
                      {formatAUD(g.balance)}
                    </div>
                    <button
                      type="button"
                      className={`${actionClass} min-h-9`}
                      onClick={() => {
                        setUseCard(g);
                        setModal('use');
                      }}
                    >
                      Use
                    </button>
                  </div>
                </li>
              ))}
            </ul>

            <div className="hidden sm:block overflow-x-auto scrollbar-thin">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-text-muted border-b border-bg-border">
                    <th className="py-2 pr-3 text-xs font-semibold uppercase tracking-[0.05em]">Shop</th>
                    <th className="py-2 pr-3 text-xs font-semibold uppercase tracking-[0.05em]">Date</th>
                    <th className="py-2 pr-3 text-xs font-semibold uppercase tracking-[0.05em] text-right">
                      Balance
                    </th>
                    <th className="py-2 text-xs font-semibold uppercase tracking-[0.05em] text-right">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((g) => (
                    <tr key={g.id} className="border-b border-bg-border/70 last:border-0">
                      <td className="py-2.5 pr-3 text-text-primary">{g.shop}</td>
                      <td className="py-2.5 pr-3 text-text-secondary tabular-nums">
                        {formatDateShort(g.date)}
                      </td>
                      <td className="py-2.5 pr-3 text-right tabular-money text-text-primary">
                        {formatAUD(g.balance)}
                      </td>
                      <td className="py-2.5 text-right">
                        <button
                          type="button"
                          className={actionClass}
                          onClick={() => {
                            setUseCard(g);
                            setModal('use');
                          }}
                        >
                          Use
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

      {modal === 'buy' && (
        <Modal title="Buy giftcard" onClose={closeModal} maxWidth="max-w-lg">
          <BuyGiftcardForm
            metadata={metadata}
            balances={balances}
            onSaved={handleSaved}
            onClose={closeModal}
          />
        </Modal>
      )}

      {modal === 'use' && useCard && (
        <Modal title={`Use — ${useCard.shop}`} onClose={closeModal} maxWidth="max-w-lg">
          <UseGiftcardForm
            giftcard={useCard}
            metadata={metadata}
            onSaved={handleSaved}
            onClose={closeModal}
          />
        </Modal>
      )}
    </div>
    </PageHeader>
  );
}
