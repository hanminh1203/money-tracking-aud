import { useEffect, useMemo, useRef, useState } from 'react';
import { Field, inputClass, selectClass } from './FormField';
import { addReceipt, extractReceiptFromImage, getGiftcards } from '../lib/api';
import { fileToDataUrl } from '../lib/imageUtils';
import { formatAUD } from '../lib/transform';

const UNITS = ['kg', 'g', 'ml', 'l', 'piece'];

const todayISO = () => new Date().toISOString().slice(0, 10);
const emptySource = () => ({ source: '', amount: '' });
const emptyGiftcardPayment = () => ({ giftcardId: '', amount: '' });
const emptyItem = () => ({ name: '', amount: '', unit: 'piece', money: '' });

const cancelClass = 'btn-secondary';
const submitClass = 'btn-secondary';
const primaryClass = 'btn-primary';

export default function ReceiptForm({ metadata, onSaved, onClose }) {
  const [store, setStore] = useState('');
  const [date, setDate] = useState(todayISO());
  const [subCategory, setSubCategory] = useState('');
  const [comment, setComment] = useState('');
  const [sources, setSources] = useState([emptySource()]);
  const [giftcardPayments, setGiftcardPayments] = useState([]);
  const [giftcards, setGiftcards] = useState([]);
  const [items, setItems] = useState([emptyItem()]);
  const [submitting, setSubmitting] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [status, setStatus] = useState(null);
  const fileInputRef = useRef(null);
  const closeAfterRef = useRef(false);

  const expenseCategories = useMemo(
    () => metadata.categories.filter((c) => c.type === 'Expense'),
    [metadata.categories]
  );

  const paymentSources = useMemo(
    () => (metadata.sources || []).filter((s) => s.name !== 'Giftcard'),
    [metadata.sources]
  );

  const itemsTotal = useMemo(
    () => items.reduce((sum, it) => sum + (Math.abs(Number(it.money)) || 0), 0),
    [items]
  );

  const sourcesTotal = useMemo(
    () => sources.reduce((sum, s) => sum + (Math.abs(Number(s.amount)) || 0), 0),
    [sources]
  );

  const giftcardTotal = useMemo(
    () => giftcardPayments.reduce((sum, p) => sum + (Math.abs(Number(p.amount)) || 0), 0),
    [giftcardPayments]
  );

  const fundingTotal = sourcesTotal + giftcardTotal;

  const sourcesMatch =
    itemsTotal > 0 && Math.abs(itemsTotal - fundingTotal) < 0.009;

  const giftcardBalanceById = useMemo(() => {
    const map = new Map();
    for (const g of giftcards) {
      map.set(String(g.id), Number(g.balance) || 0);
    }
    return map;
  }, [giftcards]);

  const giftcardOverBalance = useMemo(() => {
    const used = new Map();
    for (const row of giftcardPayments) {
      if (!row.giftcardId) continue;
      const amt = Math.abs(Number(row.amount)) || 0;
      if (!amt) continue;
      used.set(row.giftcardId, (used.get(row.giftcardId) || 0) + amt);
    }
    for (const [id, total] of used) {
      const balance = giftcardBalanceById.get(String(id)) || 0;
      if (total > balance + 0.009) {
        const card = giftcards.find((g) => String(g.id) === String(id));
        return {
          id,
          total,
          balance,
          label: card ? card.shop : id,
        };
      }
    }
    return null;
  }, [giftcardPayments, giftcardBalanceById, giftcards]);

  const hasFunding =
    sources.some((s) => s.source && Number(s.amount) > 0) ||
    giftcardPayments.some((p) => p.giftcardId && Number(p.amount) > 0);

  const canSubmit =
    store.trim() &&
    date &&
    subCategory &&
    items.some((it) => it.name.trim() && Number(it.money) > 0) &&
    hasFunding &&
    sourcesMatch &&
    !giftcardOverBalance &&
    !submitting &&
    !extracting;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await getGiftcards();
        if (!cancelled) setGiftcards(Array.isArray(rows) ? rows : []);
      } catch {
        if (!cancelled) setGiftcards([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function updateSource(index, patch) {
    setSources((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  }

  function updateGiftcardPayment(index, patch) {
    setGiftcardPayments((prev) =>
      prev.map((p, i) => (i === index ? { ...p, ...patch } : p))
    );
  }

  function updateItem(index, patch) {
    setItems((prev) => prev.map((it, i) => (i === index ? { ...it, ...patch } : it)));
  }

  function resetForm() {
    setStore('');
    setDate(todayISO());
    setSubCategory('');
    setComment('');
    setSources([emptySource()]);
    setGiftcardPayments([]);
    setItems([emptyItem()]);
    setPreviewUrl(null);
  }

  async function handleImageSelected(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;

    // Clear previous entry so stale fields are not visible while OCR runs.
    resetForm();
    setExtracting(true);
    setStatus(null);
    try {
      const dataUrl = await fileToDataUrl(file);
      setPreviewUrl(dataUrl);

      const extracted = await extractReceiptFromImage({
        imageDataUrl: dataUrl,
        metadata,
      });

      // Replace every form field with the AI result (do not merge).
      setStore(extracted.store);
      setDate(extracted.date);
      setSubCategory(extracted.subCategory);
      setComment(extracted.comment);
      setSources(extracted.sources?.length ? extracted.sources : [emptySource()]);
      setGiftcardPayments([]);
      setItems(extracted.items);
      setStatus({
        ok: true,
        msg: `Extracted ${extracted.items.filter((it) => it.name).length} item(s) from receipt — review and save.`,
      });
    } catch (err) {
      setStatus({ ok: false, msg: err.message || String(err) });
    } finally {
      setExtracting(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    const shouldClose = closeAfterRef.current;
    closeAfterRef.current = false;
    setSubmitting(true);
    setStatus(null);
    try {
      const paymentRows = sources
        .filter((s) => s.source && Number(s.amount) > 0)
        .map((s) => ({ source: s.source, amount: Number(s.amount) }));
      const giftcardRows = giftcardPayments
        .filter((p) => p.giftcardId && Number(p.amount) > 0)
        .map((p) => ({ giftcardId: p.giftcardId, amount: Number(p.amount) }));
      const result = await addReceipt({
        date,
        store,
        subCategory,
        comment,
        sources: [...paymentRows, ...giftcardRows],
        items: items.filter((it) => it.name.trim() && Number(it.money) > 0),
      });
      setStatus({
        ok: true,
        msg: `Receipt saved (${result.items} items, ${result.transactions} payment${result.transactions === 1 ? '' : 's'}).`,
      });
      onSaved?.();
      if (shouldClose) {
        onClose?.();
      } else {
        resetForm();
      }
    } catch (err) {
      setStatus({ ok: false, msg: err.message || String(err) });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
        <div className="rounded-lg border border-dashed border-bg-border bg-bg-raised/40 p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm font-medium text-text-primary">Scan with AI</p>
              <p className="text-xs text-text-muted mt-0.5">
                Upload a receipt photo — Groq fills the form (replaces existing values).
              </p>
            </div>
            <button
              type="button"
              disabled={extracting}
              onClick={() => fileInputRef.current?.click()}
              className="px-3 py-2 rounded-lg bg-bg-raised border border-bg-border text-sm text-text-primary hover:border-accent disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
            >
              {extracting ? 'Extracting…' : 'Upload image'}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*,.heic,.heif,image/heic,image/heif"
              capture="environment"
              className="hidden"
              onChange={handleImageSelected}
            />
          </div>
          {previewUrl && (
            <img
              src={previewUrl}
              alt="Receipt preview"
              className="max-h-40 rounded-md border border-bg-border object-contain bg-bg"
            />
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Store">
            <input
              type="text"
              placeholder="e.g. Woolworths"
              value={store}
              onChange={(e) => setStore(e.target.value)}
              className={inputClass}
              required
            />
          </Field>
          <Field label="Date">
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className={inputClass}
              required
            />
          </Field>
        </div>

        <Field label="Sub Category">
          <select
            value={subCategory}
            onChange={(e) => setSubCategory(e.target.value)}
            className={selectClass}
            required
          >
            <option value="" disabled>
              Select a category
            </option>
            {expenseCategories.map((c) => (
              <option key={`${c.mainCategory}-${c.subCategory}`} value={c.subCategory}>
                {c.mainCategory} — {c.subCategory}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Comment (optional)">
          <input
            type="text"
            placeholder="e.g. weekly groceries"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className={inputClass}
          />
        </Field>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium text-text-secondary">Payment sources</h4>
            <button
              type="button"
              onClick={() => setSources((prev) => [...prev, emptySource()])}
              className="text-sm text-accent hover:text-accent-hover cursor-pointer"
            >
              + Add source
            </button>
          </div>
          {sources.length === 0 ? (
            <p className="text-sm text-text-muted">
              Optional when the full amount is paid with giftcards.
            </p>
          ) : (
            <div className="space-y-2">
              {sources.map((s, i) => (
                <div
                  key={i}
                  className="grid grid-cols-1 min-[400px]:grid-cols-[1fr_7rem_auto] gap-2 items-stretch min-[400px]:items-end rounded-lg border border-bg-border/60 p-3 min-[400px]:border-0 min-[400px]:p-0"
                >
                  <Field label="Source">
                    <select
                      value={s.source}
                      onChange={(e) => updateSource(i, { source: e.target.value })}
                      className={selectClass}
                    >
                      <option value="" disabled>
                        Select source
                      </option>
                      {paymentSources.map((src) => (
                        <option key={src.name} value={src.name}>
                          {src.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Amount">
                    <input
                      type="number"
                      inputMode="decimal"
                      step="0.01"
                      min="0"
                      placeholder="0.00"
                      value={s.amount}
                      onChange={(e) => updateSource(i, { amount: e.target.value })}
                      className={inputClass}
                    />
                  </Field>
                  <button
                    type="button"
                    onClick={() => setSources((prev) => prev.filter((_, j) => j !== i))}
                    aria-label="Remove source"
                    className="inline-flex items-center justify-center min-h-11 min-w-11 self-end justify-self-end rounded-lg text-text-muted hover:text-expense hover:bg-expense/10 cursor-pointer"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium text-text-secondary">Giftcards</h4>
            <button
              type="button"
              onClick={() => setGiftcardPayments((prev) => [...prev, emptyGiftcardPayment()])}
              disabled={giftcards.length === 0}
              className="text-sm text-accent hover:text-accent-hover cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            >
              + Add giftcard
            </button>
          </div>
          {giftcards.length === 0 ? (
            <p className="text-sm text-text-muted">No giftcards with remaining balance.</p>
          ) : (
            <div className="space-y-2">
              {giftcardPayments.map((p, i) => {
                const selected = giftcards.find((g) => String(g.id) === String(p.giftcardId));
                const maxBalance = selected ? Number(selected.balance) || 0 : undefined;
                return (
                  <div
                    key={i}
                    className="grid grid-cols-1 min-[400px]:grid-cols-[1fr_7rem_auto] gap-2 items-stretch min-[400px]:items-end rounded-lg border border-bg-border/60 p-3 min-[400px]:border-0 min-[400px]:p-0"
                  >
                    <Field label="Giftcard">
                      <select
                        value={p.giftcardId}
                        onChange={(e) => updateGiftcardPayment(i, { giftcardId: e.target.value })}
                        className={selectClass}
                      >
                        <option value="" disabled>Select giftcard</option>
                        {giftcards.map((g) => (
                          <option key={g.id} value={g.id}>
                            {g.shop} — remaining {formatAUD(g.balance)}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Amount">
                      <input
                        type="number"
                        inputMode="decimal"
                        step="0.01"
                        min="0"
                        max={maxBalance || undefined}
                        placeholder="0.00"
                        value={p.amount}
                        onChange={(e) => updateGiftcardPayment(i, { amount: e.target.value })}
                        className={inputClass}
                      />
                    </Field>
                    <button
                      type="button"
                      onClick={() => setGiftcardPayments((prev) => prev.filter((_, j) => j !== i))}
                      aria-label="Remove giftcard"
                      className="inline-flex items-center justify-center min-h-11 min-w-11 self-end justify-self-end rounded-lg text-text-muted hover:text-expense hover:bg-expense/10 cursor-pointer"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium text-text-secondary">Items</h4>
            <button
              type="button"
              onClick={() => setItems((prev) => [...prev, emptyItem()])}
              className="text-sm text-accent hover:text-accent-hover cursor-pointer"
            >
              + Add item
            </button>
          </div>
          <div className="space-y-2">
            {items.map((it, i) => (
              <div
                key={i}
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
                    {UNITS.map((u) => (
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
                <button
                  type="button"
                  disabled={items.length === 1}
                  onClick={() => setItems((prev) => prev.filter((_, j) => j !== i))}
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
        </section>

        <div className="flex items-center justify-between px-1">
          <span className="text-sm text-text-secondary">Total from items</span>
          <span className="text-lg font-semibold text-text-primary tabular-nums">
            {formatAUD(itemsTotal)}
          </span>
        </div>

        {itemsTotal > 0 && !sourcesMatch && (
          <p className="text-sm text-expense">
            Payments ({formatAUD(fundingTotal)}) must equal items total ({formatAUD(itemsTotal)}).
          </p>
        )}

        {giftcardOverBalance && (
          <p className="text-sm text-expense">
            Giftcard {giftcardOverBalance.label} payment ({formatAUD(giftcardOverBalance.total)}) exceeds
            remaining balance ({formatAUD(giftcardOverBalance.balance)}).
          </p>
        )}

        <div className="flex flex-wrap items-center justify-end gap-2 pt-1 [&_button]:flex-1 sm:[&_button]:flex-none">
          <button type="button" onClick={() => onClose?.()} className={cancelClass}>
            Cancel
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            onClick={() => { closeAfterRef.current = false; }}
            className={submitClass}
          >
            {submitting ? 'Saving…' : 'Submit'}
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            onClick={() => { closeAfterRef.current = true; }}
            className={`${primaryClass} basis-full sm:basis-auto`}
          >
            {submitting ? 'Saving…' : 'Submit and Close'}
          </button>
        </div>

        {status && (
          <p className={`text-sm ${status.ok ? 'text-income' : 'text-expense'}`}>{status.msg}</p>
        )}
    </form>
  );
}
