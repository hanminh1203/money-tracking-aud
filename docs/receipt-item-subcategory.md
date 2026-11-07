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

Column 7 sits immediately after `Money`. The seven named columns must be one contiguous block. A column between them makes an append fail. The value must match a `Sub category` on the `Category` tab for that user. A blank cell is allowed; backfill fills it, and the homepage treats a blank line as the transaction subcategory.

The app cannot create the column on a user-managed sheet.

## Homepage monthly breakdown

Income, expense, and saving on the homepage are still the sum of `Transaction.change` for Income and Expense categories. Giftcard balances stay in net worth only. Buying a giftcard is `Exchange (self)` and is not an expense. Using a giftcard is one expense.

The three-month subcategory table splits each of those same signed amounts:

1. No receipt items: the whole change stays on the transaction subcategory.
2. Item money sums to `abs(Change)`: each line keeps its money, with the transaction's sign, on its subcategory.
3. Item money sums to less (a fee, a tip, or a line that was not itemised): each line keeps its money, and the remainder stays on the transaction subcategory.
4. Item money sums to more (a discount or rounding): lines are scaled down in proportion to their money and rounded down to cents. Leftover cents stay on the transaction subcategory.

A blank line subcategory, or one whose category type is not the transaction's type, is labelled with the transaction subcategory. Income stays positive. Expense stays negative. The pieces sum to the transaction change, so the month's subcategory rows still add up to the transaction-based income and expense. Receipt totals are not added again, and giftcard funding is not a second spend.

## Backfill

`python manage.py backfill_receipt_item_subcategories` fills blank `Receipt_Items` → `Sub category` cells from the transaction.

- The sheet is written first, then Postgres, so Management → Sync does not clear the cells.
- `--dry-run` counts and writes nothing. Management → **Backfill item subcategories** previews the same way, then asks before it writes.
- A cell that already has a subcategory is not overwritten.
- If the sheet cell is filled and Postgres is blank or different, Postgres is set from the sheet and the sheet cell is left as it is.
- The sheet transaction subcategory is used when it matches a Category row. Otherwise the Postgres transaction subcategory is used.
- A transaction with no subcategory, or a subcategory that is not on the Category tab, is skipped.
- Re-running is safe.

`python manage.py backfill_transaction_receipts` writes the same column on lines it creates.

## How to update data on the Google Sheet

### 1. Backup

In Google Sheets, **File → Make a copy** of the live spreadsheet. The app writes to the spreadsheet ID saved under Management. The copy is the rollback. Restoring also discards other sheet edits made after the copy.

### 2. Add the column

On the `Receipt_Items` table:

1. Confirm the current columns, in order, are `Receipt Item ID`, `Receipt ID`, `Name`, `Amount`, `Unit`, `Money`.
2. Add a column immediately after `Money`. Do not insert it between the existing columns.
3. Set the header to exactly `Sub category`.
4. Include that column in the named table so it is column 7. Leave existing item cells blank. The backfill fills them.
5. If Management says Postgres is behind the sheet, run **Sync** first.

### 3. Preview, then write

**Management (signed-in session)**

1. Open **Management**. The sheet ID must already be saved.
2. Click **Backfill item subcategories**. The app runs a dry run and does not write yet.
3. If nothing would change, it shows the preview and stops.
4. Otherwise confirm the dialog. **Cancel** leaves the sheet unchanged.
5. Confirming writes the sheet first, then Postgres, then refreshes Management status.

**Management command**

Preview, which reads the sheet and writes nothing:

```bash
cd backend
GOOGLE_ACCESS_TOKEN="<google access token>" \
DATABASE_URL="<session pooler url>" \
DJANGO_DEBUG=false \
DJANGO_SECRET_KEY="<32+ character secret>" \
python manage.py backfill_receipt_item_subcategories --dry-run --user-email you@example.com
```

Write the same way without `--dry-run`. Put `GOOGLE_ACCESS_TOKEN` in the environment, not on the command line. Pass `--user-email` when more than one user exists.

`updated` is how many blank cells will be filled from the transaction. `repaired_from_sheet` is how many cells already set on the sheet will be copied into Postgres with no sheet change. `skipped_already_set` is cells that already match.

### 4. What gets written

Only blank `Sub category` cells on `Receipt_Items`. The transaction row is not changed. No rows are appended.

Example. The transaction is Groceries and the item cell is blank:

| Receipt Item ID | Receipt ID | Name | Amount | Unit | Money | Sub category |
| --- | --- | --- | --- | --- | --- | --- |
| `33333333-3333-3333-3333-333333333333` | `22222222-2222-2222-2222-222222222222` | Milk | 1 | piece | 8.50 | Groceries |

An item that already says `Household` stays `Household`, even when the transaction says `Groceries`.

### 5. Verify

1. `updated` matches the number of cells that changed from blank to a subcategory.
2. Spot-check one item: its `Sub category` equals its transaction's `Sub category`.
3. Spot-check one item that already had a different subcategory: that cell is unchanged.
4. Spot-check an `Exchange (self)` row: it still has no receipt.
5. Open **Management** and refresh status. **Receipt_Items** should match the sheet. Run **Sync** only if status still shows a drift you want Postgres to take from the sheet.

### 6. Rollback

Sync copies the sheet into Postgres and deletes the previous Postgres rows for those tables. Restore the sheet first, then Sync.

1. Put the backup back into the live spreadsheet (the ID saved in Management), including `Receipt_Items`. A separate copy does nothing until the live spreadsheet is restored.
2. Open **Management** and run **Sync**.

If the sheet write succeeded and Postgres failed, do not restore yet. Run the backfill again. It copies the filled sheet cells into Postgres.
