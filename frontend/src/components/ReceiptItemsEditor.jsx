import { Field, inputClass, selectClass } from './FormField';
import { formatAUD } from '../lib/transform';

const DEFAULT_UNITS = ['kg', 'g', 'ml', 'l', 'piece'];

export const emptyReceiptItem = () => ({
  key: `new-${Date.now()}-${Math.random().toString(16).slice(2)}`,
  id: '',
  name: '',
  amount: '',
  unit: 'piece',
  money: '',
  productId: '',
  productItemId: '',
});

export function toReceiptItemForm(item) {
  return {
    key: item.id || emptyReceiptItem().key,
    id: item.id || '',
    name: item.name || '',
    amount: item.amount == null || item.amount === '' ? '' : String(item.amount),
    unit: item.unit || 'piece',
    money: item.money == null || item.money === '' ? '' : String(item.money),
    productId: item.productId || '',
    productItemId: item.productItemId || '',
  };
}

export default function ReceiptItemsEditor({ items, onChange, total, products = [] }) {
  const units = [...DEFAULT_UNITS];
  for (const it of items) {
    if (it.unit && !units.includes(it.unit)) units.push(it.unit);
  }

  function updateItem(index, patch) {
    onChange(items.map((it, i) => (i === index ? { ...it, ...patch } : it)));
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-text-secondary">Items</h4>
        <button
          type="button"
          onClick={() => onChange([...items, emptyReceiptItem()])}
          className="text-sm text-accent hover:text-accent-hover cursor-pointer min-h-11"
        >
          + Add item
        </button>
      </div>
      <div className="space-y-2">
        {items.map((it, i) => (
          <div
            key={it.key}
            className="grid grid-cols-2 sm:grid-cols-[1fr_5rem_5.5rem_6rem_auto] gap-2 items-end rounded-lg border border-bg-border/60 p-3 sm:border-0 sm:p-0"
          >
            <Field label="Name" className="col-span-2 sm:col-span-1">
              <input
                type="text"
                placeholder="Item name"
                value={it.name}
                onChange={(e) => updateItem(i, { name: e.target.value })}
                className={inputClass}
                required
              />
            </Field>
            <Field label="Amount">
              <input
                type="number"
                inputMode="decimal"
                step="any"
                min="0"
                placeholder="0"
                value={it.amount}
                onChange={(e) => updateItem(i, { amount: e.target.value })}
                className={inputClass}
              />
            </Field>
            <Field label="Unit">
              <select
                value={it.unit}
                onChange={(e) => updateItem(i, { unit: e.target.value })}
                className={selectClass}
                required
              >
                {units.map((u) => (
                  <option key={u} value={u}>
                    {u}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Money">
              <input
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                placeholder="0.00"
                value={it.money}
                onChange={(e) => updateItem(i, { money: e.target.value })}
                className={inputClass}
                required
              />
            </Field>
            {it.id && products.length > 0 && (
              <Field label="Product" className="col-span-2 sm:col-span-1">
                <select
                  value={it.productId || ''}
                  onChange={(e) =>
                    updateItem(i, { productId: e.target.value, productItemId: '' })
                  }
                  className={selectClass}
                >
                  <option value="">None</option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            <button
              type="button"
              disabled={items.length === 1}
              onClick={() => onChange(items.filter((_, j) => j !== i))}
              aria-label="Remove item"
              className="col-span-2 sm:col-span-1 inline-flex items-center justify-center min-h-11 min-w-11 sm:self-end sm:justify-self-end rounded-lg text-text-muted hover:text-expense hover:bg-expense/10 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between pt-1 border-t border-bg-border">
        <span className="text-xs font-medium uppercase tracking-[0.05em] text-text-muted">Total</span>
        <span className="text-base font-semibold text-text-primary tabular-money">
          {formatAUD(total)}
        </span>
      </div>
    </div>
  );
}
