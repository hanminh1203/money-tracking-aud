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
- `Receipt_Items`: name = description, amount = 1, unit = `piece`, money = that total, sub category = the transaction sub category

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

## Existing rows

New transactions get the one-line receipt when they are created. Transactions already on the sheet that have no receipt are not backfilled. Add the receipt on the Google Sheet, then **Management → Sync**. Sync deletes the Postgres copy of these tables and reloads it from the sheet, so a receipt that exists only in Postgres would be removed, and a receipt that exists only on the sheet appears after Sync.

There is no management command and no Management button for this.

## How to update data on the Google Sheet

Default table names are `Transactions`, `Receipt`, and `Receipt_Items` (`TRANSACTIONS_TABLE`, `RECEIPT_TABLE`, `RECEIPT_ITEMS_TABLE` if you renamed them). The app looks up columns by header name. The named columns on each table must be one contiguous block.

| Tab | Columns |
| --- | --- |
| Transactions | `Transaction ID`, `Date`, `Change`, `Comment`, `Sub category` |
| Receipt | `Receipt ID`, `Transaction ID`, `Date`, `Total` |
| Receipt_Items | `Receipt Item ID`, `Receipt ID`, `Name`, `Amount`, `Unit`, `Money`, `Sub category` |

`Comment` is the description. `Change` stays signed. `Total` and `Money` are the absolute amount. `Sub category` on an item is column 7, immediately after `Money`. See [receipt-item-subcategory.md](receipt-item-subcategory.md).

### 1. Backup

In Google Sheets, **File → Make a copy** of the live spreadsheet. The app writes to the spreadsheet ID saved under Management. The copy is the rollback.

### 2. Add a receipt for each transaction that has none

Skip `Exchange (self)` rows (transfers and giftcard purchases) and zero-amount rows. For each other transaction, append one **Receipt** row and one **Receipt_Items** row. Give both new UUIDs. The date is the transaction date (`YYYY-MM-DD`). `Total` and `Money` are `abs(Change)`. `Amount` is `1`. `Unit` is `piece`. `Name` is the **Comment**. `Sub category` is the transaction's **Sub category**.

Example. This expense has no receipt yet:

| Transaction ID | Date | Change | Comment | Sub category |
| --- | --- | --- | --- | --- |
| `11111111-1111-1111-1111-111111111111` | 2026-01-08 | -8.50 | Milk | Groceries |

Append:

**Receipt**

| Receipt ID | Transaction ID | Date | Total |
| --- | --- | --- | --- |
| `22222222-2222-2222-2222-222222222222` | `11111111-1111-1111-1111-111111111111` | 2026-01-08 | 8.50 |

**Receipt_Items**

| Receipt Item ID | Receipt ID | Name | Amount | Unit | Money | Sub category |
| --- | --- | --- | --- | --- | --- | --- |
| `33333333-3333-3333-3333-333333333333` | `22222222-2222-2222-2222-222222222222` | Milk | 1 | piece | 8.50 | Groceries |

Income is the same shape. A `+20.00` salary row gets `Total` `20.00` and `Money` `20.00`. `Change` stays positive. Do not add a receipt for an **Exchange (self)** row.

The **Transactions** row count does not change.

### 3. Sync

1. Spot-check one new pair: same **Transaction ID**, same date, `Total` = `abs(Change)`, one item with that description, amount `1`, unit `piece`, money = `Total`, subcategory = the transaction subcategory.
2. Open **Management** and run **Sync**. Postgres reloads from the sheet, including the new receipt rows.

### 4. Rollback

Restore **Receipt** and **Receipt_Items** from the backup, then run **Sync**. Postgres drops receipt rows that are no longer on the sheet.
