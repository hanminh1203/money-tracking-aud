import { formatAUD } from '../lib/transform';

const TYPE_LABEL = { Liquid: 'Liquid', Saving: 'Savings', Giftcard: 'Gift card' };

export default function SourceGrid({ balances, sourceTypes, onSelect, selected }) {
  const entries = Object.entries(balances).sort((a, b) => b[1] - a[1]);

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5">
      {entries.map(([source, balance]) => {
        const type = sourceTypes[source];
        const isActive = selected === source;
        return (
          <button
            key={source}
            type="button"
            onClick={() => onSelect(source)}
            className={`text-left p-3.5 min-h-[5.5rem] rounded-xl border transition-all duration-200 cursor-pointer active:scale-[0.99] ${
              isActive
                ? 'border-accent bg-accent-muted/60 shadow-card ring-1 ring-accent/20'
                : 'border-bg-border bg-bg-surface hover:border-accent/35 hover:bg-bg-raised/60'
            }`}
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <span className="text-sm font-medium text-text-primary leading-snug line-clamp-2">{source}</span>
              {type && (
                <span className="text-[10px] uppercase tracking-wide text-text-muted bg-bg-raised px-1.5 py-0.5 rounded shrink-0">
                  {TYPE_LABEL[type] || type}
                </span>
              )}
            </div>
            <div
              className={`text-base sm:text-lg font-semibold tabular-money ${
                balance < 0 ? 'text-expense' : 'text-text-primary'
              }`}
            >
              {formatAUD(balance)}
            </div>
          </button>
        );
      })}
    </div>
  );
}
