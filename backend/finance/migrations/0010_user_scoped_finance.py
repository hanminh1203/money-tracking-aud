# User model + user ownership on Transaction/Receipt/ReceiptItem/Giftcard

import django.db.models.deletion
import uuid
from django.db import migrations, models


def wipe_user_owned(apps, schema_editor):
    Transaction = apps.get_model('finance', 'Transaction')
    ReceiptItem = apps.get_model('finance', 'ReceiptItem')
    Receipt = apps.get_model('finance', 'Receipt')
    Giftcard = apps.get_model('finance', 'Giftcard')
    Transaction.objects.all().delete()
    ReceiptItem.objects.all().delete()
    Receipt.objects.all().delete()
    Giftcard.objects.all().delete()


class Migration(migrations.Migration):
    # Wipe + ALTER in one atomic block hits Postgres "pending trigger events".
    atomic = False

    dependencies = [
        ('finance', '0009_enable_row_level_security'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('sheet_id', models.CharField(blank=True, default='', max_length=256)),
                ('creation_date', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'app_user',
            },
        ),
        migrations.RunPython(wipe_user_owned, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='giftcard',
            name='row_number',
            field=models.PositiveIntegerField(
                help_text='1-based Google Sheets row number in the Giftcard table.',
            ),
        ),
        migrations.AlterField(
            model_name='transaction',
            name='row_number',
            field=models.PositiveIntegerField(
                help_text='1-based Google Sheets row number in the Transactions table.',
            ),
        ),
        migrations.AddField(
            model_name='giftcard',
            name='user',
            field=models.ForeignKey(
                db_column='user_id',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='giftcards',
                to='finance.user',
            ),
        ),
        migrations.AddField(
            model_name='receipt',
            name='user',
            field=models.ForeignKey(
                db_column='user_id',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='receipts',
                to='finance.user',
            ),
        ),
        migrations.AddField(
            model_name='receiptitem',
            name='user',
            field=models.ForeignKey(
                db_column='user_id',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='receipt_items',
                to='finance.user',
            ),
        ),
        migrations.AddField(
            model_name='transaction',
            name='user',
            field=models.ForeignKey(
                db_column='user_id',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='transactions',
                to='finance.user',
            ),
        ),
        migrations.AddConstraint(
            model_name='giftcard',
            constraint=models.UniqueConstraint(
                fields=('user', 'row_number'),
                name='giftcard_user_row_number_uniq',
            ),
        ),
        migrations.AddConstraint(
            model_name='transaction',
            constraint=models.UniqueConstraint(
                fields=('user', 'row_number'),
                name='transaction_user_row_number_uniq',
            ),
        ),
    ]
