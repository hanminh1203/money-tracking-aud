"""Copy each transaction subcategory onto receipt items that have none.

Postgres only. A blank item is filled from its own transaction. An item that
already has a subcategory is left as it is. Reverse is a no-op: the values are
real data, not a schema default that should be cleared.
"""

from django.db import migrations

# One statement. Joins stay inside this user's receipt and transaction.
FILL_BLANK_ITEM_CATEGORIES = """
UPDATE receipt_item AS item
SET category_id = tx.category_id,
    version = item.version + 1
FROM receipt AS r
INNER JOIN "transaction" AS tx ON tx.id = r.transaction_id
WHERE item.receipt_id = r.id
  AND item.user_id = r.user_id
  AND r.user_id = tx.user_id
  AND item.category_id IS NULL
  AND tx.category_id IS NOT NULL
"""


def fill_blank_item_categories(apps, schema_editor):
    schema_editor.execute(FILL_BLANK_ITEM_CATEGORIES)


def noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0018_receiptitem_category'),
    ]

    operations = [
        migrations.RunPython(fill_blank_item_categories, noop, elidable=True),
    ]
