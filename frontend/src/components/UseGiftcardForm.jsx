import { useMemo, useRef, useState } from 'react';
import { DecimalInput, Field, inputClass, selectClass } from './FormField';
import { useGiftcard } from '../lib/api';
import { formatAUD } from '../lib/transform';

const cancelClass = 'btn-secondary';
const submitClass = 'btn-secondary';
const primaryClass = 'btn-primary';

export default function UseGiftcardForm({ giftcard, metadata, onSaved, onClose }) {
  const [amount, setAmount] = useState('');
  const [subCategory, setSubCategory] = useState('');
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState(null);
  const closeAfterRef = useRef(false);

  const categoryOptions = useMemo(
    () => (metadata?.categories || []).filter((c) => c.type === 'Expense'),
    [metadata?.categories]
  );

  const maxBalance = Number(giftcard?.balance) || 0;
  const canSubmit = amount && Number(amount) > 0 && subCategory && !submitting;

  function resetForm() {
    setAmount('');
    setSubCategory('');
    setComment('');
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    const shouldClose = closeAfterRef.current;
    closeAfterRef.current = false;
    setSubmitting(true);
    setStatus(null);
    try {
      await useGiftcard(giftcard.id, { amount, comment, subCategory });
      setStatus({ ok: true, msg: 'Giftcard use recorded.' });
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
    <form onSubmit={handleSubmit} className="space-y-4">
      <p className="text-sm text-text-secondary">
        {giftcard.shop} — remaining {formatAUD(maxBalance)}
      </p>

      <Field label="Amount (AUD)">
        <DecimalInput
          placeholder="0.00"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          className={inputClass}
          required
        />
      </Field>

      <Field label="Sub category">
        <select
          value={subCategory}
          onChange={(e) => setSubCategory(e.target.value)}
          className={selectClass}
          required
        >
          <option value="" disabled>Select a category</option>
          {categoryOptions.map((c) => (
            <option key={`${c.mainCategory}-${c.subCategory}`} value={c.subCategory}>
              {c.mainCategory} — {c.subCategory}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Comment (optional)">
        <input
          type="text"
          placeholder="e.g. Groceries"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          className={inputClass}
        />
      </Field>

      <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
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
          className={primaryClass}
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
