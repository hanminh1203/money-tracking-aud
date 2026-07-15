# Generated manually for initial finance tables

import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Receipt',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version', models.PositiveIntegerField(default=1)),
                ('date', models.DateField()),
                ('total', models.DecimalField(decimal_places=2, max_digits=14)),
            ],
            options={
                'db_table': 'receipt',
            },
        ),
        migrations.CreateModel(
            name='ReceiptItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version', models.PositiveIntegerField(default=1)),
                ('name', models.CharField(max_length=512)),
                ('amount', models.DecimalField(decimal_places=4, max_digits=14)),
                ('unit', models.CharField(max_length=64)),
                ('money', models.DecimalField(decimal_places=2, max_digits=14)),
                (
                    'receipt',
                    models.ForeignKey(
                        db_column='receipt_id',
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='items',
                        to='finance.receipt',
                    ),
                ),
            ],
            options={
                'db_table': 'receipt_item',
            },
        ),
        migrations.CreateModel(
            name='Transaction',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version', models.PositiveIntegerField(default=1)),
                ('date', models.DateField()),
                ('change', models.DecimalField(decimal_places=2, max_digits=14)),
                ('source', models.CharField(max_length=256)),
                ('comment', models.TextField(blank=True, default='')),
                ('sub_category', models.CharField(blank=True, default='', max_length=256)),
                (
                    'receipt',
                    models.ForeignKey(
                        blank=True,
                        db_column='receipt_id',
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='transactions',
                        to='finance.receipt',
                    ),
                ),
            ],
            options={
                'db_table': 'transaction',
            },
        ),
    ]
