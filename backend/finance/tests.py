from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from finance.db_reader import get_dashboard_data
from finance.db_sync import sync_from_sheets
from finance.models import Category, Giftcard, Source, Transaction, User


class DashboardDataTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email='dash@example.com')
        self.other = User.objects.create(email='other@example.com')
        self.source = Source.objects.create(name='Everyday', type='Bank')
        self.salary = Category.objects.create(
            main_category='Earnings',
            sub_category='Salary',
            type='Income',
        )
        self.groceries = Category.objects.create(
            main_category='Living',
            sub_category='Groceries',
            type='Expense',
        )
        self.rent = Category.objects.create(
            main_category='Living',
            sub_category='Rent',
            type='Expense',
        )

    def add_transaction(self, row, value, amount, category=None, comment='', user=None):
        return Transaction.objects.create(
            user=user or self.user,
            row_number=row,
            date=value,
            change=Decimal(amount),
            source=self.source,
            category=category,
            comment=comment,
        )

    @patch('finance.db_reader.timezone.localdate', return_value=date(2026, 1, 15))
    def test_dashboard_calculates_current_month_and_three_month_breakdowns(self, _localdate):
        self.add_transaction(1, date(2025, 9, 30), '100.00', self.salary)
        self.add_transaction(2, date(2025, 10, 10), '400.00', self.salary)
        self.add_transaction(3, date(2025, 11, 10), '-50.00', self.groceries)
        self.add_transaction(4, date(2025, 12, 10), '200.00', self.salary)
        self.add_transaction(5, date(2026, 1, 5), '1000.00', self.salary)
        self.add_transaction(6, date(2026, 1, 7), '-300.00', self.rent)
        self.add_transaction(7, date(2026, 1, 8), '-75.00', self.groceries)
        self.add_transaction(8, date(2026, 1, 9), '-25.00', None, 'Transfer')
        # Other user's data must not affect this dashboard.
        self.add_transaction(
            1, date(2026, 1, 5), '9999.00', self.salary, user=self.other
        )

        data = get_dashboard_data(user=self.user)

        self.assertEqual(data['months'], ['2025/11', '2025/12', '2026/01'])
        self.assertEqual(
            data['summary'],
            {
                'netWorth': 1250.0,
                'income': 1000.0,
                'expense': -375.0,
                'saving': 625.0,
            },
        )
        self.assertEqual(
            data['incomeBreakdown'],
            [{
                'subCategory': 'Salary',
                'amounts': {
                    '2025/11': 0.0,
                    '2025/12': 200.0,
                    '2026/01': 1000.0,
                },
            }],
        )
        self.assertEqual(
            data['expenseBreakdown'],
            [
                {
                    'subCategory': 'Groceries',
                    'amounts': {
                        '2025/11': -50.0,
                        '2025/12': 0.0,
                        '2026/01': -75.0,
                    },
                },
                {
                    'subCategory': 'Rent',
                    'amounts': {
                        '2025/11': 0.0,
                        '2025/12': 0.0,
                        '2026/01': -300.0,
                    },
                },
            ],
        )
        self.assertEqual(
            [transaction['date'] for transaction in data['transactions']],
            ['2026-01-09', '2026-01-08', '2026-01-07', '2026-01-05'],
        )
        self.assertEqual(data['transactions'][1]['subCategory'], 'Groceries')
        self.assertEqual(data['transactions'][1]['type'], 'Expense')

    @patch('finance.db_reader.timezone.localdate', return_value=date(2026, 1, 15))
    def test_dashboard_zero_fills_month_with_no_data(self, _localdate):
        data = get_dashboard_data(user=self.user)

        self.assertEqual(
            data['summary'],
            {'netWorth': 0.0, 'income': 0.0, 'expense': 0.0, 'saving': 0.0},
        )
        self.assertEqual(data['incomeBreakdown'], [])
        self.assertEqual(data['expenseBreakdown'], [])
        self.assertEqual(data['transactions'], [])


class DashboardApiTests(TestCase):
    def test_dashboard_requires_authentication(self):
        response = self.client.get('/api/dashboard')

        self.assertEqual(response.status_code, 401)

    @patch('finance.api_views.get_dashboard_data')
    @patch('finance.api_views.oauth.get_finance_user')
    @patch('finance.api_views.oauth.get_access_token', return_value='token')
    def test_dashboard_returns_backend_payload(self, _access_token, get_user, get_data):
        user = User.objects.create(email='api@example.com')
        get_user.return_value = user
        get_data.return_value = {
            'summary': {'netWorth': 10, 'income': 5, 'expense': -2, 'saving': 3},
            'months': [],
            'incomeBreakdown': [],
            'expenseBreakdown': [],
            'transactions': [],
        }

        response = self.client.get('/api/dashboard')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), get_data.return_value)
        get_data.assert_called_once_with(user=user)


class SyncIsolationTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create(email='a@example.com', sheet_id='sheet-a')
        self.user_b = User.objects.create(email='b@example.com', sheet_id='sheet-b')
        self.source = Source.objects.create(name='Everyday', type='Bank')
        self.salary = Category.objects.create(
            main_category='Earnings',
            sub_category='Salary',
            type='Income',
        )
        Transaction.objects.create(
            user=self.user_b,
            row_number=1,
            date=date(2026, 1, 1),
            change=Decimal('50.00'),
            source=self.source,
            category=self.salary,
        )
        Giftcard.objects.create(
            user=self.user_b,
            row_number=2,
            shop='Other Shop',
            date=date(2026, 1, 1),
            balance=Decimal('10.00'),
        )

    def test_sync_only_replaces_current_user_rows(self):
        client = MagicMock()
        client.get_mirror_source_rows.return_value = {
            'transactions': [
                {
                    '__sheet_row': 2,
                    'Date': '2026-01-10',
                    'Change': '100',
                    'Source': 'Everyday',
                    'Comment': 'Pay',
                    'Sub category': 'Salary',
                    'Receipt ID': '',
                    'Giftcard ID': '',
                }
            ],
            'receipts': [],
            'receipt_items': [],
            'giftcards': [],
        }

        result = sync_from_sheets(client, user=self.user_a)

        self.assertTrue(result['ok'])
        self.assertEqual(result['inserted']['transactions'], 1)
        self.assertEqual(Transaction.objects.filter(user=self.user_a).count(), 1)
        self.assertEqual(Transaction.objects.filter(user=self.user_b).count(), 1)
        self.assertEqual(Giftcard.objects.filter(user=self.user_b).count(), 1)
        self.assertEqual(Source.objects.count(), 1)
        self.assertEqual(Category.objects.count(), 1)
