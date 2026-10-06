import { useEffect, useId, useRef, useState } from 'react';
import { Field, inputClass } from './FormField';

function CategoryMultiSelect({ options, selected, onChange }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const listId = useId();

  useEffect(() => {
    if (!open) return undefined;
    function handlePointerDown(event) {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    function handleKeyDown(event) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  const selectedSet = new Set(selected);
  const label =
    selected.length === 0
      ? 'All categories'
      : selected.length === 1
        ? options.find((o) => o.value === selected[0])?.label || selected[0]
        : `${selected.length} categories`;

  function toggle(value) {
    if (selectedSet.has(value)) {
      onChange(selected.filter((v) => v !== value));
    } else {
      onChange([...selected, value]);
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        className={`${inputClass} flex items-center justify-between gap-2 text-left`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((v) => !v)}
      >
        <span className={selected.length ? 'text-text-primary' : 'text-text-muted'}>{label}</span>
        <span className="text-text-muted text-xs" aria-hidden>
          ▾
        </span>
      </button>
      {open && (
        <div
          id={listId}
          role="listbox"
          aria-multiselectable="true"
          className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-bg-border bg-bg-surface shadow-card py-1"
        >
          {options.length === 0 ? (
            <div className="px-3 py-2 text-sm text-text-muted">No categories</div>
          ) : (
            options.map((opt) => {
              const checked = selectedSet.has(opt.value);
              return (
                <label
                  key={opt.value}
                  role="option"
                  aria-selected={checked}
                  className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-bg-raised/40"
                >
                  <input
                    type="checkbox"
                    className="rounded border-bg-border text-accent focus:ring-accent/30"
                    checked={checked}
                    onChange={() => toggle(opt.value)}
                  />
                  <span className="truncate">{opt.label}</span>
                </label>
              );
            })
          )}
          {selected.length > 0 && (
            <button
              type="button"
              className="w-full border-t border-bg-border px-3 py-2 text-left text-xs text-accent hover:bg-bg-raised/40"
              onClick={() => onChange([])}
            >
              Clear selection
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function TransactionFilters({
  search,
  onSearchChange,
  categories,
  selectedCategories,
  onCategoriesChange,
  includeExchange,
  onIncludeExchangeChange,
}) {
  const categoryOptions = (categories || []).map((c) => ({
    value: c.subCategory,
    label: c.mainCategory ? `${c.mainCategory} — ${c.subCategory}` : c.subCategory,
  }));

  return (
    <div className="mb-4 grid gap-3 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto] sm:items-end">
      <Field label="Search">
        <input
          type="search"
          className={inputClass}
          placeholder="Comment or receipt item"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          autoComplete="off"
        />
      </Field>
      <Field label="Category">
        <CategoryMultiSelect
          options={categoryOptions}
          selected={selectedCategories}
          onChange={onCategoriesChange}
        />
      </Field>
      <label className="flex items-center gap-2 pb-2.5 text-sm text-text-primary cursor-pointer select-none">
        <input
          type="checkbox"
          className="rounded border-bg-border text-accent focus:ring-accent/30"
          checked={includeExchange}
          onChange={(e) => onIncludeExchangeChange(e.target.checked)}
        />
        Exchange
      </label>
    </div>
  );
}
