# Transaction descriptions and automatic receipts

The sheet column `Comment` is the transaction description. The API field is still `comment`.

## When a description is required

Create and edit of a plain transaction (`POST /api/transactions`, `PUT /api/transactions/<id>`) reject a
blank description with `Description is required.` The add and edit forms do the same.

These flows store a description even when the form leaves the note blank:

| Flow | Stored description |
| --- | --- |
| Transfer (both legs) | The note, or `Exchange` |
| Buy giftcard | `Buy giftcard: {shop}` |
| Giftcard cashback | `Buy giftcard cashback: {shop}` |
| Use giftcard | The note, or `Use giftcard: {shop}` |

The assistant refuses to log a transaction until the message includes a description.

## Automatic receipt line

Creating a transaction that is not already a receipt, and not `Exchange (self)`, also appends:

- `Receipt`: same transaction id, same date, total = absolute transaction amount
- `Receipt_Items`: name = description, amount = 1, unit = `piece`, money = that total

This is written to the sheet first, then to Postgres in the same database transaction as the
transaction row. Redeeming a giftcard does this too, because that row is a purchase. A real receipt
created from the receipt form is unchanged (its own lines, comment `Store : note`).

Not given a synthetic receipt:

- Cash transfers (`Exchange (self)` on both legs). A receipt on each leg would look like two purchases of the same move.
- Buying a giftcard, including its cashback income. The debit is an asset conversion (`Exchange (self)`), and the cashback is part of that purchase flow rather than a separate itemised spend.

Receipt total is always a positive amount. `Transaction.change` keeps its sign, so an income row stays
income. Dashboard income, expense, and category breakdowns sum `change` for Income and Expense
categories. They do not add receipt totals, so the extra line is not a second spend. Deleting the
transaction deletes its receipt and items in the same unwind as today. Product links are either a
transaction or a receipt item, never both, so a synthetic line does not by itself double-count a product.

## Edits

A receipt is still synthetic when it has exactly one item, amount 1, unit `piece` (any capitalisation),
the item name equals the stored description, and both the item money and the receipt total equal
`abs(change)`.

- Editing the description or amount of that transaction updates the same receipt item (the item id is
  kept, so a product link on it survives). Income stays income.
- A receipt that has been itemised (extra lines, another unit, a different name, or money that no
  longer matches) is left as the user edited it. Changing the description does not rename those lines.
  Itemised receipts still set the transaction to an expense equal to the items total, which is the
  existing receipt-edit rule.
- The transaction screen keeps the amount field for a synthetic line and offers **Edit receipt items**
  when you want to itemise it.

## Backfill

`python manage.py backfill_transaction_receipts` applies the same rule to transactions that have no
receipt yet. It reads the sheet (source of truth), appends missing receipt rows there, then inserts
them in Postgres. Management → **Backfill receipt lines** runs the same function with the signed-in
session.

- `--dry-run` prints counts and writes nothing. The Management button previews the same way before it asks to continue.
- Re-running is safe. A Postgres receipt is skipped. A receipt that is already on the sheet but missing
  in Postgres is mirrored, not appended again.
- `Exchange (self)` and zero-amount rows are skipped.
- A blank description becomes `(no description)` on the sheet comment (only when that cell is blank)
  and on the receipt line. Postgres comment is filled only when it was blank, so a description that
  exists on only one side is kept. When the sheet comment is blank and Postgres has one, that text is
  written to the sheet so a later Sync does not wipe it.
- Transactions that are in Postgres but not on the sheet are skipped. Sync first if the database is behind the sheet.
- A sheet receipt with no items, or two receipt rows for one transaction, is skipped and counted. Fix those rows by hand, then run the command again.
- If the sheet write succeeds and Postgres fails, the command exits non-zero. Run it again, or Sync.

Run instructions for production are in [DEPLOYMENT.md](DEPLOYMENT.md). No new columns are required.

## How to update data on the Google Sheet

Nothing in this change adds, removes, or renames a tab or a column. The backfill only:

- fills a blank **Comment** cell on **Transactions**
- appends one row to **Receipt** and one row to **Receipt_Items** for each eligible transaction

Default table names are `Transactions`, `Receipt`, and `Receipt_Items` (`TRANSACTIONS_TABLE`, `RECEIPT_TABLE`, `RECEIPT_ITEMS_TABLE` if you renamed them). The app looks up columns by these header names. The named columns on each table must be one contiguous block. A column sitting between them makes the append fail.

Expected headers, in this order:

| Tab | Columns |
| --- | --- |
| Transactions | `Transaction ID`, `Date`, `Change`, `Comment`, `Sub category` |
| Receipt | `Receipt ID`, `Transaction ID`, `Date`, `Total` |
| Receipt_Items | `Receipt Item ID`, `Receipt ID`, `Name`, `Amount`, `Unit`, `Money` |

`Comment` is the description. `Change` stays signed. `Total` and `Money` are the absolute amount.

### 1. Pre-checks

1. In Google Sheets, **File → Make a copy** of the live spreadsheet. The app writes to the spreadsheet ID saved under Management, so the copy is your rollback.
2. Confirm the three named tables above exist and the headers match. Do not add a column for this release.
3. If Management status says Postgres is behind the sheet, run **Sync** first. The backfill only considers transactions that are already in Postgres and also present on the sheet. A row that exists only on the sheet is skipped until Sync. A row that exists only in Postgres is skipped and is not written.

### 2. Blank descriptions

For each eligible transaction the description is chosen in this order:

1. The sheet **Comment**, if it has any non-whitespace text. That cell is left as it is.
2. Otherwise the Postgres comment, if it has text. That text is written into the blank sheet **Comment**.
3. Otherwise the exact text `(no description)`. That text is written into the blank sheet **Comment** and used as the receipt line name.

Whitespace-only counts as blank. Postgres is updated only when its comment was blank. A non-blank sheet **Comment** is never overwritten.

`Exchange (self)` rows (transfers and giftcard purchases) and zero-amount rows are skipped entirely: no comment fill and no receipt, even when **Comment** is empty.

### 3. Run the backfill

**Management (signed-in session, preferred on the hosted app)**

1. Open **Management**. The sheet ID must already be saved.
2. Click **Backfill receipt lines**. The app runs a dry run first and does not write yet.
3. If there is nothing to add or repair, it shows the preview counts and stops.
4. Otherwise confirm the dialog. It reports how many receipt lines will be added, how many existing sheet receipts will be repaired into Postgres, and how many blank descriptions will be stored as `(no description)`. **Cancel** leaves the sheet unchanged.
5. Confirming writes the sheet first, then Postgres, then refreshes Management status.

**Management command**

Preview, which reads the sheet and writes nothing:

```bash
cd backend
GOOGLE_ACCESS_TOKEN="<google access token>" \
DATABASE_URL="<session pooler url>" \
DJANGO_DEBUG=false \
DJANGO_SECRET_KEY="<32+ character secret>" \
python manage.py backfill_transaction_receipts --dry-run --user-email you@example.com
```

Write the same way without `--dry-run`. Put `GOOGLE_ACCESS_TOKEN` in the environment, not on the command line. Pass `--user-email` when more than one user exists. Read the printed JSON before you run it without `--dry-run`.

`created` is how many new receipt pairs will be appended. `repaired_from_sheet` is how many receipts already on the sheet will be copied into Postgres with no new sheet row. `placeholders` is how many comments will become `(no description)`.

### 4. What gets appended

One **Receipt** row and one **Receipt_Items** row per eligible transaction that has no receipt on the sheet and none in Postgres. Eligible means: on the sheet, absolute `Change` greater than zero, and subcategory not `Exchange (self)` on either the sheet or in Postgres.

Ids are new UUIDs. The date is the transaction date, written as `YYYY-MM-DD`. `Total` and `Money` are `abs(Change)` as a positive amount. `Amount` is `1`. `Unit` is `piece`. `Name` is the description chosen above.

Example. This expense has no receipt yet:

| Transaction ID | Date | Change | Comment | Sub category |
| --- | --- | --- | --- | --- |
| `11111111-1111-1111-1111-111111111111` | 2026-01-08 | -8.50 | Milk | Groceries |

If **Comment** had been blank on both the sheet and in Postgres, that cell would become `(no description)` and the item name would be `(no description)`. With **Comment** already `Milk`, the transaction row is otherwise unchanged, and these two rows are appended:

**Receipt**

| Receipt ID | Transaction ID | Date | Total |
| --- | --- | --- | --- |
| `22222222-2222-2222-2222-222222222222` | `11111111-1111-1111-1111-111111111111` | 2026-01-08 | 8.50 |

**Receipt_Items**

| Receipt Item ID | Receipt ID | Name | Amount | Unit | Money |
| --- | --- | --- | --- | --- | --- |
| `33333333-3333-3333-3333-333333333333` | `22222222-2222-2222-2222-222222222222` | Milk | 1 | piece | 8.50 |

Income is the same shape with a positive `Change`. A `+20.00` salary row gets `Total` `20.00` and `Money` `20.00`. `Change` stays positive.

A receipt that is already on the sheet is not appended again. If Postgres is missing it, the backfill copies that existing sheet receipt (and may fill a blank **Comment**). A sheet receipt with no items, or two receipt rows for one transaction, is skipped and counted.

The **Transactions** row count does not change.

### 5. Verify

1. Read the summary. `created` should match the number of new **Receipt** rows and the number of new **Receipt_Items** rows. `skipped_exchange` and `skipped_zero` should match the rows you expected to leave alone.
2. In the sheet, spot-check one former blank **Comment**. It is either the old Postgres text or `(no description)`.
3. Spot-check one new pair: same **Transaction ID**, same date, `Total` = `abs(Change)`, one item with that description, amount `1`, unit `piece`, money = `Total`.
4. Spot-check an **Exchange (self)** row: **Comment** unchanged, no new receipt for that transaction id.
5. Open **Management** and refresh status. **Receipt** and **Receipt_Items** should match the sheet. The Management button refreshes status after a successful write. If you used the command, refresh status yourself. Run **Sync** only if status still shows a drift you want Postgres to take from the sheet. Sync replaces the Postgres copy of these tables with the sheet.

### 6. Rollback

Sync copies the sheet into Postgres and deletes the previous Postgres rows for those tables. To undo the backfill, restore the sheet first, then Sync.

1. Put the backup back into the live spreadsheet (the ID saved in Management). Copy **Transactions**, **Receipt**, and **Receipt_Items** from the copy over the live tabs, or replace that file's contents. A separate copy does nothing until the live spreadsheet is restored. Restoring also discards any other sheet edits made after the copy.
2. Open **Management** and run **Sync**. Postgres reloads from the restored sheet, including removal of receipt rows the backfill had inserted in the database.

If the sheet write succeeded and Postgres failed, do not restore yet. Run the backfill again (it mirrors the sheet receipt) or run **Sync**.
