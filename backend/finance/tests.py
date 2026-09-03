from datetime import date
from decimal import Decimal
import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase

from finance.db_reader import ReaderError, get_dashboard_data, get_product_detail, get_products, get_transaction
from finance.db_sync import sync_from_sheets
from finance.models import (
    Category,
    Giftcard,
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
        client.get_mirror_source_rows.return_value = {
            'transactions': [
                {
                    '__sheet_row': 2,
                    'Transaction ID': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                    'Date': '2026-01-10',
                    'Change': '100',
                    'Comment': 'Pay',
                    'Sub category': 'Salary',
                    'Receipt ID': '',
                }
            ],
            'payments': [
                {
                    '__sheet_row': 3,
                    'Payment ID': 'e5f6a7b8-c9d0-1234-ef01-234567890abc',
                    'Transaction ID': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                    'Source': 'Everyday',
                    'Amount': '100',
                }
            ],
            'giftcard_payments': [],
            'receipts': [],
            'receipt_items': [],
            'giftcards': [],
            'products': [],
            'product_items': [],
        }

        result = sync_from_sheets(client, user=self.user_a)

        self.assertTrue(result['ok'])
        self.assertEqual(result['inserted']['transactions'], 1)
        self.assertEqual(Transaction.objects.filter(user=self.user_a).count(), 1)
        self.assertEqual(Transaction.objects.filter(user=self.user_b).count(), 1)
        self.assertEqual(Giftcard.objects.filter(user=self.user_b).count(), 1)
        self.assertEqual(Source.objects.count(), 1)
        self.assertEqual(Category.objects.count(), 1)
        synced = Transaction.objects.get(user=self.user_a)
        self.assertEqual(
            str(synced.id), 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        )

    def test_sync_product_item_links_by_transaction_id(self):
        tx_id = uuid.UUID('b2c3d4e5-f6a7-8901-bcde-f12345678901')
        product_id = uuid.UUID('c3d4e5f6-a7b8-9012-cdef-123456789012')
        product_item_id = uuid.UUID('d4e5f6a7-b8c9-0123-def0-234567890123')
        client = MagicMock()
        client.get_mirror_source_rows.return_value = {
            'transactions': [
                {
                    '__sheet_row': 2,
                    'Transaction ID': str(tx_id),
                    'Date': '2026-01-10',
                    'Change': '-25',
                    'Comment': 'Shop',
                    'Sub category': 'Salary',
                    'Receipt ID': '',
                }
            ],
            'payments': [
                {
                    '__sheet_row': 3,
                    'Payment ID': 'f6a7b8c9-d0e1-2345-f012-345678901bcd',
                    'Transaction ID': str(tx_id),
                    'Source': 'Everyday',
                    'Amount': '25',
                }
            ],
            'giftcard_payments': [],
            'receipts': [],
            'receipt_items': [],
            'giftcards': [],
            'products': [
                {'Product ID': str(product_id), 'Name': 'Milk'},
            ],
            'product_items': [
                {
                    'Product Item ID': str(product_item_id),
                    'Product ID': str(product_id),
                    'Price': '12.50',
                    'Transaction ID': str(tx_id),
                    'Receipt Item ID': '',
                }
            ],
        }

        result = sync_from_sheets(client, user=self.user_a)

        self.assertTrue(result['ok'])
        pi = ProductItem.objects.get(user=self.user_a, id=product_item_id)
        self.assertEqual(pi.transaction_id, tx_id)
        self.assertEqual(pi.price, Decimal('12.50'))


class TransactionDetailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email='detail@example.com')
        self.other = User.objects.create(email='other-detail@example.com')
        self.source = Source.objects.create(name='Everyday', type='Bank')
        self.groceries = Category.objects.create(
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
            main_category='Earnings',
            sub_category='Salary',
            type='Income',
        )
        savings = Source.objects.create(name='Savings', type='Bank')

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
        self.source = Source.objects.create(name='Everyday', type='Bank')
        self.groceries = Category.objects.create(
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
