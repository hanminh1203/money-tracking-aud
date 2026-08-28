import { formatAUD, formatDateShort } from '../lib/transform';

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

export default function TransactionDetailView({ transaction }) {
  if (!transaction) return null;

  const t = transaction;

  return (
    <dl>
      <DetailRow label="Date">{formatDateShort(t.date)}</DetailRow>
      <DetailRow label="Category">{categoryLabel(t)}</DetailRow>
      <DetailRow label="Source">{t.source}</DetailRow>
      <DetailRow label="Amount" className={`font-medium tabular-money ${amountClass(t)}`}>
        {formatAUD(t.change)}
      </DetailRow>
      <DetailRow label="Comment">{t.comment}</DetailRow>
    </dl>
  );
}
