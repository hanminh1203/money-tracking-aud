# Transaction.source / sub_category → FKs to Source / Category

import django.db.models.deletion
from django.db import migrations, models


def clear_mirror_tables(apps, schema_editor):
    """Wipe mirror rows so unique/FK changes apply cleanly; re-sync via Management."""
    Transaction = apps.get_model('finance', 'Transaction')
    ReceiptItem = apps.get_model('finance', 'ReceiptItem')
    Receipt = apps.get_model('finance', 'Receipt')
    Category = apps.get_model('finance', 'Category')
    Source = apps.get_model('finance', 'Source')
    Transaction.objects.all().delete()
    ReceiptItem.objects.all().delete()
    Receipt.objects.all().delete()
    Category.objects.all().delete()
    Source.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0002_category_source'),
    ]

    operations = [
        migrations.RunPython(clear_mirror_tables, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='category',
            name='sub_category',
            field=models.CharField(max_length=256, unique=True),
        ),
        migrations.AlterField(
            model_name='source',
            name='name',
            field=models.CharField(max_length=256, unique=True),
        ),
        migrations.RemoveField(
            model_name='transaction',
            name='source',
        ),
        migrations.RemoveField(
            model_name='transaction',
            name='sub_category',
        ),
        migrations.AddField(
            model_name='transaction',
            name='source',
            field=models.ForeignKey(
                db_column='source_id',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='transactions',
                to='finance.source',
            ),
        ),
        migrations.AddField(
            model_name='transaction',
            name='category',
            field=models.ForeignKey(
                blank=True,
                db_column='category_id',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='transactions',
                to='finance.category',
            ),
        ),
    ]
