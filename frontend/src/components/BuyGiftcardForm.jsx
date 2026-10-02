import { useMemo, useRef, useState } from 'react';
import { DecimalInput, Field, inputClass, selectClass } from './FormField';
import { buyGiftcard } from '../lib/api';
import { formatAUD, localDateIso } from '../lib/transform';

const cancelClass = 'btn-secondary';
const submitClass = 'btn-secondary';
const primaryClass = 'btn-primary';

function defaultIncomeSubCategory(categories) {
  const hasCashback = (categories || []).some(
    (c) => c.type === 'Income' && c.subCategory === 'Cashback'
  );
  return hasCashback ? 'Cashback' : '';
}

export default function BuyGiftcardForm({ metadata, balances, onSaved, onClose }) {
  const incomeCategories = useMemo(
    () => (metadata?.categories || []).filter((c) => c.type === 'Income'),
    [metadata?.categories]
  );
  const [shop, setShop] = useState('');
  const [date, setDate] = useState(localDateIso());
  const [balance, setBalance] = useState('');
  const [cashback, setCashback] = useState('');
  const [source, setSource] = useState('');
  const [subCategory, setSubCategory] = useState(() =>
    defaultIncomeSubCategory(metadata?.categories)
  );
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState(null);
  const closeAfterRef = useRef(false);

  const paymentSources = (metadata.sources || []).filter((s) => s.name !== 'Giftcard');

  const balanceNum = Number(balance);
  const cashbackNum = cashback === '' ? 0 : Number(cashback);
  const cashbackValid =
    cashback === '' ||
    (!Number.isNaN(cashbackNum) && cashbackNum >= 0 && cashbackNum <= balanceNum);
  const needsIncomeCategory = cashbackNum > 0;
  const spend =
    !Number.isNaN(balanceNum) && balanceNum > 0 && cashbackValid
      ? balanceNum - cashbackNum
      : null;

  const canSubmit =
    shop.trim() &&
    balance &&
    balanceNum > 0 &&
    source &&
    cashbackValid &&
    (!needsIncomeCategory || subCategory) &&
    !submitting;

  function resetForm() {
    setShop('');
    setDate(localDateIso());
    setBalance('');
    setCashback('');
    setSource('');
    setSubCategory(defaultIncomeSubCategory(metadata?.categories));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    const shouldClose = closeAfterRef.current;
    closeAfterRef.current = false;
    setSubmitting(true);
    setStatus(null);
    try {
      const payload = {
        shop: shop.trim(),
        date,
        balance,
        source,
        cashback: cashbackNum,
      };
      if (needsIncomeCategory) {
        payload.subCategory = subCategory;
      }
      await buyGiftcard(payload);
      setStatus({
        ok: true,
        msg: needsIncomeCategory
          ? 'Giftcard purchased with cashback redeemed.'
          : 'Giftcard purchased. Cash converted to store credit.',
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
    <form onSubmit={handleSubmit} className="space-y-4">
      <Field label="Shop">
        <input
          type="text"
          placeholder="e.g. Woolworths"
          value={shop}
          onChange={(e) => setShop(e.target.value)}
          className={inputClass}
          required
        />
      </Field>

      <Field label="Date">
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={inputClass} required />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Balance (AUD)">
          <DecimalInput
            placeholder="0.00"
            value={balance}
            onChange={(e) => setBalance(e.target.value)}
            className={inputClass}
            required
          />
        </Field>
        <Field label="Cashback (AUD)">
          <DecimalInput
            placeholder="0.00"
            value={cashback}
            onChange={(e) => setCashback(e.target.value)}
            className={inputClass}
          />
        </Field>
      </div>

      <Field label="Payment source">
        <select value={source} onChange={(e) => setSource(e.target.value)} className={selectClass} required>
          <option value="" disabled>Select a source</option>
          {paymentSources.map((s) => (
            <option key={s.name} value={s.name}>{s.name}</option>
          ))}
        </select>
        {source && (
          <p className="text-xs text-text-muted mt-1">Balance: {formatAUD(balances[source] || 0)}</p>
        )}
      </Field>

      <Field label="Income subcategory">
        <select
          value={subCategory}
          onChange={(e) => setSubCategory(e.target.value)}
          className={selectClass}
          required={needsIncomeCategory}
        >
          <option value="" disabled={needsIncomeCategory}>
            {needsIncomeCategory ? 'Select a category' : 'Optional'}
          </option>
          {incomeCategories.map((c) => (
            <option key={`${c.mainCategory}-${c.subCategory}`} value={c.subCategory}>
              {c.mainCategory} — {c.subCategory}
            </option>
          ))}
        </select>
      </Field>

      {spend != null && (
        <p className="text-sm text-text-secondary">
          Spend: {formatAUD(spend)}
          {cashbackNum > 0 ? ` (balance − cashback)` : ''}
        </p>
      )}

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
