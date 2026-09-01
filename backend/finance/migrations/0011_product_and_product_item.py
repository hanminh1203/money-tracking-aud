# Product and ProductItem models

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0010_user_scoped_finance'),
    ]

    operations = [
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version', models.PositiveIntegerField(default=1)),
                ('creation_date', models.DateTimeField(auto_now_add=True)),
                ('name', models.CharField(max_length=256)),
                (
                    'user',
                    models.ForeignKey(
                        db_column='user_id',
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='products',
                        to='finance.user',
                    ),
                ),
            ],
            options={
                'db_table': 'product',
            },
        ),
        migrations.CreateModel(
            name='ProductItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version', models.PositiveIntegerField(default=1)),
                ('creation_date', models.DateTimeField(auto_now_add=True)),
                ('price', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                (
                    'product',
                    models.ForeignKey(
                        db_column='product_id',
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='items',
                        to='finance.product',
                    ),
                ),
                (
                    'receipt_item',
                    models.ForeignKey(
                        blank=True,
                        db_column='receipt_item_id',
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='product_items',
                        to='finance.receiptitem',
                    ),
                ),
                (
                    'transaction',
                    models.ForeignKey(
                        blank=True,
                        db_column='transaction_id',
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='product_items',
                        to='finance.transaction',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        db_column='user_id',
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='product_items',
                        to='finance.user',
                    ),
                ),
            ],
            options={
                'db_table': 'product_item',
            },
        ),
        migrations.AddConstraint(
            model_name='productitem',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ('transaction__isnull', False),
                    ('receipt_item__isnull', True),
                )
                | models.Q(
                    ('transaction__isnull', True),
                    ('receipt_item__isnull', False),
                ),
                name='product_item_xor_link',
            ),
        ),
        migrations.AddConstraint(
            model_name='productitem',
            constraint=models.CheckConstraint(
                condition=models.Q(('transaction__isnull', True))
                | models.Q(('price__isnull', False)),
                name='product_item_price_required_for_tx',
            ),
        ),
        migrations.AddConstraint(
            model_name='productitem',
            constraint=models.UniqueConstraint(
                condition=models.Q(('transaction__isnull', False)),
                fields=('product', 'transaction'),
                name='product_item_product_tx_uniq',
            ),
        ),
        migrations.AddConstraint(
            model_name='productitem',
            constraint=models.UniqueConstraint(
                condition=models.Q(('receipt_item__isnull', False)),
                fields=('product', 'receipt_item'),
                name='product_item_product_receipt_item_uniq',
            ),
        ),
    ]
