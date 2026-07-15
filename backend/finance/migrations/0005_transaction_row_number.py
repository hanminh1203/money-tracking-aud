# Transaction.row_number — Google Sheets 1-based row in the Transactions table

from django.db import migrations, models


def wipe_transactions(apps, schema_editor):
    Transaction = apps.get_model('finance', 'Transaction')
    Transaction.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0004_audited_creation_date'),
    ]

    operations = [
        migrations.RunPython(wipe_transactions, migrations.RunPython.noop),
        migrations.AddField(
            model_name='transaction',
            name='row_number',
            field=models.PositiveIntegerField(
                help_text='1-based Google Sheets row number in the Transactions table.',
                unique=True,
            ),
        ),
    ]
