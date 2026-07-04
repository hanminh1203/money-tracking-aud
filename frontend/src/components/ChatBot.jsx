import { useEffect, useRef, useState } from 'react';
import Card from './Card';
import { inputClass } from './FormField';
import { parseFinanceMessage } from '../lib/groqAgent';
import { addTransaction, addTransfer } from '../lib/sheetsApi';
import { formatAUD } from '../lib/transform';

const GROQ_API_KEY = import.meta.env.VITE_GROQ_API_KEY;
const GROQ_MODEL = import.meta.env.VITE_GROQ_MODEL || 'llama-3.3-70b-versatile';

const WELCOME = 'Tell me about a transaction or transfer — e.g. "Spent $45 on groceries at Woolworths from Commonwealth today" or "Transfer $200 from Commonwealth to ING Savings".';

export default function ChatBot({ metadata, token, onSaved }) {
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

    if (!GROQ_API_KEY) {
      setMessages((m) => [
        ...m,
        { role: 'user', text },
        { role: 'assistant', error: true, text: 'VITE_GROQ_API_KEY is not set. Add it to frontend/.env.' },
      ]);
      setInput('');
      return;
    }

    setMessages((m) => [...m, { role: 'user', text }]);
    setInput('');
    setBusy(true);

    try {
      const parsed = await parseFinanceMessage({ apiKey: GROQ_API_KEY, model: GROQ_MODEL, message: text, metadata });

      if (parsed.action === 'transaction') {
        const { date, amount, type, source, subCategory, comment } = parsed;
        if (!amount || !type || !source || !subCategory) {
          throw new Error('Could not extract amount, type, source, and category from that. Try being more specific.');
        }
        await addTransaction(token, { date, amount, type, source, subCategory, comment });
        onSaved?.();
        setMessages((m) => [
          ...m,
          {
            role: 'assistant',
            text: `✅ Added ${type.toLowerCase()} of ${formatAUD(Math.abs(amount))} — "${source}" / ${subCategory}${
              comment ? ` ("${comment}")` : ''
            } on ${date}.`,
          },
        ]);
      } else if (parsed.action === 'transfer') {
        const { date, amount, fromSource, toSource, comment } = parsed;
        if (!amount || !fromSource || !toSource) {
          throw new Error('Could not extract amount, source, and destination for that transfer. Try being more specific.');
        }
        await addTransfer(token, { date, amount, fromSource, toSource, comment });
        onSaved?.();
        setMessages((m) => [
          ...m,
          {
            role: 'assistant',
            text: `✅ Transferred ${formatAUD(amount)} from "${fromSource}" to "${toSource}" on ${date} (2 linked transactions recorded).`,
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
      setMessages((m) => [...m, { role: 'assistant', error: true, text: `❌ ${err.message || String(err)}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Finance Assistant" className="max-w-2xl mx-auto flex flex-col h-[70vh]">
      <div className="flex-1 overflow-y-auto scrollbar-thin space-y-3 pr-1">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] px-3.5 py-2.5 rounded-xl text-sm whitespace-pre-wrap ${
                m.role === 'user'
                  ? 'bg-accent text-white'
                  : m.error
                  ? 'bg-expense/10 text-expense border border-expense/30'
                  : 'bg-bg-raised text-text-primary'
              }`}
            >
              {m.text}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex justify-start">
            <div className="max-w-[85%] px-3.5 py-2.5 rounded-xl text-sm bg-bg-raised text-text-muted">Thinking…</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSend} className="mt-4 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. Paid $32 for coffee with Cash yesterday"
          className={inputClass + ' flex-1'}
          disabled={busy}
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="px-4 py-2.5 rounded-lg bg-accent hover:bg-accent-hover disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium transition-colors cursor-pointer"
        >
          Send
        </button>
      </form>
    </Card>
  );
}