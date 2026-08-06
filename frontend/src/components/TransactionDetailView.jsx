import { formatAUD, formatDateShort } from '../lib/transform';

const viewBtnClass =
  'inline-flex items-center justify-center min-h-9 px-3 py-1.5 rounded-md border border-bg-border bg-bg-surface text-xs text-text-secondary hover:text-text-primary hover:border-accent/50 transition-colors duration-200 cursor-pointer';

function DetailRow({ label, children, className = '' }) {
  const value = children == null || children === '' ? '—' : children;
  return (
    <div className="flex gap-3 items-baseline justify-between py-1.5 border-b border-bg-border/50 last:border-b-0">
      <dt className="shrink-0 text-xs font-medium uppercase tracking-[0.05em] text-text-muted">
        {label}
      </dt>
      <dd
        className={`text-sm text-right break-words min-w-0 ${className || 'text-text-primary'}`.trim()}
      >
        {value}
      </dd>
    </div>
  );
}

function amountClass(t) {
  if (t.change < 0) return 'text-expense';
  if (t.type === 'Income') return 'text-income';
  return 'text-text-primary';
}

function categoryLabel(t) {
  if (t.mainCategory && t.subCategory) return `${t.mainCategory} — ${t.subCategory}`;
  return t.subCategory || t.mainCategory || '';
}

export default function TransactionDetailView({ transaction, onClose, onViewReceipt }) {
  if (!transaction) return null;

  const t = transaction;

  return (
    <div className="space-y-4">
      <dl>
        <DetailRow label="Date">{formatDateShort(t.date)}</DetailRow>
        <DetailRow label="Source">{t.source}</DetailRow>
        <DetailRow label="Category">{categoryLabel(t)}</DetailRow>
        <DetailRow label="Amount" className={`font-medium tabular-money ${amountClass(t)}`}>
          {formatAUD(t.change)}
        </DetailRow>
        <DetailRow label="Comment">{t.comment}</DetailRow>
        {t.receiptId ? (
          <DetailRow label="Receipt">
            <button
              type="button"
              className={viewBtnClass}
              onClick={() => onViewReceipt?.(t.receiptId)}
            >
              View receipt
            </button>
          </DetailRow>
        ) : null}
      </dl>

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
