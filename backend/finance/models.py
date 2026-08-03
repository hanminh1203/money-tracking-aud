import uuid

from django.db import models


class AuditedModel(models.Model):
    """Shared audit columns for all finance tables."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.PositiveIntegerField(default=1)
    creation_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class User(models.Model):
    """App user created from Google OAuth email."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    sheet_id = models.CharField(max_length=256, blank=True, default='')
    creation_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'app_user'

    def __str__(self) -> str:
        return self.email


class Receipt(AuditedModel):
    """Mirrors Sheets Receipt; id equals sheet Receipt ID."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='receipts',
        db_column='user_id',
    )
    date = models.DateField()
    total = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = 'receipt'


class ReceiptItem(AuditedModel):
    """Mirrors Sheets Receipt_Items."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='receipt_items',
        db_column='user_id',
    )
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


class Giftcard(AuditedModel):
    """Mirrors Sheets Giftcard; id equals sheet Giftcard ID."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='giftcards',
        db_column='user_id',
    )
    row_number = models.PositiveIntegerField(
        help_text='1-based Google Sheets row number in the Giftcard table.',
    )
    shop = models.CharField(max_length=256)
    date = models.DateField()
    balance = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = 'giftcard'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'row_number'],
                name='giftcard_user_row_number_uniq',
            ),
        ]


class Transaction(AuditedModel):
    """Mirrors Sheets Transactions row."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='transactions',
        db_column='user_id',
    )
    row_number = models.PositiveIntegerField(
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
    giftcard = models.ForeignKey(
        Giftcard,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions',
        db_column='giftcard_id',
    )

    class Meta:
        db_table = 'transaction'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'row_number'],
                name='transaction_user_row_number_uniq',
            ),
        ]
