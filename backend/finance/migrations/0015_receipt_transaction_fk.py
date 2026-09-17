"""Move receipt↔transaction link onto Receipt (Transaction ID column)."""

import django.db.models.deletion
from django.db import migrations, models


def forwards_move_link(apps, schema_editor):
    Transaction = apps.get_model('finance', 'Transaction')
    Receipt = apps.get_model('finance', 'Receipt')
    ReceiptItem = apps.get_model('finance', 'ReceiptItem')

    assigned_tx_ids: set = set()
    for tx in (
        Transaction.objects.exclude(receipt_id=None)
        .order_by('creation_date', 'id')
        .iterator()
    ):
        if tx.id in assigned_tx_ids:
            continue
        updated = Receipt.objects.filter(
            pk=tx.receipt_id, transaction_id__isnull=True
        ).update(transaction_id=tx.id)
        if updated:
            assigned_tx_ids.add(tx.id)

    orphans = Receipt.objects.filter(transaction_id__isnull=True)
    ReceiptItem.objects.filter(receipt__in=orphans).delete()
    orphans.delete()


def backwards_move_link(apps, schema_editor):
    Transaction = apps.get_model('finance', 'Transaction')
    Receipt = apps.get_model('finance', 'Receipt')

    for receipt in Receipt.objects.exclude(transaction_id=None).iterator():
        Transaction.objects.filter(pk=receipt.transaction_id).update(
            receipt_id=receipt.id
        )


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0014_remove_productitem_product_item_xor_link_and_more'),
    ]

    operations = [
        # related_name='+' avoids clashing with Transaction.receipt while both exist.
        migrations.AddField(
            model_name='receipt',
            name='transaction',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='+',
                to='finance.transaction',
                db_column='transaction_id',
            ),
        ),
        migrations.RunPython(forwards_move_link, backwards_move_link),
        migrations.RemoveField(
            model_name='transaction',
            name='receipt',
        ),
        migrations.AlterField(
            model_name='receipt',
            name='transaction',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='receipt',
                to='finance.transaction',
                db_column='transaction_id',
            ),
        ),
    ]
