# Category and Source belong to a user (same as other mirror tables).

import django.db.models.deletion
from django.db import migrations, models


def wipe_lookup_tables(apps, schema_editor):
    """Wipe rows that depend on or are Category/Source so the user FK can be required."""
    ProductItem = apps.get_model('finance', 'ProductItem')
    Transaction = apps.get_model('finance', 'Transaction')
    Category = apps.get_model('finance', 'Category')
    Source = apps.get_model('finance', 'Source')
    ProductItem.objects.all().delete()
    Transaction.objects.all().delete()
    Category.objects.all().delete()
    Source.objects.all().delete()


class Migration(migrations.Migration):
    # Wipe + ALTER in one atomic block hits Postgres "pending trigger events".
    atomic = False

    dependencies = [
        ('finance', '0012_productitem_end_date'),
    ]

    operations = [
        migrations.RunPython(wipe_lookup_tables, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='category',
            name='sub_category',
            field=models.CharField(max_length=256),
        ),
        migrations.AlterField(
            model_name='source',
            name='name',
            field=models.CharField(max_length=256),
        ),
        migrations.AddField(
            model_name='category',
            name='user',
            field=models.ForeignKey(
                db_column='user_id',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='categories',
                to='finance.user',
            ),
        ),
        migrations.AddField(
            model_name='source',
            name='user',
            field=models.ForeignKey(
                db_column='user_id',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='sources',
                to='finance.user',
            ),
        ),
        migrations.AddConstraint(
            model_name='category',
            constraint=models.UniqueConstraint(
                fields=('user', 'sub_category'),
                name='category_user_sub_category_uniq',
            ),
        ),
        migrations.AddConstraint(
            model_name='source',
            constraint=models.UniqueConstraint(
                fields=('user', 'name'),
                name='source_user_name_uniq',
            ),
        ),
    ]
