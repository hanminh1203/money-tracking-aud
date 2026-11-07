# Receipt item subcategories

Each receipt line has its own subcategory. The transaction subcategory stays the default and the primary label.

## What the transaction subcategory means

`Transactions` → `Sub category` is unchanged.

- Transaction lists, filters, search, and the transaction row use that category. They do not switch to receipt-item categories.
- A new receipt item starts as that subcategory. The receipt form and the transaction editor do this, and receipt OCR does it when a line has no subcategory of its own.
- A synthetic one-line receipt (the automatic line from a plain transaction or a giftcard redemption) keeps the same subcategory as the transaction. Editing the transaction subcategory updates that line while the receipt is still one piece, named from the description, with money equal to `abs(Change)`.
- Once a line has a different subcategory, or the receipt is itemised (extra lines, another unit, a renamed line, or money that no longer matches), later edits of the transaction subcategory do not overwrite the lines.
- `Exchange (self)` transfers and giftcard purchases still have no receipt. Their subcategory stays on the transaction only.

## Sheet column

Tab: `Receipt_Items` (or `RECEIPT_ITEMS_TABLE` if you renamed it).

| Position | Header |
| --- | --- |
| 1 | `Receipt Item ID` |
| 2 | `Receipt ID` |
| 3 | `Name` |
| 4 | `Amount` |
| 5 | `Unit` |
| 6 | `Money` |
| 7 | `Sub category` |

The header is exactly `Sub category` (capital S, lowercase c), the same spelling as on `Transactions`. The app also accepts `Sub Category` when it reads. It writes `Sub category`.

Column 7 sits immediately after `Money`. The seven named columns must be one contiguous block. A column between them makes an append fail. The value must match a `Sub category` on the `Category` tab for that user. A blank cell is allowed. The homepage treats a blank line as the transaction subcategory, so totals stay correct until the cell is filled.

The app cannot create the column on a user-managed sheet. Add it and fill it by hand. There is no backfill command.

## Homepage monthly breakdown

Income, expense, and saving on the homepage are still the sum of `Transaction.change` for Income and Expense categories. Giftcard balances stay in net worth only. Buying a giftcard is `Exchange (self)` and is not an expense. Using a giftcard is one expense.

The three-month subcategory table splits each of those same signed amounts:

1. No receipt items: the whole change stays on the transaction subcategory.
2. Item money sums to `abs(Change)`: each line keeps its money, with the transaction's sign, on its subcategory.
3. Item money sums to less (a fee, a tip, or a line that was not itemised): each line keeps its money, and the remainder stays on the transaction subcategory.
4. Item money sums to more (a discount or rounding): lines are scaled down in proportion to their money and rounded down to cents. Leftover cents stay on the transaction subcategory.

A blank line subcategory, or one whose category type is not the transaction's type, is labelled with the transaction subcategory. Income stays positive. Expense stays negative. The pieces sum to the transaction change, so the month's subcategory rows still add up to the transaction-based income and expense. Receipt totals are not added again, and giftcard funding is not a second spend.

## Database migration

`python manage.py migrate` adds `receipt_item.category_id` and then copies each transaction's subcategory onto receipt items that do not have one. Only nulls are filled. An item that already has a subcategory is left as it is. An item whose transaction has no subcategory stays blank. The reverse migration does not clear those values.

This writes Postgres only. It does not call Google Sheets.

**Do not run Management → Sync until the sheet column is filled.** Sync deletes the Postgres rows for these tables and reloads them from the sheet. A blank `Sub category` cell becomes a null category and replaces the value the migration just wrote. Homepage totals still match, because a blank line falls back to the transaction subcategory, but any subcategory you had only in Postgres is gone.

## How to update data on the Google Sheet

The database is updated by the migration. The spreadsheet is updated by you.

### 1. Backup

In Google Sheets, **File → Make a copy** of the live spreadsheet. The app writes to the spreadsheet ID saved under Management. The copy is the rollback.

### 2. Run migrations

Deploy, or run migrate against the session pooler. Postgres receipt items with no subcategory are filled from their transaction. You do not run a management command or a Management button for this.

```bash
cd backend
DATABASE_URL="<session pooler url>" \
DJANGO_DEBUG=false \
DJANGO_SECRET_KEY="<32+ character secret>" \
python manage.py migrate
```

GitHub Actions runs the same migrate on push when `MIGRATION_DATABASE_URL` is set. See [DEPLOYMENT.md](DEPLOYMENT.md).

### 3. Add the column

On the `Receipt_Items` table, before any Sync:

1. Confirm the current columns, in order, are `Receipt Item ID`, `Receipt ID`, `Name`, `Amount`, `Unit`, `Money`.
2. Add a column immediately after `Money`. Do not insert it between the existing columns.
3. Set the header to exactly `Sub category`.
4. Include that column in the named table so it is column 7.

### 4. Fill the column from the transaction

Each existing item should get the subcategory of the transaction its receipt belongs to.

Suggested approach:

1. On `Receipt_Items`, in the new `Sub category` column, use a lookup through `Receipt` to `Transactions`. With the default headers, for the data row in row 2 (adjust the row and the ranges to your sheet):

```
=IFERROR(INDEX(Transactions[Sub category], MATCH(INDEX(Receipt[Transaction ID], MATCH([@[Receipt ID]], Receipt[Receipt ID], 0)), Transactions[Transaction ID], 0)), "")
```

`[@[Receipt ID]]` is the receipt id on that `Receipt_Items` row. Named tables use the table names you actually have (`Receipt`, `Transactions`, `Receipt_Items`).

2. Fill the formula down the column.
3. Spot-check a few rows against the transaction.
4. Copy the column and **Paste special → Values only**, so the cells are text rather than formulas. The app reads values.

An item you want in a different subcategory can be typed over after the paste. Leave `Exchange (self)` transactions alone: they have no receipt.

### 5. Verify, then Sync

1. Spot-check one item: `Sub category` equals its transaction's `Sub category`.
2. Spot-check one item you set by hand to something else: that cell is unchanged.
3. Open **Management** and refresh status. **Receipt_Items** will show a mismatch until the sheet matches Postgres.
4. Run **Sync** only after the column is filled. Sync reloads Postgres from the sheet. Blank cells replace the migrated categories. Until you Sync, the app keeps the migrated Postgres values, and a blank sheet cell is not read.

### 6. Rollback

To undo the sheet edit, restore `Receipt_Items` from the backup, then run **Sync** only if you also want Postgres to drop the filled categories. Restoring the sheet and then Syncing copies the blanks back into Postgres. Homepage totals still fall back to the transaction subcategory.

To undo only the database fill, restore a database backup from before migrate. The reverse of this migration does not clear `category_id`.
