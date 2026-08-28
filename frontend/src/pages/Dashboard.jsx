import Card from '../components/Card';
import StatCard from '../components/StatCard';
import PageHeader from '../components/PageHeader';
import CategoryBreakdownTable from '../components/CategoryBreakdownTable';
import TransactionList from '../components/TransactionList';

export default function Dashboard({ data }) {
  const { summary, months, incomeBreakdown, expenseBreakdown, transactions } = data;
  const currentMonth = months[months.length - 1];

  return (
    <PageHeader
      title="Overview"
      description={
        <>
          <span className="sm:hidden">Month totals, category trends, and recent activity.</span>
          <span className="hidden sm:inline">
            Current month totals, three-month category breakdowns, and this month&apos;s activity.
          </span>
        </>
      }
    >
      <div className="space-y-5 stagger-children">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        <StatCard
          label="Net Worth"
          value={summary.netWorth}
          tone="accent"
          sublabel="Across all sources"
        />
        <StatCard
          label="This Month Income"
          value={summary.income}
          tone="income"
          sublabel={currentMonth}
        />
        <StatCard
          label="This Month Expense"
          value={summary.expense}
          tone="expense"
          sublabel={currentMonth}
        />
        <StatCard
          label="This Month Saving"
          value={summary.saving}
          tone={summary.saving >= 0 ? 'income' : 'expense'}
          sublabel={currentMonth}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Income by Subcategory">
          <CategoryBreakdownTable
            months={months}
            rows={incomeBreakdown}
            emptyLabel="No income in the last three months"
          />
        </Card>

        <Card title="Expense by Subcategory">
          <CategoryBreakdownTable
            months={months}
            rows={expenseBreakdown}
            emptyLabel="No expenses in the last three months"
          />
        </Card>
      </div>

      <Card title="This Month Transactions">
        <TransactionList
          transactions={transactions}
          emptyLabel="No transactions this month"
        />
      </Card>
    </div>
    </PageHeader>
  );
}
