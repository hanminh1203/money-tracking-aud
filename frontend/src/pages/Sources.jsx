import { useEffect, useMemo, useState } from 'react';
import Card from '../components/Card';
import PageHeader from '../components/PageHeader';
import SourceGrid from '../components/SourceGrid';
import TransactionList from '../components/TransactionList';
import { getTransactionData } from '../lib/api';
import { currentBalances, normalizeRows } from '../lib/transform';

export default function Sources({ transactions, metadata, listVersion }) {
  const balances = useMemo(() => currentBalances(transactions), [transactions]);
  const sourceTypes = useMemo(
    () => Object.fromEntries(metadata.sources.map((s) => [s.name, s.type])),
    [metadata.sources]
  );
  const [selected, setSelected] = useState(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(0);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!selected) {
      setRows([]);
      setTotal(0);
      setTotalPages(1);
      setPageSize(0);
      setPage(1);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getTransactionData({ page, source: selected });
        if (cancelled) return;
        setRows(normalizeRows(data.rows, metadata.categories, { sort: false }));
        setPageSize(data.pageSize);
        setTotal(data.total);
        setTotalPages(data.totalPages);
        if (data.page !== page) setPage(data.page);
      } catch (err) {
        if (!cancelled) setError(err.message || String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected, page, listVersion, metadata.categories]);

  function handleSelect(source) {
    setSelected(source);
    setPage(1);
  }

  return (
    <PageHeader
      title="Sources"
      description="Balances by account or wallet. Select one to browse its history."
    >
      <div className="space-y-5">

      <Card title="Balances by Source">
        <SourceGrid
          balances={balances}
          sourceTypes={sourceTypes}
          onSelect={handleSelect}
          selected={selected}
        />
      </Card>

      <Card title={selected ? `Transactions — ${selected}` : 'Select a source'}>
        {selected ? (
          <>
            {error && <div className="mb-3 text-sm text-expense">{error}</div>}
            <TransactionList
              transactions={rows}
              page={page}
              pageSize={pageSize}
              total={total}
              totalPages={totalPages}
              onPageChange={setPage}
              loading={loading}
            />
          </>
        ) : (
          <p className="text-text-muted text-sm py-10 text-center">
            Click a source above to see its history.
          </p>
        )}
      </Card>
    </div>
    </PageHeader>
  );
}
