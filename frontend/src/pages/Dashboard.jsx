import { useEffect, useMemo, useState } from 'react';
import Card from '../components/Card';
import StatCard from '../components/StatCard';
import NetWorthChart from '../components/NetWorthChart';
import IncomeExpenseChart from '../components/IncomeExpenseChart';
import CategoryDoughnut from '../components/CategoryDoughnut';
import TransactionList from '../components/TransactionList';
import { getSpendingByCategory } from '../lib/api';
import { currentBalances, netWorthTrend, compareTransactionsDesc } from '../lib/transform';

export default function Dashboard({ transactions, monthlySummary, listVersion }) {
  const [monthFilter, setMonthFilter] = useState('all');
  const [breakdown, setBreakdown] = useState([]);
  const [breakdownLoading, setBreakdownLoading] = useState(false);
  const [breakdownError, setBreakdownError] = useState(null);

  const balances = useMemo(() => currentBalances(transactions), [transactions]);
  const netWorth = useMemo(() => Object.values(balances).reduce((s, b) => s + b, 0), [balances]);
  const trend = useMemo(() => netWorthTrend(transactions), [transactions]);
  const recent = useMemo(
    () => transactions.slice().sort(compareTransactionsDesc).slice(0, 8),
    [transactions],
  );

  useEffect(() => {
    if (!listVersion) return;
    const ac = new AbortController();
    setBreakdownLoading(true);
    setBreakdownError(null);
    getSpendingByCategory(monthFilter, { signal: ac.signal })
      .then((data) => {
        setBreakdown(Array.isArray(data) ? data : []);
      })
      .catch((err) => {
        if (err?.name === 'AbortError') return;
        setBreakdown([]);
        setBreakdownError(err.message || String(err));
      })
      .finally(() => {
        if (!ac.signal.aborted) setBreakdownLoading(false);
      });
    return () => ac.abort();
  }, [monthFilter, listVersion]);

  const latestMonth = monthlySummary[monthlySummary.length - 1];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard label="Net Worth" value={netWorth} tone="accent" sublabel="Across all sources" />
        <StatCard
          label="This Month Income"
          value={latestMonth?.income || 0}
          tone="income"
          sublabel={latestMonth?.month}
        />
        <StatCard
          label="This Month Expense"
          value={latestMonth?.expense || 0}
          tone="expense"
          sublabel={latestMonth?.month}
        />
      </div>

      <Card title="Net Worth Trend">
        <NetWorthChart points={trend} />
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Income vs Expense by Month">
          <IncomeExpenseChart months={monthlySummary} />
        </Card>

        <Card
          title="Spending by Category"
          action={
            <select
              value={monthFilter}
              onChange={(e) => setMonthFilter(e.target.value)}
              className="bg-bg-raised border border-bg-border rounded-lg px-2 py-1 text-xs text-text-secondary cursor-pointer"
            >
              <option value="all">All time</option>
              {monthlySummary.map((m) => (
                <option key={m.month} value={m.month}>{m.month}</option>
              ))}
            </select>
          }
        >
          {breakdownError ? (
            <div className="h-64 flex items-center justify-center text-expense text-sm">{breakdownError}</div>
          ) : breakdownLoading ? (
            <div className="h-64 flex items-center justify-center text-text-muted text-sm">Loading…</div>
          ) : (
            <CategoryDoughnut breakdown={breakdown} />
          )}
        </Card>
      </div>

      <Card title="Recent Transactions">
        <TransactionList transactions={recent} />
      </Card>
    </div>
  );
}
