import { useState } from 'react';
import { Link } from 'react-router-dom';
import ReceiptView from './ReceiptView';
import { formatAUD, formatDateShort } from '../lib/transform';

const viewBtnClass =
  'inline-flex items-center justify-center min-h-9 px-3 py-1.5 rounded-md border border-bg-border bg-bg-surface text-xs text-text-secondary hover:text-text-primary hover:border-accent/50 transition-colors duration-200 cursor-pointer';

const pageBtnClass =
  'inline-flex items-center justify-center min-h-11 px-3 py-1.5 rounded-md border border-bg-border bg-bg-surface text-xs text-text-secondary hover:text-text-primary hover:border-accent/50 transition-colors duration-200 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:border-bg-border disabled:hover:text-text-secondary';

function amountClass(t) {
  if (t.change < 0) return 'text-expense';
  if (t.type === 'Income') return 'text-income';
  return 'text-text-secondary';
}

function DetailsLink({ transaction }) {
  if (!transaction?.id) return null;
  return (
    <Link
      to={`/transactions/${transaction.id}`}
      className={viewBtnClass}
      aria-label="View transaction details"
    >
      Details
    </Link>
  );
}

function MobileTransactionCards({ transactions, onViewReceipt }) {
  return (
    <ul className="space-y-2 sm:hidden">
      {transactions.map((t, i) => (
        <li
          key={t.id || i}
          className="rounded-lg border border-bg-border/70 bg-bg-raised/20 px-3 py-3"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-text-muted">
                <span className="tabular-nums">{formatDateShort(t.date)}</span>
                {t.subCategory ? <span className="truncate">{t.subCategory}</span> : null}
              </div>
              <p className="mt-1 text-sm text-text-primary leading-snug break-words">
                {t.comment || '—'}
              </p>
              {t.source ? (
                <p className="mt-0.5 text-xs text-text-muted truncate">{t.source}</p>
              ) : null}
            </div>
            <div className="shrink-0 text-right space-y-1.5">
              <div className={`text-sm font-medium tabular-money ${amountClass(t)}`}>
                {formatAUD(t.change)}
              </div>
              <div className="flex flex-col items-end gap-1.5">
                <DetailsLink transaction={t} />
                {t.receiptId ? (
                  <button
                    type="button"
                    className={viewBtnClass}
                    onClick={() => onViewReceipt(t.receiptId)}
                  >
                    Receipt
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function TransactionList({
  transactions,
  emptyLabel = 'No transactions yet',
  page,
  pageSize,
  total,
  totalPages,
  onPageChange,
  loading = false,
}) {
  const [viewReceiptId, setViewReceiptId] = useState(null);

  const paginated = Number.isFinite(pageSize) && pageSize > 0 && total != null;
  const safePage = paginated ? Math.min(Math.max(1, page || 1), Math.max(1, totalPages || 1)) : 1;
  const pages = paginated ? Math.max(1, totalPages || 1) : 1;

  if (!loading && transactions.length === 0) {
    return <div className="text-text-muted text-sm py-10 text-center">{emptyLabel}</div>;
  }

  const from = paginated && total > 0 ? (safePage - 1) * pageSize + 1 : transactions.length ? 1 : 0;
  const to = paginated && total > 0 ? Math.min(safePage * pageSize, total) : transactions.length;

  return (
    <>
      <div className={loading ? 'opacity-60' : undefined}>
        <MobileTransactionCards
          transactions={transactions}
          onViewReceipt={setViewReceiptId}
        />

        <div className="hidden sm:block overflow-x-auto scrollbar-thin">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-text-muted border-b border-bg-border">
                <th className="py-2 pr-4 text-xs font-semibold uppercase tracking-[0.05em]">Date</th>
                <th className="py-2 pr-4 text-xs font-semibold uppercase tracking-[0.05em]">Comment</th>
                <th className="py-2 pr-4 text-xs font-semibold uppercase tracking-[0.05em] hidden md:table-cell">
                  Category
                </th>
                <th className="py-2 pr-4 text-xs font-semibold uppercase tracking-[0.05em] hidden lg:table-cell">
                  Source
                </th>
                <th className="py-2 pl-4 text-xs font-semibold uppercase tracking-[0.05em] text-right">
                  Amount
                </th>
                <th className="py-2 pl-4 text-xs font-semibold uppercase tracking-[0.05em] text-right">
                  Receipt
                </th>
                <th className="py-2 pl-4 text-xs font-semibold uppercase tracking-[0.05em] text-right">
                  Details
                </th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((t, i) => (
                <tr
                  key={t.id || i}
                  className="border-b border-bg-border/70 hover:bg-bg-raised/50 transition-colors duration-150"
                >
                  <td className="py-2.5 pr-4 text-text-secondary whitespace-nowrap tabular-nums">
                    {formatDateShort(t.date)}
                  </td>
                  <td className="py-2.5 pr-4 text-text-primary max-w-[280px] truncate">
                    {t.comment || '—'}
                  </td>
                  <td className="py-2.5 pr-4 text-text-secondary hidden md:table-cell whitespace-nowrap">
                    {t.subCategory || '—'}
                  </td>
                  <td className="py-2.5 pr-4 text-text-secondary hidden lg:table-cell whitespace-nowrap">
                    {t.source}
                  </td>
                  <td className={`py-2.5 pl-4 text-right font-medium tabular-money whitespace-nowrap ${amountClass(t)}`}>
                    {formatAUD(t.change)}
                  </td>
                  <td className="py-2.5 pl-4 text-right whitespace-nowrap">
                    {t.receiptId ? (
                      <button
                        type="button"
                        className={viewBtnClass}
                        onClick={() => setViewReceiptId(t.receiptId)}
                      >
                        View
                      </button>
                    ) : null}
                  </td>
                  <td className="py-2.5 pl-4 text-right whitespace-nowrap">
                    <DetailsLink transaction={t} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {paginated && (
        <div className="flex flex-col min-[400px]:flex-row flex-wrap items-stretch min-[400px]:items-center justify-between gap-3 mt-4 pt-3 border-t border-bg-border">
          <p className="text-xs text-text-muted tabular-nums text-center min-[400px]:text-left">
            {total === 0 ? '0 of 0' : `${from}–${to} of ${total}`}
          </p>
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
            <button
              type="button"
              className={pageBtnClass}
              disabled={loading || safePage <= 1}
              onClick={() => onPageChange?.(safePage - 1)}
            >
              Previous
            </button>
            <span className="text-xs text-text-secondary tabular-nums px-1 text-center whitespace-nowrap">
              {safePage} / {pages}
            </span>
            <button
              type="button"
              className={pageBtnClass}
              disabled={loading || safePage >= pages}
              onClick={() => onPageChange?.(safePage + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {viewReceiptId && (
        <ReceiptView receiptId={viewReceiptId} onClose={() => setViewReceiptId(null)} />
      )}
    </>
  );
}
