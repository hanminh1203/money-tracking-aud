// Sheet values may arrive as native numbers/Dates (typical) or as formatted
// strings like "$1,540.00" / "-$10.00" (if the sheet has text formatting).
// These helpers normalize both.

export function parseAmount(val) {
  if (typeof val === 'number') return val;
  if (!val) return 0;
  const cleaned = String(val).replace(/[^0-9.\-]/g, '');
  const n = parseFloat(cleaned);
  return isNaN(n) ? 0 : n;
}

export function parseDate(val) {
  if (val instanceof Date) return val;
  if (typeof val === 'number') {
    // Google Sheets serial date (rare via Apps Script JSON, but handle it)
    return new Date(Math.round((val - 25569) * 86400 * 1000));
  }
  if (typeof val === 'string') {
    // dd/mm/yyyy
    const m = val.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (m) return new Date(+m[3], +m[2] - 1, +m[1]);
    const d = new Date(val);
    if (!isNaN(d)) return d;
  }
  return null;
}

export function monthKey(date) {
  if (!date) return 'Unknown';
  return `${date.getFullYear()}/${String(date.getMonth() + 1).padStart(2, '0')}`;
}

export function formatAUD(n) {
  const sign = n < 0 ? '-' : '';
  return `${sign}$${Math.abs(n).toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatDateShort(date) {
  if (!date) return '';
  return date.toLocaleDateString('en-AU', { day: '2-digit', month: 'short', year: 'numeric' });
}

/**
 * Normalizes raw transaction rows into a consistent shape.
 * Joins Main Category / Type from metadata categories by sub category.
 */
export function normalizeRows(rows, categories = [], { sort = true } = {}) {
  const bySub = new Map(
    (categories || []).map((c) => [String(c.subCategory || '').trim(), c])
  );
  const mapped = rows
    .map((r) => {
      const subCategory = String(r['Sub category'] || r['Sub Category'] || '').trim();
      const cat = bySub.get(subCategory);
      return {
        row: r.__row,
        date: parseDate(r['Date']),
        creationDate: parseDate(r['Creation Date'] || r.creationDate),
        change: parseAmount(r['Change']),
        source: String(r['Source'] || '').trim(),
        comment: String(r['Comment'] || '').trim(),
        subCategory,
        mainCategory: String(cat?.mainCategory || r['Main Category'] || '').trim(),
        type: String(cat?.type || r['Type'] || '').trim(),
        receiptId: String(r['Receipt ID'] || r.receiptId || '').trim() || null,
      };
    })
    .filter((r) => r.date && r.source);

  if (!sort) return mapped;
  return mapped.sort((a, b) => (a.date - b.date) || ((a.creationDate || 0) - (b.creationDate || 0)));
}

/** Running balance per source, keyed by source name -> current balance. */
export function currentBalances(transactions) {
  const balances = {};
  for (const t of transactions) {
    balances[t.source] = (balances[t.source] || 0) + t.change;
  }
  return balances;
}

/** Monthly income / expense / net, sorted chronologically. */
export function monthlySummary(transactions) {
  const map = new Map();
  for (const t of transactions) {
    const key = monthKey(t.date);
    if (!map.has(key)) map.set(key, { month: key, income: 0, expense: 0, net: 0 });
    const bucket = map.get(key);
    if (t.type === 'Income') bucket.income += t.change;
    else if (t.type === 'Expense') bucket.expense += t.change; // negative
    bucket.net += t.change;
  }
  return Array.from(map.values()).sort((a, b) => a.month.localeCompare(b.month));
}

/** Net worth trend: cumulative balance across ALL sources over time, one point per transaction date. */
export function netWorthTrend(transactions) {
  const points = [];
  let running = 0;
  for (const t of transactions) {
    running += t.change;
    points.push({ date: t.date, total: running });
  }
  // Collapse to one point per day (last value of the day)
  const byDay = new Map();
  for (const p of points) {
    const key = p.date.toISOString().slice(0, 10);
    byDay.set(key, p.total);
  }
  return Array.from(byDay.entries()).map(([date, total]) => ({ date, total }));
}

/** Newest date first; newest creation_date first when dates match. */
export function compareTransactionsDesc(a, b) {
  return (b.date - a.date) || ((b.creationDate || 0) - (a.creationDate || 0));
}
