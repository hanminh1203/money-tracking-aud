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
