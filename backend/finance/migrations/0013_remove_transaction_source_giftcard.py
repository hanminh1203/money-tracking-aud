# Remove legacy source/giftcard FKs from Transaction (after payment migration)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0012_payment_giftcard_payment'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='transaction',
            name='giftcard',
        ),
        migrations.RemoveField(
            model_name='transaction',
            name='source',
        ),
    ]
