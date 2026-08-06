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

export function formatAUD(n) {
  const sign = n < 0 ? '-' : '';
  return `${sign}$${Math.abs(n).toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatDateShort(date) {
  const d = date instanceof Date ? date : parseDate(date);
  if (!d) return '';
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  return `${dd}/${mm}/${d.getFullYear()}`;
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
        giftcardId: String(r['Giftcard ID'] || r.giftcardId || '').trim() || null,
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
