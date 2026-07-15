import uuid

from django.db import models


class AuditedModel(models.Model):
    """Shared audit columns for all finance tables."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.PositiveIntegerField(default=1)

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


class Transaction(AuditedModel):
    """Mirrors Sheets Transactions row."""

    date = models.DateField()
    change = models.DecimalField(max_digits=14, decimal_places=2)
    source = models.CharField(max_length=256)
    comment = models.TextField(blank=True, default='')
    sub_category = models.CharField(max_length=256, blank=True, default='')
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
