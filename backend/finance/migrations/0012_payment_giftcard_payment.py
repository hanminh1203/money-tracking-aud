# Payment / GiftcardPayment tables; migrate funding off Transaction; drop source/giftcard FKs

from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


GIFTCARD_SOURCE_NAME = 'Giftcard'


def migrate_transaction_funding(apps, schema_editor):
    Transaction = apps.get_model('finance', 'Transaction')
    Payment = apps.get_model('finance', 'Payment')
    GiftcardPayment = apps.get_model('finance', 'GiftcardPayment')
    ProductItem = apps.get_model('finance', 'ProductItem')
    Receipt = apps.get_model('finance', 'Receipt')

    credit_tx_ids = set(
        Transaction.objects.filter(
            source__name=GIFTCARD_SOURCE_NAME,
            giftcard_id__isnull=False,
            change__gt=0,
        ).values_list('id', flat=True)
    )

    payment_row_by_user: dict[uuid.UUID, int] = {}
    gcp_row_by_user: dict[uuid.UUID, int] = {}

    def next_payment_row(user_id):
        payment_row_by_user[user_id] = payment_row_by_user.get(user_id, 0) + 1
        return payment_row_by_user[user_id]

    def next_gcp_row(user_id):
        gcp_row_by_user[user_id] = gcp_row_by_user.get(user_id, 0) + 1
        return gcp_row_by_user[user_id]

    def add_payment(tx, amount):
        Payment.objects.create(
            id=uuid.uuid4(),
            version=1,
            user_id=tx.user_id,
            transaction_id=tx.id,
            source_id=tx.source_id,
            amount=abs(Decimal(str(amount))),
            row_number=next_payment_row(tx.user_id),
        )

    def add_giftcard_payment(tx, amount):
        GiftcardPayment.objects.create(
            id=uuid.uuid4(),
            version=1,
            user_id=tx.user_id,
            transaction_id=tx.id,
            giftcard_id=tx.giftcard_id,
            amount=abs(Decimal(str(amount))),
            row_number=next_gcp_row(tx.user_id),
        )

    sibling_delete_ids: set[uuid.UUID] = set()
    receipt_ids = (
        Transaction.objects.filter(receipt_id__isnull=False)
        .exclude(id__in=credit_tx_ids)
        .values_list('receipt_id', flat=True)
        .distinct()
    )
    for rid in receipt_ids:
        siblings = list(
            Transaction.objects.filter(receipt_id=rid)
            .exclude(id__in=credit_tx_ids)
            .select_related('source')
            .order_by('row_number')
        )
        if len(siblings) <= 1:
            continue
        canonical = siblings[0]
        try:
            receipt = Receipt.objects.get(pk=rid)
            canonical.change = -abs(receipt.total)
        except Receipt.DoesNotExist:
            canonical.change = sum(Decimal(str(s.change)) for s in siblings)
        canonical.save(update_fields=['change'])

        for s in siblings:
            if s.source.name == GIFTCARD_SOURCE_NAME and s.giftcard_id:
                add_giftcard_payment(s, s.change)
            else:
                add_payment(s, s.change)
            if s.id != canonical.id:
                sibling_delete_ids.add(s.id)
                ProductItem.objects.filter(transaction_id=s.id).update(
                    transaction_id=canonical.id
                )

    Transaction.objects.filter(id__in=credit_tx_ids | sibling_delete_ids).delete()

    for tx in Transaction.objects.select_related('source').iterator():
        if Payment.objects.filter(transaction_id=tx.id).exists():
            continue
        if GiftcardPayment.objects.filter(transaction_id=tx.id).exists():
            continue
        if tx.source.name == GIFTCARD_SOURCE_NAME and tx.giftcard_id:
            add_giftcard_payment(tx, tx.change)
        else:
            add_payment(tx, tx.change)


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0011_product_and_product_item'),
    ]

    operations = [
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version', models.PositiveIntegerField(default=1)),
                ('creation_date', models.DateTimeField(auto_now_add=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('row_number', models.PositiveIntegerField(help_text='1-based Google Sheets row number in the Payment table.')),
                ('source', models.ForeignKey(db_column='source_id', on_delete=django.db.models.deletion.PROTECT, related_name='payments', to='finance.source')),
                ('transaction', models.ForeignKey(db_column='transaction_id', on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='finance.transaction')),
                ('user', models.ForeignKey(db_column='user_id', on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='finance.user')),
            ],
            options={
                'db_table': 'payment',
            },
        ),
        migrations.CreateModel(
            name='GiftcardPayment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version', models.PositiveIntegerField(default=1)),
                ('creation_date', models.DateTimeField(auto_now_add=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('row_number', models.PositiveIntegerField(help_text='1-based Google Sheets row number in the GiftcardPayment table.')),
                ('giftcard', models.ForeignKey(db_column='giftcard_id', on_delete=django.db.models.deletion.PROTECT, related_name='giftcard_payments', to='finance.giftcard')),
                ('transaction', models.ForeignKey(db_column='transaction_id', on_delete=django.db.models.deletion.CASCADE, related_name='giftcard_payments', to='finance.transaction')),
                ('user', models.ForeignKey(db_column='user_id', on_delete=django.db.models.deletion.CASCADE, related_name='giftcard_payments', to='finance.user')),
            ],
            options={
                'db_table': 'giftcard_payment',
            },
        ),
        migrations.AddConstraint(
            model_name='payment',
            constraint=models.UniqueConstraint(fields=('user', 'row_number'), name='payment_user_row_number_uniq'),
        ),
        migrations.AddConstraint(
            model_name='giftcardpayment',
            constraint=models.UniqueConstraint(fields=('user', 'row_number'), name='giftcard_payment_user_row_number_uniq'),
        ),
        migrations.RunPython(migrate_transaction_funding, migrations.RunPython.noop, atomic=False),
    ]
