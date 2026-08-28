import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import Card from '../components/Card';
import PageHeader from '../components/PageHeader';
import ReceiptItemsTable from '../components/ReceiptItemsTable';
import TransactionDetailView from '../components/TransactionDetailView';
import { getTransaction } from '../lib/api';
import { formatAUD, formatDateShort } from '../lib/transform';

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

export default function TransactionDetail() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    getTransaction(id)
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
  }, [id]);

  const receipt = data?.receipt;
  const hasReceipt = Boolean(data?.receiptId && receipt);
  const items = receipt?.items || [];
  const itemsTotal = items.reduce((sum, it) => sum + (Math.abs(Number(it.money)) || 0), 0);
  const receiptTotal = receipt?.total != null ? Number(receipt.total) : itemsTotal;

  const description = data
    ? [formatDateShort(data.date), data.subCategory, formatAUD(data.change)].filter(Boolean).join(' · ')
    : 'Date, category, source, amount, and linked receipt items.';

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
          <div
            className={
              hasReceipt
                ? 'grid grid-cols-1 md:grid-cols-2 gap-4 items-start'
                : 'max-w-xl'
            }
          >
            <Card title="Transaction details">
              <TransactionDetailView transaction={data} />
            </Card>
            {hasReceipt && (
              <Card title="Receipt items">
                <ReceiptItemsTable items={items} total={receiptTotal} />
              </Card>
            )}
          </div>
        )}
      </div>
    </PageHeader>
  );
}
