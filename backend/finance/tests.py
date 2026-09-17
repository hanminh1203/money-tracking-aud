from datetime import date
from decimal import Decimal
import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase

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
        return Transaction.objects.create(
            user=user or self.user,
            row_number=row,
            date=value,
            change=Decimal(amount),
            source=source or self.source,
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
        client.get_mirror_source_rows.return_value = sheet_mirror(
            transactions=[
                {
                    '__sheet_row': 2,
                    'Transaction ID': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                    'Date': '2026-01-10',
                    'Change': '100',
                    'Source': 'Everyday',
                    'Comment': 'Pay',
                    'Sub category': 'Salary',
                    'Receipt ID': '',
                    'Giftcard ID': '',
                }
            ],
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
        self.assertEqual(synced.source.user_id, self.user_a.id)
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
                    'Source': 'Everyday',
                    'Comment': 'Shop',
                    'Sub category': 'Salary',
                    'Receipt ID': '',
                    'Giftcard ID': '',
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
        defaults = {
            'user': self.user,
            'row_number': 1,
            'date': date(2026, 1, 8),
            'change': Decimal('-42.50'),
            'source': self.source,
            'category': self.groceries,
            'comment': 'Woolworths : weekly shop',
        }
        defaults.update(kwargs)
        return Transaction.objects.create(**defaults)

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
        receipt = Receipt.objects.create(
            user=self.user,
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
        tx = self.add_transaction(receipt=receipt)

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
            source='Savings',
            comment='Pay',
            sub_category='Salary',
        )

        tx.refresh_from_db()
        self.assertEqual(tx.date, date(2026, 2, 1))
        self.assertEqual(tx.change, Decimal('150.00'))
        self.assertEqual(tx.source_id, savings.id)
        self.assertEqual(tx.comment, 'Pay')
        self.assertEqual(tx.category_id, salary.id)
        self.assertEqual(tx.version, 2)

    def test_update_transaction_detail_replaces_receipt_items(self):
        from finance.db_writer import update_transaction_detail

        receipt = Receipt.objects.create(
            user=self.user,
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
        tx = self.add_transaction(receipt=receipt)

        update_transaction_detail(
            user=self.user,
            transaction=tx,
            date='2026-01-09',
            change='-10.00',
            source='Everyday',
            comment='Coles : restock',
            sub_category='Groceries',
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
        receipt = Receipt.objects.create(
            user=self.user,
            date=date(2026, 1, 8),
            total=Decimal('12.50'),
        )
        tx = self.add_transaction(receipt=receipt)
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
        receipt = Receipt.objects.create(
            user=self.user,
            date=date(2026, 1, 8),
            total=Decimal('12.50'),
        )
        tx = self.add_transaction(receipt=receipt)
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
        self.assertIn('must equal items total', str(ctx.exception))

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
        return Transaction.objects.create(
            user=self.user,
            row_number=row,
            date=value,
            change=Decimal(amount),
            source=self.source,
            category=self.groceries,
            comment=comment,
        )

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
        receipt = Receipt.objects.create(user=self.user, date=date(2026, 1, 1), total=Decimal('8.50'))
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
        self.assertAlmostEqual(detail['stats']['costPerDay'], 12.0 / 10)

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
        receipt = Receipt.objects.create(
            user=self.user, date=date(2026, 1, 8), total=Decimal('8.50')
        )
        item = ReceiptItem.objects.create(
            user=self.user,
            receipt=receipt,
            name='Paste',
            amount=Decimal('1'),
            unit='tube',
            money=Decimal('8.50'),
        )
        Transaction.objects.create(
            user=self.user,
            row_number=9,
            date=date(2026, 1, 8),
            change=Decimal('-8.50'),
            source=self.source,
            category=self.groceries,
            receipt=receipt,
        )
        ProductItem.objects.create(
            user=self.user,
            product=self.product,
            receipt_item=item,
            end_date=date(2026, 5, 1),
        )
        data = get_transaction(
            user=self.user,
            transaction_id=str(Transaction.objects.get(user=self.user, receipt=receipt).id),
        )
        linked = data['receipt']['items'][0]
        self.assertEqual(linked['productId'], str(self.product.id))
        self.assertEqual(linked['endDate'], '2026-05-01')

    def test_product_item_xor_still_enforced_with_end_date(self):
        tx = self.add_transaction(1, date(2026, 1, 1), '-8.50')
        receipt = Receipt.objects.create(
            user=self.user, date=date(2026, 1, 1), total=Decimal('8.50')
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
