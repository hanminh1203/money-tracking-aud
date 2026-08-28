import { useEffect, useRef, useState } from 'react';
import Card from './Card';
import PageHeader from './PageHeader';
import { inputClass } from './FormField';
import { parseFinanceMessage, addTransaction, addTransfer } from '../lib/api';
import { formatAUD, formatDateShort } from '../lib/transform';

const WELCOME = 'Tell me about a transaction or transfer — e.g. "Spent $45 on groceries at Woolworths from Commonwealth today" or "Transfer $200 from Commonwealth to ING Savings".';

export default function ChatBot({ metadata, onSaved }) {
  const [messages, setMessages] = useState([{ role: 'assistant', text: WELCOME }]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, busy]);

  async function handleSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;

    setMessages((m) => [...m, { role: 'user', text }]);
    setInput('');
    setBusy(true);

    try {
      const parsed = await parseFinanceMessage({ message: text, metadata });

      if (parsed.action === 'transaction') {
        const { date, amount, type, source, subCategory, comment } = parsed;
        if (!amount || !type || !source || !subCategory) {
          throw new Error('Could not extract amount, type, source, and category from that. Try being more specific.');
        }
        await addTransaction({ date, amount, type, source, subCategory, comment });
        onSaved?.();
        setMessages((m) => [
          ...m,
          {
            role: 'assistant',
            text: `Added ${type.toLowerCase()} of ${formatAUD(Math.abs(amount))} — "${source}" / ${subCategory}${
              comment ? ` ("${comment}")` : ''
            } on ${formatDateShort(date)}.`,
          },
        ]);
      } else if (parsed.action === 'transfer') {
        const { date, amount, fromSource, toSource, comment } = parsed;
        if (!amount || !fromSource || !toSource) {
          throw new Error('Could not extract amount, source, and destination for that transfer. Try being more specific.');
        }
        await addTransfer({ date, amount, fromSource, toSource, comment });
        onSaved?.();
        setMessages((m) => [
          ...m,
          {
            role: 'assistant',
            text: `Transferred ${formatAUD(amount)} from "${fromSource}" to "${toSource}" on ${formatDateShort(date)} (2 linked transactions recorded).`,
          },
        ]);
      } else {
        setMessages((m) => [
          ...m,
          {
            role: 'assistant',
            error: true,
            text: parsed.reason || "I couldn't understand that as a transaction or transfer. Include an amount, a source, and a category.",
          },
        ]);
      }
    } catch (err) {
      setMessages((m) => [...m, { role: 'assistant', error: true, text: err.message || String(err) }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageHeader
      title="Assistant"
      description="Describe a purchase or transfer in plain language and I will log it."
      fill
    >
      <Card title="Conversation" className="flex flex-col flex-1 min-h-0 max-w-2xl w-full overflow-hidden">
        <div className="flex-1 overflow-y-auto overscroll-contain scrollbar-thin space-y-3 pr-1 min-h-0">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[85%] px-3.5 py-2.5 rounded-xl text-sm whitespace-pre-wrap break-words ${
                  m.role === 'user'
                    ? 'bg-accent text-white'
                    : m.error
                      ? 'bg-expense/5 text-expense border border-expense/30'
                      : 'bg-bg-raised text-text-primary'
                }`}
              >
                {m.text}
              </div>
            </div>
          ))}
          {busy && (
            <div className="flex justify-start">
              <div className="max-w-[85%] px-3.5 py-2.5 rounded-xl text-sm bg-bg-raised text-text-muted">
                Thinking…
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <form onSubmit={handleSend} className="mt-4 shrink-0 flex flex-col min-[400px]:flex-row gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="e.g. Paid $32 for coffee with Cash yesterday"
            className={`${inputClass} flex-1 min-w-0`}
            disabled={busy}
          />
          <button type="submit" disabled={busy || !input.trim()} className="btn-primary shrink-0 w-full min-[400px]:w-auto">
            Send
          </button>
        </form>
      </Card>
    </PageHeader>
  );
}
