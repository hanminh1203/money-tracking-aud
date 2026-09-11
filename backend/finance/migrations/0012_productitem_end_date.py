# ProductItem.end_date — expected date the purchased product runs out

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0011_product_and_product_item'),
    ]

    operations = [
        migrations.AddField(
            model_name='productitem',
            name='end_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
