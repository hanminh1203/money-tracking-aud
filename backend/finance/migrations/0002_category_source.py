# Generated manually for Category and Source mirror tables

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0001_initial_finance_tables'),
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version', models.PositiveIntegerField(default=1)),
                ('main_category', models.CharField(max_length=256)),
                ('sub_category', models.CharField(max_length=256)),
                ('type', models.CharField(blank=True, default='', max_length=64)),
            ],
            options={
                'db_table': 'category',
            },
        ),
        migrations.CreateModel(
            name='Source',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version', models.PositiveIntegerField(default=1)),
                ('name', models.CharField(max_length=256)),
                ('type', models.CharField(blank=True, default='', max_length=64)),
            ],
            options={
                'db_table': 'source',
            },
        ),
    ]
