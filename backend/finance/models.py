import uuid

from django.db import models


class AuditedModel(models.Model):
    """Shared audit columns for all finance tables."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.PositiveIntegerField(default=1)
    creation_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class Receipt(AuditedModel):
    """Mirrors Sheets Receipt; id equals sheet Receipt ID."""

    date = models.DateField()
    total = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = 'receipt'


class ReceiptItem(AuditedModel):
    """Mirrors Sheets Receipt_Items."""

    receipt = models.ForeignKey(
        Receipt,
        on_delete=models.CASCADE,
        related_name='items',
        db_column='receipt_id',
    )
    name = models.CharField(max_length=512)
    amount = models.DecimalField(max_digits=14, decimal_places=4)
    unit = models.CharField(max_length=64)
    money = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = 'receipt_item'


class Category(AuditedModel):
    """Mirrors Sheets Category row."""

    main_category = models.CharField(max_length=256)
    sub_category = models.CharField(max_length=256, unique=True)
    type = models.CharField(max_length=64, blank=True, default='')

    class Meta:
        db_table = 'category'


class Source(AuditedModel):
    """Mirrors Sheets Sources row."""

    name = models.CharField(max_length=256, unique=True)
    type = models.CharField(max_length=64, blank=True, default='')

    class Meta:
        db_table = 'source'


class Transaction(AuditedModel):
    """Mirrors Sheets Transactions row."""

    row_number = models.PositiveIntegerField(
        unique=True,
        help_text='1-based Google Sheets row number in the Transactions table.',
    )
    date = models.DateField()
    change = models.DecimalField(max_digits=14, decimal_places=2)
    source = models.ForeignKey(
        Source,
        on_delete=models.PROTECT,
        related_name='transactions',
        db_column='source_id',
    )
    comment = models.TextField(blank=True, default='')
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='transactions',
        db_column='category_id',
    )
    receipt = models.ForeignKey(
        Receipt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions',
        db_column='receipt_id',
    )

    class Meta:
        db_table = 'transaction'
