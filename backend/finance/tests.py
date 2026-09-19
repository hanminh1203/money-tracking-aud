from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal
import uuid
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from finance.db_reader import (
    ReaderError,
    get_dashboard_data,
    get_export_payload,
    get_metadata,
    get_product_detail,
    get_products,
    get_transaction,
)
from finance.db_sync import SyncError, compare_mirror, sync_from_sheets
from finance.db_writer import save_product_item, update_product_item
from finance.models import (
    Category,
    Giftcard,
    GiftcardPayment,
    Payment,
    Product,
    ProductItem,
    Receipt,
    ReceiptItem,
    Source,
    Transaction,
    User,
)
from finance.sheets_client import SheetsClient, SheetsError


def sheet_mirror(**overrides):
    """Minimal Sheets payload for sync/compare tests, including lookups."""
    payload = {
        'transactions': [],
        'receipts': [],
        'receipt_items': [],
        'giftcards': [],
        'products': [],
        'product_items': [],
        'payments': [],
        'giftcard_payments': [],
        'categories': [
            {
                'Main Category': 'Earnings',
                'Sub category': 'Salary',
                'Type': 'Income',
            }
        ],
        'sources': [{'Name': 'Everyday', 'Type': 'Bank'}],
    }
    payload.update(overrides)
    return payload


class DashboardDataTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email='dash@example.com')
        self.other = User.objects.create(email='other@example.com')
        self.source = Source.objects.create(user=self.user, name='Everyday', type='Bank')
        self.salary = Category.objects.create(
            user=self.user,
            main_category='Earnings',
            sub_category='Salary',
            type='Income',
        )
        self.groceries = Category.objects.create(
            user=self.user,
            main_category='Living',
            sub_category='Groceries',
            type='Expense',
        )
        self.rent = Category.objects.create(
            user=self.user,
            main_category='Living',
            sub_category='Rent',
            type='Expense',
        )

    def add_transaction(self, row, value, amount, category=None, comment='', user=None, source=None):
        owner = user or self.user
        src = source or self.source
        signed = Decimal(amount)
        tx = Transaction.objects.create(
            user=owner,
            row_number=row,
            date=value,
            change=signed,
            category=category,
            comment=comment,
        )
        Payment.objects.create(
            user=owner,
            transaction=tx,
            source=src,
            amount=abs(signed),
            row_number=row,
        )
        return tx

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
        other_source = Source.objects.create(user=self.other, name='Everyday', type='Bank')
        other_salary = Category.objects.create(
            user=self.other,
            main_category='Earnings',
            sub_category='Salary',
            type='Income',
        )
        self.add_transaction(
            1,
            date(2026, 1, 5),
            '9999.00',
            other_salary,
            user=self.other,
            source=other_source,
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

    @patch('finance.db_reader.timezone.localdate', return_value=date(2026, 1, 15))
    def test_giftcard_buy_then_use_counts_net_worth_and_spend_once(self, _localdate):
        exchange = Category.objects.create(
            user=self.user,
            main_category='Transfer',
            sub_category='Exchange (self)',
            type='',
        )
        self.add_transaction(1, date(2026, 1, 2), '100.00', self.salary)

        buy = Transaction.objects.create(
            user=self.user,
            row_number=2,
            date=date(2026, 1, 5),
            change=Decimal('-20.00'),
            category=exchange,
            comment='Buy giftcard: Coles',
        )
        Payment.objects.create(
            user=self.user,
            transaction=buy,
            source=self.source,
            amount=Decimal('20.00'),
            row_number=2,
        )
        card = Giftcard.objects.create(
            user=self.user,
            row_number=1,
            shop='Coles',
            date=date(2026, 1, 5),
            balance=Decimal('20.00'),
        )

        after_buy = get_dashboard_data(user=self.user)
        self.assertEqual(after_buy['summary']['netWorth'], 100.0)
        self.assertEqual(after_buy['summary']['income'], 100.0)
        self.assertEqual(after_buy['summary']['expense'], 0.0)
        self.assertEqual(after_buy['summary']['saving'], 100.0)
        self.assertEqual(
            [row['subCategory'] for row in after_buy['expenseBreakdown']],
            [],
        )

        use = Transaction.objects.create(
            user=self.user,
            row_number=3,
            date=date(2026, 1, 10),
            change=Decimal('-20.00'),
            category=self.groceries,
            comment='Use giftcard: Coles',
        )
        GiftcardPayment.objects.create(
            user=self.user,
            transaction=use,
            giftcard=card,
            amount=Decimal('20.00'),
            row_number=1,
        )
        card.balance = Decimal('0.00')
        card.save(update_fields=['balance'])

        after_use = get_dashboard_data(user=self.user)
        self.assertEqual(after_use['summary']['netWorth'], 80.0)
        self.assertEqual(after_use['summary']['income'], 100.0)
        self.assertEqual(after_use['summary']['expense'], -20.0)
        self.assertEqual(after_use['summary']['saving'], 80.0)
        self.assertEqual(
            after_use['expenseBreakdown'],
            [
                {
                    'subCategory': 'Groceries',
                    'amounts': {
                        '2025/11': 0.0,
                        '2025/12': 0.0,
                        '2026/01': -20.0,
                    },
                }
            ],
        )

    @patch('finance.db_reader.timezone.localdate', return_value=date(2026, 1, 15))
    def test_mixed_cash_and_giftcard_spend_counts_once(self, _localdate):
        exchange = Category.objects.create(
            user=self.user,
            main_category='Transfer',
            sub_category='Exchange (self)',
            type='',
        )
        self.add_transaction(1, date(2026, 1, 2), '100.00', self.salary)
        buy = Transaction.objects.create(
            user=self.user,
            row_number=2,
            date=date(2026, 1, 5),
            change=Decimal('-20.00'),
            category=exchange,
            comment='Buy giftcard: Coles',
        )
        Payment.objects.create(
            user=self.user,
            transaction=buy,
            source=self.source,
            amount=Decimal('20.00'),
            row_number=2,
        )
        card = Giftcard.objects.create(
            user=self.user,
            row_number=1,
            shop='Coles',
            date=date(2026, 1, 5),
            balance=Decimal('20.00'),
        )

        spend = Transaction.objects.create(
            user=self.user,
            row_number=3,
            date=date(2026, 1, 12),
            change=Decimal('-50.00'),
            category=self.groceries,
            comment='Weekly shop',
        )
        Payment.objects.create(
            user=self.user,
            transaction=spend,
            source=self.source,
            amount=Decimal('30.00'),
            row_number=3,
        )
        GiftcardPayment.objects.create(
            user=self.user,
            transaction=spend,
            giftcard=card,
            amount=Decimal('20.00'),
            row_number=2,
        )
        card.balance = Decimal('0.00')
        card.save(update_fields=['balance'])

        data = get_dashboard_data(user=self.user)
        self.assertEqual(data['summary']['netWorth'], 50.0)
        self.assertEqual(data['summary']['expense'], -50.0)

    def test_source_history_excludes_giftcard_only_shop_name(self):
        from finance.db_reader import get_transaction_data

        self.add_transaction(1, date(2026, 1, 2), '40.00', self.salary)
        card = Giftcard.objects.create(
            user=self.user,
            row_number=1,
            shop='Everyday',
            date=date(2026, 1, 3),
            balance=Decimal('0.00'),
        )
        use = Transaction.objects.create(
            user=self.user,
            row_number=2,
            date=date(2026, 1, 4),
            change=Decimal('-15.00'),
            category=self.groceries,
            comment='Use giftcard: Everyday',
        )
        GiftcardPayment.objects.create(
            user=self.user,
            transaction=use,
            giftcard=card,
            amount=Decimal('15.00'),
            row_number=1,
        )

        data = get_transaction_data(user=self.user, source='Everyday')
        self.assertEqual(len(data['rows']), 1)
        self.assertEqual(data['rows'][0]['Change'], 40.0)


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


class MetadataIsolationTests(TestCase):
    def test_get_metadata_only_returns_current_user_rows(self):
        user = User.objects.create(email='meta@example.com')
        other = User.objects.create(email='other-meta@example.com')
        Source.objects.create(user=user, name='Mine', type='Bank')
        Source.objects.create(user=other, name='Theirs', type='Bank')
        Category.objects.create(
            user=user,
            main_category='Living',
            sub_category='Groceries',
            type='Expense',
        )
        Category.objects.create(
            user=other,
            main_category='Living',
            sub_category='Rent',
            type='Expense',
        )

        data = get_metadata(user=user)

        self.assertEqual([s['name'] for s in data['sources']], ['Mine'])
        self.assertEqual([c['subCategory'] for c in data['categories']], ['Groceries'])

    @patch('finance.api_views.oauth.get_finance_user')
    @patch('finance.api_views.oauth.get_access_token', return_value='token')
    def test_metadata_api_returns_current_user_rows(self, _access_token, get_user):
        user = User.objects.create(email='meta-api@example.com')
        other = User.objects.create(email='other-meta-api@example.com')
        get_user.return_value = user
        Source.objects.create(user=user, name='Mine', type='Cash')
        Source.objects.create(user=other, name='Theirs', type='Cash')

        response = self.client.get('/api/metadata')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['sources'], [{'name': 'Mine', 'type': 'Cash'}])
        self.assertEqual(response.json()['categories'], [])


class SyncIsolationTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create(email='a@example.com', sheet_id='sheet-a')
        self.user_b = User.objects.create(email='b@example.com', sheet_id='sheet-b')
        self.source = Source.objects.create(user=self.user_b, name='Everyday', type='Bank')
        self.salary = Category.objects.create(
            user=self.user_b,
            main_category='Earnings',
            sub_category='Salary',
            type='Income',
        )
        tx_b = Transaction.objects.create(
            user=self.user_b,
            row_number=1,
            date=date(2026, 1, 1),
            change=Decimal('50.00'),
            category=self.salary,
        )
        Payment.objects.create(
            user=self.user_b,
            transaction=tx_b,
            source=self.source,
            amount=Decimal('50.00'),
            row_number=1,
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
        client.get_mirror_source_rows.return_value = sheet_mirror(
            transactions=[
                {
                    '__sheet_row': 2,
                    'Transaction ID': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                    'Date': '2026-01-10',
                    'Change': '100',
                    'Comment': 'Pay',
                    'Sub category': 'Salary',
                }
            ],
            payments=[
                {
                    '__sheet_row': 3,
                    'Payment ID': 'e5f6a7b8-c9d0-1234-ef01-234567890abc',
                    'Transaction ID': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                    'Source': 'Everyday',
                    'Amount': '100',
                }
            ],
            giftcard_payments=[],
        )

        result = sync_from_sheets(client, user=self.user_a)

        self.assertTrue(result['ok'])
        self.assertEqual(result['inserted']['transactions'], 1)
        self.assertEqual(result['inserted']['sources'], 1)
        self.assertEqual(result['inserted']['category'], 1)
        self.assertEqual(Transaction.objects.filter(user=self.user_a).count(), 1)
        self.assertEqual(Transaction.objects.filter(user=self.user_b).count(), 1)
        self.assertEqual(Giftcard.objects.filter(user=self.user_b).count(), 1)
        self.assertEqual(Source.objects.filter(user=self.user_a).count(), 1)
        self.assertEqual(Source.objects.filter(user=self.user_b).count(), 1)
        self.assertEqual(Category.objects.filter(user=self.user_a).count(), 1)
        self.assertEqual(Category.objects.filter(user=self.user_b).count(), 1)
        synced = Transaction.objects.get(user=self.user_a)
        self.assertEqual(
            str(synced.id), 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        )
        payment = Payment.objects.get(transaction=synced)
        self.assertEqual(payment.source.user_id, self.user_a.id)
        self.assertEqual(synced.category.user_id, self.user_a.id)

    def test_sync_replaces_current_user_sources_and_categories(self):
        Source.objects.create(user=self.user_a, name='Old Source', type='Bank')
        Category.objects.create(
            user=self.user_a,
            main_category='Old',
            sub_category='Stale',
            type='Expense',
        )
        client = MagicMock()
        client.get_mirror_source_rows.return_value = sheet_mirror()

        result = sync_from_sheets(client, user=self.user_a)

        self.assertTrue(result['ok'])
        self.assertFalse(Source.objects.filter(user=self.user_a, name='Old Source').exists())
        self.assertTrue(Source.objects.filter(user=self.user_a, name='Everyday').exists())
        self.assertFalse(
            Category.objects.filter(user=self.user_a, sub_category='Stale').exists()
        )
        self.assertTrue(
            Category.objects.filter(user=self.user_a, sub_category='Salary').exists()
        )
        self.assertTrue(Source.objects.filter(user=self.user_b, name='Everyday').exists())
        self.assertTrue(
            Category.objects.filter(user=self.user_b, sub_category='Salary').exists()
        )

    def test_sync_product_item_links_by_transaction_id(self):
        tx_id = uuid.UUID('b2c3d4e5-f6a7-8901-bcde-f12345678901')
        product_id = uuid.UUID('c3d4e5f6-a7b8-9012-cdef-123456789012')
        product_item_id = uuid.UUID('d4e5f6a7-b8c9-0123-def0-234567890123')
        client = MagicMock()
        client.get_mirror_source_rows.return_value = sheet_mirror(
            transactions=[
                {
                    '__sheet_row': 2,
                    'Transaction ID': str(tx_id),
                    'Date': '2026-01-10',
                    'Change': '-25',
                    'Comment': 'Shop',
                    'Sub category': 'Salary',
                }
            ],
            payments=[
                {
                    '__sheet_row': 3,
                    'Payment ID': 'f6a7b8c9-d0e1-2345-f012-345678901bcd',
                    'Transaction ID': str(tx_id),
                    'Source': 'Everyday',
                    'Amount': '25',
                }
            ],
            giftcard_payments=[],
            products=[
                {'Product ID': str(product_id), 'Name': 'Milk'},
            ],
            product_items=[
                {
                    'Product Item ID': str(product_item_id),
                    'Product ID': str(product_id),
                    'Price': '12.50',
                    'Transaction ID': str(tx_id),
                    'Receipt Item ID': '',
                }
            ],
        )

        result = sync_from_sheets(client, user=self.user_a)

        self.assertTrue(result['ok'])
        pi = ProductItem.objects.get(user=self.user_a, id=product_item_id)
        self.assertEqual(pi.transaction_id, tx_id)
        self.assertEqual(pi.price, Decimal('12.50'))
        self.assertIsNone(pi.end_date)

    def test_sync_product_item_with_and_without_end_date(self):
        tx_id = uuid.UUID('b2c3d4e5-f6a7-8901-bcde-f12345678901')
        product_id = uuid.UUID('c3d4e5f6-a7b8-9012-cdef-123456789012')
        with_end_id = uuid.UUID('d4e5f6a7-b8c9-0123-def0-234567890123')
        without_end_id = uuid.UUID('e5f6a7b8-c9d0-1234-ef01-345678901234')
        tx2_id = uuid.UUID('f6a7b8c9-d0e1-2345-f012-456789012345')
        source = sheet_mirror(
            transactions=[
                {
                    '__sheet_row': 2,
                    'Transaction ID': str(tx_id),
                    'Date': '2026-01-10',
                    'Change': '-25',
                    'Source': 'Everyday',
                    'Comment': 'Shop',
                    'Sub category': 'Salary',
                    'Receipt ID': '',
                    'Giftcard ID': '',
                },
                {
                    '__sheet_row': 3,
                    'Transaction ID': str(tx2_id),
                    'Date': '2026-01-20',
                    'Change': '-8',
                    'Source': 'Everyday',
                    'Comment': 'Shop',
                    'Sub category': 'Salary',
                    'Receipt ID': '',
                    'Giftcard ID': '',
                },
            ],
            payments=[
                {
                    '__sheet_row': 2,
                    'Payment ID': 'a1a1a1a1-b2b2-c3c3-d4d4-e5e5e5e5e5e5',
                    'Transaction ID': str(tx_id),
                    'Source': 'Everyday',
                    'Amount': '25',
                },
                {
                    '__sheet_row': 3,
                    'Payment ID': 'b2b2b2b2-c3c3-d4d4-e5e5-f6f6f6f6f6f6',
                    'Transaction ID': str(tx2_id),
                    'Source': 'Everyday',
                    'Amount': '8',
                },
            ],
            products=[
                {'Product ID': str(product_id), 'Name': 'Milk'},
            ],
            product_items=[
                {
                    'Product Item ID': str(with_end_id),
                    'Product ID': str(product_id),
                    'Price': '12.50',
                    'Transaction ID': str(tx_id),
                    'Receipt Item ID': '',
                    'End Date': '15/03/2026',
                },
                {
                    'Product Item ID': str(without_end_id),
                    'Product ID': str(product_id),
                    'Price': '8.00',
                    'Transaction ID': str(tx2_id),
                    'Receipt Item ID': '',
                    'End Date': '',
                },
            ],
        )
        client = MagicMock()
        client.get_mirror_source_rows.return_value = source

        result = sync_from_sheets(client, user=self.user_a)

        self.assertTrue(result['ok'])
        with_end = ProductItem.objects.get(user=self.user_a, id=with_end_id)
        without_end = ProductItem.objects.get(user=self.user_a, id=without_end_id)
        self.assertEqual(with_end.end_date, date(2026, 3, 15))
        self.assertIsNone(without_end.end_date)

        comparison = compare_mirror(client, user=self.user_a)
        self.assertTrue(comparison['matched'])
        self.assertTrue(comparison['tables']['product_items']['matched'])
        self.assertTrue(comparison['tables']['category']['matched'])
        self.assertTrue(comparison['tables']['sources']['matched'])

        without_end.end_date = date(2026, 4, 1)
        without_end.save(update_fields=['end_date'])
        drifted = compare_mirror(client, user=self.user_a)
        self.assertFalse(drifted['matched'])
        self.assertFalse(drifted['tables']['product_items']['matched'])

    def test_sync_rejects_invalid_end_date(self):
        tx_id = uuid.UUID('b2c3d4e5-f6a7-8901-bcde-f12345678901')
        product_id = uuid.UUID('c3d4e5f6-a7b8-9012-cdef-123456789012')
        product_item_id = uuid.UUID('d4e5f6a7-b8c9-0123-def0-234567890123')
        client = MagicMock()
        client.get_mirror_source_rows.return_value = sheet_mirror(
            transactions=[
                {
                    '__sheet_row': 2,
                    'Transaction ID': str(tx_id),
                    'Date': '2026-01-10',
                    'Change': '-25',
                    'Source': 'Everyday',
                    'Comment': 'Shop',
                    'Sub category': 'Salary',
                    'Receipt ID': '',
                    'Giftcard ID': '',
                }
            ],
            payments=[
                {
                    '__sheet_row': 2,
                    'Payment ID': 'c3c3c3c3-d4d4-e5e5-f6f6-a7a7a7a7a7a7',
                    'Transaction ID': str(tx_id),
                    'Source': 'Everyday',
                    'Amount': '25',
                }
            ],
            products=[
                {'Product ID': str(product_id), 'Name': 'Milk'},
            ],
            product_items=[
                {
                    'Product Item ID': str(product_item_id),
                    'Product ID': str(product_id),
                    'Price': '12.50',
                    'Transaction ID': str(tx_id),
                    'Receipt Item ID': '',
                    'End Date': 'not-a-date',
                }
            ],
        )
        with self.assertRaises(SyncError) as ctx:
            sync_from_sheets(client, user=self.user_a)
        self.assertIn('Invalid date', str(ctx.exception))


class TransactionDetailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email='detail@example.com')
        self.other = User.objects.create(email='other-detail@example.com')
        self.source = Source.objects.create(user=self.user, name='Everyday', type='Bank')
        self.groceries = Category.objects.create(
            user=self.user,
            main_category='Living',
            sub_category='Groceries',
            type='Expense',
        )

    def add_transaction(self, **kwargs):
        source = kwargs.pop('source', self.source)
        defaults = {
            'user': self.user,
            'row_number': 1,
            'date': date(2026, 1, 8),
            'change': Decimal('-42.50'),
            'category': self.groceries,
            'comment': 'Woolworths : weekly shop',
        }
        defaults.update(kwargs)
        tx = Transaction.objects.create(**defaults)
        Payment.objects.create(
            user=tx.user,
            transaction=tx,
            source=source,
            amount=abs(tx.change),
            row_number=tx.row_number,
        )
        return tx

    def test_get_transaction_without_receipt(self):
        tx = self.add_transaction()

        data = get_transaction(user=self.user, transaction_id=str(tx.id))

        self.assertEqual(data['id'], str(tx.id))
        self.assertEqual(data['date'], '2026-01-08')
        self.assertEqual(data['change'], -42.5)
        self.assertEqual(data['source'], 'Everyday')
        self.assertEqual(data['subCategory'], 'Groceries')
        self.assertEqual(data['mainCategory'], 'Living')
        self.assertEqual(data['type'], 'Expense')
        self.assertEqual(data['comment'], 'Woolworths : weekly shop')
        self.assertIsNone(data['receiptId'])
        self.assertIsNone(data['receipt'])

    def test_get_transaction_with_receipt_items(self):
        tx = self.add_transaction()
        receipt = Receipt.objects.create(
            user=self.user,
            transaction=tx,
            date=date(2026, 1, 8),
            total=Decimal('12.50'),
        )
        milk = ReceiptItem.objects.create(
            user=self.user,
            receipt=receipt,
            name='Milk',
            amount=Decimal('2'),
            unit='L',
            money=Decimal('4.50'),
        )
        bread = ReceiptItem.objects.create(
            user=self.user,
            receipt=receipt,
            name='Bread',
            amount=Decimal('1'),
            unit='loaf',
            money=Decimal('8.00'),
        )

        data = get_transaction(user=self.user, transaction_id=str(tx.id))

        self.assertEqual(data['receiptId'], str(receipt.id))
        self.assertEqual(data['receipt']['receiptId'], str(receipt.id))
        self.assertEqual(data['receipt']['total'], 12.5)
        self.assertEqual(
            data['receipt']['items'],
            [
                {
                    'id': str(milk.id),
                    'name': 'Milk',
                    'amount': 2.0,
                    'unit': 'L',
                    'money': 4.5,
                },
                {
                    'id': str(bread.id),
                    'name': 'Bread',
                    'amount': 1.0,
                    'unit': 'loaf',
                    'money': 8.0,
                },
            ],
        )

    def test_get_transaction_not_found(self):
        with self.assertRaises(ReaderError) as ctx:
            get_transaction(
                user=self.user,
                transaction_id='00000000-0000-0000-0000-000000000001',
            )
        self.assertEqual(ctx.exception.status, 404)

    def test_get_transaction_hides_other_user_rows(self):
        tx = self.add_transaction(user=self.other, row_number=2)

        with self.assertRaises(ReaderError) as ctx:
            get_transaction(user=self.user, transaction_id=str(tx.id))
        self.assertEqual(ctx.exception.status, 404)

    def test_get_transaction_invalid_uuid(self):
        with self.assertRaises(ReaderError) as ctx:
            get_transaction(user=self.user, transaction_id='not-a-uuid')
        self.assertEqual(ctx.exception.status, 404)

    def test_get_transaction_requires_id(self):
        with self.assertRaises(ReaderError) as ctx:
            get_transaction(user=self.user, transaction_id='  ')
        self.assertEqual(ctx.exception.status, 400)

    def test_detail_api_requires_authentication(self):
        response = self.client.get(
            '/api/transactions/00000000-0000-0000-0000-000000000001'
        )
        self.assertEqual(response.status_code, 401)

    @patch('finance.api_views.oauth.get_finance_user')
    @patch('finance.api_views.oauth.get_access_token', return_value='token')
    def test_detail_api_returns_payload(self, _access_token, get_user):
        get_user.return_value = self.user
        tx = self.add_transaction()

        response = self.client.get(f'/api/transactions/{tx.id}')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['id'], str(tx.id))
        self.assertEqual(payload['source'], 'Everyday')
        self.assertIsNone(payload['receipt'])

    @patch('finance.api_views.oauth.get_finance_user')
    @patch('finance.api_views.oauth.get_access_token', return_value='token')
    def test_detail_api_returns_404_for_missing(self, _access_token, get_user):
        get_user.return_value = self.user

        response = self.client.get(
            '/api/transactions/00000000-0000-0000-0000-000000000001'
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error'], 'Transaction not found')

    def test_update_transaction_detail_without_receipt(self):
        from finance.db_writer import update_transaction_detail

        tx = self.add_transaction()
        salary = Category.objects.create(
            user=self.user,
            main_category='Earnings',
            sub_category='Salary',
            type='Income',
        )
        savings = Source.objects.create(user=self.user, name='Savings', type='Bank')

        update_transaction_detail(
            user=self.user,
            transaction=tx,
            date='2026-02-01',
            change='150.00',
            comment='Pay',
            sub_category='Salary',
            payments=[{'source': 'Savings', 'amount': '150.00', 'row_number': 2}],
        )

        tx.refresh_from_db()
        self.assertEqual(tx.date, date(2026, 2, 1))
        self.assertEqual(tx.change, Decimal('150.00'))
        payment = Payment.objects.get(transaction=tx)
        self.assertEqual(payment.source_id, savings.id)
        self.assertEqual(payment.amount, Decimal('150.00'))
        self.assertEqual(tx.comment, 'Pay')
        self.assertEqual(tx.category_id, salary.id)
        self.assertEqual(tx.version, 2)

    def test_update_transaction_detail_replaces_receipt_items(self):
        from finance.db_writer import update_transaction_detail

        tx = self.add_transaction()
        receipt = Receipt.objects.create(
            user=self.user,
            transaction=tx,
            date=date(2026, 1, 8),
            total=Decimal('12.50'),
        )
        ReceiptItem.objects.create(
            user=self.user,
            receipt=receipt,
            name='Milk',
            amount=Decimal('2'),
            unit='L',
            money=Decimal('4.50'),
        )

        update_transaction_detail(
            user=self.user,
            transaction=tx,
            date='2026-01-09',
            change='-10.00',
            comment='Coles : restock',
            sub_category='Groceries',
            payments=[{'source': 'Everyday', 'amount': '10.00', 'row_number': 1}],
            receipt_total='10.00',
            items=[
                {'name': 'Eggs', 'amount': 12, 'unit': 'piece', 'money': 10},
            ],
        )

        tx.refresh_from_db()
        receipt.refresh_from_db()
        items = list(receipt.items.order_by('name'))
        self.assertEqual(tx.date, date(2026, 1, 9))
        self.assertEqual(tx.change, Decimal('-10.00'))
        self.assertEqual(tx.comment, 'Coles : restock')
        self.assertEqual(receipt.date, date(2026, 1, 9))
        self.assertEqual(receipt.total, Decimal('10.00'))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, 'Eggs')
        self.assertEqual(items[0].money, Decimal('10'))

    @patch('finance.api_views.sheets_for')
    @patch('finance.api_views.oauth.get_finance_user')
    @patch('finance.api_views.oauth.get_access_token', return_value='token')
    def test_detail_api_put_updates_transaction(self, _access_token, get_user, sheets_for):
        get_user.return_value = self.user
        tx = self.add_transaction()
        client = MagicMock()
        client.update_transaction.return_value = {
            'id': str(tx.id),
            'updated': 1,
            'receiptUpdated': False,
            'items': 0,
        }
        sheets_for.return_value = client

        response = self.client.put(
            f'/api/transactions/{tx.id}',
            data={
                'date': '2026-02-01',
                'amount': 20,
                'type': 'Expense',
                'source': 'Everyday',
                'subCategory': 'Groceries',
                'comment': 'Updated',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        client.update_transaction.assert_called_once()
        kwargs = client.update_transaction.call_args.kwargs
        self.assertEqual(kwargs['date'], '2026-02-01')
        self.assertEqual(kwargs['amount'], 20)
        self.assertEqual(kwargs['comment'], 'Updated')
        self.assertIsNone(kwargs['items'])

    def test_detail_api_put_requires_authentication(self):
        response = self.client.put(
            '/api/transactions/00000000-0000-0000-0000-000000000001',
            data={},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)

    def test_update_requires_items_when_receipt_linked(self):
        tx = self.add_transaction()
        Receipt.objects.create(
            user=self.user,
            transaction=tx,
            date=date(2026, 1, 8),
            total=Decimal('12.50'),
        )
        client = SheetsClient('token', 'sheet-id', user=self.user)

        with self.assertRaises(SheetsError) as ctx:
            client.update_transaction(
                str(tx.id),
                date='2026-01-08',
                amount=12.5,
                type='Expense',
                source='Everyday',
                sub_category='Groceries',
                comment='Woolworths : weekly shop',
            )
        self.assertIn('items are required', str(ctx.exception))

    def test_update_rejects_item_total_mismatch(self):
        tx = self.add_transaction()
        Receipt.objects.create(
            user=self.user,
            transaction=tx,
            date=date(2026, 1, 8),
            total=Decimal('12.50'),
        )
        client = SheetsClient('token', 'sheet-id', user=self.user)

        with self.assertRaises(SheetsError) as ctx:
            client.update_transaction(
                str(tx.id),
                date='2026-01-08',
                amount=12.5,
                type='Expense',
                source='Everyday',
                sub_category='Groceries',
                comment='Woolworths : weekly shop',
                items=[{'name': 'Milk', 'amount': 1, 'unit': 'L', 'money': 4.5}],
            )
        self.assertIn('must equal', str(ctx.exception))

    def test_update_rejects_items_when_not_receipt_linked(self):
        tx = self.add_transaction()
        client = SheetsClient('token', 'sheet-id', user=self.user)

        with self.assertRaises(SheetsError) as ctx:
            client.update_transaction(
                str(tx.id),
                date='2026-01-08',
                amount=12.5,
                type='Expense',
                source='Everyday',
                sub_category='Groceries',
                comment='Note',
                items=[{'name': 'Milk', 'amount': 1, 'unit': 'L', 'money': 12.5}],
            )
        self.assertIn('not linked to a receipt', str(ctx.exception))


class ProductTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email='products@example.com')
        self.source = Source.objects.create(user=self.user, name='Everyday', type='Bank')
        self.groceries = Category.objects.create(
            user=self.user,
            main_category='Living',
            sub_category='Groceries',
            type='Expense',
        )
        self.product = Product.objects.create(user=self.user, name='Toothpaste')

    def add_transaction(self, row, value, amount, comment=''):
        tx = Transaction.objects.create(
            user=self.user,
            row_number=row,
            date=value,
            change=Decimal(amount),
            category=self.groceries,
            comment=comment,
        )
        Payment.objects.create(
            user=self.user,
            transaction=tx,
            source=self.source,
            amount=abs(Decimal(amount)),
            row_number=row,
        )
        return tx

    def test_product_item_requires_price_for_transaction_link(self):
        tx = self.add_transaction(1, date(2026, 1, 1), '-8.50')
        with self.assertRaises(Exception):
            ProductItem.objects.create(
                user=self.user,
                product=self.product,
                transaction=tx,
                price=None,
            )

    def test_product_item_xor_link_constraint(self):
        tx = self.add_transaction(1, date(2026, 1, 1), '-8.50')
        receipt_tx = self.add_transaction(3, date(2026, 1, 1), '-8.50')
        receipt = Receipt.objects.create(
            user=self.user,
            transaction=receipt_tx,
            date=date(2026, 1, 1),
            total=Decimal('8.50'),
        )
        item = ReceiptItem.objects.create(
            user=self.user,
            receipt=receipt,
            name='Paste',
            amount=Decimal('1'),
            unit='tube',
            money=Decimal('8.50'),
        )
        with self.assertRaises(Exception):
            ProductItem.objects.create(
                user=self.user,
                product=self.product,
                transaction=tx,
                receipt_item=item,
                price=Decimal('8.50'),
            )

    @patch('finance.db_reader.timezone.localdate', return_value=date(2026, 1, 31))
    def test_product_detail_stats(self, _localdate):
        tx1 = self.add_transaction(1, date(2026, 1, 1), '-10.00')
        tx2 = self.add_transaction(2, date(2026, 1, 21), '-12.00')
        ProductItem.objects.create(
            user=self.user,
            product=self.product,
            transaction=tx1,
            price=Decimal('10.00'),
        )
        ProductItem.objects.create(
            user=self.user,
            product=self.product,
            transaction=tx2,
            price=Decimal('12.00'),
        )

        detail = get_product_detail(user=self.user, product_id=str(self.product.id))
        self.assertEqual(detail['stats']['totalPurchases'], 2)
        self.assertEqual(detail['stats']['totalSpent'], 22.0)
        self.assertEqual(detail['stats']['lastPurchaseDate'], '2026-01-21')
        self.assertEqual(detail['stats']['avgDaysBetweenPurchases'], 20.0)
        # No end date on latest → purchase date through today (10 days).
        self.assertAlmostEqual(detail['stats']['costPerDay'], 12.0 / 10)

    @patch('finance.db_reader.timezone.localdate', return_value=date(2026, 1, 31))
    def test_product_cost_per_day_uses_latest_end_date(self, _localdate):
        tx1 = self.add_transaction(1, date(2026, 1, 1), '-10.00')
        tx2 = self.add_transaction(2, date(2026, 1, 21), '-12.00')
        ProductItem.objects.create(
            user=self.user,
            product=self.product,
            transaction=tx1,
            price=Decimal('10.00'),
            end_date=date(2026, 1, 20),
        )
        ProductItem.objects.create(
            user=self.user,
            product=self.product,
            transaction=tx2,
            price=Decimal('12.00'),
            end_date=date(2026, 1, 27),
        )

        detail = get_product_detail(user=self.user, product_id=str(self.product.id))
        # Latest purchase 21→27 Jan = 6 days, not through today.
        self.assertAlmostEqual(detail['stats']['costPerDay'], 12.0 / 6)

        products = get_products(user=self.user)
        self.assertAlmostEqual(products[0]['costPerDay'], 12.0 / 6)

    def test_get_products_list(self):
        tx = self.add_transaction(1, date(2026, 1, 10), '-5.00')
        ProductItem.objects.create(
            user=self.user,
            product=self.product,
            transaction=tx,
            price=Decimal('5.00'),
        )
        rows = get_products(user=self.user)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], 'Toothpaste')
        self.assertEqual(rows[0]['purchaseCount'], 1)

    @patch('finance.api_views.sheets_for')
    @patch('finance.api_views.oauth.get_finance_user')
    @patch('finance.api_views.oauth.get_access_token', return_value='token')
    def test_create_product_api(self, _access_token, get_user, sheets_for):
        get_user.return_value = self.user
        client = MagicMock()
        client.add_product.return_value = {'productId': 'abc', 'name': 'Shampoo'}
        sheets_for.return_value = client

        response = self.client.post(
            '/api/products',
            data={'name': 'Shampoo'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        client.add_product.assert_called_once_with(name='Shampoo')

    def test_save_and_update_product_item_end_date(self):
        tx = self.add_transaction(1, date(2026, 1, 1), '-8.50')
        item_id = uuid.uuid4()
        save_product_item(
            user=self.user,
            product_item_id=item_id,
            product_id=self.product.id,
            price='8.50',
            transaction_id=tx.id,
        )
        created = ProductItem.objects.get(pk=item_id)
        self.assertIsNone(created.end_date)

        update_product_item(user=self.user, product_item_id=item_id, end_date='2026-02-28')
        created.refresh_from_db()
        self.assertEqual(created.end_date, date(2026, 2, 28))

        update_product_item(user=self.user, product_item_id=item_id, end_date='')
        created.refresh_from_db()
        self.assertIsNone(created.end_date)

        with_end_id = uuid.uuid4()
        tx2 = self.add_transaction(2, date(2026, 1, 10), '-9.00')
        save_product_item(
            user=self.user,
            product_item_id=with_end_id,
            product_id=self.product.id,
            price='9.00',
            transaction_id=tx2.id,
            end_date='28/02/2026',
        )
        self.assertEqual(
            ProductItem.objects.get(pk=with_end_id).end_date, date(2026, 2, 28)
        )

    def test_product_detail_and_transaction_include_end_date(self):
        tx = self.add_transaction(1, date(2026, 1, 10), '-5.00', comment='Coles : paste')
        ProductItem.objects.create(
            user=self.user,
            product=self.product,
            transaction=tx,
            price=Decimal('5.00'),
            end_date=date(2026, 3, 1),
        )

        detail = get_product_detail(user=self.user, product_id=str(self.product.id))
        self.assertEqual(detail['purchases'][0]['endDate'], '2026-03-01')

        data = get_transaction(user=self.user, transaction_id=str(tx.id))
        self.assertEqual(data['products'][0]['endDate'], '2026-03-01')

        export = get_export_payload(user=self.user)
        self.assertEqual(
            export['product_items']['columns'][-1],
            'End Date',
        )
        self.assertEqual(export['product_items']['rows'][0][-1], '2026-03-01')

    def test_receipt_item_product_includes_end_date(self):
        tx = Transaction.objects.create(
            user=self.user,
            row_number=9,
            date=date(2026, 1, 8),
            change=Decimal('-8.50'),
            category=self.groceries,
        )
        Payment.objects.create(
            user=self.user,
            transaction=tx,
            source=self.source,
            amount=Decimal('8.50'),
            row_number=9,
        )
        receipt = Receipt.objects.create(
            user=self.user,
            transaction=tx,
            date=date(2026, 1, 8),
            total=Decimal('8.50'),
        )
        item = ReceiptItem.objects.create(
            user=self.user,
            receipt=receipt,
            name='Paste',
            amount=Decimal('1'),
            unit='tube',
            money=Decimal('8.50'),
        )
        ProductItem.objects.create(
            user=self.user,
            product=self.product,
            receipt_item=item,
            end_date=date(2026, 5, 1),
        )
        data = get_transaction(user=self.user, transaction_id=str(tx.id))
        linked = data['receipt']['items'][0]
        self.assertEqual(linked['productId'], str(self.product.id))
        self.assertEqual(linked['endDate'], '2026-05-01')

    def test_product_item_xor_still_enforced_with_end_date(self):
        tx = self.add_transaction(1, date(2026, 1, 1), '-8.50')
        receipt_tx = self.add_transaction(3, date(2026, 1, 1), '-8.50')
        receipt = Receipt.objects.create(
            user=self.user,
            transaction=receipt_tx,
            date=date(2026, 1, 1),
            total=Decimal('8.50'),
        )
        item = ReceiptItem.objects.create(
            user=self.user,
            receipt=receipt,
            name='Paste',
            amount=Decimal('1'),
            unit='tube',
            money=Decimal('8.50'),
        )
        with self.assertRaises(Exception):
            ProductItem.objects.create(
                user=self.user,
                product=self.product,
                transaction=tx,
                receipt_item=item,
                price=Decimal('8.50'),
                end_date=date(2026, 4, 1),
            )

    @patch('finance.api_views.sheets_for')
    @patch('finance.api_views.oauth.get_finance_user')
    @patch('finance.api_views.oauth.get_access_token', return_value='token')
    def test_create_product_item_api_passes_end_date(
        self, _access_token, get_user, sheets_for
    ):
        get_user.return_value = self.user
        client = MagicMock()
        client.add_product_item.return_value = {
            'productItemId': 'pi-1',
            'endDate': '2026-03-01',
        }
        sheets_for.return_value = client

        response = self.client.post(
            '/api/product-items',
            data={
                'productId': str(self.product.id),
                'transactionId': 'tx-1',
                'price': 8.5,
                'endDate': '2026-03-01',
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        client.add_product_item.assert_called_once_with(
            product_id=str(self.product.id),
            transaction_id='tx-1',
            receipt_item_id=None,
            price=8.5,
            end_date='2026-03-01',
        )

    @patch('finance.api_views.sheets_for')
    @patch('finance.api_views.oauth.get_finance_user')
    @patch('finance.api_views.oauth.get_access_token', return_value='token')
    def test_update_product_item_api_passes_end_date(
        self, _access_token, get_user, sheets_for
    ):
        get_user.return_value = self.user
        client = MagicMock()
        client.update_product_item.return_value = {
            'productItemId': 'pi-1',
            'endDate': None,
        }
        sheets_for.return_value = client

        response = self.client.put(
            '/api/product-items/pi-1',
            data={'endDate': None},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        client.update_product_item.assert_called_once_with(
            product_item_id='pi-1',
            end_date=None,
        )


class FundingTests(TestCase):
    def test_validate_funding_allows_giftcard_only(self):
        from finance.funding import validate_funding

        validate_funding(
            '-25',
            [],
            [{'giftcard_id': 'g1', 'amount': '25'}],
        )

    def test_aggregate_giftcard_debits(self):
        from finance.funding import aggregate_giftcard_debits

        totals = aggregate_giftcard_debits(
            [
                {'giftcardId': 'aaa', 'amount': '10'},
                {'giftcard_id': 'aaa', 'amount': '5.50'},
                {'giftcard_id': 'bbb', 'amount': '3'},
            ]
        )
        self.assertEqual(totals['aaa'], Decimal('15.50'))
        self.assertEqual(totals['bbb'], Decimal('3'))

    def test_validate_giftcard_debit_rejects_overspend(self):
        from finance.funding import validate_giftcard_debit

        self.assertEqual(validate_giftcard_debit('20.00', '7.50'), Decimal('12.50'))
        with self.assertRaises(ValueError) as ctx:
            validate_giftcard_debit('10.00', '10.50')
        self.assertIn('exceeds giftcard balance', str(ctx.exception))

    def test_net_giftcard_debits_credits_and_debits_difference(self):
        from finance.funding import net_giftcard_debits

        deltas = net_giftcard_debits(
            [{'giftcard_id': 'aaa', 'amount': '10'}],
            previous_payments=[
                {'giftcard_id': 'aaa', 'amount': '20'},
                {'giftcard_id': 'bbb', 'amount': '5'},
            ],
        )
        self.assertEqual(deltas['aaa'], Decimal('-10'))
        self.assertEqual(deltas['bbb'], Decimal('-5'))


class GiftcardDebitWriteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email='gc-debit@example.com')
        self.source = Source.objects.create(user=self.user, name='Everyday', type='Bank')
        self.groceries = Category.objects.create(
            user=self.user,
            main_category='Living',
            sub_category='Groceries',
            type='Expense',
        )
        self.giftcard = Giftcard.objects.create(
            user=self.user,
            row_number=2,
            shop='Coles',
            date=date(2026, 1, 1),
            balance=Decimal('40.00'),
        )

    def test_save_transaction_bundle_debits_giftcard(self):
        from finance import db_writer

        gid = str(self.giftcard.id)
        db_writer.save_transaction_bundle(
            user=self.user,
            date='2026-01-15',
            change='-50.00',
            row_number=1,
            sub_category='Groceries',
            comment='Mixed pay',
            payments=[
                {
                    'payment_id': str(uuid.uuid4()),
                    'source': 'Everyday',
                    'amount': '30.00',
                    'row_number': 1,
                }
            ],
            giftcard_payments=[
                {
                    'giftcard_payment_id': str(uuid.uuid4()),
                    'giftcard_id': gid,
                    'amount': '20.00',
                    'row_number': 1,
                }
            ],
            giftcard_debits=[{'giftcard_id': gid, 'new_balance': '20.00'}],
        )
        self.giftcard.refresh_from_db()
        self.assertEqual(self.giftcard.balance, Decimal('20.00'))
        tx = Transaction.objects.get(user=self.user, row_number=1)
        self.assertEqual(tx.payments.count(), 1)
        self.assertEqual(tx.giftcard_payments.count(), 1)

    def test_plan_giftcard_debits_rejects_overspend(self):
        client = SheetsClient(access_token='token', sheet_id='sheet', user=self.user)
        with self.assertRaises(SheetsError) as ctx:
            client.plan_giftcard_debits(
                [{'giftcard_id': str(self.giftcard.id), 'amount': '50'}]
            )
        self.assertIn('exceeds giftcard balance', str(ctx.exception))

    def test_plan_giftcard_debits_aggregates_same_card(self):
        client = SheetsClient(access_token='token', sheet_id='sheet', user=self.user)
        planned = client.plan_giftcard_debits(
            [
                {'giftcard_id': str(self.giftcard.id), 'amount': '10'},
                {'giftcard_id': str(self.giftcard.id), 'amount': '5'},
            ]
        )
        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0]['amount'], 15.0)
        self.assertEqual(planned[0]['new_balance'], 25.0)

    @patch.object(SheetsClient, 'apply_giftcard_debits')
    @patch.object(SheetsClient, 'append_funding_rows')
    @patch.object(SheetsClient, 'append_transaction_row', return_value=5)
    def test_add_transaction_applies_giftcard_debit(
        self, _append_tx, append_funding, apply_debits
    ):
        from finance import db_writer

        gid = str(self.giftcard.id)
        append_funding.return_value = (
            [
                {
                    'payment_id': str(uuid.uuid4()),
                    'source': 'Everyday',
                    'amount': 30.0,
                    'row_number': 1,
                }
            ],
            [
                {
                    'giftcard_payment_id': str(uuid.uuid4()),
                    'giftcard_id': gid,
                    'amount': 20.0,
                    'row_number': 1,
                }
            ],
        )
        client = SheetsClient(access_token='token', sheet_id='sheet', user=self.user)
        with patch.object(db_writer, 'save_transaction_bundle', wraps=db_writer.save_transaction_bundle) as save_bundle:
            result = client.add_transaction(
                date='2026-01-15',
                amount=50,
                type='Expense',
                sub_category='Groceries',
                comment='Shop',
                payments=[{'source': 'Everyday', 'amount': 30}],
                giftcard_payments=[{'giftcardId': gid, 'amount': 20}],
            )
        self.assertEqual(result['added'], 1)
        apply_debits.assert_called_once()
        debits = apply_debits.call_args.args[0]
        self.assertEqual(debits[0]['new_balance'], 20.0)
        save_bundle.assert_called_once()
        self.assertEqual(
            save_bundle.call_args.kwargs['giftcard_debits'][0]['new_balance'],
            20.0,
        )
        self.giftcard.refresh_from_db()
        self.assertEqual(self.giftcard.balance, Decimal('20.00'))

    def test_plan_giftcard_debits_credits_previous_payment_on_edit(self):
        # $40 card already reduced by this transaction's $20 giftcard payment.
        self.giftcard.balance = Decimal('20.00')
        self.giftcard.save(update_fields=['balance'])
        client = SheetsClient(access_token='token', sheet_id='sheet', user=self.user)
        gid = str(self.giftcard.id)
        planned = client.plan_giftcard_debits(
            [{'giftcard_id': gid, 'amount': '10'}],
            previous_payments=[{'giftcard_id': gid, 'amount': '20'}],
        )
        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0]['amount'], -10.0)
        self.assertEqual(planned[0]['new_balance'], 30.0)

    def test_plan_giftcard_debits_edit_overspend_uses_remaining_balance(self):
        client = SheetsClient(access_token='token', sheet_id='sheet', user=self.user)
        gid = str(self.giftcard.id)
        with self.assertRaises(SheetsError) as ctx:
            client.plan_giftcard_debits(
                [{'giftcard_id': gid, 'amount': '50'}],
                previous_payments=[{'giftcard_id': gid, 'amount': '5'}],
            )
        self.assertIn('exceeds giftcard balance', str(ctx.exception))

    def test_update_transaction_detail_moves_giftcard_balance(self):
        from finance.db_writer import update_transaction_detail

        gid = str(self.giftcard.id)
        tx = Transaction.objects.create(
            user=self.user,
            row_number=8,
            date=date(2026, 1, 10),
            change=Decimal('-20.00'),
            category=self.groceries,
            comment='Use giftcard: Coles',
        )
        GiftcardPayment.objects.create(
            user=self.user,
            transaction=tx,
            giftcard=self.giftcard,
            amount=Decimal('20.00'),
            row_number=8,
        )
        self.giftcard.balance = Decimal('20.00')
        self.giftcard.save(update_fields=['balance'])

        update_transaction_detail(
            user=self.user,
            transaction=tx,
            date='2026-01-10',
            change='-10.00',
            comment='Use giftcard: Coles',
            sub_category='Groceries',
            payments=[],
            giftcard_payments=[
                {
                    'giftcard_payment_id': str(uuid.uuid4()),
                    'giftcard_id': gid,
                    'amount': '10.00',
                    'row_number': 9,
                }
            ],
            giftcard_debits=[{'giftcard_id': gid, 'new_balance': '30.00'}],
        )
        self.giftcard.refresh_from_db()
        self.assertEqual(self.giftcard.balance, Decimal('30.00'))
        self.assertEqual(tx.giftcard_payments.get().amount, Decimal('10.00'))

    @patch.object(SheetsClient, 'append_funding_rows')
    @patch.object(SheetsClient, 'append_rows')
    def test_buy_giftcard_records_transfer_not_expense(
        self, append_rows, append_funding
    ):
        Category.objects.create(
            user=self.user,
            main_category='Transfer',
            sub_category='Exchange (self)',
            type='',
        )
        append_rows.side_effect = [[4], [5]]
        append_funding.return_value = (
            [
                {
                    'payment_id': str(uuid.uuid4()),
                    'source': 'Everyday',
                    'amount': 20.0,
                    'row_number': 6,
                }
            ],
            [],
        )
        client = SheetsClient(access_token='token', sheet_id='sheet', user=self.user)
        result = client.buy_giftcard(
            shop='Coles',
            date='2026-01-05',
            balance=20,
            source='Everyday',
        )
        self.assertEqual(result['balance'], 20)
        tx_values = append_rows.call_args_list[1].args[2][0]
        self.assertEqual(tx_values[2], -20)
        self.assertEqual(tx_values[4], 'Exchange (self)')
        tx = Transaction.objects.get(user=self.user, comment='Buy giftcard: Coles')
        self.assertEqual(tx.change, Decimal('-20.00'))
        self.assertEqual(tx.category.sub_category, 'Exchange (self)')
        self.assertEqual(tx.category.type, '')
        card = Giftcard.objects.get(pk=result['giftcardId'])
        self.assertEqual(card.balance, Decimal('20.00'))

    @patch('finance.db_reader.timezone.localdate', return_value=date(2026, 1, 15))
    def test_save_giftcard_purchase_and_use_single_count_dashboard(self, _localdate):
        from finance import db_writer

        self.giftcard.balance = Decimal('0.00')
        self.giftcard.save(update_fields=['balance'])

        Category.objects.create(
            user=self.user,
            main_category='Transfer',
            sub_category='Exchange (self)',
            type='',
        )
        salary = Category.objects.create(
            user=self.user,
            main_category='Earnings',
            sub_category='Salary',
            type='Income',
        )
        income_tx = Transaction.objects.create(
            user=self.user,
            row_number=10,
            date=date(2026, 1, 2),
            change=Decimal('100.00'),
            category=salary,
        )
        Payment.objects.create(
            user=self.user,
            transaction=income_tx,
            source=self.source,
            amount=Decimal('100.00'),
            row_number=10,
        )
        giftcard_id = str(uuid.uuid4())
        buy_tx_id = str(uuid.uuid4())
        db_writer.save_giftcard_purchase(
            user=self.user,
            giftcard_id=giftcard_id,
            shop='Coles',
            date='2026-01-05',
            balance='20.00',
            row_number=11,
            transaction={
                'transaction_id': buy_tx_id,
                'date': '2026-01-05',
                'change': '-20.00',
                'comment': 'Buy giftcard: Coles',
                'sub_category': 'Exchange (self)',
                'row_number': 12,
            },
            payment={
                'payment_id': str(uuid.uuid4()),
                'source': 'Everyday',
                'amount': '20.00',
                'row_number': 13,
            },
        )
        after_buy = get_dashboard_data(user=self.user)
        self.assertEqual(after_buy['summary']['netWorth'], 100.0)
        self.assertEqual(after_buy['summary']['expense'], 0.0)

        db_writer.save_giftcard_use(
            user=self.user,
            giftcard_id=giftcard_id,
            new_balance='0.00',
            date='2026-01-10',
            change='-20.00',
            comment='Use giftcard: Coles',
            sub_category='Groceries',
            row_number=14,
            transaction_id=str(uuid.uuid4()),
            giftcard_payment={
                'giftcard_payment_id': str(uuid.uuid4()),
                'giftcard_id': giftcard_id,
                'amount': '20.00',
                'row_number': 15,
            },
        )
        after_use = get_dashboard_data(user=self.user)
        self.assertEqual(after_use['summary']['netWorth'], 80.0)
        self.assertEqual(after_use['summary']['expense'], -20.0)
        self.assertEqual(Giftcard.objects.get(pk=giftcard_id).balance, Decimal('0.00'))

    @override_settings(TIME_ZONE='Australia/Perth')
    @patch(
        'django.utils.timezone.now',
        return_value=datetime(2026, 9, 18, 20, 0, tzinfo=dt_timezone.utc),
    )
    @patch.object(SheetsClient, 'update_table_cell_at_row')
    @patch.object(SheetsClient, 'append_funding_rows')
    @patch.object(SheetsClient, 'append_rows', return_value=[8])
    def test_use_giftcard_date_uses_perth_calendar(
        self, append_rows, append_funding, _update, _now
    ):
        from finance import db_writer

        gid = str(self.giftcard.id)
        append_funding.return_value = (
            [],
            [
                {
                    'giftcard_payment_id': str(uuid.uuid4()),
                    'giftcard_id': gid,
                    'amount': 10.0,
                    'row_number': 1,
                }
            ],
        )
        client = SheetsClient(access_token='token', sheet_id='sheet', user=self.user)
        with patch.object(db_writer, 'save_giftcard_use') as save_use:
            client.use_giftcard(
                giftcard_id=gid,
                amount=10,
                comment='Milk',
                sub_category='Groceries',
            )

        self.assertEqual(append_rows.call_args.args[2][0][1], '2026-09-19')
        self.assertEqual(save_use.call_args.kwargs['date'], '2026-09-19')


PERTH_AFTER_UTC_MIDNIGHT = datetime(2026, 9, 18, 20, 0, tzinfo=dt_timezone.utc)
PERTH_MONTH_BOUNDARY = datetime(2026, 9, 30, 20, 0, tzinfo=dt_timezone.utc)


class TimeZoneSettingsTests(SimpleTestCase):
    def test_default_time_zone_is_australia_perth(self):
        self.assertEqual(settings.TIME_ZONE, 'Australia/Perth')


@override_settings(TIME_ZONE='Australia/Perth')
class PerthLocalCalendarTests(TestCase):
    """UTC calendar date can differ from Australia/Perth (UTC+8, no DST)."""

    def setUp(self):
        self.user = User.objects.create(email='perth@example.com')
        self.source = Source.objects.create(user=self.user, name='Everyday', type='Bank')
        self.salary = Category.objects.create(
            user=self.user,
            main_category='Earnings',
            sub_category='Salary',
            type='Income',
        )

    def add_transaction(self, row, value, amount, category=None):
        signed = Decimal(amount)
        tx = Transaction.objects.create(
            user=self.user,
            row_number=row,
            date=value,
            change=signed,
            category=category,
        )
        Payment.objects.create(
            user=self.user,
            transaction=tx,
            source=self.source,
            amount=abs(signed),
            row_number=row,
        )
        return tx

    def test_localdate_is_next_day_while_utc_is_still_previous_evening(self):
        # 2026-09-18 20:00 UTC = 2026-09-19 04:00 in Perth.
        self.assertEqual(PERTH_AFTER_UTC_MIDNIGHT.date(), date(2026, 9, 18))
        with patch('django.utils.timezone.now', return_value=PERTH_AFTER_UTC_MIDNIGHT):
            self.assertEqual(timezone.localdate(), date(2026, 9, 19))

    def test_utc_time_zone_keeps_previous_calendar_day(self):
        with override_settings(TIME_ZONE='UTC'):
            with patch('django.utils.timezone.now', return_value=PERTH_AFTER_UTC_MIDNIGHT):
                self.assertEqual(timezone.localdate(), date(2026, 9, 18))

    def test_dashboard_this_month_uses_perth_month_boundary(self):
        # 2026-09-30 20:00 UTC = 2026-10-01 04:00 Perth → current month is October.
        self.add_transaction(1, date(2026, 9, 30), '100.00', self.salary)
        self.add_transaction(2, date(2026, 10, 1), '200.00', self.salary)

        with patch('django.utils.timezone.now', return_value=PERTH_MONTH_BOUNDARY):
            data = get_dashboard_data(user=self.user)

        self.assertEqual(data['months'], ['2026/08', '2026/09', '2026/10'])
        self.assertEqual(data['summary']['income'], 200.0)
        self.assertEqual(
            [transaction['date'] for transaction in data['transactions']],
            ['2026-10-01'],
        )

    @patch(
        'django.utils.timezone.now',
        return_value=PERTH_AFTER_UTC_MIDNIGHT,
    )
    @patch('finance.groq_client._chat', return_value={'action': 'unknown', 'reason': 'x'})
    def test_chat_today_prompt_uses_perth_date(self, chat, _now):
        from finance.groq_client import parse_finance_message

        parse_finance_message('hello', {'sources': [], 'categories': []})
        system = chat.call_args.args[0][0]['content']
        self.assertIn("Today's date is 2026-09-19", system)
        self.assertNotIn("Today's date is 2026-09-18", system)

    @patch(
        'django.utils.timezone.now',
        return_value=PERTH_AFTER_UTC_MIDNIGHT,
    )
    @patch(
        'finance.groq_client._chat',
        return_value={'store': 'X', 'date': 'blurry', 'items': []},
    )
    def test_receipt_fallback_date_uses_perth_date(self, _chat, _now):
        from finance.groq_client import extract_receipt_from_image

        result = extract_receipt_from_image(
            'data:image/png;base64,xx',
            {'sources': [], 'categories': []},
        )
        self.assertEqual(result['date'], '2026-09-19')
