import { formatAUD } from '../lib/transform';

export default function StatCard({ label, value, tone = 'default', sublabel, format = 'money' }) {
  const toneClass = {
    default: 'text-text-primary',
    income: 'text-income',
    expense: 'text-expense',
    accent: 'text-accent',
  }[tone];

  const barClass = {
    default: 'bg-bg-border',
    income: 'bg-income',
    expense: 'bg-expense',
    accent: 'bg-accent',
  }[tone];

  return (
    <div className="relative overflow-hidden bg-bg-surface border border-bg-border rounded-xl p-4 sm:p-5 shadow-card transition-shadow duration-200 hover:shadow-soft">
      <div className={`absolute left-0 top-0 bottom-0 w-1 ${barClass}`} aria-hidden />
      <div className="pl-2">
        <div className="text-xs font-medium uppercase tracking-[0.06em] text-text-muted mb-1.5">
          {label}
        </div>
        <div className={`text-2xl sm:text-[1.65rem] font-semibold tabular-money leading-none ${toneClass}`}>
          {format === 'number' ? value : formatAUD(value)}
        </div>
        {sublabel && <div className="text-xs text-text-muted mt-2">{sublabel}</div>}
      </div>
    </div>
  );
}
