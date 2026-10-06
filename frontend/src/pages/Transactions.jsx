import { useEffect, useState } from 'react';
import Card from '../components/Card';
import Modal from '../components/Modal';
import PageHeader, { PageActions } from '../components/PageHeader';
import TransactionFilters from '../components/TransactionFilters';
import TransactionList from '../components/TransactionList';
import AddTransactionForm from '../components/AddTransactionForm';
import TransferForm from '../components/TransferForm';
import ReceiptForm from '../components/ReceiptForm';
import { deleteTransaction, getTransactionData } from '../lib/api';
import { normalizeRows } from '../lib/transform';

const LIST_DELETE_CONFIRM =
  'Delete this transaction? Payments, its receipt (if any), and product links will be removed. Giftcard spend will be credited back. The other side of a transfer is not deleted. This cannot be undone.';

const SEARCH_DEBOUNCE_MS = 300;

export default function Transactions({ metadata, balances, onSaved, listVersion }) {
  const [modal, setModal] = useState(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(0);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedCategories, setSelectedCategories] = useState([]);
  const [includeExchange, setIncludeExchange] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearch(search.trim());
      setPage(1);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getTransactionData({
          page,
          q: debouncedSearch || undefined,
          categories: selectedCategories.length ? selectedCategories : undefined,
          includeExchange,
        });
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
  }, [
    page,
    listVersion,
    metadata.categories,
    debouncedSearch,
    selectedCategories,
    includeExchange,
  ]);

  function handleCategoriesChange(next) {
    setSelectedCategories(next);
    setPage(1);
  }

  function handleIncludeExchangeChange(next) {
    setIncludeExchange(next);
    setPage(1);
  }

  function closeModal() {
    setModal(null);
  }

  async function handleDelete(transaction) {
    if (!transaction?.id) return;
    if (!window.confirm(LIST_DELETE_CONFIRM)) return;
    setDeletingId(transaction.id);
    setError(null);
    try {
      await deleteTransaction(transaction.id);
      onSaved?.();
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <PageHeader
      title="Transactions"
      description="Record spending, income, transfers, and receipts."
    >
      <div className="space-y-5">
      <PageActions>
        <button type="button" onClick={() => setModal('add')} className="btn-primary">
          Add Transaction
        </button>
        <button type="button" onClick={() => setModal('transfer')} className="btn-secondary">
          Transfers
        </button>
        <button type="button" onClick={() => setModal('receipt')} className="btn-secondary">
          Add Receipt
        </button>
      </PageActions>

      <Card title="All Transactions">
        {error && <div className="mb-3 text-sm text-expense">{error}</div>}
        <TransactionFilters
          search={search}
          onSearchChange={setSearch}
          categories={metadata.categories}
          selectedCategories={selectedCategories}
          onCategoriesChange={handleCategoriesChange}
          includeExchange={includeExchange}
          onIncludeExchangeChange={handleIncludeExchangeChange}
        />
        <TransactionList
          transactions={rows}
          page={page}
          pageSize={pageSize}
          total={total}
          totalPages={totalPages}
          onPageChange={setPage}
          loading={loading || Boolean(deletingId)}
          onDelete={handleDelete}
          deletingId={deletingId}
        />
      </Card>

      {modal === 'add' && (
        <Modal title="Add Transaction" onClose={closeModal} maxWidth="max-w-2xl">
          <AddTransactionForm key="add" metadata={metadata} onSaved={onSaved} onClose={closeModal} />
        </Modal>
      )}
      {modal === 'transfer' && (
        <Modal title="Transfer Between Sources" onClose={closeModal} maxWidth="max-w-lg">
          <TransferForm
            key="transfer"
            metadata={metadata}
            balances={balances}
            onSaved={onSaved}
            onClose={closeModal}
          />
        </Modal>
      )}
      {modal === 'receipt' && (
        <Modal title="Add Receipt" onClose={closeModal} maxWidth="max-w-2xl">
          <ReceiptForm key="receipt" metadata={metadata} onSaved={onSaved} onClose={closeModal} />
        </Modal>
      )}
    </div>
    </PageHeader>
  );
}
