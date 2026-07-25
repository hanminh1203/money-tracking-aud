import { formatAUD } from '../lib/transform';

function amountText(value) {
  const amount = Number(value) || 0;
  if (amount === 0) return '-';
  return formatAUD(amount);
}

function monthChange(current, previous) {
  if (previous == null) return null;
  const curr = Number(current) || 0;
  const prev = Number(previous) || 0;
  if (curr > prev) return 'up';
  if (curr < prev) return 'down';
  return null;
}

function ChangeArrow({ direction }) {
  if (!direction) return null;
  return (
    <span
      className={`ml-1 inline-block text-xs leading-none ${
        direction === 'up' ? 'text-income' : 'text-expense'
      }`}
      aria-label={direction === 'up' ? 'Increased from previous month' : 'Decreased from previous month'}
    >
      {direction === 'up' ? '▲' : '▼'}
    </span>
  );
}

function AmountValue({ value, previous, className = '' }) {
  const text = amountText(value);
  const change = monthChange(value, previous);
  return (
    <span className={`inline-flex items-center justify-end tabular-money whitespace-nowrap text-text-primary ${className}`}>
      <span className={text === '-' ? 'text-text-muted' : undefined}>{text}</span>
      <ChangeArrow direction={change} />
    </span>
  );
}

function AmountCell({ value, previous, className = '' }) {
  return (
    <td className={`px-3 text-right ${className}`}>
      <AmountValue value={value} previous={previous} />
    </td>
  );
}

function MobileBreakdown({ months, rows, totals }) {
  return (
    <div className="space-y-3 sm:hidden">
      {rows.map((row) => (
        <div
          key={row.subCategory}
          className="rounded-lg border border-bg-border/70 bg-bg-raised/30 px-3 py-2.5"
        >
          <div className="text-sm font-medium text-text-primary mb-2 truncate">{row.subCategory}</div>
          <dl className="space-y-1.5">
            {months.map((month, index) => (
              <div key={month} className="flex items-center justify-between gap-3 text-sm">
                <dt className="text-text-muted shrink-0">{month}</dt>
                <dd>
                  <AmountValue
                    value={row.amounts[month]}
                    previous={index === 0 ? null : row.amounts[months[index - 1]]}
                  />
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
      <div className="rounded-lg border border-bg-border bg-bg-raised px-3 py-2.5">
        <div className="text-xs font-semibold uppercase tracking-wide text-text-secondary mb-2">Total</div>
        <dl className="space-y-1.5">
          {months.map((month, index) => (
            <div key={month} className="flex items-center justify-between gap-3 text-sm">
              <dt className="text-text-muted shrink-0">{month}</dt>
              <dd>
                <AmountValue
                  className="font-semibold"
                  value={totals[month]}
                  previous={index === 0 ? null : totals[months[index - 1]]}
                />
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}

export default function CategoryBreakdownTable({ months, rows, emptyLabel }) {
  if (rows.length === 0) {
    return <div className="py-8 text-center text-sm text-text-muted">{emptyLabel}</div>;
  }

  const totals = Object.fromEntries(
    months.map((month) => [
      month,
      rows.reduce((sum, row) => sum + (Number(row.amounts[month]) || 0), 0),
    ]),
  );

  return (
    <>
      <MobileBreakdown months={months} rows={rows} totals={totals} />

      <div className="hidden sm:block overflow-x-auto scrollbar-thin">
        <table className="w-full min-w-[480px] text-sm">
          <thead>
            <tr className="border-b border-bg-border text-text-muted">
              <th className="py-2 pr-4 text-left text-xs font-semibold uppercase tracking-[0.05em]">
                Subcategory
              </th>
              {months.map((month) => (
                <th
                  key={month}
                  className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-[0.05em] whitespace-nowrap"
                >
                  {month}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.subCategory}
                className="border-b border-bg-border/60 transition-colors hover:bg-bg-raised/40"
              >
                <td className="py-2.5 pr-4 text-text-primary whitespace-nowrap">
                  {row.subCategory}
                </td>
                {months.map((month, index) => (
                  <AmountCell
                    key={month}
                    className="py-2.5"
                    value={row.amounts[month]}
                    previous={index === 0 ? null : row.amounts[months[index - 1]]}
                  />
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-bg-border bg-bg-raised">
              <td className="py-3 pr-4 text-xs font-semibold uppercase tracking-wide text-text-secondary whitespace-nowrap">
                Total
              </td>
              {months.map((month, index) => (
                <AmountCell
                  key={month}
                  className="py-3 text-base font-semibold"
                  value={totals[month]}
                  previous={index === 0 ? null : totals[months[index - 1]]}
                />
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
    </>
  );
}
