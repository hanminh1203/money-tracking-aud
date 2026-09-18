import { useRef, useState } from 'react';
import { DecimalInput, Field, inputClass, selectClass } from './FormField';
import { addTransfer } from '../lib/api';
import { formatAUD } from '../lib/transform';

const todayISO = () => new Date().toISOString().slice(0, 10);

const cancelClass = 'btn-secondary';
const submitClass = 'btn-secondary';
const primaryClass = 'btn-primary';

export default function TransferForm({ metadata, balances, onSaved, onClose }) {
  const [date, setDate] = useState(todayISO());
  const [amount, setAmount] = useState('');
  const [fromSource, setFromSource] = useState('');
  const [toSource, setToSource] = useState('');
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState(null);
  const closeAfterRef = useRef(false);

  const canSubmit = amount && fromSource && toSource && fromSource !== toSource && !submitting;

  function resetForm() {
    setDate(todayISO());
    setAmount('');
    setFromSource('');
    setToSource('');
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
      await addTransfer({ date, amount, fromSource, toSource, comment });
      setStatus({ ok: true, msg: 'Transfer recorded (2 linked transactions).' });
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
      <div className="grid grid-cols-2 gap-3">
        <Field label="From">
          <select value={fromSource} onChange={(e) => setFromSource(e.target.value)} className={selectClass} required>
            <option value="" disabled>Select source</option>
            {metadata.sources.map((s) => (
              <option key={s.name} value={s.name}>{s.name}</option>
            ))}
          </select>
          {fromSource && (
            <p className="text-xs text-text-muted mt-1">Balance: {formatAUD(balances[fromSource] || 0)}</p>
          )}
        </Field>
        <Field label="To">
          <select value={toSource} onChange={(e) => setToSource(e.target.value)} className={selectClass} required>
            <option value="" disabled>Select source</option>
            {metadata.sources.filter((s) => s.name !== fromSource).map((s) => (
              <option key={s.name} value={s.name}>{s.name}</option>
            ))}
          </select>
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Date">
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={inputClass} required />
        </Field>
        <Field label="Amount (AUD)">
          <DecimalInput
            placeholder="0.00"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className={inputClass}
            required
          />
        </Field>
      </div>

      <Field label="Comment (optional)">
        <input
          type="text"
          placeholder="e.g. Move to savings"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          className={inputClass}
        />
      </Field>

      {fromSource && fromSource === toSource && (
        <p className="text-sm text-expense">Source and destination must differ.</p>
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

      {status && <p className={`text-sm ${status.ok ? 'text-income' : 'text-expense'}`}>{status.msg}</p>}
    </form>
  );
}
