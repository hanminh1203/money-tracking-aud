# Merge payment-table branch with product end_date + user-scoped lookups.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0013_user_scoped_category_source'),
        ('finance', '0015_receipt_transaction_fk'),
    ]

    operations = []
