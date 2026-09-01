import { formatAUD } from '../lib/transform';

export default function ReceiptItemsTable({ items = [], total }) {
  if (items.length === 0) {
    return <p className="text-sm text-text-muted py-1.5">No items</p>;
  }

  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs font-medium uppercase tracking-[0.05em] text-text-muted border-b border-bg-border/50">
            <th className="py-1.5 pr-2 font-medium">Name</th>
            <th className="py-1.5 px-2 font-medium text-right whitespace-nowrap">Amount</th>
            <th className="py-1.5 px-2 font-medium whitespace-nowrap">Unit</th>
            <th className="py-1.5 pl-2 font-medium text-right whitespace-nowrap">Money</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-bg-border/50">
          {items.map((it, i) => (
            <tr key={i}>
              <td className="py-1.5 pr-2 text-text-primary break-words min-w-0">{it.name || '—'}</td>
              <td className="py-1.5 px-2 text-text-primary text-right tabular-nums whitespace-nowrap">
                {it.amount != null && it.amount !== '' ? it.amount : '—'}
              </td>
              <td className="py-1.5 px-2 text-text-primary whitespace-nowrap">{it.unit || '—'}</td>
              <td className="py-1.5 pl-2 text-text-primary text-right tabular-money whitespace-nowrap">
                {formatAUD(Number(it.money) || 0)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {total != null && (
        <div className="flex items-center justify-between pt-3 mt-1 border-t border-bg-border">
          <span className="text-xs font-medium uppercase tracking-[0.05em] text-text-muted">Total</span>
          <span className="text-base font-semibold text-text-primary tabular-money">
            {formatAUD(total)}
          </span>
        </div>
      )}
    </div>
  );
}
